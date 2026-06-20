"""Async lab-document pipeline (P2 #3).

Replaces the synchronous mock interpret with a queue-driven pipeline:

    upload -> enqueue -> OCR -> parse -> normalize biomarkers -> store LabResult
            -> audit -> notify user

State machine on ``LabDocument.status``:

    uploaded -> ocr_pending -> ocr_done -> interpreted
                     |             |
                     v             v
                 ocr_failed   interpretation_failed   (both retryable -> ocr_pending)

The queue is a built-in asyncio.Queue drained by a worker task started in the
FastAPI lifespan (no Celery/RQ/Redis). Enqueue is idempotent: a document already
in-flight or already interpreted is a no-op. ``process_document`` is synchronous
and self-contained so it is unit-testable without a running event loop.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from enum import StrEnum

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.domain import lab_interpreter
from app.models.clinical import LabDocument, LabResult
from app.models.patient import PatientProfile
from app.services import audit, notifications
from app.services.ocr import OCRError, get_ocr_provider

logger = logging.getLogger("mcp.lab_pipeline")


class LabDocStatus(StrEnum):
    UPLOADED = "uploaded"
    OCR_PENDING = "ocr_pending"
    OCR_DONE = "ocr_done"
    OCR_FAILED = "ocr_failed"
    INTERPRETED = "interpreted"
    INTERPRETATION_FAILED = "interpretation_failed"


class InvalidTransition(ValueError):
    """Raised when an illegal state-machine transition is attempted."""


_ALLOWED: dict[LabDocStatus, set[LabDocStatus]] = {
    LabDocStatus.UPLOADED: {LabDocStatus.OCR_PENDING},
    LabDocStatus.OCR_PENDING: {LabDocStatus.OCR_DONE, LabDocStatus.OCR_FAILED},
    LabDocStatus.OCR_DONE: {LabDocStatus.INTERPRETED, LabDocStatus.INTERPRETATION_FAILED},
    LabDocStatus.OCR_FAILED: {LabDocStatus.OCR_PENDING},
    LabDocStatus.INTERPRETATION_FAILED: {LabDocStatus.OCR_PENDING},
    LabDocStatus.INTERPRETED: set(),
}

# A document can (re-)enter the queue only from these states.
_ENQUEUEABLE = {
    LabDocStatus.UPLOADED,
    LabDocStatus.OCR_FAILED,
    LabDocStatus.INTERPRETATION_FAILED,
}


def _transition(doc: LabDocument, new: LabDocStatus) -> None:
    current = LabDocStatus(doc.status)
    if new not in _ALLOWED[current]:
        raise InvalidTransition(f"{current} -> {new} is not allowed")
    doc.status = new.value


def _patient_user_id(db: Session, patient_id: str) -> str:
    profile = db.get(PatientProfile, patient_id)
    return profile.user_id if profile and profile.user_id else patient_id


# --------------------------------------------------------------------------- #
# Pipeline core (synchronous, self-contained, unit-testable)
# --------------------------------------------------------------------------- #

def process_document(db: Session, *, document_id: str) -> LabDocument | None:
    """Run OCR + interpretation for a document that is in OCR_PENDING.

    Idempotent: a document not in OCR_PENDING is left untouched (returns it). All
    failures move the document to a terminal failed state + audit (never raise to
    the worker loop)."""
    doc = db.get(LabDocument, document_id)
    if doc is None:
        return None
    if doc.status != LabDocStatus.OCR_PENDING.value:
        return doc  # already processed / not enqueued -> no-op

    user_id = _patient_user_id(db, doc.patient_id)

    # ---- OCR ----
    try:
        extraction = get_ocr_provider().extract(doc.storage_key)
    except OCRError as exc:
        _transition(doc, LabDocStatus.OCR_FAILED)
        doc.ocr_status = "failed"
        audit.record(
            db,
            actor_type="system",
            actor_id="ocr_worker",
            action="ocr_extract",
            resource_type="lab_document",
            resource_id=doc.id,
            outcome="failure",
            severity="warning",
        )
        db.commit()
        notifications.notify(user_id, "lab_ocr_failed", document_id=doc.id)
        logger.warning("ocr_failed document_id=%s: %s", doc.id, exc)
        return doc

    doc.raw_text = extraction.text
    _transition(doc, LabDocStatus.OCR_DONE)
    doc.ocr_status = "done"
    db.flush()

    # ---- Interpretation + normalized LabResult rows ----
    try:
        interpretation = lab_interpreter.interpret_panel(extraction.values)
        new_rows: list[LabResult] = []
        for b in interpretation.biomarkers:
            lr = LabResult(
                patient_id=doc.patient_id,
                document_id=doc.id,
                test_name=b.raw_name,
                canonical_name=b.canonical,
                value=b.value,
                unit=b.unit,
                reference_range=b.reference_range,
                status=b.status.value,
                ocr_confidence=b.ocr_confidence,
            )
            db.add(lr)
            new_rows.append(lr)
        db.flush()
        # Promote into health_metrics so the dashboard + trends reflect these results.
        from app.services.lab import promote_lab_rows_to_metrics
        promote_lab_rows_to_metrics(db, patient_id=doc.patient_id, rows=new_rows, test_date=None)
        _transition(doc, LabDocStatus.INTERPRETED)
    except Exception as exc:  # interpretation must never crash the worker
        _transition(doc, LabDocStatus.INTERPRETATION_FAILED)
        audit.record(
            db,
            actor_type="system",
            actor_id="ocr_worker",
            action="interpret",
            resource_type="lab_document",
            resource_id=doc.id,
            outcome="failure",
            severity="warning",
        )
        db.commit()
        notifications.notify(user_id, "lab_interpretation_failed", document_id=doc.id)
        logger.warning("interpretation_failed document_id=%s: %s", doc.id, exc)
        return doc

    audit.record(
        db,
        actor_type="system",
        actor_id="ocr_worker",
        action="interpret",
        resource_type="lab_document",
        resource_id=doc.id,
        outcome="success",
    )
    db.commit()
    notifications.notify(user_id, "lab_interpreted", document_id=doc.id)
    return doc


# --------------------------------------------------------------------------- #
# Worker manager: idempotent enqueue + asyncio queue + drain
# --------------------------------------------------------------------------- #

class OCRWorkerManager:
    def __init__(self) -> None:
        self._inflight: set[str] = set()
        self._buffer: list[str] = []  # ids waiting to be processed
        self._lock = threading.Lock()
        self._event: asyncio.Event | None = None
        self._task: asyncio.Task | None = None
        self._stop = False
        self.processed_count = 0

    # ---- enqueue (sync, idempotent) ----
    def enqueue(self, db: Session, *, document_id: str, requester_id: str) -> bool:
        """Transition a document to OCR_PENDING and queue it. No-op (False) if the
        document is missing, already in-flight, or already interpreted."""
        doc = db.get(LabDocument, document_id)
        if doc is None:
            return False
        if LabDocStatus(doc.status) not in _ENQUEUEABLE:
            return False
        with self._lock:
            if document_id in self._inflight:
                return False
            self._inflight.add(document_id)
            self._buffer.append(document_id)

        _transition(doc, LabDocStatus.OCR_PENDING)
        doc.ocr_status = "pending"
        audit.record(
            db,
            actor_type="user",
            actor_id=requester_id,
            action="ocr_enqueue",
            resource_type="lab_document",
            resource_id=document_id,
        )
        db.commit()
        if self._event is not None:
            self._event.set()
        return True

    def pending(self) -> int:
        with self._lock:
            return len(self._buffer)

    def _pop(self) -> str | None:
        with self._lock:
            if not self._buffer:
                return None
            return self._buffer.pop(0)

    def _release(self, document_id: str) -> None:
        with self._lock:
            self._inflight.discard(document_id)

    # ---- drain one (sync; opens its own session) ----
    def process_next(self) -> str | None:
        document_id = self._pop()
        if document_id is None:
            return None
        db = SessionLocal()
        try:
            process_document(db, document_id=document_id)
        finally:
            db.close()
            self._release(document_id)
            self.processed_count += 1
        return document_id

    def drain(self) -> int:
        """Process the whole buffer synchronously (tests / shutdown flush)."""
        n = 0
        while self.process_next() is not None:
            n += 1
        return n

    # ---- async worker (started in lifespan) ----
    async def run(self) -> None:
        self._event = asyncio.Event()
        self._stop = False
        loop = asyncio.get_running_loop()
        while not self._stop:
            if self.pending() == 0:
                self._event.clear()
                try:
                    await asyncio.wait_for(self._event.wait(), timeout=0.5)
                except TimeoutError:
                    continue
            # Offload the (blocking) sync DB work to a thread.
            await loop.run_in_executor(None, self.process_next)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        self._stop = True
        if self._event is not None:
            self._event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=1.0)
            except (TimeoutError, asyncio.CancelledError):
                self._task.cancel()
            self._task = None

    def reset(self) -> None:
        with self._lock:
            self._inflight.clear()
            self._buffer.clear()
        self.processed_count = 0


_manager = OCRWorkerManager()


def get_worker() -> OCRWorkerManager:
    return _manager
