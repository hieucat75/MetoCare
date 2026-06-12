"""Async lab-document pipeline tests (P2 #3).

Covers: state-machine transitions, idempotent re-enqueue, OCR failure path
(-> ocr_failed + audit), happy-path E2E (-> interpreted + LabResult + notify),
and the async worker draining the queue.
"""

from __future__ import annotations

import asyncio

import pytest
from app.models.clinical import LabDocument, LabResult
from app.models.governance import AuditLog
from app.services import lab, notifications
from app.services.lab_pipeline import (
    InvalidTransition,
    LabDocStatus,
    _transition,
    get_worker,
    process_document,
)
from sqlalchemy import select


def _make_doc(db, patient, storage_key="mock://lab/doc-ok.pdf"):
    return lab.register_document(
        db,
        patient_id=patient["patient_id"],
        requester_id=patient["user_id"],
        storage_key=storage_key,
        file_type="pdf",
    )


# --------------------------------------------------------------------------- #
# State machine
# --------------------------------------------------------------------------- #

def test_transition_valid_and_invalid():
    doc = LabDocument(patient_id="p", storage_key="k", status="uploaded")
    _transition(doc, LabDocStatus.OCR_PENDING)
    assert doc.status == "ocr_pending"
    _transition(doc, LabDocStatus.OCR_DONE)
    assert doc.status == "ocr_done"
    # Illegal jump.
    with pytest.raises(InvalidTransition):
        _transition(doc, LabDocStatus.OCR_PENDING)


def test_register_document_starts_uploaded(db, patient):
    doc = _make_doc(db, patient)
    assert doc.status == "uploaded"


# --------------------------------------------------------------------------- #
# Idempotent enqueue
# --------------------------------------------------------------------------- #

def test_enqueue_is_idempotent(db, patient):
    doc = _make_doc(db, patient)
    worker = get_worker()
    assert worker.enqueue(db, document_id=doc.id, requester_id=patient["user_id"]) is True
    # Already in-flight -> no-op.
    assert worker.enqueue(db, document_id=doc.id, requester_id=patient["user_id"]) is False
    assert worker.pending() == 1
    db.refresh(doc)
    assert doc.status == "ocr_pending"


def test_enqueue_missing_document(db, patient):
    worker = get_worker()
    assert worker.enqueue(db, document_id="nope", requester_id=patient["user_id"]) is False


# --------------------------------------------------------------------------- #
# Happy path E2E
# --------------------------------------------------------------------------- #

def test_pipeline_happy_path(db, patient):
    doc = _make_doc(db, patient, storage_key="mock://lab/doc-ok.pdf")
    worker = get_worker()
    worker.enqueue(db, document_id=doc.id, requester_id=patient["user_id"])
    processed = worker.process_next()
    assert processed == doc.id

    db.expire_all()
    doc = db.get(LabDocument, doc.id)
    assert doc.status == "interpreted"
    assert doc.ocr_status == "done"
    assert doc.raw_text and "mock" in doc.raw_text.lower()

    results = db.scalars(select(LabResult).where(LabResult.document_id == doc.id)).all()
    assert any(r.canonical_name == "fasting_glucose" for r in results)

    notes = notifications.recent(patient["user_id"])
    assert any(n.event == "lab_interpreted" for n in notes)


def test_pipeline_reenqueue_after_done_is_noop(db, patient):
    doc = _make_doc(db, patient)
    worker = get_worker()
    worker.enqueue(db, document_id=doc.id, requester_id=patient["user_id"])
    worker.process_next()
    db.expire_all()
    # interpreted is terminal -> not enqueueable again.
    assert worker.enqueue(db, document_id=doc.id, requester_id=patient["user_id"]) is False


# --------------------------------------------------------------------------- #
# Failure path
# --------------------------------------------------------------------------- #

def test_pipeline_ocr_failure(db, patient):
    doc = _make_doc(db, patient, storage_key="mock://lab/doc-FAIL.pdf")
    worker = get_worker()
    worker.enqueue(db, document_id=doc.id, requester_id=patient["user_id"])
    worker.process_next()

    db.expire_all()
    doc = db.get(LabDocument, doc.id)
    assert doc.status == "ocr_failed"
    assert doc.ocr_status == "failed"

    audits = db.scalars(
        select(AuditLog).where(
            AuditLog.resource_id == doc.id, AuditLog.action == "ocr_extract"
        )
    ).all()
    assert audits and audits[0].outcome == "failure"
    assert audits[0].severity == "warning"

    # Failed state is retryable.
    assert worker.enqueue(db, document_id=doc.id, requester_id=patient["user_id"]) is True


# --------------------------------------------------------------------------- #
# Process is a no-op when not pending
# --------------------------------------------------------------------------- #

def test_process_document_noop_when_not_pending(db, patient):
    doc = _make_doc(db, patient)  # status uploaded, never enqueued
    result = process_document(db, document_id=doc.id)
    assert result.status == "uploaded"  # untouched


# --------------------------------------------------------------------------- #
# Async worker drains the queue
# --------------------------------------------------------------------------- #

def test_async_worker_drains_queue(db, patient):
    doc = _make_doc(db, patient)
    worker = get_worker()
    worker.enqueue(db, document_id=doc.id, requester_id=patient["user_id"])

    async def _run():
        worker.start()
        # Wait until the worker processes the queued document.
        for _ in range(50):
            if worker.pending() == 0 and worker.processed_count >= 1:
                break
            await asyncio.sleep(0.02)
        await worker.stop()

    asyncio.run(_run())

    db.expire_all()
    doc = db.get(LabDocument, doc.id)
    assert doc.status == "interpreted"


# --------------------------------------------------------------------------- #
# HTTP endpoints
# --------------------------------------------------------------------------- #

def test_process_endpoint_enqueues(client, patient):
    headers = {"Authorization": f"Bearer {patient['token']}"}
    r = client.post(
        f"/api/v1/patients/{patient['patient_id']}/lab-documents",
        headers=headers,
        json={"storage_key": "mock://lab/doc-2.pdf", "file_type": "pdf"},
    )
    doc_id = r.json()["id"]

    r2 = client.post(f"/api/v1/lab-documents/{doc_id}/process", headers=headers)
    assert r2.status_code == 202, r2.text
    body = r2.json()
    assert body["enqueued"] is True
    assert body["status"] == "ocr_pending"

    # Drain synchronously (worker disabled in tests) then check status endpoint.
    get_worker().drain()
    r3 = client.get(f"/api/v1/lab-documents/{doc_id}", headers=headers)
    assert r3.status_code == 200
    assert r3.json()["status"] == "interpreted"
