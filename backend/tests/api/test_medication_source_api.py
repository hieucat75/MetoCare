"""GET /patients/{pid}/medications/{mid}/source — reverse provenance (BRD §F).

Covers the manual-entry fallback, the OCR-promoted happy path, the PHI allowlist
(notably that an unconfirmed OCR'd `diagnosis` never leaks onto a medication page,
§1.9), soft-delete exclusion, BOLA, and the fail-closed documents-consent gate.
"""

from __future__ import annotations

import datetime as dt

import pytest
from app.models.medical_document import (
    DocumentExtraction,
    ExtractionCandidate,
    MedicalDocument,
    PromotionLink,
)
from app.services import medication as medication_svc

_PRESCRIPTION_FIELDS = {
    "name": "Metformin",
    "strength": "500mg",
    "form": "viên",
    "quantity": "60",
    "frequency": "2 lần/ngày",
    "route": "uống",
    "duration": "30 ngày",
    "instructions": "Uống sau ăn",
    "prescription_context": {
        "facility": "Phòng khám Đa khoa ABC",
        "prescriber": "BS. Trần Văn B",
        "prescribed_date": "01/08/2026",
        # Must NEVER reach the response — an unconfirmed OCR'd diagnosis surfacing
        # as medication provenance is the §1.9 back door this guards.
        "diagnosis": "Đái tháo đường type 2",
    },
}


def _seed_promoted_medication(db, patient_id: str, *, deleted: bool = False):
    """Seed document → extraction → candidate → PromotionLink → Medication."""
    med = medication_svc.add_medication(
        db, patient_id=patient_id, data={"name": "Metformin", "dose": "500mg"}, commit=True
    )
    doc = MedicalDocument(
        patient_id=patient_id,
        quarantine_key="q",
        status="accepted",
        object_state="accepted",
        doc_type="prescription",
        source="upload",
        page_count=1,
        deleted_at=dt.datetime.now(dt.UTC) if deleted else None,
    )
    db.add(doc)
    db.flush()
    ext = DocumentExtraction(
        document_id=doc.id,
        schema_version="mdi-1",
        provider="tesseract",
        model="vie-best",
        prompt_version="p1",
        extraction_run_id="run-1",
        review_state="reviewed",
    )
    db.add(ext)
    db.flush()
    cand = ExtractionCandidate(
        extraction_id=ext.id,
        document_id=doc.id,
        patient_id=patient_id,
        candidate_type="medication",
        fields_json=_PRESCRIPTION_FIELDS,
        dedupe_key="k-metformin",
        status="confirmed",
        reviewed_at=dt.datetime.now(dt.UTC),
    )
    db.add(cand)
    db.flush()
    db.add(
        PromotionLink(
            candidate_id=cand.id,
            canonical_type="medication",
            canonical_id=med.id,
            action="created",
        )
    )
    db.commit()
    return med, doc, cand


def _get(client, patient, med_id: str):
    return client.get(
        f"/api/v1/patients/{patient['patient_id']}/medications/{med_id}/source",
        headers=patient["headers"],
    )


# ── manual entry (the common case) ───────────────────────────────────────────
def test_manual_medication_reports_no_document_source(client, patient, db):
    med = medication_svc.add_medication(
        db, patient_id=patient["patient_id"], data={"name": "Vitamin D"}, commit=True
    )
    res = _get(client, patient, med.id)
    assert res.status_code == 200
    body = res.json()
    assert body["has_document_source"] is False
    assert body["documents"] == []
    assert body["source_type"] == "patient_manual"


# ── OCR-promoted happy path ──────────────────────────────────────────────────
def test_promoted_medication_returns_document_and_ocr_provenance(client, patient, db):
    med, doc, cand = _seed_promoted_medication(db, patient["patient_id"])

    res = _get(client, patient, med.id)
    assert res.status_code == 200
    body = res.json()
    assert body["has_document_source"] is True
    assert len(body["documents"]) == 1

    src = body["documents"][0]
    assert src["document_id"] == doc.id
    assert src["doc_type"] == "prescription"
    assert src["document_status"] == "accepted"
    assert src["candidate_id"] == cand.id
    assert src["candidate_status"] == "confirmed"
    assert src["promotion_action"] == "created"
    assert src["ocr_provider"] == "tesseract"
    assert src["ocr_model"] == "vie-best"
    assert src["extraction_review_state"] == "reviewed"


def test_prescription_fields_and_context_are_allowlisted(client, patient, db):
    med, _, _ = _seed_promoted_medication(db, patient["patient_id"])
    src = _get(client, patient, med.id).json()["documents"][0]

    assert src["prescription_fields"]["strength"] == "500mg"
    assert src["prescription_fields"]["route"] == "uống"
    assert src["prescription_fields"]["instructions"] == "Uống sau ăn"
    # `name` is not allowlisted — the canonical Medication.name is authoritative.
    assert "name" not in src["prescription_fields"]

    assert src["prescription_context"]["facility"] == "Phòng khám Đa khoa ABC"
    assert src["prescription_context"]["prescriber"] == "BS. Trần Văn B"
    assert src["prescription_context"]["prescribed_date"] == "01/08/2026"


def test_unconfirmed_ocr_diagnosis_never_leaks(client, patient, db):
    """§1.9 — a diagnosis must not become canonical without clinician confirmation,
    and must not appear as medication provenance either."""
    med, _, _ = _seed_promoted_medication(db, patient["patient_id"])
    raw = _get(client, patient, med.id).text
    assert "Đái tháo đường type 2" not in raw
    assert "diagnosis" not in raw


def test_soft_deleted_source_document_is_excluded(client, patient, db):
    med, _, _ = _seed_promoted_medication(db, patient["patient_id"], deleted=True)
    body = _get(client, patient, med.id).json()
    assert body["has_document_source"] is False
    assert body["documents"] == []


# ── access control ───────────────────────────────────────────────────────────
def test_other_patients_profile_is_forbidden(client, patient, db, token_for):
    from app.models.patient import PatientProfile
    from app.models.user import User, UserRole

    other_user = User(email="other-src@example.com", password_hash="x", role=UserRole.PATIENT)
    db.add(other_user)
    db.flush()
    db.add(PatientProfile(user_id=other_user.id, full_name="Khác"))
    db.commit()

    med = medication_svc.add_medication(
        db, patient_id=patient["patient_id"], data={"name": "Metformin"}, commit=True
    )
    res = client.get(
        f"/api/v1/patients/{patient['patient_id']}/medications/{med.id}/source",
        headers=token_for(other_user.id, "patient"),
    )
    assert res.status_code == 403


def test_unknown_medication_is_404(client, patient):
    res = _get(client, patient, "00000000-0000-0000-0000-000000000000")
    assert res.status_code == 404


def test_unauthenticated_is_401(client, patient):
    res = client.get(f"/api/v1/patients/{patient['patient_id']}/medications/x/source")
    assert res.status_code == 401


# ── consent (fail-closed) ────────────────────────────────────────────────────
@pytest.mark.real_consent
def test_fail_closed_without_documents_consent(client, patient, db):
    med = medication_svc.add_medication(
        db, patient_id=patient["patient_id"], data={"name": "Metformin"}, commit=True
    )
    res = _get(client, patient, med.id)
    assert res.status_code == 403
