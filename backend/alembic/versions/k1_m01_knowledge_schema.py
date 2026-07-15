"""K1-M01: Medication Knowledge Repository schema (ADR-01 core + ADR-13 lifecycle).

Creates 12 new tables. Schema-only — no clinical content is authored here
(K1 Exit Criteria EC-07/EC-09), no API route reads/writes these tables
(EC-08), no frontend or AI change (EC-09/EC-10).

ADR-01 relational core: drug_classes, drug_ingredients, drug_products,
drug_product_ingredients, drug_product_names.

ADR-13 knowledge governance: clinical_specialties, knowledge_review_specialties.

ADR-13 knowledge tables (lifecycle + per-table business-key partial unique
index): drug_usage, drug_patient_education, drug_side_effects,
drug_monitoring, drug_contraindications. `drug_interactions` (the sixth
ADR-13 table) is deliberately NOT created here — see the note before
downgrade() and MEDICATION_K1_PR1_COMPLIANCE_REVIEW.md Section F.

See docs/medication-management/MEDICATION_K1_PR1_COMPLIANCE_REVIEW.md for the
Architecture Compliance Review and the ADR-01/ADR-13 reconciliation note.

Rollback: reverse creation order. Safe — no application code writes to any
of these tables yet (nothing deployed reads/writes them).

Revision ID: k1_m01_knowledge_schema
Revises: merge_c1m08_p0med
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "k1_m01_knowledge_schema"
down_revision: str | None = "merge_c1m08_p0med"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUS_VALUES = "'draft','clinical_review','approved','deprecated','retired'"


def _approved_invariants_sql() -> str:
    return (
        "status <> 'approved' OR ("
        "reviewed_by IS NOT NULL AND evidence_level IS NOT NULL AND "
        "source IS NOT NULL AND version IS NOT NULL AND last_reviewed_at IS NOT NULL"
        ")"
    )


def _lifecycle_columns() -> list[sa.Column]:
    """Shared provenance + lifecycle columns for the six ADR-13 tables."""
    return [
        sa.Column("source", sa.String(255), nullable=True),
        sa.Column("version", sa.String(32), nullable=True),
        sa.Column("evidence_level", sa.String(16), nullable=True),
        sa.Column("reviewed_by", sa.String(255), nullable=True),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status_changed_by", sa.String(255), nullable=False),
        sa.Column("authored_by", sa.String(255), nullable=False),
    ]


def _timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    ]


def upgrade() -> None:
    # -------------------------------------------------------------------
    # ADR-01 relational core
    # -------------------------------------------------------------------
    op.create_table(
        "drug_classes",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("atc_code", sa.String(16), nullable=True),
        sa.Column("atc_level", sa.String(8), nullable=True),
        sa.Column("parent_class_id", sa.String(36), nullable=True),
        sa.Column("required_specialties", sa.JSON(), nullable=False),
        *_timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_drug_classes_name"),
        sa.ForeignKeyConstraint(
            ["parent_class_id"], ["drug_classes.id"], name="fk_drug_classes_parent"
        ),
    )
    op.create_index("ix_drug_classes_atc_code", "drug_classes", ["atc_code"])

    op.create_table(
        "drug_ingredients",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name_inn", sa.String(255), nullable=False),
        sa.Column("name_vietnamese", sa.String(255), nullable=True),
        sa.Column("cas_number", sa.String(32), nullable=True),
        sa.Column("drug_class_id", sa.String(36), nullable=False),
        *_timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name_inn", name="uq_drug_ingredients_name_inn"),
        sa.ForeignKeyConstraint(
            ["drug_class_id"], ["drug_classes.id"], name="fk_drug_ingredients_class"
        ),
    )
    op.create_index("ix_drug_ingredients_drug_class_id", "drug_ingredients", ["drug_class_id"])

    op.create_table(
        "drug_products",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("prescription_required", sa.Boolean(), nullable=False),
        sa.Column("country", sa.String(10), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("source_version", sa.String(32), nullable=False),
        *_timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_drug_products_display_name", "drug_products", ["display_name"])
    op.create_index("ix_drug_products_is_active", "drug_products", ["is_active"])

    op.create_table(
        "drug_product_ingredients",
        sa.Column("drug_product_id", sa.String(36), nullable=False),
        sa.Column("drug_ingredient_id", sa.String(36), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("role", sa.String(32), nullable=True),
        sa.PrimaryKeyConstraint("drug_product_id", "drug_ingredient_id"),
        sa.ForeignKeyConstraint(
            ["drug_product_id"],
            ["drug_products.id"],
            name="fk_dpi_product",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["drug_ingredient_id"],
            ["drug_ingredients.id"],
            name="fk_dpi_ingredient",
            ondelete="RESTRICT",
        ),
    )

    op.create_table(
        "drug_product_names",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("drug_product_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_type", sa.String(32), nullable=False),
        sa.Column("language", sa.String(10), nullable=False),
        *_timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["drug_product_id"],
            ["drug_products.id"],
            name="fk_dpn_product",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_drug_product_names_drug_product_id", "drug_product_names", ["drug_product_id"]
    )

    # -------------------------------------------------------------------
    # ADR-13 governance
    # -------------------------------------------------------------------
    op.create_table(
        "clinical_specialties",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("display_name_vi", sa.String(128), nullable=False),
        sa.Column("display_name_en", sa.String(128), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_clinical_specialties_code"),
    )

    op.create_table(
        "knowledge_review_specialties",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("knowledge_table", sa.String(32), nullable=False),
        sa.Column("knowledge_row_id", sa.String(36), nullable=False),
        sa.Column("specialty_id", sa.String(36), nullable=False),
        sa.Column("reviewed_by", sa.String(255), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["specialty_id"], ["clinical_specialties.id"], name="fk_krs_specialty"
        ),
        sa.CheckConstraint(
            "knowledge_table IN ("
            "'drug_usage','drug_patient_education','drug_side_effects',"
            "'drug_monitoring','drug_contraindications'"
            ")",
            name="ck_krs_knowledge_table",
        ),
    )
    op.create_index(
        "ix_knowledge_review_specialties_row",
        "knowledge_review_specialties",
        ["knowledge_table", "knowledge_row_id"],
    )
    op.create_index(
        "ix_knowledge_review_specialties_specialty_id",
        "knowledge_review_specialties",
        ["specialty_id"],
    )

    # -------------------------------------------------------------------
    # ADR-13 six typed knowledge tables
    # -------------------------------------------------------------------
    op.create_table(
        "drug_usage",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("drug_ingredient_id", sa.String(36), nullable=False),
        sa.Column("locale", sa.String(10), nullable=False),
        sa.Column("audience", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        *_lifecycle_columns(),
        *_timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["drug_ingredient_id"],
            ["drug_ingredients.id"],
            name="fk_drug_usage_ingredient",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(f"status IN ({STATUS_VALUES})", name="ck_drug_usage_status"),
        sa.CheckConstraint(_approved_invariants_sql(), name="ck_drug_usage_approved_invariants"),
    )
    op.create_index("ix_drug_usage_drug_ingredient_id", "drug_usage", ["drug_ingredient_id"])
    op.create_index(
        "uq_drug_usage_approved_key",
        "drug_usage",
        ["drug_ingredient_id", "locale", "audience"],
        unique=True,
        postgresql_where=sa.text("status = 'approved'"),
        sqlite_where=sa.text("status = 'approved'"),
    )

    op.create_table(
        "drug_patient_education",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("drug_ingredient_id", sa.String(36), nullable=False),
        sa.Column("theme", sa.String(64), nullable=False),
        sa.Column("locale", sa.String(10), nullable=False),
        sa.Column("audience", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        *_lifecycle_columns(),
        *_timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["drug_ingredient_id"],
            ["drug_ingredients.id"],
            name="fk_drug_patient_education_ingredient",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            f"status IN ({STATUS_VALUES})", name="ck_drug_patient_education_status"
        ),
        sa.CheckConstraint(
            _approved_invariants_sql(), name="ck_drug_patient_education_approved_invariants"
        ),
    )
    op.create_index(
        "ix_drug_patient_education_drug_ingredient_id",
        "drug_patient_education",
        ["drug_ingredient_id"],
    )
    op.create_index(
        "uq_drug_patient_education_approved_key",
        "drug_patient_education",
        ["drug_ingredient_id", "theme", "locale", "audience"],
        unique=True,
        postgresql_where=sa.text("status = 'approved'"),
        sqlite_where=sa.text("status = 'approved'"),
    )

    op.create_table(
        "drug_side_effects",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("drug_ingredient_id", sa.String(36), nullable=False),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("concept_code", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        *_lifecycle_columns(),
        *_timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["drug_ingredient_id"],
            ["drug_ingredients.id"],
            name="fk_drug_side_effects_ingredient",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(f"status IN ({STATUS_VALUES})", name="ck_drug_side_effects_status"),
        sa.CheckConstraint(
            _approved_invariants_sql(), name="ck_drug_side_effects_approved_invariants"
        ),
    )
    op.create_index(
        "ix_drug_side_effects_drug_ingredient_id", "drug_side_effects", ["drug_ingredient_id"]
    )
    op.create_index(
        "uq_drug_side_effects_approved_key",
        "drug_side_effects",
        ["drug_ingredient_id", "level", "concept_code"],
        unique=True,
        postgresql_where=sa.text("status = 'approved'"),
        sqlite_where=sa.text("status = 'approved'"),
    )

    op.create_table(
        "drug_monitoring",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("drug_ingredient_id", sa.String(36), nullable=False),
        sa.Column("parameter", sa.String(128), nullable=False),
        sa.Column("patient_context", sa.String(64), nullable=False),
        sa.Column("guidance", sa.Text(), nullable=False),
        *_lifecycle_columns(),
        *_timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["drug_ingredient_id"],
            ["drug_ingredients.id"],
            name="fk_drug_monitoring_ingredient",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(f"status IN ({STATUS_VALUES})", name="ck_drug_monitoring_status"),
        sa.CheckConstraint(
            _approved_invariants_sql(), name="ck_drug_monitoring_approved_invariants"
        ),
    )
    op.create_index(
        "ix_drug_monitoring_drug_ingredient_id", "drug_monitoring", ["drug_ingredient_id"]
    )
    op.create_index(
        "uq_drug_monitoring_approved_key",
        "drug_monitoring",
        ["drug_ingredient_id", "parameter", "patient_context"],
        unique=True,
        postgresql_where=sa.text("status = 'approved'"),
        sqlite_where=sa.text("status = 'approved'"),
    )

    op.create_table(
        "drug_contraindications",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("drug_ingredient_id", sa.String(36), nullable=False),
        sa.Column("condition_type", sa.String(64), nullable=False),
        sa.Column("condition_key", sa.String(64), nullable=False),
        sa.Column("condition_detail", sa.Text(), nullable=False),
        *_lifecycle_columns(),
        *_timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["drug_ingredient_id"],
            ["drug_ingredients.id"],
            name="fk_drug_contraindications_ingredient",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            f"status IN ({STATUS_VALUES})", name="ck_drug_contraindications_status"
        ),
        sa.CheckConstraint(
            _approved_invariants_sql(), name="ck_drug_contraindications_approved_invariants"
        ),
    )
    op.create_index(
        "ix_drug_contraindications_drug_ingredient_id",
        "drug_contraindications",
        ["drug_ingredient_id"],
    )
    op.create_index(
        "uq_drug_contraindications_approved_key",
        "drug_contraindications",
        ["drug_ingredient_id", "condition_type", "condition_key"],
        unique=True,
        postgresql_where=sa.text("status = 'approved'"),
        sqlite_where=sa.text("status = 'approved'"),
    )

    # NOTE: drug_interactions is deliberately NOT created in this PR. Codex
    # review flagged that a single-approved-per-canonical_pair_key design
    # cannot represent ADR-02's directional/conditional interaction rules
    # (dose/lab/route/condition-dependent — multiple approved rules can
    # legitimately share the same subject pair). Deferred to a follow-up PR
    # scoped to full ADR-02 compliance, not bundled into this schema PR.


def downgrade() -> None:
    """Reverse creation order. Safe: no deployed code writes to these tables."""
    op.drop_table("drug_contraindications")
    op.drop_table("drug_monitoring")
    op.drop_table("drug_side_effects")
    op.drop_table("drug_patient_education")
    op.drop_table("drug_usage")
    op.drop_table("knowledge_review_specialties")
    op.drop_table("clinical_specialties")
    op.drop_table("drug_product_names")
    op.drop_table("drug_product_ingredients")
    op.drop_table("drug_products")
    op.drop_table("drug_ingredients")
    op.drop_table("drug_classes")
