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
from app.models.clinical import LabDocument, LabResult
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
    LabResultCorrectionIn,
    LabResultEditIn,
    LabResultListResponse,
    LabResultOut,
    LabUploadBatchOut,
)
from app.services import consent, lab, lab_batch
from app.services import narrative_cache as nc
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

    try:
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
    except lab.LabValidationError as exc:
        # 422, not 500: the submission is well-formed but its unit cannot be
        # interpreted for that analyte. The accepted units are returned so the
        # client can offer them — telling a patient only to "fix the unit" is how
        # g/L gets retyped as g/dL with the number untouched.
        raise HTTPException(
            status_code=422,
            detail={
                "message": str(exc),
                "reason": exc.reason,
                "test_name": exc.test_name,
                "accepted_units": exc.accepted_units,
            },
        ) from exc
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
    total, items = lab_batch.list_batches(db, patient_id=patient_id, limit=limit, offset=offset)
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


# ---------------------------------------------------------------------------
# Phase 3: User correction of a lab result value
# ---------------------------------------------------------------------------

_CORRECTION_ROLES = (
    UserRole.PATIENT,
    UserRole.INTERNAL_ADMIN,
    UserRole.SUPER_ADMIN,
)


@router.patch(
    "/patients/{patient_id}/lab-results/{result_id}/correct",
    response_model=LabResultOut,
    summary="Correct a lab result value and re-classify",
)
def correct_lab_result(
    patient_id: str,
    result_id: str,
    payload: LabResultCorrectionIn,
    user: CurrentUser = Depends(require_roles(*_CORRECTION_ROLES)),
    db: Session = Depends(get_session),
) -> LabResultOut:
    """User-corrects value/unit of a saved LabResult.

    - Saves provenance in correction_history_json.
    - Re-runs normalize_and_classify() → updates normalized_value_si, status.
    - PATIENT role: own results only (enforced via consent.require_access).
    """
    _require_patient_ownership(db, patient_id=patient_id, user=user)
    try:
        row = lab.correct_lab_result(
            db,
            result_id=result_id,
            patient_id=patient_id,
            requester_id=user.id,
            new_value=payload.value,
            new_unit=payload.unit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return LabResultOut.model_validate(row)


@router.patch(
    "/patients/{patient_id}/lab-results/{result_id}",
    response_model=LabResultOut,
    summary="Partial-edit a lab result (metadata + value/unit)",
)
def edit_lab_result(
    patient_id: str,
    result_id: str,
    payload: LabResultEditIn,
    user: CurrentUser = Depends(
        require_roles(
            UserRole.PATIENT,
            UserRole.DOCTOR,
            UserRole.INTERNAL_ADMIN,
            UserRole.SUPER_ADMIN,
        )
    ),
    db: Session = Depends(get_session),
) -> LabResultOut:
    """Extended partial-update for a LabResult.

    Applies any provided fields.  When value or unit changes, re-runs
    normalize_and_classify() and updates status, normalized_value_si, etc.
    Preserves id, created_at, patient_id.
    """
    _require_patient_ownership(db, patient_id=patient_id, user=user)
    try:
        row = lab.edit_lab_result(
            db,
            result_id=result_id,
            patient_id=patient_id,
            requester_id=user.id,
            **payload.model_dump(exclude_none=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    nc.invalidate_patient(patient_id)
    return LabResultOut.model_validate(row)


_DELETE_LAB_RESULT_ROLES = (
    UserRole.PATIENT,
    UserRole.DOCTOR,
    UserRole.INTERNAL_ADMIN,
    UserRole.SUPER_ADMIN,
)


@router.delete(
    "/patients/{patient_id}/lab-results/{result_id}",
    status_code=204,
    summary="Soft-delete a single lab result",
)
def delete_lab_result(
    patient_id: str,
    result_id: str,
    user: CurrentUser = Depends(require_roles(*_DELETE_LAB_RESULT_ROLES)),
    db: Session = Depends(get_session),
) -> None:
    """Soft-delete a single LabResult (sets deleted_at / deleted_by, never hard-deletes).

    Ownership: PATIENT may only delete their own results.
    After deletion, invalidates the narrative cache for this patient.
    """
    _require_patient_ownership(db, patient_id=patient_id, user=user)
    try:
        lab.delete_lab_result(
            db,
            result_id=result_id,
            patient_id=patient_id,
            requester_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    nc.invalidate_patient(patient_id)


# ---------------------------------------------------------------------------
# Claude Sonnet Clinical Explanation Layer
# ---------------------------------------------------------------------------
# These endpoints generate patient-friendly Vietnamese explanations for
# pre-classified lab results.  Claude is ONLY called here; it never
# re-classifies, never overrides canonical status/severity.
# ---------------------------------------------------------------------------

from pydantic import BaseModel as _ExplainBase  # noqa: E402 (local alias avoids collision)

from app.services.clinical_explanation import generate_explanation  # noqa: E402
from app.services.explanation_cache import invalidate_cached_explanation  # noqa: E402


def _clean_reference_range(raw: str | None, display_unit: str) -> str:
    """Strip unit suffix from reference range string if it duplicates display_unit or is garbled.

    Only strips trailing tokens that look like measurement units (contain '/').
    Preserves qualitative references: "Âm tính", "Bình thường", "Negative", "< 200".

    Examples::

        "0.6–1.3 mg/dL"     → "0.6–1.3"
        "53–115 µmol/L"     → "53–115"
        "0.6–1.3 mg/dL mg/dL" → "0.6–1.3"
        "Âm tính"           → "Âm tính"  (preserved)
        "Bình thường"       → "Bình thường"  (preserved)
        "< 200"             → "< 200"
        "70–99"             → "70–99"
    """
    import re as _re  # noqa: PLC0415

    if not raw:
        return ""
    # Only strip trailing tokens that look like units (must contain '/')
    # Pattern: whitespace + token-with-slash (e.g. mg/dL, µmol/L, IU/L)
    # Allow multiple such tokens at end (e.g. "mg/dL pmol/L")
    cleaned = _re.sub(r'(\s+\S+/\S+)+\s*$', '', raw.strip())
    return cleaned.strip() or raw.strip()  # fallback to raw if result is empty

def _build_clinical_input(row: LabResult) -> dict:
    """Convert a LabResult ORM row into the clinical_input dict for the explanation layer.

    canonical_status is derived fresh from `resolve_lab_semantics` (never from
    `row.status`, which can be a stale stored classification). We map the
    resolver's status vocabulary to the explanation layer's canonical_status
    vocabulary.

    SINGLE SOURCE OF TRUTH:
    - ``normalized_value`` / ``normalized_unit`` → display values (original OCR value/unit)
      so what Claude says matches exactly what the patient sees on screen.
    - ``canonical_value_si`` / ``canonical_unit_si`` → SI-normalised values for
      status classification and risk scoring (NOT sent to Claude for narrative).
    - ``reference_range`` → cleaned string with no appended unit suffix.
    """
    # Map resolve_lab_semantics' status vocabulary → canonical_status understood
    # by the explanation layer. Output vocabulary preserved exactly (downstream
    # Claude-prompt code depends on it) even though the INPUT below is now
    # fresh-resolved via the single shared resolver, never guard-then-trust on
    # `row.status` — a stale stored column is exactly the #153/#154 hazard.
    STATUS_MAP: dict[str | None, str] = {
        "normal": "normal",
        "borderline": "borderline_high",  # existing engine uses "borderline"
        "high": "high",
        "low": "low",
        "critical": "critical",
        # defensive: treat unknown/None as unknown
    }
    from app.domain.lab_semantics import resolve_lab_semantics  # noqa: PLC0415

    try:
        semantics = resolve_lab_semantics(
            row.canonical_name,
            row.value,
            row.unit,
            printed_reference_text=row.original_reference_range or row.reference_range,
            printed_reference_unit=row.original_unit,
            normalized_value_si=row.normalized_value_si,
            normalized_unit_si=row.normalized_unit_si,
        )
    except Exception:  # noqa: BLE001 — must never crash, but must fail CLOSED
        # CLOSED, not open: falling back to whatever `row.status` says (which
        # could be a stale confident severity) is exactly the hazard this
        # resolver exists to remove.
        semantics = None
        _resolved_status = "unknown"
    else:
        _resolved_status = (
            semantics.status if semantics is not None else (row.status or "")
        )
    canonical_status = STATUS_MAP.get(_resolved_status, "unknown")

    # Severity heuristic from status (existing engine doesn't store separate severity)
    SEVERITY_MAP: dict[str, str] = {
        "normal": "none",
        "borderline_high": "moderate",
        "high": "moderate",
        "low": "moderate",
        "critical": "critical",
        "unknown": "unknown",
    }
    canonical_severity = SEVERITY_MAP.get(canonical_status, "moderate")
    # needs_review must force a review flag on its own — canonical_status alone
    # collapses "resolver explicitly couldn't classify this" and "resolver
    # confidently said normal" into the same non-critical bucket, which would
    # silently under-flag an unresolvable value (unconvertible unit, CBC
    # dimensional guard, or a caught resolver exception above).
    doctor_required = (
        canonical_status in ("critical", "critical_high", "critical_low", "unknown")
        or (semantics is not None and semantics.needs_review)
    )

    # Vietnamese display name: the single shared resolver's name when it covers
    # this analyte, falling back to the legacy `_display_vi` lookup for a
    # canonical_name resolve_lab_semantics doesn't recognise (non-lab/unknown).
    from app.domain.patient_insight import _display_vi  # noqa: PLC0415
    from app.utils.number_format import format_lab_value as _fmt  # noqa: PLC0415

    if semantics is not None and semantics.display_name:
        display_name = semantics.display_name
    elif row.canonical_name:
        display_name = _display_vi(row.canonical_name)
    else:
        display_name = row.test_name or "xét nghiệm"

    # --- Display value = what patient sees on screen (original OCR value/unit) ---
    # Falls back to normalized_value_si only when original is absent.
    display_value = (
        row.original_value if row.original_value is not None else row.normalized_value_si
    )
    display_unit = (
        (row.original_unit or "").strip()
        if row.original_unit
        else (row.normalized_unit_si or row.unit or "")
    )

    # Format to string — eliminates float artifacts (231.63330000000002 → "232")
    display_value_str = _fmt(display_value, display_unit) if display_value is not None else "—"

    # Clean reference range: strip embedded unit suffix to prevent double-unit display.
    ref_range = _clean_reference_range(row.reference_range, display_unit)

    return {
        "biomarker_name": row.canonical_name or row.test_name or "unknown",
        "biomarker_display_name": display_name,
        "normalized_value": display_value_str,      # formatted display string (no float artifact)
        "normalized_unit": display_unit,             # original OCR unit (what patient sees)
        "canonical_value_si": (
            round(row.normalized_value_si, 4) if row.normalized_value_si is not None else None
        ),
        "canonical_unit_si": row.normalized_unit_si or row.unit or "",
        "reference_range": ref_range,                # cleaned — no trailing unit suffix
        "canonical_status": canonical_status,
        "canonical_severity": canonical_severity,
        "canonical_priority": "urgent" if doctor_required else "routine",
        "doctor_review_required": doctor_required,
        "safety_flags": [],
    }


class _ExplanationOut(_ExplainBase):
    explanation: str
    why_it_matters: str = ""
    what_to_monitor: str = ""
    what_to_ask_doctor: str = ""
    next_step: str = ""
    source: str
    validated: bool


@router.get(
    "/patients/{patient_id}/lab-results/{result_id}/explanation",
    response_model=_ExplanationOut,
    summary="Patient-friendly AI explanation for a lab result",
)
def get_lab_result_explanation(
    patient_id: str,
    result_id: str,
    user: CurrentUser = Depends(
        require_roles(
            UserRole.PATIENT,
            UserRole.DOCTOR,
            UserRole.INTERNAL_ADMIN,
            UserRole.SUPER_ADMIN,
        )
    ),
    db: Session = Depends(get_session),
) -> _ExplanationOut:
    """Generate (or return cached) patient-friendly Vietnamese explanation.

    Claude receives ONLY pre-classified canonical data.
    Validator blocks any contradicting output → deterministic fallback.
    """
    _require_patient_ownership(db, patient_id=patient_id, user=user)

    row = db.execute(
        select(LabResult).where(
            LabResult.id == result_id,
            LabResult.patient_id == patient_id,
            LabResult.deleted_at.is_(None),
        )
    ).scalar_one_or_none()

    if row is None:
        raise HTTPException(status_code=404, detail="Lab result not found.")

    clinical_input = _build_clinical_input(row)
    result = generate_explanation(result_id, clinical_input)
    return _ExplanationOut(**result)


@router.post(
    "/admin/lab-results/{result_id}/explanation/regenerate",
    response_model=_ExplanationOut,
    summary="Admin/Doctor: invalidate cache and regenerate explanation",
)
def regenerate_lab_result_explanation(
    result_id: str,
    user: CurrentUser = Depends(
        require_roles(
            UserRole.DOCTOR,
            UserRole.INTERNAL_ADMIN,
            UserRole.SUPER_ADMIN,
        )
    ),
    db: Session = Depends(get_session),
) -> _ExplanationOut:
    """Invalidate cache and regenerate Claude explanation for a lab result.

    Restricted to DOCTOR, INTERNAL_ADMIN, SUPER_ADMIN.
    """
    from sqlalchemy import select as _select  # noqa: PLC0415

    row = db.execute(
        _select(LabResult).where(
            LabResult.id == result_id,
            LabResult.deleted_at.is_(None),
        )
    ).scalar_one_or_none()

    if row is None:
        raise HTTPException(status_code=404, detail="Lab result not found.")

    # Invalidate all cache entries for this result (by generating clinical_input
    # first to get the hash, then invalidating)
    clinical_input = _build_clinical_input(row)
    from app.services.claude_client import hash_clinical_input  # noqa: PLC0415

    input_hash = hash_clinical_input(clinical_input)
    invalidate_cached_explanation(result_id, input_hash)

    result = generate_explanation(result_id, clinical_input, use_cache=False)
    return _ExplanationOut(**result)
