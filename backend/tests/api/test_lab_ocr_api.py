"""M4/2b end-to-end: lab photo → OCR → per-candidate confirm → real LabResult
(+HealthMetric for trends) via the existing lab pipeline (BRD §E). Exercises the
REAL LabExtractor + LabPromoter (mock OCR feeds VN lab-report text).
"""

from __future__ import annotations

import hashlib

import pytest
from app.main import app
from app.models.clinical import HealthMetric, LabResult
from app.services.mdi import extractors, promoter
from app.services.mdi.bootstrap import register_defaults
from app.services.ocr_engine import OcrTextResult
from app.services.storage import reset_storage
from fastapi.testclient import TestClient
from sqlalchemy import select

_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 256

_LAB = """PHÒNG XÉT NGHIỆM ABC
Ngày lấy mẫu: 20/03/2026
Glucose: 6.2 mmol/L (3.9 - 6.4)
HbA1c 6.8 % 4.0-6.0
"""


@pytest.fixture
def lab_env(monkeypatch, tmp_path):
    from app.core.config import get_settings

    monkeypatch.setenv("MCP_STORAGE_LOCAL_DIR", str(tmp_path))
    monkeypatch.setenv("FEATURE_OCR", "true")
    get_settings.cache_clear()
    reset_storage()
    monkeypatch.setattr(
        "app.services.mdi.pipeline.run_ocr",
        lambda image_bytes, mime: OcrTextResult(text=_LAB, confidence=0.9, provider="mock"),
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
            "doc_type_hint": "lab_report",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert client.put(body["signed_put_url"], content=_JPEG).status_code == 204
    fin = client.post(f"/api/v1/documents/{body['upload_id']}/finalize", headers=headers)
    assert fin.status_code == 200, fin.text
    assert fin.json()["doc_type"] == "lab_report"
    return body["upload_id"]


def test_lab_photo_to_confirmed_result_and_trend(client, patient, db, lab_env):
    doc_id = _ingest(client, patient["headers"])
    cands = client.get(
        f"/api/v1/documents/{doc_id}/candidates", headers=patient["headers"]
    ).json()["items"]
    assert all(c["candidate_type"] == "lab_result" for c in cands)
    glucose = next(c for c in cands if c["fields"]["canonical"] == "fasting_glucose")

    r = client.post(
        f"/api/v1/candidates/{glucose['id']}/confirm", headers=patient["headers"], json={}
    )
    assert r.status_code == 200, r.text
    assert r.json()["promotion"]["canonical_type"] == "lab_result"
    canonical_id = r.json()["promotion"]["canonical_id"]

    # A real LabResult exists, original value/unit preserved (§E).
    row = db.get(LabResult, canonical_id)
    assert row is not None
    assert row.patient_id == patient["patient_id"]
    assert row.canonical_name == "fasting_glucose"
    assert row.original_value == 6.2
    assert row.original_unit == "mmol/L"
    assert row.verified_by_user is True

    # Promoted to HealthMetric so trends/dashboard reflect it.
    metrics = db.execute(
        select(HealthMetric).where(HealthMetric.patient_id == patient["patient_id"])
    ).scalars().all()
    assert len(metrics) >= 1


def test_lab_reject_does_not_create_result(client, patient, db, lab_env):
    doc_id = _ingest(client, patient["headers"])
    cid = client.get(
        f"/api/v1/documents/{doc_id}/candidates", headers=patient["headers"]
    ).json()["items"][0]["id"]
    before = len(
        db.execute(
            select(LabResult).where(LabResult.patient_id == patient["patient_id"])
        ).scalars().all()
    )
    assert (
        client.post(f"/api/v1/candidates/{cid}/reject", headers=patient["headers"]).status_code
        == 200
    )
    after = len(
        db.execute(
            select(LabResult).where(LabResult.patient_id == patient["patient_id"])
        ).scalars().all()
    )
    assert after == before  # rejection writes no canonical row


def test_unrecognized_unit_blocks_then_correction_succeeds(
    client, patient, db, lab_env, monkeypatch
):
    """Review P0: a garbled/unknown unit on a spec'd analyte must NOT be silently
    classified — confirm is refused (422) until the patient corrects the unit."""
    monkeypatch.setattr(
        "app.services.mdi.pipeline.run_ocr",
        lambda image_bytes, mime: OcrTextResult(
            text="Glucose: 6.2 xyz\n", confidence=0.9, provider="mock"
        ),
    )
    doc_id = _ingest(client, patient["headers"])
    cid = client.get(
        f"/api/v1/documents/{doc_id}/candidates", headers=patient["headers"]
    ).json()["items"][0]["id"]

    blocked = client.post(
        f"/api/v1/candidates/{cid}/confirm", headers=patient["headers"], json={}
    )
    assert blocked.status_code == 422  # unit unrecognized → refuse, no canonical write
    assert (
        db.execute(
            select(LabResult).where(LabResult.patient_id == patient["patient_id"])
        ).scalars().first()
        is None
    )

    fixed = client.post(
        f"/api/v1/candidates/{cid}/confirm",
        headers=patient["headers"],
        json={"corrections": {"unit": "mmol/L"}},
    )
    assert fixed.status_code == 200, fixed.text
    row = db.get(LabResult, fixed.json()["promotion"]["canonical_id"])
    assert row is not None and row.canonical_name == "fasting_glucose"
