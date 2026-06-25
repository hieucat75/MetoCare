"""add original_value/unit/reference_range/test_name to lab_results

Revision ID: t4_m11_orlb
Revises: t4_m10_add_adhr
Create Date: 2026-06-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "t4_m11_orlb"
down_revision: str | None = "t4_m10_add_adhr"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("lab_results", schema=None) as batch_op:
        batch_op.add_column(sa.Column("original_value", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("original_unit", sa.String(24), nullable=True))
        batch_op.add_column(sa.Column("original_reference_range", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("original_test_name", sa.String(128), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("lab_results", schema=None) as batch_op:
        batch_op.drop_column("original_test_name")
        batch_op.drop_column("original_reference_range")
        batch_op.drop_column("original_unit")
        batch_op.drop_column("original_value")
