"""Medication → source-document provenance API (BRD §F, Master Plan §1.5).

Answers "where did this medication come from?" from the medication side. Purely
additive: no existing contract changes, so the mobile client is unaffected.

Patient-owned — the path ``patient_id`` must equal the caller's own
``PatientProfile.id``, and the medication must belong to that profile.

Consent (PRIV-F1): the payload describes MEDICAL DOCUMENTS, so it sits behind the
same fail-closed ``documents`` consent gate as ``routes/documents.py``. A patient
who has not granted it gets the standard 403 CONSENT_DENIED; clients must treat
that as "source unavailable — grant consent to view", not as a page failure, so
the rest of the medication detail keeps working.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.consent_policy import CATEGORY_DOCUMENTS, is_granted
from app.api.deps import CurrentUser, get_session, require_roles
from app.models.clinical import Medication
from app.models.patient import PatientProfile
from app.models.user import UserRole
from app.services import medication_provenance as provenance
from app.services.consent_guard import ConsentDenied

router = APIRouter(tags=["medication_source"])

_PatientOnly = require_roles(UserRole.PATIENT)


# ── schemas ──────────────────────────────────────────────────────────────────
class SourceDocumentOut(BaseModel):
    document_id: str
    doc_type: str | None
    document_status: str
    document_source: str
    page_count: int | None
    uploaded_at: dt.datetime | None

    promotion_action: str
    promoted_at: dt.datetime | None

    candidate_id: str
    candidate_status: str
    candidate_reviewed_at: dt.datetime | None

    #: Allowlisted prescription-line fields (strength/form/quantity/frequency/
    #: route/duration/instructions). An absent key means OCR never produced it —
    #: clients must render "chưa có dữ liệu", never a guess.
    prescription_fields: dict[str, str]
    #: Allowlisted header context (facility/prescriber/prescribed_date).
    prescription_context: dict[str, str]

    ocr_provider: str | None
    ocr_model: str | None
    ocr_prompt_version: str | None
    ocr_schema_version: str | None
    extraction_review_state: str | None


class MedicationSourceOut(BaseModel):
    medication_id: str
    #: Mirrors ``Medication.source_type`` / ``verification_status`` so a client can
    #: render provenance without a second request.
    source_type: str
    verification_status: str
    #: False when the medication was entered manually — an expected state, not an error.
    has_document_source: bool
    documents: list[SourceDocumentOut]


# ── helpers ──────────────────────────────────────────────────────────────────
def _require_self(db: Session, user: CurrentUser, patient_id: str) -> None:
    profile = db.execute(
        select(PatientProfile).where(PatientProfile.user_id == user.id)
    ).scalars().first()
    if profile is None or profile.id != patient_id:
        raise HTTPException(status_code=403, detail="Không có quyền với hồ sơ này.")


def _require_documents_consent(db: Session, user_id: str) -> None:
    if not is_granted(db, user_id, CATEGORY_DOCUMENTS):
        raise ConsentDenied(
            "Bạn cần bật quyền 'Tài liệu y tế' trong phần Quyền riêng tư để xem "
            "nguồn tài liệu của thuốc này."
        )


# ── routes ───────────────────────────────────────────────────────────────────
@router.get(
    "/patients/{patient_id}/medications/{medication_id}/source",
    response_model=MedicationSourceOut,
    summary="Source document(s) and OCR provenance for one medication",
)
def get_medication_source(
    patient_id: str,
    medication_id: str,
    user: CurrentUser = Depends(_PatientOnly),
    db: Session = Depends(get_session),
) -> MedicationSourceOut:
    _require_self(db, user, patient_id)
    _require_documents_consent(db, user.id)

    medication = db.execute(
        select(Medication).where(
            Medication.id == medication_id,
            Medication.patient_id == patient_id,
            Medication.deleted_at.is_(None),
        )
    ).scalars().first()
    if medication is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy thông tin thuốc.")

    documents = provenance.source_documents_for_medication(
        db, patient_id=patient_id, medication_id=medication_id
    )
    return MedicationSourceOut(
        medication_id=medication_id,
        source_type=medication.source_type,
        verification_status=medication.verification_status,
        has_document_source=bool(documents),
        documents=[SourceDocumentOut(**d) for d in documents],
    )
