"""add triage_logs table

Revision ID: t19_add_triage_log
Revises: t18_add_ntrl
Create Date: 2026-06-18 19:30:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "t19_add_triage_log"
down_revision: str | None = "t18_add_ntrl"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "triage_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "patient_id",
            sa.String(length=36),
            sa.ForeignKey("patient_profiles.id"),
            nullable=False,
        ),
        sa.Column("symptom_text", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("red_flags", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
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
        op.f("ix_triage_logs_patient_id"),
        "triage_logs",
        ["patient_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_triage_logs_patient_id"), table_name="triage_logs")
    op.drop_table("triage_logs")
