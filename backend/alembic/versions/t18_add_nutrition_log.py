"""add nutrition_logs table

Revision ID: t18_add_ntrl
Revises: t4_m9_add_sdel
Create Date: 2026-06-18 18:55:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "t18_add_ntrl"
down_revision: str | None = "t4_m9_add_sdel"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "nutrition_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "patient_id",
            sa.String(length=36),
            sa.ForeignKey("patient_profiles.id"),
            nullable=False,
        ),
        sa.Column("meal_type", sa.String(length=32), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("calories_kcal", sa.Integer(), nullable=True),
        sa.Column("logged_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_nutrition_logs_patient_id"),
        "nutrition_logs",
        ["patient_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_nutrition_logs_patient_id"), table_name="nutrition_logs")
    op.drop_table("nutrition_logs")
