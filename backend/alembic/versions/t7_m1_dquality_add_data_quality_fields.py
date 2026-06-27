"""Add data_quality_flag and data_quality_note to lab_results.

Revision ID: t7_m1_dquality
Revises:     t6_m1_lieng
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "t7_m1_dquality"
down_revision: str | None = "t6_m1_lieng"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "lab_results",
        sa.Column("data_quality_flag", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "lab_results",
        sa.Column("data_quality_note", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("lab_results", "data_quality_note")
    op.drop_column("lab_results", "data_quality_flag")
