"""Medical Document Intelligence API (Master Plan §2, BRD §C/§D/§E/§F).

Secure document ingestion (upload-session → finalize → accept), the one-to-many
candidate review lifecycle, and a token-verified blob endpoint for the local
Object Storage adapter. Patient-owned; every route is BOLA-checked against the
caller's ``PatientProfile.id`` and gated by ``FeatureFlag.OCR``.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, enforce_rate_limit, get_session, require_roles
from app.core.config import get_settings
from app.core.feature_flags import FeatureFlag, is_enabled
from app.fixtures import load_qa_prescription_fixture
from app.models.medical_document import (
    OBJECT_STATE_ACCEPTED,
    ExtractionCandidate,
    MedicalDocument,
)
from app.models.patient import PatientProfile
from app.models.user import UserRole
from app.schemas.medical_document import (
    CandidateListOut,
    CandidateOut,
    ConfirmIn,
    ConfirmResultOut,
    DocumentListOut,
    DocumentOut,
    ExtractionOut,
    MergeIn,
    PromotionOut,
    SignedFileOut,
    UploadSessionCreate,
    UploadSessionOut,
)
from app.services.mdi import promoter as promoter_registry
from app.services.mdi import service as mdi
from app.services.mdi.bootstrap import register_defaults
from app.services.storage import (
    BLOB_OP_GET,
    BLOB_OP_PUT,
    CONTAINER_ACCEPTED,
    CONTAINER_QUARANTINE,
    BlobTokenError,
    ObjectNotFound,
    container_of,
    derive_blob_secret,
    get_storage,
    verify_blob_token,
)

logger = logging.getLogger("mcp.documents")

router = APIRouter(tags=["documents"])

# Register the concrete prescription extractor + medication promoter at import
# (app-construction time). Tests may override via the registries' register_* seams.
register_defaults()

_MIME_BY_EXT = {"jpg": "image/jpeg", "png": "image/png", "pdf": "application/pdf"}


# ── shared helpers ───────────────────────────────────────────────────────────
def _require_flag() -> None:
    if not is_enabled(FeatureFlag.OCR):
        raise HTTPException(status_code=503, detail="Tính năng OCR đang tắt.")


def _resolve_patient_id(db: Session, user: CurrentUser) -> str:
    profile = db.execute(
        select(PatientProfile).where(PatientProfile.user_id == user.id)
    ).scalars().first()
    if profile is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ bệnh nhân.")
    return profile.id


def _doc_out(doc: MedicalDocument) -> DocumentOut:
    return DocumentOut(
        id=doc.id,
        doc_type=doc.doc_type,
        status=doc.status,
        object_state=doc.object_state,
        mime=doc.mime,
        size_bytes=doc.size_bytes,
        page_count=doc.page_count,
        classification_confidence=doc.classification_confidence,
        sha256=doc.sha256,
        scan_status=doc.scan_status,
        failure_reason=doc.failure_reason,
        superseded_by=doc.superseded_by,
        created_at=doc.created_at,
    )


def _cand_out(c: ExtractionCandidate) -> CandidateOut:
    return CandidateOut(
        id=c.id,
        document_id=c.document_id,
        candidate_type=c.candidate_type,
        ordinal=c.ordinal,
        fields=c.fields_json or {},
        field_confidence=c.field_confidence_json,
        status=c.status,
        dedupe_key=c.dedupe_key,
        reviewed_at=c.reviewed_at,
    )


def _map_mdi_error(exc: mdi.MdiError) -> HTTPException:
    if isinstance(exc, mdi.DocumentNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, mdi.DocumentAccessDenied):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, mdi.DuplicateDocument):
        return HTTPException(
            status_code=409,
            detail={"message": str(exc), "existing_id": exc.existing_id},
        )
    if isinstance(exc, mdi.UploadValidationError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, mdi.InvalidDocumentState):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


_PatientOnly = require_roles(UserRole.PATIENT)


# ── ingestion ────────────────────────────────────────────────────────────────
@router.post("/documents/upload-session", response_model=UploadSessionOut)
def create_upload_session(
    body: UploadSessionCreate,
    request: Request,
    user: CurrentUser = Depends(_PatientOnly),
    db: Session = Depends(get_session),
) -> UploadSessionOut:
    _require_flag()
    enforce_rate_limit(request, "document_upload")
    if body.declared_mime not in _MIME_BY_EXT.values():
        raise HTTPException(
            status_code=400, detail="Chỉ hỗ trợ ảnh JPG/PNG hoặc tệp PDF."
        )
    patient_id = _resolve_patient_id(db, user)
    session = mdi.create_upload_session(
        db,
        patient_id=patient_id,
        declared_mime=body.declared_mime,
        declared_sha256=body.declared_sha256,
        declared_size=body.declared_size,
        doc_type_hint=body.doc_type_hint,
    )
    db.commit()
    put = session.signed_put_url
    return UploadSessionOut(
        upload_id=session.document.id,
        signed_put_url=put.url,
        method=put.method,
        expires_at=put.expires_at,
        status=session.document.status,
    )


@router.post("/documents/qa-fixture", response_model=DocumentOut)
def create_qa_fixture_document(
    request: Request,
    user: CurrentUser = Depends(_PatientOnly),
    db: Session = Depends(get_session),
) -> DocumentOut:
    """QA-only: ingest a bundled synthetic document through the real pipeline.

    Dev/staging automation aid so Journey A (document OCR) is testable without the
    native camera. Returns 404 unless ``settings.qa_fixture_enabled`` — which the
    startup guard forbids in production — so this endpoint is unreachable in prod.
    The response ``id`` is the new ``needs_review`` document for the review screen.
    """
    if not get_settings().qa_fixture_enabled:
        raise HTTPException(status_code=404, detail="Not Found")
    _require_flag()
    enforce_rate_limit(request, "document_upload")
    patient_id = _resolve_patient_id(db, user)
    fixture = load_qa_prescription_fixture()
    try:
        doc = mdi.ingest_qa_fixture(db, patient_id=patient_id, fixture=fixture)
    except mdi.MdiError as exc:
        db.commit()  # persist any rejection/hold state before surfacing the error
        raise _map_mdi_error(exc) from exc
    db.commit()
    return _doc_out(doc)


@router.post("/documents/{upload_id}/finalize", response_model=DocumentOut)
def finalize_upload(
    upload_id: str,
    request: Request,
    user: CurrentUser = Depends(_PatientOnly),
    db: Session = Depends(get_session),
) -> DocumentOut:
    _require_flag()
    enforce_rate_limit(request, "document_finalize")
    patient_id = _resolve_patient_id(db, user)
    try:
        doc = mdi.finalize_upload(db, patient_id=patient_id, document_id=upload_id)
    except mdi.MdiError as exc:
        db.commit()  # persist a rejection/hold state change before surfacing the error
        raise _map_mdi_error(exc) from exc
    try:
        db.commit()
    except IntegrityError as exc:
        # Concurrent finalize of the same (patient, sha256) lost the race against
        # the partial-unique accepted index — treat as a duplicate, not a 500.
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Tài liệu này đã được tải lên trước đó."
        ) from exc
    # Post-commit best-effort sweep of the now-redundant quarantine object. Done
    # AFTER commit so a commit failure never strands the document (finalize stays
    # retryable from quarantine); a stray quarantine blob is caught by the TTL sweep.
    if doc.object_state == OBJECT_STATE_ACCEPTED:
        try:
            get_storage().delete(doc.quarantine_key)
        except Exception:  # noqa: BLE001 — cleanup is best-effort
            pass
    return _doc_out(doc)


# ── blob transport (local adapter; token IS the authz, like an Azure SAS) ────
@router.put("/documents/blob/{token}")
async def blob_put(token: str, request: Request) -> Response:
    settings = get_settings()
    try:
        bt = verify_blob_token(derive_blob_secret(settings.secret_key), token)
    except BlobTokenError as exc:
        raise HTTPException(status_code=403, detail="Liên kết tải lên không hợp lệ.") from exc
    if bt.op != BLOB_OP_PUT or container_of(bt.key) != CONTAINER_QUARANTINE:
        raise HTTPException(status_code=403, detail="Thao tác không được phép.")
    body = await request.body()
    max_bytes = settings.ocr_max_upload_mb * 1024 * 1024
    if len(body) > max_bytes:
        raise HTTPException(status_code=413, detail="Tệp quá lớn.")
    storage = get_storage()
    # Write-once: a quarantine key may be uploaded exactly once. Blocks a re-PUT
    # from swapping bytes after they've been read/validated by finalize (§1.7).
    if storage.exists(bt.key):
        raise HTTPException(status_code=409, detail="Tệp đã được tải lên.")
    storage.put_bytes(bt.key, body)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/documents/blob/{token}")
def blob_get(token: str) -> Response:
    settings = get_settings()
    try:
        bt = verify_blob_token(derive_blob_secret(settings.secret_key), token)
    except BlobTokenError as exc:
        raise HTTPException(status_code=403, detail="Liên kết không hợp lệ.") from exc
    if bt.op != BLOB_OP_GET or container_of(bt.key) != CONTAINER_ACCEPTED:
        # Symmetric with blob_put's quarantine-only guard: reads are only ever
        # served from accepted objects, never from unscanned quarantine (§1.7).
        raise HTTPException(status_code=403, detail="Thao tác không được phép.")
    try:
        data = get_storage().get_bytes(bt.key)
    except ObjectNotFound as exc:
        raise HTTPException(status_code=404, detail="Không tìm thấy tệp.") from exc
    ext = bt.key.rsplit(".", 1)[-1].lower()
    return Response(content=data, media_type=_MIME_BY_EXT.get(ext, "application/octet-stream"))


# ── reads ────────────────────────────────────────────────────────────────────
@router.get("/documents", response_model=DocumentListOut)
def list_documents(
    user: CurrentUser = Depends(_PatientOnly),
    db: Session = Depends(get_session),
) -> DocumentListOut:
    _require_flag()
    patient_id = _resolve_patient_id(db, user)
    docs = mdi.list_documents(db, patient_id=patient_id)
    return DocumentListOut(
        patient_id=patient_id, total=len(docs), items=[_doc_out(d) for d in docs]
    )


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: str,
    user: CurrentUser = Depends(_PatientOnly),
    db: Session = Depends(get_session),
) -> DocumentOut:
    _require_flag()
    patient_id = _resolve_patient_id(db, user)
    try:
        return _doc_out(mdi.get_document(db, patient_id=patient_id, document_id=document_id))
    except mdi.MdiError as exc:
        raise _map_mdi_error(exc) from exc


@router.get("/documents/{document_id}/file", response_model=SignedFileOut)
def get_document_file(
    document_id: str,
    user: CurrentUser = Depends(_PatientOnly),
    db: Session = Depends(get_session),
) -> SignedFileOut:
    """Issue a per-request, authorized, short-lived signed READ url (§1.7.5)."""
    _require_flag()
    patient_id = _resolve_patient_id(db, user)
    try:
        doc = mdi.get_document(db, patient_id=patient_id, document_id=document_id)
    except mdi.MdiError as exc:
        raise _map_mdi_error(exc) from exc
    key = doc.accepted_key
    if not key:
        raise HTTPException(status_code=409, detail="Tài liệu chưa sẵn sàng để xem.")
    settings = get_settings()
    signed = get_storage().signed_get_url(
        key, expires_in=settings.storage_download_url_ttl_seconds
    )
    return SignedFileOut(url=signed.url, method=signed.method, expires_at=signed.expires_at)


@router.get("/documents/{document_id}/extraction", response_model=ExtractionOut)
def get_extraction(
    document_id: str,
    user: CurrentUser = Depends(_PatientOnly),
    db: Session = Depends(get_session),
) -> ExtractionOut:
    _require_flag()
    patient_id = _resolve_patient_id(db, user)
    try:
        extraction = mdi.latest_extraction(db, patient_id=patient_id, document_id=document_id)
    except mdi.MdiError as exc:
        raise _map_mdi_error(exc) from exc
    if extraction is None:
        raise HTTPException(status_code=404, detail="Chưa có kết quả trích xuất.")
    return ExtractionOut(
        id=extraction.id,
        document_id=extraction.document_id,
        schema_version=extraction.schema_version,
        provider=extraction.provider,
        model=extraction.model,
        extraction_run_id=extraction.extraction_run_id,
        review_state=extraction.review_state,
        created_at=extraction.created_at,
    )


@router.get("/documents/{document_id}/candidates", response_model=CandidateListOut)
def list_candidates(
    document_id: str,
    user: CurrentUser = Depends(_PatientOnly),
    db: Session = Depends(get_session),
) -> CandidateListOut:
    _require_flag()
    patient_id = _resolve_patient_id(db, user)
    try:
        cands = mdi.list_candidates(db, patient_id=patient_id, document_id=document_id)
    except mdi.MdiError as exc:
        raise _map_mdi_error(exc) from exc
    return CandidateListOut(
        document_id=document_id, total=len(cands), items=[_cand_out(c) for c in cands]
    )


# ── review actions ───────────────────────────────────────────────────────────
def _confirm_result(candidate: ExtractionCandidate, link) -> ConfirmResultOut:
    return ConfirmResultOut(
        candidate=_cand_out(candidate),
        promotion=PromotionOut(
            candidate_id=link.candidate_id,
            canonical_type=link.canonical_type,
            canonical_id=link.canonical_id,
            action=link.action,
        ),
    )


@router.post("/candidates/{candidate_id}/confirm", response_model=ConfirmResultOut)
def confirm_candidate(
    candidate_id: str,
    body: ConfirmIn,
    request: Request,
    user: CurrentUser = Depends(_PatientOnly),
    db: Session = Depends(get_session),
) -> ConfirmResultOut:
    _require_flag()
    enforce_rate_limit(request, "document_review")
    patient_id = _resolve_patient_id(db, user)
    try:
        candidate, link = mdi.confirm_candidate(
            db,
            patient_id=patient_id,
            candidate_id=candidate_id,
            actor_user_id=user.id,
            corrections=body.corrections,
        )
    except promoter_registry.PromotionUnavailable as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except promoter_registry.PromotionDenied as exc:
        db.rollback()
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except promoter_registry.PromotionInvalid as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Mục này đã được xác nhận trước đó.") from exc
    except mdi.MdiError as exc:
        db.rollback()
        raise _map_mdi_error(exc) from exc
    db.commit()
    return _confirm_result(candidate, link)


@router.post("/candidates/{candidate_id}/merge", response_model=ConfirmResultOut)
def merge_candidate(
    candidate_id: str,
    body: MergeIn,
    request: Request,
    user: CurrentUser = Depends(_PatientOnly),
    db: Session = Depends(get_session),
) -> ConfirmResultOut:
    _require_flag()
    enforce_rate_limit(request, "document_review")
    patient_id = _resolve_patient_id(db, user)
    try:
        candidate, link = mdi.merge_candidate(
            db,
            patient_id=patient_id,
            candidate_id=candidate_id,
            actor_user_id=user.id,
            merge_target_id=body.merge_target_id,
            corrections=body.corrections,
        )
    except promoter_registry.PromotionUnavailable as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except promoter_registry.PromotionDenied as exc:
        db.rollback()
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except promoter_registry.PromotionInvalid as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Mục này đã được xác nhận trước đó.") from exc
    except mdi.MdiError as exc:
        db.rollback()
        raise _map_mdi_error(exc) from exc
    db.commit()
    return _confirm_result(candidate, link)


@router.post("/candidates/{candidate_id}/reject", response_model=CandidateOut)
def reject_candidate(
    candidate_id: str,
    request: Request,
    user: CurrentUser = Depends(_PatientOnly),
    db: Session = Depends(get_session),
) -> CandidateOut:
    _require_flag()
    enforce_rate_limit(request, "document_review")
    patient_id = _resolve_patient_id(db, user)
    try:
        candidate = mdi.reject_candidate(
            db, patient_id=patient_id, candidate_id=candidate_id, actor_user_id=user.id
        )
    except mdi.MdiError as exc:
        db.rollback()
        raise _map_mdi_error(exc) from exc
    db.commit()
    return _cand_out(candidate)


@router.post("/documents/{document_id}/reprocess", response_model=ExtractionOut)
def reprocess_document(
    document_id: str,
    request: Request,
    user: CurrentUser = Depends(_PatientOnly),
    db: Session = Depends(get_session),
) -> ExtractionOut:
    _require_flag()
    enforce_rate_limit(request, "document_reprocess")
    patient_id = _resolve_patient_id(db, user)
    try:
        extraction = mdi.reprocess_document(db, patient_id=patient_id, document_id=document_id)
    except mdi.MdiError as exc:
        db.rollback()
        raise _map_mdi_error(exc) from exc
    db.commit()
    return ExtractionOut(
        id=extraction.id,
        document_id=extraction.document_id,
        schema_version=extraction.schema_version,
        provider=extraction.provider,
        model=extraction.model,
        extraction_run_id=extraction.extraction_run_id,
        review_state=extraction.review_state,
        created_at=extraction.created_at,
    )
