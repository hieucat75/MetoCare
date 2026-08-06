"""Lab-upload draft endpoint (OCR Lab Upload track §5).

``POST /api/v1/lab-uploads`` — accept an image/PDF file OR a pasted URL, run the
local OCR + parse pipeline, and return a **review-only draft** of canonical lab
values. NOTHING is persisted; the patient reviews/edits then confirms via the
existing manual-entry endpoint to write the canonical record.

Gated by ``FeatureFlag.OCR`` (503 when off) **and** by the patient's ``documents``
consent (403 CONSENT_DENIED when absent/revoked — PRIV-F4). Patient role only (+
platform admins); doctors/clinic-admins are excluded — they reach lab data through
the consent-gated read paths, not the patient upload surface.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import select as _select
from sqlalchemy.orm import Session

from app.ai.consent_policy import CATEGORY_DOCUMENTS, is_granted
from app.api.deps import CurrentUser, enforce_rate_limit, get_session, require_roles
from app.core.config import get_settings
from app.core.feature_flags import FeatureFlag, is_enabled
from app.core.ssrf import SSRFError, fetch_url
from app.models.patient import PatientProfile as _PatientProfile
from app.models.user import UserRole
from app.schemas.lab_upload import LabUploadDraftItemOut, LabUploadDraftOut
from app.services import audit, lab_upload
from app.services import ocr_case as ocr_case_svc
from app.services.consent_guard import ConsentDenied

logger = logging.getLogger("mcp.lab_upload_route")

router = APIRouter(tags=["lab"])


def _require_documents_consent(db: Session, user_id: str) -> None:
    """PRIV-F4: lab-document upload runs the same OCR pipeline as routes/documents.py,
    so it must honour the same fail-closed ``documents`` consent gate. Without this,
    revoking the patient-facing "Tài liệu y tế" toggle still allowed a medical
    document to be uploaded and OCR'd. Mirrors ``documents._require_documents_consent``.
    """
    if not is_granted(db, user_id, CATEGORY_DOCUMENTS):
        raise ConsentDenied(
            "Bạn cần bật quyền 'Tài liệu y tế' trong phần Quyền riêng tư để "
            "tải lên, xử lý hoặc xem tài liệu y tế."
        )


@router.post(
    "/lab-uploads",
    response_model=LabUploadDraftOut,
    summary="OCR a lab image/PDF/URL into a review-only draft (no save)",
)
async def create_lab_upload_draft(
    request: Request,
    file: UploadFile | None = File(default=None),
    url: str | None = Form(default=None),
    user: CurrentUser = Depends(
        require_roles(UserRole.PATIENT, UserRole.INTERNAL_ADMIN, UserRole.SUPER_ADMIN)
    ),
    db: Session = Depends(get_session),
) -> LabUploadDraftOut:
    # Throttle first: this drives a synchronous Tesseract OCR pass, so an
    # unbounded request rate is a CPU/cost DoS. Mirrors documents.py.
    enforce_rate_limit(request, "lab_upload")
    if not is_enabled(FeatureFlag.OCR):
        raise HTTPException(status_code=503, detail="Tính năng OCR đang tắt.")
    # PRIV-F4: fail-closed documents-consent gate, checked before any bytes are read.
    _require_documents_consent(db, user.id)

    has_file = file is not None and (file.filename or "").strip() != ""
    has_url = bool(url and url.strip())
    if has_file == has_url:  # both or neither
        raise HTTPException(
            status_code=400, detail="Cung cấp đúng một: tệp tải lên HOẶC đường link."
        )

    settings = get_settings()
    max_bytes = settings.ocr_max_upload_mb * 1024 * 1024

    if has_file:
        data = await file.read()
        declared = file.content_type
    else:
        try:
            fetched = fetch_url(
                url.strip(),
                max_bytes=max_bytes,
                timeout_seconds=settings.ocr_url_fetch_timeout_seconds,
            )
        except SSRFError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        data = fetched.content
        declared = fetched.content_type

    try:
        draft = lab_upload.process_bytes(data, declared_mime=declared)
    except lab_upload.LabUploadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    # Audit the draft creation WITHOUT any PHI — only a text hash + counts.
    audit.record(
        db,
        actor_type="user",
        actor_id=user.id,
        action="ocr_draft",
        resource_type="lab_upload",
        resource_id=draft.raw_text_sha256 or "none",
    )

    # Create OCRCase to track this OCR session (non-blocking; failure logs but never raises).
    # Resolve PatientProfile.id so OCRCase.patient_id matches the lab domain convention
    # (lab routes use PatientProfile.id, not User.id). Without this, confirm_case() would
    # fail the ownership check and never store the gap analysis.
    _patient_profile = (
        db.execute(_select(_PatientProfile).where(_PatientProfile.user_id == user.id))
        .scalars()
        .first()
    )
    ocr_patient_id = _patient_profile.id if _patient_profile is not None else None

    ocr_case_id: str | None = None
    if ocr_patient_id:
        try:
            extracted_rows = [
                {
                    "test_name": i.test_name,
                    "original_test_name": i.original_test_name,
                    "display_name_vi": i.display_name_vi,
                    "mapped_metric_type": i.canonical,
                    "value": i.value,
                    "unit": i.unit,
                }
                for i in draft.parsed_values
            ]
            case = ocr_case_svc.create_case(
                db,
                patient_id=ocr_patient_id,
                extracted_rows=extracted_rows,
                hospital_id=draft.hospital_id,
                hospital_confidence=draft.hospital_confidence,
                source_file_hash=draft.raw_text_sha256 or None,
                ocr_engine_version=draft.provider_used,
            )
            ocr_case_id = case.id
        except Exception:
            logger.exception("ocr_case_create_failed user=%s", user.id)
    else:
        logger.warning("ocr_case_skipped_no_profile user=%s", user.id)

    db.commit()

    return LabUploadDraftOut(
        provider_used=draft.provider_used,
        confidence_avg=draft.confidence_avg,
        parsed_values=[
            LabUploadDraftItemOut(
                test_name=i.test_name,
                canonical=i.canonical,
                value=i.value,
                unit=i.unit,
                reference_range=i.reference_range,
                status=i.status,
                confidence=i.confidence,
                needs_verification=i.needs_verification,
                confidence_reasons=i.confidence_reasons,
                original_value=i.original_value,
                original_unit=i.original_unit,
                original_test_name=i.original_test_name,
                display_name_vi=i.display_name_vi,
                canonical_value=i.canonical_value,
                canonical_unit=i.canonical_unit,
                display_reference_range=i.display_reference_range,
            )
            for i in draft.parsed_values
        ],
        warnings=draft.warnings,
        raw_text_sha256=draft.raw_text_sha256,
        low_confidence=draft.low_confidence,
        manual_fallback=draft.manual_fallback,
        extracted_test_date=draft.extracted_test_date,
        test_date_label=draft.test_date_label,
        test_date_confidence=draft.test_date_confidence,
        ocr_case_id=ocr_case_id,
        date_needs_confirmation=draft.date_needs_confirmation,
    )
