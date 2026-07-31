"""Medical Document Intelligence (MDI) models — Master Plan §1.5.

The document-first core. A ``MedicalDocument`` is an uploaded artifact (image/PDF)
that flows quarantine → accepted → OCR → extraction. An extraction produces MANY
``ExtractionCandidate`` rows (one document → many meds / lab results / diagnoses);
each candidate is independently confirmed/rejected and — once confirmed — promoted
into a canonical clinical record via exactly one ``PromotionLink``. MDI never owns
canonical clinical data; it produces candidates the domain contexts accept.

Provenance chain (bidirectional):
  canonical record ← PromotionLink ← ExtractionCandidate ← DocumentExtraction
  ← MedicalDocument / DocumentPage / bounding box.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    JSON,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.crypto import EncryptedString
from app.core.database import Base

from ._mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKey

# JSONB on Postgres, plain JSON on SQLite tests (matches app/models/clinical.py).
_JSON_VARIANT = JSON().with_variant(JSONB(astext_type=Text()), "postgresql")

# ── Canonical document status set (§1.5). `object_state` (below) is the separate
# object-storage lifecycle; `quarantined` is NOT a document status.
DOC_STATUS_UPLOADED = "uploaded"
DOC_STATUS_PREPROCESSING = "preprocessing"
DOC_STATUS_PROCESSING = "processing"
DOC_STATUS_NEEDS_REVIEW = "needs_review"
DOC_STATUS_PARTIALLY_CONFIRMED = "partially_confirmed"
DOC_STATUS_CONFIRMED = "confirmed"
DOC_STATUS_REJECTED = "rejected"
DOC_STATUS_FAILED = "failed"
DOC_STATUS_SUPERSEDED = "superseded"

# ── Object-storage lifecycle (§1.7) — orthogonal to document status.
OBJECT_STATE_QUARANTINED = "quarantined"
OBJECT_STATE_ACCEPTED = "accepted"
OBJECT_STATE_REJECTED = "rejected"

# ── Candidate types (§1.5 / §1.9).
CANDIDATE_MEDICATION = "medication"
CANDIDATE_LAB_RESULT = "lab_result"
CANDIDATE_DIAGNOSIS = "diagnosis"
CANDIDATE_PROCEDURE = "procedure"
CANDIDATE_FINDING = "finding"
CANDIDATE_RECOMMENDATION = "recommendation"
CANDIDATE_FOLLOW_UP = "follow_up"

# ── Candidate status set (§1.5).
CAND_STATUS_EXTRACTED = "extracted"
CAND_STATUS_NEEDS_REVIEW = "needs_review"
CAND_STATUS_CONFIRMED = "confirmed"
CAND_STATUS_REJECTED = "rejected"
CAND_STATUS_MERGED = "merged"
CAND_STATUS_SUPERSEDED = "superseded"


class MedicalDocument(UUIDPrimaryKey, TimestampMixin, SoftDeleteMixin, Base):
    """An uploaded medical document artifact (§1.5)."""

    __tablename__ = "medical_documents"

    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    # SHA-256 hex of raw bytes — duplicate detection is scoped WITHIN the patient.
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    # Object-storage keys (never the binary itself). quarantine_key is set at
    # upload-session; accepted_key only after validation+scan pass (§1.7).
    quarantine_key: Mapped[str] = mapped_column(String(512), nullable=False)
    accepted_key: Mapped[str | None] = mapped_column(String(512))
    mime: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    # prescription | lab_report | general | unknown
    doc_type: Mapped[str | None] = mapped_column(String(32), index=True)
    classification_confidence: Mapped[float | None] = mapped_column(Float)
    page_count: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(
        String(32), default="mobile_upload", server_default="mobile_upload"
    )
    status: Mapped[str] = mapped_column(
        String(32), default=DOC_STATUS_UPLOADED, server_default=DOC_STATUS_UPLOADED, index=True
    )
    object_state: Mapped[str] = mapped_column(
        String(24), default=OBJECT_STATE_QUARANTINED, server_default=OBJECT_STATE_QUARANTINED
    )
    scan_status: Mapped[str | None] = mapped_column(String(24))  # pending|clean|failed|skipped
    failure_reason: Mapped[str | None] = mapped_column(String(255))
    # TTL for quarantine sweep of never-finalized / rejected objects (§1.7.7).
    upload_expires_at: Mapped[dt.datetime | None] = mapped_column()
    # Correction/supersession chain (§1.5).
    superseded_by: Mapped[str | None] = mapped_column(
        ForeignKey("medical_documents.id"), nullable=True
    )
    data_classification: Mapped[str] = mapped_column(
        String(32), default="sensitive_health", server_default="sensitive_health"
    )


class DocumentPage(UUIDPrimaryKey, TimestampMixin, Base):
    """One page of a document, with its own OCR raw text + layout blocks."""

    __tablename__ = "document_pages"
    __table_args__ = (UniqueConstraint("document_id", "page_no", name="uq_document_page_no"),)

    document_id: Mapped[str] = mapped_column(
        ForeignKey("medical_documents.id"), index=True, nullable=False
    )
    page_no: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(512))
    # PHI: raw OCR text encrypted at rest; decrypt failure → None (never raises).
    ocr_raw: Mapped[str | None] = mapped_column(EncryptedString(on_decrypt_failure="none"))
    blocks_json: Mapped[dict | None] = mapped_column(_JSON_VARIANT)


class DocumentExtraction(UUIDPrimaryKey, TimestampMixin, Base):
    """Immutable raw-provenance record of one extraction run (§1.5).

    A re-run creates a NEW row — it never mutates a prior one.
    """

    __tablename__ = "document_extractions"

    document_id: Mapped[str] = mapped_column(
        ForeignKey("medical_documents.id"), index=True, nullable=False
    )
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    # mock | tesseract | azure | anthropic
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str | None] = mapped_column(String(64))
    prompt_version: Mapped[str | None] = mapped_column(String(32))
    extraction_run_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    review_state: Mapped[str] = mapped_column(
        String(24), default="pending", server_default="pending"
    )


class ExtractionCandidate(UUIDPrimaryKey, TimestampMixin, Base):
    """The one-to-many core: an independently-confirmable extracted item (§1.5)."""

    __tablename__ = "extraction_candidates"
    __table_args__ = (
        # Re-extraction of the same document never creates duplicate candidates.
        UniqueConstraint("extraction_id", "dedupe_key", name="uq_extraction_dedupe_key"),
    )

    extraction_id: Mapped[str] = mapped_column(
        ForeignKey("document_extractions.id"), index=True, nullable=False
    )
    # Denormalized for cheap listing + BOLA scoping without a 3-way join.
    document_id: Mapped[str] = mapped_column(
        ForeignKey("medical_documents.id"), index=True, nullable=False
    )
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    candidate_type: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    ordinal: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    fields_json: Mapped[dict] = mapped_column(_JSON_VARIANT, nullable=False)
    field_confidence_json: Mapped[dict | None] = mapped_column(_JSON_VARIANT)
    dedupe_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), default=CAND_STATUS_EXTRACTED, server_default=CAND_STATUS_EXTRACTED, index=True
    )
    corrections_json: Mapped[dict | None] = mapped_column(_JSON_VARIANT)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[dt.datetime | None] = mapped_column()


class PromotionLink(UUIDPrimaryKey, TimestampMixin, Base):
    """Records the promotion of a CONFIRMED candidate into a canonical record (§1.5).

    Unique(candidate_id) enforces: a candidate promotes at most once. Reprocessing
    carries confirmed candidates forward, never re-promoting them.
    """

    __tablename__ = "promotion_links"
    __table_args__ = (
        UniqueConstraint("candidate_id", name="uq_promotion_candidate_once"),
    )

    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("extraction_candidates.id"), nullable=False
    )
    # medication | lab_result | diagnosis | ...
    canonical_type: Mapped[str] = mapped_column(String(24), nullable=False)
    canonical_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)  # created|merged_into
    promoted_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
