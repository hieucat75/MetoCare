"""Lab-upload draft endpoint (OCR Lab Upload track §5).

``POST /api/v1/lab-uploads`` — accept an image/PDF file OR a pasted URL, run the
local OCR + parse pipeline, and return a **review-only draft** of canonical lab
values. NOTHING is persisted; the patient reviews/edits then confirms via the
existing manual-entry endpoint to write the canonical record.

Gated by ``FeatureFlag.OCR`` (503 when off). Patient role only (+ platform
admins); doctors/clinic-admins are excluded — they reach lab data through the
consent-gated read paths, not the patient upload surface.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_session, require_roles
from app.core.config import get_settings
from app.core.feature_flags import FeatureFlag, is_enabled
from app.core.ssrf import SSRFError, fetch_url
from app.models.user import UserRole
from app.schemas.lab_upload import LabUploadDraftItemOut, LabUploadDraftOut
from app.services import audit, lab_upload

logger = logging.getLogger("mcp.lab_upload_route")

router = APIRouter(tags=["lab"])


@router.post(
    "/lab-uploads",
    response_model=LabUploadDraftOut,
    summary="OCR a lab image/PDF/URL into a review-only draft (no save)",
)
async def create_lab_upload_draft(
    file: UploadFile | None = File(default=None),
    url: str | None = Form(default=None),
    user: CurrentUser = Depends(
        require_roles(UserRole.PATIENT, UserRole.INTERNAL_ADMIN, UserRole.SUPER_ADMIN)
    ),
    db: Session = Depends(get_session),
) -> LabUploadDraftOut:
    if not is_enabled(FeatureFlag.OCR):
        raise HTTPException(status_code=503, detail="Tính năng OCR đang tắt.")

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
            )
            for i in draft.parsed_values
        ],
        warnings=draft.warnings,
        raw_text_sha256=draft.raw_text_sha256,
        low_confidence=draft.low_confidence,
        manual_fallback=draft.manual_fallback,
    )
