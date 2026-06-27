"""Lab document + interpretation routes (mock OCR in dev/test).

T18A additions:
  GET /patients/{patient_id}/lab-documents — list all lab documents for a patient.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_session, require_roles
from app.core.feature_flags import FeatureFlag, is_enabled
from app.models.clinical import LabDocument
from app.models.patient import PatientProfile
from app.models.user import UserRole
from app.schemas.lab import (
    BatchLabResultListResponse,
    DuplicateCheckRequest,
    DuplicateCheckResponse,
    InterpretationOut,
    LabBatchListResponse,
    LabDocumentCreate,
    LabDocumentOut,
    LabDocumentStatusOut,
    LabManualEntryCreate,
    LabResultListResponse,
    LabResultOut,
    LabUploadBatchOut,
)
from app.services import consent, lab, lab_batch
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
    "/patients/{patient_id}/lab-results",
    response_model=LabResultListResponse,
    status_code=201,
    summary="Manually enter structured lab results (no OCR/file)",
)
def create_manual_lab_results(
    patient_id: str,
    payload: LabManualEntryCreate,
    user: CurrentUser = Depends(
        require_roles(
            UserRole.PATIENT,
            UserRole.DOCTOR,
            UserRole.INTERNAL_ADMIN,
            UserRole.SUPER_ADMIN,
        )
    ),
    db: Session = Depends(get_session),
) -> LabResultListResponse:
    """Create a manual lab entry (PR-B) — a document + typed result rows.

    No file/OCR. Available regardless of the OCR feature flag. Access rules
    match the upload path (patient owns; doctor consent-gated; AI/CLINIC_ADMIN
    excluded by role allowlist).
    """
    _require_patient_ownership(db, patient_id=patient_id, user=user)

    # Duplicate guard: if force_mode is absent, check for existing batch first.
    if payload.force_mode is None:
        biomarker_names = [r.test_name for r in payload.results]
        is_dup, existing_id, reason = lab_batch.check_duplicate(
            db,
            patient_id=patient_id,
            test_date=payload.test_date,
            lab_name=payload.lab_name,
            biomarker_names=biomarker_names,
        )
        if is_dup:
            raise HTTPException(
                status_code=409,
                detail={
                    "duplicate": True,
                    "existing_batch_id": existing_id,
                    "existing_test_date": str(payload.test_date),
                    "reason": reason,
                    "message": (
                        "Có vẻ kết quả xét nghiệm ngày này đã được lưu. "
                        "Chọn 'Ghi đè' để thay thế hoặc 'Bản mới' để lưu thêm."
                    ),
                },
            )

    _, rows = lab.create_manual_entry(
        db,
        patient_id=patient_id,
        requester_id=user.id,
        lab_name=payload.lab_name,
        test_date=payload.test_date,
        results=[r.model_dump() for r in payload.results],
        force_mode=payload.force_mode,
        existing_batch_id=payload.existing_batch_id,
        ocr_case_id=payload.ocr_case_id,
        review_time_seconds=payload.review_time_seconds,
    )
    return LabResultListResponse(
        patient_id=patient_id,
        total=len(rows),
        items=[LabResultOut.model_validate(r) for r in rows],
    )


_PATIENT_ROLES = (
    UserRole.PATIENT,
    UserRole.INTERNAL_ADMIN,
    UserRole.SUPER_ADMIN,
)


@router.post(
    "/patients/{patient_id}/lab-batches/check-duplicate",
    response_model=DuplicateCheckResponse,
    summary="Check whether a lab upload would be a duplicate",
)
def check_duplicate(
    patient_id: str,
    payload: DuplicateCheckRequest,
    user: CurrentUser = Depends(require_roles(*_PATIENT_ROLES)),
    db: Session = Depends(get_session),
) -> DuplicateCheckResponse:
    """Pre-flight: returns is_duplicate=True + existing_batch_id if a matching
    non-deleted batch already exists for this patient + test_date."""
    _require_patient_ownership(db, patient_id=patient_id, user=user)
    consent.require_access(db, patient_id=patient_id, requester_id=user.id, scope="lab")
    is_dup, existing_id, reason = lab_batch.check_duplicate(
        db,
        patient_id=patient_id,
        test_date=payload.test_date,
        lab_name=payload.lab_name,
        biomarker_names=payload.biomarker_names,
    )
    return DuplicateCheckResponse(
        is_duplicate=is_dup,
        existing_batch_id=existing_id,
        existing_test_date=payload.test_date if is_dup else None,
        reason=reason,
    )


@router.get(
    "/patients/{patient_id}/lab-batches",
    response_model=LabBatchListResponse,
    summary="List lab upload batches (upload sessions) for a patient",
)
def list_lab_batches(
    patient_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(require_roles(*_PATIENT_ROLES)),
    db: Session = Depends(get_session),
) -> LabBatchListResponse:
    _require_patient_ownership(db, patient_id=patient_id, user=user)
    consent.require_access(db, patient_id=patient_id, requester_id=user.id, scope="lab")
    total, items = lab_batch.list_batches(
        db, patient_id=patient_id, limit=limit, offset=offset
    )
    return LabBatchListResponse(
        patient_id=patient_id,
        total=total,
        items=[LabUploadBatchOut(**item) for item in items],
    )


@router.delete(
    "/patients/{patient_id}/lab-batches/{batch_id}",
    status_code=204,
    summary="Soft-delete a lab batch and cascade to lab_results + health_metrics",
)
def delete_lab_batch(
    patient_id: str,
    batch_id: str,
    reason: str | None = None,
    user: CurrentUser = Depends(require_roles(*_PATIENT_ROLES)),
    db: Session = Depends(get_session),
) -> None:
    _require_patient_ownership(db, patient_id=patient_id, user=user)
    try:
        lab_batch.delete_batch(
            db,
            batch_id=batch_id,
            deleted_by_user_id=user.id,
            reason=reason,
            patient_id=patient_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get(
    "/patients/{patient_id}/lab-batches/{batch_id}/results",
    response_model=BatchLabResultListResponse,
    summary="List lab results scoped to a single batch (batch-safe, ownership-checked)",
)
def get_batch_results(
    patient_id: str,
    batch_id: str,
    user: CurrentUser = Depends(
        require_roles(
            UserRole.PATIENT,
            UserRole.DOCTOR,
            UserRole.INTERNAL_ADMIN,
            UserRole.SUPER_ADMIN,
        )
    ),
    db: Session = Depends(get_session),
) -> BatchLabResultListResponse:
    """Return all LabResult rows belonging to *batch_id* for *patient_id*.

    Ownership check: PATIENT role may only access their own batches.
    Returns HTTP 404 if the batch does not exist or is not owned by the patient.
    Returns HTTP 200 + empty list if the batch exists but has no results.
    """
    _require_patient_ownership(db, patient_id=patient_id, user=user)
    consent.require_access(db, patient_id=patient_id, requester_id=user.id, scope="lab")
    rows = lab.get_results_by_batch(db, batch_id=batch_id, patient_id=patient_id)
    if rows is None:
        raise HTTPException(
            status_code=404,
            detail=f"Lab batch '{batch_id}' not found or does not belong to patient.",
        )
    return BatchLabResultListResponse(
        batch_id=batch_id,
        patient_id=patient_id,
        total=len(rows),
        items=[LabResultOut.model_validate(r) for r in rows],
    )


@router.get(
    "/patients/{patient_id}/lab-results",
    response_model=LabResultListResponse,
    summary="List structured lab results for a patient (newest first)",
)
def list_lab_results(
    patient_id: str,
    limit: int = Query(default=50, ge=1, le=100),
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
) -> LabResultListResponse:
    _require_patient_ownership(db, patient_id=patient_id, user=user)
    consent.require_access(db, patient_id=patient_id, requester_id=user.id, scope="lab")
    total, rows = lab.list_lab_results(db, patient_id=patient_id, limit=limit, offset=offset)
    return LabResultListResponse(
        patient_id=patient_id,
        total=total,
        items=[LabResultOut.model_validate(r) for r in rows],
    )


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
    if not is_enabled(FeatureFlag.OCR):
        raise HTTPException(status_code=503, detail="OCR feature is disabled.")
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
    if not is_enabled(FeatureFlag.OCR):
        raise HTTPException(status_code=503, detail="OCR feature is disabled.")
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


# ---------------------------------------------------------------------------
# Admin — reclassify / backfill
# ---------------------------------------------------------------------------

from pydantic import BaseModel as _BaseModel  # noqa: E402

class _ReclassifyRequest(_BaseModel):
    batch_id: str | None = None
    dry_run: bool = False

class _ReclassifyResponse(_BaseModel):
    updated: int
    skipped: int
    errors: list[str]


@router.post(
    "/admin/labs/reclassify",
    response_model=_ReclassifyResponse,
    summary="Admin: recompute status/severity for LabResult records",
)
def admin_reclassify_lab_results(
    body: _ReclassifyRequest,
    user: CurrentUser = Depends(
        require_roles(
            UserRole.INTERNAL_ADMIN,
            UserRole.SUPER_ADMIN,
        )
    ),
    db: Session = Depends(get_session),
) -> _ReclassifyResponse:
    """Admin-only: idempotent status backfill for LabResult rows.

    Safe to run multiple times. Use dry_run=true first to preview counts.
    """
    result = lab.reclassify_lab_results(db, batch_id=body.batch_id, dry_run=body.dry_run)
    return _ReclassifyResponse(**result)
