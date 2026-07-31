"""M3 end-to-end: prescription photo → OCR → per-candidate confirm → real
Medication created via the statement-first path (BRD §D). Exercises the REAL
PrescriptionExtractor + MedicationPromoter (mock OCR feeds VN prescription text).
"""

from __future__ import annotations

import hashlib

import pytest
from app.main import app
from app.models.clinical import Medication
from app.models.medical_document import ExtractionCandidate, PromotionLink
from app.services.mdi import extractors, promoter
from app.services.mdi.bootstrap import register_defaults
from app.services.ocr_engine import OcrTextResult
from app.services.storage import reset_storage
from fastapi.testclient import TestClient
from sqlalchemy import select

_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 256

_RX = """PHÒNG KHÁM ĐA KHOA ABC
Bác sĩ: Nguyễn Văn A
Ngày 15/03/2026
Chẩn đoán: Đái tháo đường type 2
1) Metformin 500mg - SL 60 viên
   Uống ngày 2 lần, sáng - tối, sau ăn
2) Amlodipine 5mg x 30 viên
   Uống ngày 1 lần vào buổi sáng trong 30 ngày
"""


@pytest.fixture
def rx_env(monkeypatch, tmp_path):
    """Real extractor+promoter; mock OCR returns a VN prescription; temp storage."""
    from app.core.config import get_settings

    monkeypatch.setenv("MCP_STORAGE_LOCAL_DIR", str(tmp_path))
    monkeypatch.setenv("FEATURE_OCR", "true")
    get_settings.cache_clear()
    reset_storage()
    monkeypatch.setattr(
        "app.services.mdi.pipeline.run_ocr",
        lambda image_bytes, mime: OcrTextResult(text=_RX, confidence=0.9, provider="mock"),
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


def _ingest(client, headers, data=_JPEG):
    sha = hashlib.sha256(data).hexdigest()
    r = client.post(
        "/api/v1/documents/upload-session",
        headers=headers,
        json={
            "declared_mime": "image/jpeg",
            "declared_sha256": sha,
            "declared_size": len(data),
            "doc_type_hint": "prescription",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert client.put(body["signed_put_url"], content=data).status_code == 204
    fin = client.post(f"/api/v1/documents/{body['upload_id']}/finalize", headers=headers)
    assert fin.status_code == 200, fin.text
    return body["upload_id"]


def test_prescription_photo_to_confirmed_medication(client, patient, db, rx_env):
    doc_id = _ingest(client, patient["headers"])
    cands = client.get(
        f"/api/v1/documents/{doc_id}/candidates", headers=patient["headers"]
    ).json()["items"]
    assert {c["fields"]["name"] for c in cands} == {"Metformin", "Amlodipine"}

    metformin = next(c for c in cands if c["fields"]["name"] == "Metformin")
    r = client.post(
        f"/api/v1/candidates/{metformin['id']}/confirm", headers=patient["headers"], json={}
    )
    assert r.status_code == 200, r.text
    canonical_id = r.json()["promotion"]["canonical_id"]

    # A real canonical Medication now exists, statement-first, stamped ocr_confirmed.
    med = db.get(Medication, canonical_id)
    assert med is not None
    assert med.patient_id == patient["patient_id"]
    assert med.name == "Metformin"
    assert med.source_type == "ocr_confirmed"
    assert med.dose == "500mg" or "500mg" in (med.dose or "")


def test_reprocess_after_confirm_never_double_promotes(client, patient, db, rx_env):
    doc_id = _ingest(client, patient["headers"])
    cands = client.get(
        f"/api/v1/documents/{doc_id}/candidates", headers=patient["headers"]
    ).json()["items"]
    metformin = next(c for c in cands if c["fields"]["name"] == "Metformin")
    client.post(
        f"/api/v1/candidates/{metformin['id']}/confirm", headers=patient["headers"], json={}
    )

    client.post(f"/api/v1/documents/{doc_id}/reprocess", headers=patient["headers"])

    meds = db.execute(
        select(Medication).where(Medication.patient_id == patient["patient_id"])
    ).scalars().all()
    assert sum(1 for m in meds if m.name == "Metformin") == 1  # exactly one, not two
    # Scope links to THIS patient's candidates (rows from other tests persist in
    # the session-scoped DB).
    my_cand_ids = list(
        db.execute(
            select(ExtractionCandidate.id).where(
                ExtractionCandidate.patient_id == patient["patient_id"]
            )
        ).scalars()
    )
    links = db.execute(
        select(PromotionLink).where(PromotionLink.candidate_id.in_(my_cand_ids))
    ).scalars().all()
    assert len(links) == 1  # single promotion survived reprocess


def test_merge_into_existing_medication(client, patient, db, rx_env):
    # Seed an existing canonical medication to merge into.
    from app.services import medication as medication_svc

    existing = medication_svc.add_medication(
        db, patient_id=patient["patient_id"], data={"name": "Metformin"}, commit=True
    )
    doc_id = _ingest(client, patient["headers"])
    cid = next(
        c["id"]
        for c in client.get(
            f"/api/v1/documents/{doc_id}/candidates", headers=patient["headers"]
        ).json()["items"]
        if c["fields"]["name"] == "Metformin"
    )
    r = client.post(
        f"/api/v1/candidates/{cid}/merge",
        headers=patient["headers"],
        json={"merge_target_id": existing.id},
    )
    assert r.status_code == 200, r.text
    assert r.json()["promotion"]["action"] == "merged_into"
    assert r.json()["promotion"]["canonical_id"] == existing.id


def test_merge_into_other_patients_medication_forbidden(
    client, patient, token_for, db, rx_env
):
    """P1-4: cross-patient merge_target must be refused (403)."""
    from app.models.patient import PatientProfile
    from app.models.user import User, UserRole
    from app.services import medication as medication_svc

    other = User(email="o2@example.com", password_hash="x", role=UserRole.PATIENT, full_name="O2")
    db.add(other)
    db.flush()
    other_profile = PatientProfile(user_id=other.id, full_name="O2")
    db.add(other_profile)
    db.commit()
    other_med = medication_svc.add_medication(
        db, patient_id=other_profile.id, data={"name": "Metformin"}, commit=True
    )

    doc_id = _ingest(client, patient["headers"])
    cid = next(
        c["id"]
        for c in client.get(
            f"/api/v1/documents/{doc_id}/candidates", headers=patient["headers"]
        ).json()["items"]
        if c["fields"]["name"] == "Metformin"
    )
    r = client.post(
        f"/api/v1/candidates/{cid}/merge",
        headers=patient["headers"],
        json={"merge_target_id": other_med.id},
    )
    assert r.status_code == 403


def _first_candidate(client, headers, doc_id):
    return client.get(
        f"/api/v1/documents/{doc_id}/candidates", headers=headers
    ).json()["items"][0]["id"]


def test_nested_corrections_rejected_422(client, patient, rx_env):
    """P1-4: corrections must be a flat scalar map (no nested JSON)."""
    doc_id = _ingest(client, patient["headers"])
    cid = _first_candidate(client, patient["headers"], doc_id)
    r = client.post(
        f"/api/v1/candidates/{cid}/confirm",
        headers=patient["headers"],
        json={"corrections": {"name": {"evil": "nested"}}},
    )
    assert r.status_code == 422


def test_correction_blanking_name_rejected_422(client, patient, rx_env):
    """P2-6: a correction that empties the medicine name is a validation error."""
    doc_id = _ingest(client, patient["headers"])
    cid = _first_candidate(client, patient["headers"], doc_id)
    r = client.post(
        f"/api/v1/candidates/{cid}/confirm",
        headers=patient["headers"],
        json={"corrections": {"name": ""}},
    )
    assert r.status_code == 422


def test_merge_into_entered_in_error_forbidden(client, patient, db, rx_env):
    """P2-5: a terminal (entered_in_error) medication cannot be a merge target."""
    from app.services import medication as medication_svc

    med = medication_svc.add_medication(
        db, patient_id=patient["patient_id"], data={"name": "Metformin"}, commit=False
    )
    med.lifecycle_status = "entered_in_error"
    db.commit()
    doc_id = _ingest(client, patient["headers"])
    cid = next(
        c["id"]
        for c in client.get(
            f"/api/v1/documents/{doc_id}/candidates", headers=patient["headers"]
        ).json()["items"]
        if c["fields"]["name"] == "Metformin"
    )
    r = client.post(
        f"/api/v1/candidates/{cid}/merge",
        headers=patient["headers"],
        json={"merge_target_id": med.id},
    )
    assert r.status_code == 403
