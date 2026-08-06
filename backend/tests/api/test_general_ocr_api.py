"""M7/2c end-to-end: general medical report → typed candidates → per-candidate
confirm (§1.9). Diagnosis becomes a confirmed record only on explicit confirm and
never writes a canonical medication/lab row. Uses the REAL GeneralReportExtractor
+ RecordOnlyPromoter (mock OCR feeds VN report text).
"""

from __future__ import annotations

import hashlib

import pytest
from app.main import app
from app.models.clinical import LabResult, Medication
from app.services.mdi import extractors, promoter
from app.services.mdi.bootstrap import register_defaults
from app.services.ocr_engine import OcrTextResult
from app.services.storage import reset_storage
from fastapi.testclient import TestClient
from sqlalchemy import select

_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 256

_RPT = """BỆNH VIỆN ABC - PHIẾU XUẤT VIỆN
Ngày ra viện: 18/03/2026
Chẩn đoán: Tăng huyết áp vô căn
Lời dặn: Ăn nhạt, tập thể dục đều
Tái khám: sau 4 tuần
"""


@pytest.fixture
def gen_env(monkeypatch, tmp_path):
    from app.core.config import get_settings

    monkeypatch.setenv("MCP_STORAGE_LOCAL_DIR", str(tmp_path))
    monkeypatch.setenv("FEATURE_OCR", "true")
    get_settings.cache_clear()
    reset_storage()
    monkeypatch.setattr(
        "app.services.mdi.pipeline.run_ocr",
        lambda image_bytes, mime: OcrTextResult(text=_RPT, confidence=0.9, provider="mock"),
    )
    register_defaults()
    yield
    extractors.reset_extractors()
    promoter.reset_promoters()
    reset_storage()
    get_settings.cache_clear()


@pytest.fixture
def client():
    return TestClient(app)


def _ingest(client, headers):
    sha = hashlib.sha256(_JPEG).hexdigest()
    r = client.post(
        "/api/v1/documents/upload-session",
        headers=headers,
        json={
            "declared_mime": "image/jpeg",
            "declared_sha256": sha,
            "declared_size": len(_JPEG),
            "doc_type_hint": "general",
        },
    )
    body = r.json()
    assert client.put(body["signed_put_url"], content=_JPEG).status_code == 204
    fin = client.post(f"/api/v1/documents/{body['upload_id']}/finalize", headers=headers)
    assert fin.status_code == 200, fin.text
    assert fin.json()["doc_type"] == "general"
    return body["upload_id"]


def test_general_report_typed_candidates_and_confirm(client, patient, db, gen_env):
    doc_id = _ingest(client, patient["headers"])
    cands = client.get(
        f"/api/v1/documents/{doc_id}/candidates", headers=patient["headers"]
    ).json()["items"]
    types = {c["candidate_type"] for c in cands}
    assert {"diagnosis", "recommendation", "follow_up"} <= types

    diagnosis = next(c for c in cands if c["candidate_type"] == "diagnosis")
    r = client.post(
        f"/api/v1/candidates/{diagnosis['id']}/confirm", headers=patient["headers"], json={}
    )
    assert r.status_code == 200, r.text
    # Confirmed as a record-only diagnosis (canonical_id points back to the candidate).
    assert r.json()["promotion"]["canonical_type"] == "diagnosis"
    assert r.json()["candidate"]["status"] == "confirmed"

    # §1.9 — a diagnosis NEVER creates a canonical medication/lab row.
    assert (
        db.execute(
            select(Medication).where(Medication.patient_id == patient["patient_id"])
        ).scalars().first()
        is None
    )
    assert (
        db.execute(
            select(LabResult).where(LabResult.patient_id == patient["patient_id"])
        ).scalars().first()
        is None
    )


def test_follow_up_confirm_records_intent(client, patient, gen_env):
    doc_id = _ingest(client, patient["headers"])
    cands = client.get(
        f"/api/v1/documents/{doc_id}/candidates", headers=patient["headers"]
    ).json()["items"]
    follow = next(c for c in cands if c["candidate_type"] == "follow_up")
    r = client.post(
        f"/api/v1/candidates/{follow['id']}/confirm", headers=patient["headers"], json={}
    )
    assert r.status_code == 200
    assert r.json()["promotion"]["canonical_type"] == "follow_up"


def test_merge_on_record_only_type_rejected(client, patient, gen_env):
    """P1: record-only types (diagnosis/…) have nothing to merge into → 403."""
    doc_id = _ingest(client, patient["headers"])
    diag = next(
        c
        for c in client.get(
            f"/api/v1/documents/{doc_id}/candidates", headers=patient["headers"]
        ).json()["items"]
        if c["candidate_type"] == "diagnosis"
    )
    r = client.post(
        f"/api/v1/candidates/{diag['id']}/merge",
        headers=patient["headers"],
        json={"merge_target_id": "whatever-id"},
    )
    assert r.status_code == 403


def test_blank_text_correction_rejected(client, patient, gen_env):
    """P2: correcting a candidate's text to blank is a validation error (422)."""
    doc_id = _ingest(client, patient["headers"])
    diag = next(
        c
        for c in client.get(
            f"/api/v1/documents/{doc_id}/candidates", headers=patient["headers"]
        ).json()["items"]
        if c["candidate_type"] == "diagnosis"
    )
    r = client.post(
        f"/api/v1/candidates/{diag['id']}/confirm",
        headers=patient["headers"],
        json={"corrections": {"text": "   "}},
    )
    assert r.status_code == 422
