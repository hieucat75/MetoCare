"""MDI service — secure ingestion (§1.7), staged extraction (§1.4), and the
one-to-many candidate lifecycle + promotion (§1.5).

All functions are patient-scoped: the caller passes the resolved
``PatientProfile.id`` and the service treats it as the ownership boundary. Route-
layer BOLA (does this User own this PatientProfile?) is enforced separately.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.medical_document import (
    CAND_STATUS_CONFIRMED,
    CAND_STATUS_EXTRACTED,
    CAND_STATUS_MERGED,
    CAND_STATUS_NEEDS_REVIEW,
    CAND_STATUS_REJECTED,
    CAND_STATUS_SUPERSEDED,
    DOC_STATUS_CONFIRMED,
    DOC_STATUS_FAILED,
    DOC_STATUS_NEEDS_REVIEW,
    DOC_STATUS_PARTIALLY_CONFIRMED,
    DOC_STATUS_PROCESSING,
    DOC_STATUS_REJECTED,
    DOC_STATUS_UPLOADED,
    OBJECT_STATE_ACCEPTED,
    OBJECT_STATE_QUARANTINED,
    OBJECT_STATE_REJECTED,
    DocumentExtraction,
    DocumentPage,
    ExtractionCandidate,
    MedicalDocument,
    PromotionLink,
)
from app.services import audit
from app.services.lab_upload import (
    LabUploadError,
    PayloadTooLargeError,
    UnsupportedMediaError,
    validate_upload,
)
from app.services.storage import (
    CONTAINER_ACCEPTED,
    CONTAINER_QUARANTINE,
    ObjectNotFound,
    SignedUrl,
    build_object_key,
    ext_for_mime,
    get_storage,
)

from . import promoter as promoter_registry
from .pipeline import SCHEMA_VERSION, run_pipeline


class MdiError(Exception):
    """Base MDI service error."""


class DocumentNotFound(MdiError):
    pass


class DocumentAccessDenied(MdiError):
    pass


class DuplicateDocument(MdiError):
    def __init__(self, existing_id: str) -> None:
        super().__init__("Tài liệu này đã được tải lên trước đó.")
        self.existing_id = existing_id


class InvalidDocumentState(MdiError):
    pass


class UploadValidationError(MdiError):
    """Wraps finalize validation failures (bad hash/size/mime/scan)."""


@dataclass(frozen=True)
class UploadSession:
    document: MedicalDocument
    signed_put_url: SignedUrl


# ── ingestion ──────────────────────────────────────────────────────────────
def create_upload_session(
    db: Session,
    *,
    patient_id: str,
    declared_mime: str,
    declared_sha256: str | None = None,
    declared_size: int | None = None,
    doc_type_hint: str | None = None,
) -> UploadSession:
    """Create a document row + a write-only signed URL to a quarantine key (§1.7.1)."""
    settings = get_settings()
    ext = ext_for_mime(declared_mime)
    quarantine_key = build_object_key(
        container=CONTAINER_QUARANTINE, patient_id=patient_id, ext=ext
    )
    doc = MedicalDocument(
        patient_id=patient_id,
        quarantine_key=quarantine_key,
        mime=declared_mime,
        sha256=declared_sha256,
        size_bytes=declared_size,
        doc_type=doc_type_hint,
        status=DOC_STATUS_UPLOADED,
        object_state=OBJECT_STATE_QUARANTINED,
        scan_status="pending",
    )
    db.add(doc)
    db.flush()
    signed = get_storage().signed_put_url(
        quarantine_key, expires_in=settings.storage_upload_url_ttl_seconds
    )
    audit.record(
        db,
        actor_type="patient",
        actor_id=patient_id,
        action="document.upload_session",
        resource_type="medical_document",
        resource_id=doc.id,
    )
    return UploadSession(document=doc, signed_put_url=signed)


def finalize_upload(
    db: Session, *, patient_id: str, document_id: str, doc_type_hint: str | None = None
) -> MedicalDocument:
    """Validate + scan + accept the quarantined object, then extract (§1.7.3–.4)."""
    doc = _load_owned(db, patient_id=patient_id, document_id=document_id)
    if doc.object_state != OBJECT_STATE_QUARANTINED or doc.accepted_key:
        raise InvalidDocumentState("Tài liệu đã được xử lý.")

    storage = get_storage()
    try:
        data = storage.get_bytes(doc.quarantine_key)
    except ObjectNotFound as exc:
        raise UploadValidationError("Chưa nhận được tệp tải lên.") from exc

    # ── validate: magic-byte MIME + size (reuse lab_upload) ──────────────────
    try:
        sniffed_mime = validate_upload(data)
    except (UnsupportedMediaError, PayloadTooLargeError, LabUploadError) as exc:
        _reject(db, doc, reason=str(exc))
        raise UploadValidationError(str(exc)) from exc

    # ── validate: declared sha256 / size integrity ───────────────────────────
    actual_sha = hashlib.sha256(data).hexdigest()
    if doc.sha256 and doc.sha256 != actual_sha:
        _reject(db, doc, reason="sha256_mismatch")
        raise UploadValidationError("Tệp không toàn vẹn (sai mã băm).")
    if doc.size_bytes is not None and doc.size_bytes != len(data):
        _reject(db, doc, reason="size_mismatch")
        raise UploadValidationError("Kích thước tệp không khớp.")
    doc.sha256 = actual_sha
    doc.size_bytes = len(data)
    doc.mime = sniffed_mime

    # ── page limits ──────────────────────────────────────────────────────────
    page_count = _count_pages(data, sniffed_mime)
    settings = get_settings()
    if page_count is not None and page_count > settings.document_max_pages:
        _reject(db, doc, reason="too_many_pages")
        raise UploadValidationError(
            f"Tài liệu vượt quá {settings.document_max_pages} trang."
        )
    doc.page_count = page_count or 1

    # ── duplicate detection (BOLA-safe: within this patient only) ────────────
    dup = db.execute(
        select(MedicalDocument).where(
            MedicalDocument.patient_id == patient_id,
            MedicalDocument.sha256 == actual_sha,
            MedicalDocument.id != doc.id,
            MedicalDocument.object_state == OBJECT_STATE_ACCEPTED,
            MedicalDocument.deleted_at.is_(None),
        )
    ).scalars().first()
    if dup is not None:
        _reject(db, doc, reason="duplicate")
        raise DuplicateDocument(existing_id=dup.id)

    # ── scan posture (§1.7.3) — always an EXPLICIT decision, never silent ─────
    mode = (settings.document_scan_mode or "skip").lower()
    if mode == "hold":
        doc.scan_status = "pending"
        # Object-storage state stays quarantined; never handed to a worker.
        audit.record(
            db,
            actor_type="patient",
            actor_id=patient_id,
            action="document.quarantine_hold",
            resource_type="medical_document",
            resource_id=doc.id,
        )
        return doc
    if mode == "clamav":
        # Real ClamAV wiring is DIST-RC; without a scanner we must NOT accept.
        doc.scan_status = "pending"
        audit.record(
            db,
            actor_type="patient",
            actor_id=patient_id,
            action="document.quarantine_hold",
            resource_type="medical_document",
            resource_id=doc.id,
        )
        return doc
    doc.scan_status = "skipped"  # mode == "skip": explicit, audited no-AV accept

    # ── accept: write the VALIDATED in-memory bytes to a fresh accepted key ───
    # We copy `data` (already hash/MIME/size-validated) rather than moving the
    # quarantine object: (1) the accepted object is guaranteed to be exactly the
    # validated bytes even if a client re-PUT the quarantine key after we read it
    # (TOCTOU-safe); (2) the quarantine object survives, so a mid-pipeline failure
    # rolls back cleanly and finalize stays retryable — never a stranded document.
    # The quarantine object is swept post-commit by the route (and by TTL).
    accepted_key = build_object_key(
        container=CONTAINER_ACCEPTED, patient_id=patient_id, ext=ext_for_mime(sniffed_mime)
    )
    storage.put_bytes(accepted_key, data)
    doc.accepted_key = accepted_key
    doc.object_state = OBJECT_STATE_ACCEPTED
    doc.status = DOC_STATUS_PROCESSING
    audit.record(
        db,
        actor_type="patient",
        actor_id=patient_id,
        action="document.accepted",
        resource_type="medical_document",
        resource_id=doc.id,
    )

    # ── extract (workers process accepted objects only) ──────────────────────
    _run_extraction(db, doc=doc, data=data, doc_type_hint=doc_type_hint or doc.doc_type)
    return doc


def _run_extraction(
    db: Session, *, doc: MedicalDocument, data: bytes, doc_type_hint: str | None
) -> DocumentExtraction:
    """Run the staged pipeline and persist extraction + pages + candidates (§1.5)."""
    result = run_pipeline(
        page_bytes=[data],
        mime=doc.mime or "application/octet-stream",
        doc_type_hint=doc_type_hint,
    )
    doc.doc_type = result.doc_type
    doc.classification_confidence = result.classification_confidence

    extraction = DocumentExtraction(
        document_id=doc.id,
        schema_version=SCHEMA_VERSION,
        provider=result.provider,
        model=result.model,
        extraction_run_id=str(uuid.uuid4()),
        review_state="pending",
    )
    db.add(extraction)
    db.flush()

    # Pages belong to the physical document, not the extraction run — a reprocess
    # re-reads the same bytes, so only materialize pages on the first extraction.
    has_pages = db.execute(
        select(DocumentPage.id).where(DocumentPage.document_id == doc.id).limit(1)
    ).scalars().first()
    if has_pages is None:
        for page in result.pages:
            db.add(
                DocumentPage(
                    document_id=doc.id,
                    page_no=page.page_no,
                    storage_key=doc.accepted_key,
                    ocr_raw=page.ocr_raw,
                    blocks_json=page.blocks,
                )
            )

    # Carry-forward guard (§1.5): never re-create a candidate whose logical item
    # already has a LIVE candidate (confirmed/merged OR still under review) in a
    # prior extraction of THIS document. Confirmed items are thus never re-promoted,
    # and reprocessing never duplicates an unresolved candidate — only genuinely new
    # items enter needs_review.
    existing_keys = _live_dedupe_keys(db, document_id=doc.id)
    seen_this_run: set[str] = set()  # in-batch dedupe: a repeated OCR line must
    # not create two rows with the same dedupe_key (would violate
    # uq_extraction_dedupe_key and abort the whole finalize).
    created = 0
    for draft in result.candidates:
        if draft.dedupe_key in existing_keys or draft.dedupe_key in seen_this_run:
            continue
        seen_this_run.add(draft.dedupe_key)
        db.add(
            ExtractionCandidate(
                extraction_id=extraction.id,
                document_id=doc.id,
                patient_id=doc.patient_id,
                candidate_type=draft.candidate_type,
                ordinal=draft.ordinal,
                fields_json=draft.fields,
                field_confidence_json=draft.field_confidence,
                dedupe_key=draft.dedupe_key,
                status=CAND_STATUS_NEEDS_REVIEW,
            )
        )
        created += 1

    db.flush()
    doc.status = DOC_STATUS_NEEDS_REVIEW if created else _recompute_doc_status(db, doc)
    return extraction


# ── candidate lifecycle ─────────────────────────────────────────────────────
def list_documents(db: Session, *, patient_id: str) -> list[MedicalDocument]:
    return list(
        db.execute(
            select(MedicalDocument)
            .where(
                MedicalDocument.patient_id == patient_id,
                MedicalDocument.deleted_at.is_(None),
            )
            .order_by(MedicalDocument.created_at.desc())
        ).scalars()
    )


def get_document(db: Session, *, patient_id: str, document_id: str) -> MedicalDocument:
    return _load_owned(db, patient_id=patient_id, document_id=document_id)


def list_candidates(
    db: Session, *, patient_id: str, document_id: str
) -> list[ExtractionCandidate]:
    _load_owned(db, patient_id=patient_id, document_id=document_id)
    return list(
        db.execute(
            select(ExtractionCandidate)
            .where(
                ExtractionCandidate.document_id == document_id,
                ExtractionCandidate.patient_id == patient_id,
            )
            .order_by(ExtractionCandidate.ordinal)
        ).scalars()
    )


def latest_extraction(
    db: Session, *, patient_id: str, document_id: str
) -> DocumentExtraction | None:
    _load_owned(db, patient_id=patient_id, document_id=document_id)
    return db.execute(
        select(DocumentExtraction)
        .where(DocumentExtraction.document_id == document_id)
        .order_by(DocumentExtraction.created_at.desc())
    ).scalars().first()


def confirm_candidate(
    db: Session,
    *,
    patient_id: str,
    candidate_id: str,
    actor_user_id: str,
    corrections: dict | None = None,
) -> tuple[ExtractionCandidate, PromotionLink]:
    """Confirm → promote a candidate into a canonical record (§1.5)."""
    candidate = _load_owned_candidate(
        db, patient_id=patient_id, candidate_id=candidate_id, for_update=True
    )
    _assert_reviewable(candidate)
    _apply_corrections(candidate, corrections)

    promoter = promoter_registry.get_promoter(candidate.candidate_type)
    outcome = promoter.promote(db, candidate, actor_user_id=actor_user_id)
    link = _record_promotion(db, candidate, outcome, actor_user_id)

    candidate.status = (
        CAND_STATUS_MERGED
        if outcome.action == promoter_registry.ACTION_MERGED_INTO
        else CAND_STATUS_CONFIRMED
    )
    candidate.reviewed_by = actor_user_id
    _stamp_reviewed(candidate)
    _post_review(db, candidate, actor_user_id, action="document.candidate_confirm")
    return candidate, link


def merge_candidate(
    db: Session,
    *,
    patient_id: str,
    candidate_id: str,
    actor_user_id: str,
    merge_target_id: str,
    corrections: dict | None = None,
) -> tuple[ExtractionCandidate, PromotionLink]:
    """Confirm a candidate by merging into an existing canonical record (§1.5)."""
    candidate = _load_owned_candidate(
        db, patient_id=patient_id, candidate_id=candidate_id, for_update=True
    )
    _assert_reviewable(candidate)
    _apply_corrections(candidate, corrections)

    promoter = promoter_registry.get_promoter(candidate.candidate_type)
    outcome = promoter.promote(
        db, candidate, actor_user_id=actor_user_id, merge_target_id=merge_target_id
    )
    link = _record_promotion(db, candidate, outcome, actor_user_id)
    candidate.status = CAND_STATUS_MERGED
    candidate.reviewed_by = actor_user_id
    _stamp_reviewed(candidate)
    _post_review(db, candidate, actor_user_id, action="document.candidate_merge")
    return candidate, link


def reject_candidate(
    db: Session, *, patient_id: str, candidate_id: str, actor_user_id: str
) -> ExtractionCandidate:
    candidate = _load_owned_candidate(
        db, patient_id=patient_id, candidate_id=candidate_id, for_update=True
    )
    _assert_reviewable(candidate)
    candidate.status = CAND_STATUS_REJECTED
    candidate.reviewed_by = actor_user_id
    _stamp_reviewed(candidate)
    _post_review(db, candidate, actor_user_id, action="document.candidate_reject")
    return candidate


def reprocess_document(
    db: Session, *, patient_id: str, document_id: str
) -> DocumentExtraction:
    """Re-run extraction: new DocumentExtraction, confirmed items carried forward,
    only genuinely new candidates enter needs_review — never a double promotion (§1.5)."""
    doc = _load_owned(db, patient_id=patient_id, document_id=document_id)
    if doc.object_state != OBJECT_STATE_ACCEPTED or not doc.accepted_key:
        raise InvalidDocumentState("Chỉ có thể xử lý lại tài liệu đã được chấp nhận.")
    data = get_storage().get_bytes(doc.accepted_key)
    return _run_extraction(db, doc=doc, data=data, doc_type_hint=doc.doc_type)


# ── helpers ─────────────────────────────────────────────────────────────────
def _load_owned(db: Session, *, patient_id: str, document_id: str) -> MedicalDocument:
    doc = db.get(MedicalDocument, document_id)
    if doc is None or doc.deleted_at is not None:
        raise DocumentNotFound("Không tìm thấy tài liệu.")
    if doc.patient_id != patient_id:
        raise DocumentAccessDenied("Không có quyền truy cập tài liệu này.")
    return doc


def _load_owned_candidate(
    db: Session, *, patient_id: str, candidate_id: str, for_update: bool = False
) -> ExtractionCandidate:
    if for_update:
        # Row-lock the candidate for the confirm/merge/reject transition so two
        # concurrent reviews can't both pass _assert_reviewable and race (a reject
        # silently overwriting a confirm, or vice-versa). No-op on SQLite (which
        # serializes writers anyway); real SELECT … FOR UPDATE on PostgreSQL.
        candidate = db.execute(
            select(ExtractionCandidate)
            .where(ExtractionCandidate.id == candidate_id)
            .with_for_update()
        ).scalars().first()
    else:
        candidate = db.get(ExtractionCandidate, candidate_id)
    if candidate is None:
        raise DocumentNotFound("Không tìm thấy mục trích xuất.")
    if candidate.patient_id != patient_id:
        raise DocumentAccessDenied("Không có quyền truy cập mục này.")
    return candidate


def _assert_reviewable(candidate: ExtractionCandidate) -> None:
    if candidate.status not in (CAND_STATUS_EXTRACTED, CAND_STATUS_NEEDS_REVIEW):
        raise InvalidDocumentState(
            f"Mục đã ở trạng thái '{candidate.status}', không thể thao tác lại."
        )


def _apply_corrections(candidate: ExtractionCandidate, corrections: dict | None) -> None:
    if not corrections:
        return
    # Append to correction history (immutable raw stays in the extraction).
    history = (
        list(candidate.corrections_json)
        if isinstance(candidate.corrections_json, list)
        else []
    )
    history.append({"fields": dict(candidate.fields_json or {}), "corrections": corrections})
    candidate.corrections_json = history
    merged = dict(candidate.fields_json or {})
    merged.update(corrections)
    candidate.fields_json = merged


def _record_promotion(
    db: Session, candidate: ExtractionCandidate, outcome, actor_user_id: str
) -> PromotionLink:
    link = PromotionLink(
        candidate_id=candidate.id,
        canonical_type=outcome.canonical_type,
        canonical_id=outcome.canonical_id,
        action=outcome.action,
        promoted_by=actor_user_id,
    )
    db.add(link)
    db.flush()  # surfaces uq_promotion_candidate_once immediately
    return link


def _stamp_reviewed(candidate: ExtractionCandidate) -> None:
    from datetime import datetime

    candidate.reviewed_at = datetime.now(UTC)


def _post_review(
    db: Session, candidate: ExtractionCandidate, actor_user_id: str, *, action: str
) -> None:
    # autoflush is off (SessionLocal) — flush the candidate's new status so the
    # recompute query below sees it.
    db.flush()
    doc = db.get(MedicalDocument, candidate.document_id)
    if doc is not None:
        doc.status = _recompute_doc_status(db, doc)
    audit.record(
        db,
        actor_type="patient",
        actor_id=actor_user_id,
        action=action,
        resource_type="extraction_candidate",
        resource_id=candidate.id,
    )


def _recompute_doc_status(db: Session, doc: MedicalDocument) -> str:
    rows = list(
        db.execute(
            select(ExtractionCandidate.status).where(
                ExtractionCandidate.document_id == doc.id
            )
        ).scalars()
    )
    if not rows:
        return doc.status
    open_states = {CAND_STATUS_EXTRACTED, CAND_STATUS_NEEDS_REVIEW}
    promoted = {CAND_STATUS_CONFIRMED, CAND_STATUS_MERGED}
    has_open = any(s in open_states for s in rows)
    has_promoted = any(s in promoted for s in rows)
    if has_open:
        # some resolved (confirmed/merged/rejected) + some still open → partial
        resolved_any = has_promoted or any(s == CAND_STATUS_REJECTED for s in rows)
        return DOC_STATUS_PARTIALLY_CONFIRMED if resolved_any else DOC_STATUS_NEEDS_REVIEW
    # nothing open: confirmed only if ≥1 was promoted; all-rejected → rejected.
    return DOC_STATUS_CONFIRMED if has_promoted else DOC_STATUS_REJECTED


def _live_dedupe_keys(db: Session, *, document_id: str) -> set[str]:
    """Dedupe keys of candidates that are NOT rejected/superseded — i.e. still
    live (confirmed, merged, or under review). Reprocessing skips these."""
    rows = db.execute(
        select(ExtractionCandidate.dedupe_key).where(
            ExtractionCandidate.document_id == document_id,
            ExtractionCandidate.status.notin_(
                (CAND_STATUS_REJECTED, CAND_STATUS_SUPERSEDED)
            ),
        )
    ).scalars()
    return set(rows)


def _reject(db: Session, doc: MedicalDocument, *, reason: str) -> None:
    doc.status = DOC_STATUS_FAILED if reason == "duplicate" else DOC_STATUS_REJECTED
    doc.object_state = OBJECT_STATE_REJECTED
    if reason.startswith("scan"):
        doc.scan_status = "failed"
    doc.failure_reason = reason
    # Sweep the quarantined bytes — a rejected object is never processed.
    try:
        get_storage().delete(doc.quarantine_key)
    except Exception:  # noqa: BLE001 — best-effort cleanup, never blocks the reject
        pass


def _count_pages(data: bytes, mime: str) -> int | None:
    if mime != "application/pdf":
        return 1
    try:
        import io

        from pypdf import PdfReader

        return len(PdfReader(io.BytesIO(data)).pages)
    except Exception:  # noqa: BLE001 — unknown page count → treat as single unit
        return None
