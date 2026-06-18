"""Lab document + interpretation routes (mock OCR in dev/test).

T18A additions:
  GET /patients/{patient_id}/lab-documents — list all lab documents for a patient.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_session, require_roles
from app.models.clinical import LabDocument
from app.models.patient import PatientProfile
from app.models.user import UserRole
from app.schemas.lab import (
    InterpretationOut,
    LabDocumentCreate,
    LabDocumentOut,
    LabDocumentStatusOut,
)
from app.services import consent, lab
from app.services.lab_pipeline import get_worker

router = APIRouter(tags=["lab"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_patient_ownership(
    db: Session,
    *,
    patient_id: str,
    user: CurrentUser,
) -> None:
    """For PATIENT role: verify the requesting user owns the given patient profile.

    INTERNAL_ADMIN and SUPER_ADMIN bypass ownership checks.
    Raises HTTP 403 if the patient attempts to access another patient's data.
    """
    # DOCTOR and CLINIC_ADMIN: consent gate in service layer handles access
    # — no ownership check here
    if user.role in (UserRole.INTERNAL_ADMIN.value, UserRole.SUPER_ADMIN.value):
        return
    if user.role == UserRole.PATIENT.value:
        profile = db.get(PatientProfile, patient_id)
        if profile is None or profile.user_id != user.id:
            raise HTTPException(
                status_code=403,
                detail="Patients may only access their own lab documents.",
            )

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get(
    "/patients/{patient_id}/lab-documents",
    response_model=list[LabDocumentOut],
    summary="List lab documents for a patient (newest first)",
)
def list_patient_lab_documents(
    patient_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(
        require_roles(
            UserRole.PATIENT,
            UserRole.DOCTOR,
            UserRole.INTERNAL_ADMIN,
            UserRole.SUPER_ADMIN,
        )
    ),
    db: Session = Depends(get_session),
) -> list[LabDocumentOut]:
    """Return paginated lab documents for *patient_id* (newest first).

    Access rules:
    - **PATIENT** — own documents only.
    - **DOCTOR** — consent-gated (scope='lab').
    - **INTERNAL_ADMIN / SUPER_ADMIN** — unrestricted.
    """
    _require_patient_ownership(db, patient_id=patient_id, user=user)
    consent.require_access(db, patient_id=patient_id, requester_id=user.id, scope="lab")

    stmt = (
        select(LabDocument)
        .where(LabDocument.patient_id == patient_id)
        .order_by(LabDocument.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    docs = db.execute(stmt).scalars().all()
    return [LabDocumentOut.model_validate(d) for d in docs]


@router.post(
    "/patients/{patient_id}/lab-documents",
    response_model=LabDocumentOut,
    status_code=201,
)
def register_document(
    patient_id: str,
    payload: LabDocumentCreate,
    user: CurrentUser = Depends(
        require_roles(
            UserRole.PATIENT,
            UserRole.DOCTOR,
            UserRole.INTERNAL_ADMIN,
            UserRole.SUPER_ADMIN,
        )
    ),
    db: Session = Depends(get_session),
) -> LabDocumentOut:
    _require_patient_ownership(db, patient_id=patient_id, user=user)
    doc = lab.register_document(
        db,
        patient_id=patient_id,
        requester_id=user.id,
        storage_key=payload.storage_key,
        file_type=payload.file_type,
        lab_name=payload.lab_name,
    )
    return LabDocumentOut.model_validate(doc)


@router.post(
    "/lab-documents/{document_id}/process",
    response_model=LabDocumentStatusOut,
    status_code=202,
)
def enqueue_document(
    document_id: str,
    user: CurrentUser = Depends(
        require_roles(
            UserRole.PATIENT,
            UserRole.DOCTOR,
            UserRole.INTERNAL_ADMIN,
            UserRole.SUPER_ADMIN,
        )
    ),
    db: Session = Depends(get_session),
) -> LabDocumentStatusOut:
    """Enqueue a document for async OCR + interpretation (idempotent)."""
    doc = db.get(LabDocument, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="lab document not found")
    _require_patient_ownership(db, patient_id=doc.patient_id, user=user)
    consent.require_access(db, patient_id=doc.patient_id, requester_id=user.id, scope="lab")
    enqueued = get_worker().enqueue(db, document_id=document_id, requester_id=user.id)
    db.refresh(doc)
    return LabDocumentStatusOut(
        id=doc.id, status=doc.status, ocr_status=doc.ocr_status, enqueued=enqueued
    )


@router.get("/lab-documents/{document_id}", response_model=LabDocumentStatusOut)
def document_status(
    document_id: str,
    user: CurrentUser = Depends(
        require_roles(
            UserRole.PATIENT,
            UserRole.DOCTOR,
            UserRole.CLINIC_ADMIN,
            UserRole.INTERNAL_ADMIN,
            UserRole.SUPER_ADMIN,
        )
    ),
    db: Session = Depends(get_session),
) -> LabDocumentStatusOut:
    doc = db.get(LabDocument, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="lab document not found")
    _require_patient_ownership(db, patient_id=doc.patient_id, user=user)
    consent.require_access(db, patient_id=doc.patient_id, requester_id=user.id, scope="lab")
    return LabDocumentStatusOut(id=doc.id, status=doc.status, ocr_status=doc.ocr_status)


@router.post("/lab-documents/{document_id}/interpret", response_model=InterpretationOut)
def interpret_document(
    document_id: str,
    user: CurrentUser = Depends(
        require_roles(
            UserRole.PATIENT,
            UserRole.DOCTOR,
            UserRole.INTERNAL_ADMIN,
            UserRole.SUPER_ADMIN,
        )
    ),
    db: Session = Depends(get_session),
) -> InterpretationOut:
    doc = db.get(LabDocument, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="lab document not found")
    _require_patient_ownership(db, patient_id=doc.patient_id, user=user)
    try:
        result = lab.interpret_document(db, document_id=document_id, requester_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return InterpretationOut(
        biomarkers=[
            {
                "canonical": b.canonical,
                "value": b.value,
                "unit": b.unit,
                "status": b.status.value,
                "reference_range": b.reference_range,
                "needs_verification": b.needs_verification,
                "patient_note": b.patient_note,
            }
            for b in result.biomarkers
        ],
        abnormal=result.abnormal,
        critical=result.critical,
        needs_verification=result.needs_verification,
        patient_explanation=result.patient_explanation,
        doctor_summary=result.doctor_summary,
    )
