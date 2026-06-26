"""Lab intelligence provenance columns.

Revision ID: t6_m1_lieng
Revises:     t5_m2_ocase
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "t6_m1_lieng"
down_revision: str | None = "t5_m2_ocase"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("lab_results", sa.Column("source_type", sa.String(length=32), nullable=False, server_default="manual_entry"))
    op.add_column("lab_results", sa.Column("correction_history_json", sa.Text(), nullable=True))
    op.add_column("lab_results", sa.Column("normalized_value_si", sa.Float(), nullable=True))
    op.add_column("lab_results", sa.Column("normalized_unit_si", sa.String(length=24), nullable=True))


def downgrade() -> None:
    op.drop_column("lab_results", "normalized_unit_si")
    op.drop_column("lab_results", "normalized_value_si")
    op.drop_column("lab_results", "correction_history_json")
    op.drop_column("lab_results", "source_type")
