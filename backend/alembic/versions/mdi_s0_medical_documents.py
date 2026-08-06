"""MDI Slice 0: Medical Document Intelligence + Object Storage tables.

Adds the document-first core (Master Plan §1.5): medical_documents,
document_pages, document_extractions, extraction_candidates, promotion_links.
Purely additive — no existing table or row is touched. Portable across SQLite
(dev/test) and PostgreSQL (staging); JSON columns use JSONB on Postgres.

Idempotency invariants enforced at the DB layer:
- uq_extraction_dedupe_key(extraction_id, dedupe_key): re-extraction of the same
  document never creates duplicate candidates.
- uq_promotion_candidate_once(candidate_id): a candidate promotes at most once.
- uq_document_page_no(document_id, page_no): one row per page.

Revision ID: mdi_s0_medical_documents
Revises: k2_s0_round3_hardening
Create Date: 2026-07-31
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# NOTE: revision id kept ≤ 32 chars to fit alembic_version.version_num
# VARCHAR(32) on PostgreSQL (test_migrations.py guards this — a Postgres-only
# failure that SQLite would not surface).
revision: str = "mdi_s0_medical_documents"
down_revision: str | None = "k2_s0_round3_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOW = sa.text("CURRENT_TIMESTAMP")


def _json() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
    ]


def upgrade() -> None:
    # ── medical_documents (self-referential superseded_by) ──────────────────
    op.create_table(
        "medical_documents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("patient_id", sa.String(length=36), sa.ForeignKey("patient_profiles.id"), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("quarantine_key", sa.String(length=512), nullable=False),
        sa.Column("accepted_key", sa.String(length=512), nullable=True),
        sa.Column("mime", sa.String(length=64), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("doc_type", sa.String(length=32), nullable=True),
        sa.Column("classification_confidence", sa.Float(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=32), server_default="mobile_upload", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="uploaded", nullable=False),
        sa.Column("object_state", sa.String(length=24), server_default="quarantined", nullable=False),
        sa.Column("scan_status", sa.String(length=24), nullable=True),
        sa.Column("failure_reason", sa.String(length=255), nullable=True),
        sa.Column("upload_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_by", sa.String(length=36), sa.ForeignKey("medical_documents.id"), nullable=True),
        sa.Column("data_classification", sa.String(length=32), server_default="sensitive_health", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_medical_documents_patient_id", "medical_documents", ["patient_id"])
    op.create_index("ix_medical_documents_sha256", "medical_documents", ["sha256"])
    op.create_index("ix_medical_documents_doc_type", "medical_documents", ["doc_type"])
    op.create_index("ix_medical_documents_status", "medical_documents", ["status"])
    # Backs the within-patient duplicate guard (§1.7.6) at the DB layer so two
    # concurrent finalizes of identical bytes can't both accept. Partial: only
    # accepted, non-deleted rows — quarantined/rejected/duplicate rows (which may
    # share a sha256) are excluded.
    op.create_index(
        "uq_medical_documents_patient_sha_accepted",
        "medical_documents",
        ["patient_id", "sha256"],
        unique=True,
        sqlite_where=sa.text("object_state = 'accepted' AND deleted_at IS NULL"),
        postgresql_where=sa.text("object_state = 'accepted' AND deleted_at IS NULL"),
    )

    # ── document_pages ──────────────────────────────────────────────────────
    op.create_table(
        "document_pages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("document_id", sa.String(length=36), sa.ForeignKey("medical_documents.id"), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=True),
        sa.Column("ocr_raw", sa.Text(), nullable=True),  # EncryptedString → Text at rest
        sa.Column("blocks_json", _json(), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("document_id", "page_no", name="uq_document_page_no"),
    )
    op.create_index("ix_document_pages_document_id", "document_pages", ["document_id"])

    # ── document_extractions (immutable provenance) ─────────────────────────
    op.create_table(
        "document_extractions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("document_id", sa.String(length=36), sa.ForeignKey("medical_documents.id"), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("prompt_version", sa.String(length=32), nullable=True),
        sa.Column("extraction_run_id", sa.String(length=36), nullable=False),
        sa.Column("review_state", sa.String(length=24), server_default="pending", nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_document_extractions_document_id", "document_extractions", ["document_id"])
    op.create_index(
        "ix_document_extractions_extraction_run_id", "document_extractions", ["extraction_run_id"]
    )

    # ── extraction_candidates (one-to-many core) ────────────────────────────
    op.create_table(
        "extraction_candidates",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("extraction_id", sa.String(length=36), sa.ForeignKey("document_extractions.id"), nullable=False),
        sa.Column("document_id", sa.String(length=36), sa.ForeignKey("medical_documents.id"), nullable=False),
        sa.Column("patient_id", sa.String(length=36), sa.ForeignKey("patient_profiles.id"), nullable=False),
        sa.Column("candidate_type", sa.String(length=24), nullable=False),
        sa.Column("ordinal", sa.Integer(), server_default="0", nullable=False),
        sa.Column("fields_json", _json(), nullable=False),
        sa.Column("field_confidence_json", _json(), nullable=True),
        sa.Column("dedupe_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="extracted", nullable=False),
        sa.Column("corrections_json", _json(), nullable=True),
        sa.Column("reviewed_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("extraction_id", "dedupe_key", name="uq_extraction_dedupe_key"),
    )
    op.create_index("ix_extraction_candidates_extraction_id", "extraction_candidates", ["extraction_id"])
    op.create_index("ix_extraction_candidates_document_id", "extraction_candidates", ["document_id"])
    op.create_index("ix_extraction_candidates_patient_id", "extraction_candidates", ["patient_id"])
    op.create_index("ix_extraction_candidates_candidate_type", "extraction_candidates", ["candidate_type"])
    op.create_index("ix_extraction_candidates_status", "extraction_candidates", ["status"])

    # ── promotion_links ─────────────────────────────────────────────────────
    op.create_table(
        "promotion_links",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("candidate_id", sa.String(length=36), sa.ForeignKey("extraction_candidates.id"), nullable=False),
        sa.Column("canonical_type", sa.String(length=24), nullable=False),
        sa.Column("canonical_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("promoted_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("candidate_id", name="uq_promotion_candidate_once"),
    )


def downgrade() -> None:
    op.drop_table("promotion_links")
    op.drop_index("ix_extraction_candidates_status", table_name="extraction_candidates")
    op.drop_index("ix_extraction_candidates_candidate_type", table_name="extraction_candidates")
    op.drop_index("ix_extraction_candidates_patient_id", table_name="extraction_candidates")
    op.drop_index("ix_extraction_candidates_document_id", table_name="extraction_candidates")
    op.drop_index("ix_extraction_candidates_extraction_id", table_name="extraction_candidates")
    op.drop_table("extraction_candidates")
    op.drop_index("ix_document_extractions_extraction_run_id", table_name="document_extractions")
    op.drop_index("ix_document_extractions_document_id", table_name="document_extractions")
    op.drop_table("document_extractions")
    op.drop_index("ix_document_pages_document_id", table_name="document_pages")
    op.drop_table("document_pages")
    op.drop_index("uq_medical_documents_patient_sha_accepted", table_name="medical_documents")
    op.drop_index("ix_medical_documents_status", table_name="medical_documents")
    op.drop_index("ix_medical_documents_doc_type", table_name="medical_documents")
    op.drop_index("ix_medical_documents_sha256", table_name="medical_documents")
    op.drop_index("ix_medical_documents_patient_id", table_name="medical_documents")
    op.drop_table("medical_documents")
