"""Structured reference persistence (A1b-F1, ADR-13 extension).

Replaces the Phase A plan's rejected "references only in source YAML"
proposal — PTH required references be queryable from the repository, not
just present in a versioned file (patient-facing source display, reviewer
traceability, source/version comparison over time, and a genuine
many-to-many between knowledge items and citations a single VARCHAR
`source` column cannot express). See
docs/medication-management/MEDICATION_PHASE_A_BLOCKING_FINDINGS.md Finding 1.

`knowledge_reference_links` is a polymorphic association (no single
physical FK target, spans all 5 knowledge tables) — same pattern and same
rationale as `knowledge_review_specialties`
(drug_knowledge_governance.py): this table is metadata-about-provenance,
never joined for clinical content itself.

No clinical content is authored by this migration — both tables are
created empty.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from ._mixins import TimestampMixin, UUIDPrimaryKey
from .drug_knowledge_governance import KNOWLEDGE_TABLES


class DrugReference(UUIDPrimaryKey, TimestampMixin, Base):
    """One structured citation, shareable across knowledge items."""

    __tablename__ = "drug_references"

    publisher: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    document_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    publication_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    source_version: Mapped[str] = mapped_column(String(32), nullable=False)
    accessed_at: Mapped[dt.date] = mapped_column(Date, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "source_type IN "
            "('formulary','clinical_guideline','product_label','peer_reviewed','other')",
            name="ck_drug_references_source_type",
        ),
        CheckConstraint(
            "url IS NOT NULL OR document_identifier IS NOT NULL",
            name="ck_drug_references_locator_present",
        ),
        # Two-tiered citation identity (Codex round-1 P2): prefer the stable
        # document_identifier when present — the same document cited under a
        # different title/publisher spelling still resolves to one identity —
        # falling back to publisher/title/publication_date only when no
        # identifier exists. Both branches include accessed_at so re-citing
        # the same source at a later date creates a new provenance row
        # instead of colliding with, or overwriting, the earlier citation.
        Index(
            "uq_drug_references_by_document_identifier",
            "document_identifier",
            "source_version",
            "accessed_at",
            unique=True,
            postgresql_where=text("document_identifier IS NOT NULL"),
            sqlite_where=text("document_identifier IS NOT NULL"),
        ),
        Index(
            "uq_drug_references_by_title",
            "publisher",
            "title",
            "publication_date",
            "source_version",
            "accessed_at",
            unique=True,
            postgresql_where=text("document_identifier IS NULL"),
            sqlite_where=text("document_identifier IS NULL"),
        ),
    )


class KnowledgeReferenceLink(UUIDPrimaryKey, TimestampMixin, Base):
    """One knowledge row's citation of one reference (many-to-many)."""

    __tablename__ = "knowledge_reference_links"

    knowledge_table: Mapped[str] = mapped_column(String(32), nullable=False)
    # Polymorphic reference resolved by knowledge_table, not a physical FK —
    # see module docstring.
    knowledge_row_id: Mapped[str] = mapped_column(String(36), nullable=False)
    drug_reference_id: Mapped[str] = mapped_column(
        ForeignKey("drug_references.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    __table_args__ = (
        CheckConstraint(
            "knowledge_table IN (" + ",".join(f"'{t}'" for t in KNOWLEDGE_TABLES) + ")",
            name="ck_krl_knowledge_table",
        ),
        UniqueConstraint(
            "knowledge_table",
            "knowledge_row_id",
            "drug_reference_id",
            name="uq_krl_no_duplicate_link",
        ),
        Index("ix_knowledge_reference_links_row", "knowledge_table", "knowledge_row_id"),
    )
