"""Drug knowledge relational core — ADR-01 (Medication Knowledge Structure).

Replaces the flat `drug_catalog.active_ingredients` / `drug_class` JSON/string
fields with normalized entities so ingredients, classes, and products can be
joined and referenced by ID. `drug_catalog` (DrugEntry) is left untouched —
migrating its data into these tables is a separate, later PR (EC-03/EC-04),
not part of this schema-only change.

Reconciliation note (see MEDICATION_K1_PR1_COMPLIANCE_REVIEW.md): ADR-01's
"Consequences" section originally proposed a single generic
`drug_ingredient_knowledge(knowledge_type, value_json)` table. That proposal
is superseded in practice by the six typed tables in
`drug_knowledge_content.py`, per the K0 Medication Knowledge Architecture doc
referenced in ARCHITECTURE_DECISION_INDEX.md v1.1 and built on by ADR-13.
This file implements only the parts of ADR-01 that are unambiguous and still
current: the relational core (`drug_classes`, `drug_ingredients`,
`drug_products`, `drug_product_ingredients`, `drug_product_names`).
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.database import Base

from ._mixins import TimestampMixin, UUIDPrimaryKey


class DrugClass(UUIDPrimaryKey, TimestampMixin, Base):
    """Drug class hierarchy with WHO ATC codes (ADR-01 `drug_classes`)."""

    __tablename__ = "drug_classes"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    atc_code: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    atc_level: Mapped[str | None] = mapped_column(String(8), nullable=True)
    parent_class_id: Mapped[str | None] = mapped_column(
        ForeignKey("drug_classes.id"), nullable=True
    )
    # ADR-13 "Per-Table Business Key & Uniqueness Policy": list of
    # clinical_specialties.code values required for a knowledge row under
    # this class to reach 'approved'. Not a strict FK array (no dialect-
    # portable array-of-FK construct) — validated in the service layer,
    # same convention as clinic.py's doctor_ids/branch_ids JSON columns.
    required_specialties: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Named explicitly (not inline unique=True) so the ORM's metadata-driven
    # DDL (SQLite dev/test create_all) matches the migration's constraint
    # name exactly — Codex review flagged this drift for name_inn below;
    # applying the same fix here for consistency.
    __table_args__ = (UniqueConstraint("name", name="uq_drug_classes_name"),)


class DrugIngredient(UUIDPrimaryKey, TimestampMixin, Base):
    """Normalized ingredient entity, canonical name = INN (ADR-01 OQ-2)."""

    __tablename__ = "drug_ingredients"

    name_inn: Mapped[str] = mapped_column(String(255), nullable=False)
    name_vietnamese: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cas_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    drug_class_id: Mapped[str] = mapped_column(
        ForeignKey("drug_classes.id"), nullable=False, index=True
    )

    __table_args__ = (UniqueConstraint("name_inn", name="uq_drug_ingredients_name_inn"),)


class DrugProduct(UUIDPrimaryKey, TimestampMixin, Base):
    """Reference drug product (ADR-01 target shape for `drug_catalog`)."""

    __tablename__ = "drug_products"

    display_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    prescription_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    country: Mapped[str] = mapped_column(String(10), nullable=False, default="VN")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    source_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0.0")


class DrugProductIngredient(Base):
    """Product ↔ ingredient many-to-many (ADR-01 `drug_product_ingredients`)."""

    __tablename__ = "drug_product_ingredients"

    drug_product_id: Mapped[str] = mapped_column(
        ForeignKey("drug_products.id", ondelete="CASCADE"), primary_key=True
    )
    drug_ingredient_id: Mapped[str] = mapped_column(
        ForeignKey("drug_ingredients.id", ondelete="RESTRICT"), primary_key=True
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    role: Mapped[str | None] = mapped_column(String(32), nullable=True)


class DrugProductName(UUIDPrimaryKey, TimestampMixin, Base):
    """Brand/alias/common names for a product (ADR-01 `drug_product_names`)."""

    __tablename__ = "drug_product_names"

    drug_product_id: Mapped[str] = mapped_column(
        ForeignKey("drug_products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_type: Mapped[str] = mapped_column(String(32), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="vi")
