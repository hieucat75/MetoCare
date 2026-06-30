"""t9_m1: add drug_catalog reference table

Revision ID: t9_m1_drug_cat
Revises: t8_m1_unitlen
Create Date: 2026-06-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "t9_m1_drug_cat"
down_revision = "t8_m1_unitlen"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "drug_catalog",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generic_name", sa.String(255), nullable=False),
        sa.Column("brand_names", sa.JSON(), nullable=False),
        sa.Column("vietnamese_common_names", sa.JSON(), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("active_ingredients", sa.JSON(), nullable=False),
        sa.Column("drug_class", sa.String(128), nullable=False),
        sa.Column("metric_groups", sa.JSON(), nullable=False),
        sa.Column("common_indications", sa.JSON(), nullable=False),
        sa.Column("prescription_required", sa.Boolean(), nullable=False),
        sa.Column("country_context", sa.String(10), nullable=False),
        sa.Column("caution_flags", sa.JSON(), nullable=False),
        sa.Column("contraindication_keywords", sa.JSON(), nullable=False),
        sa.Column("renal_caution", sa.Boolean(), nullable=False),
        sa.Column("hepatic_caution", sa.Boolean(), nullable=False),
        sa.Column("pregnancy_caution", sa.Boolean(), nullable=False),
        sa.Column("notes_for_matching_only", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("source_version", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_drug_catalog_generic_name", "drug_catalog", ["generic_name"])
    op.create_index("ix_drug_catalog_is_active", "drug_catalog", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_drug_catalog_is_active", table_name="drug_catalog")
    op.drop_index("ix_drug_catalog_generic_name", table_name="drug_catalog")
    op.drop_table("drug_catalog")
