"""Drug reference catalog model.

A read-only reference table populated by seed scripts and used ONLY for
medication name lookup and autocomplete.  It is NOT linked to patient data and
carries no prescribing logic.
"""

from __future__ import annotations

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.database import Base
from ._mixins import TimestampMixin, UUIDPrimaryKey


class DrugEntry(UUIDPrimaryKey, TimestampMixin, Base):
    """Single entry in the drug reference catalog."""

    __tablename__ = "drug_catalog"

    # Primary identity
    generic_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    brand_names: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    vietnamese_common_names: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    aliases: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    active_ingredients: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Classification
    drug_class: Mapped[str] = mapped_column(String(128), nullable=False)
    metric_groups: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    common_indications: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Regulatory
    prescription_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    country_context: Mapped[str] = mapped_column(String(10), nullable=False, default="VN")

    # Safety signals (for matching context only — not clinical advice)
    caution_flags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    contraindication_keywords: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    renal_caution: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hepatic_caution: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pregnancy_caution: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Internal notes — never returned to clients
    notes_for_matching_only: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Catalog management
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    source_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0.0")
