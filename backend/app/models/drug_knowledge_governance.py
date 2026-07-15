"""Knowledge review governance — ADR-13 (Knowledge Content Lifecycle).

Controlled-vocabulary specialty roster + the join table recording which
specialty signed off on which knowledge row. `knowledge_review_specialties`
is a deliberate polymorphic association (no single physical FK target,
since it spans six different tables) — same rationale ADR-13 gives for why
this is acceptable here: the table is metadata-about-review, never joined
for clinical content itself.
"""

from __future__ import annotations

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from ._mixins import UUIDPrimaryKey

# Valid values for knowledge_review_specialties.knowledge_table — the six
# ADR-13 knowledge tables. Kept as a plain tuple (not a DB enum type) so it
# stays a single source of truth referenced by both the model CHECK
# constraint and the Alembic migration.
KNOWLEDGE_TABLES = (
    "drug_usage",
    "drug_patient_education",
    "drug_side_effects",
    "drug_monitoring",
    "drug_contraindications",
    "drug_interactions",
)


class ClinicalSpecialty(UUIDPrimaryKey, Base):
    """Controlled vocabulary of reviewer specialties (ADR-13 round-1 addendum)."""

    __tablename__ = "clinical_specialties"

    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    display_name_vi: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name_en: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class KnowledgeReviewSpecialty(UUIDPrimaryKey, Base):
    """One specialty's sign-off on one knowledge row (ADR-13)."""

    __tablename__ = "knowledge_review_specialties"

    knowledge_table: Mapped[str] = mapped_column(String(32), nullable=False)
    # Polymorphic reference resolved by knowledge_table, not a physical FK —
    # see module docstring.
    knowledge_row_id: Mapped[str] = mapped_column(String(36), nullable=False)
    specialty_id: Mapped[str] = mapped_column(
        ForeignKey("clinical_specialties.id"), nullable=False, index=True
    )
    reviewed_by: Mapped[str] = mapped_column(String(255), nullable=False)
    reviewed_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index(
            "ix_knowledge_review_specialties_row",
            "knowledge_table",
            "knowledge_row_id",
        ),
    )
