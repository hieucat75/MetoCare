"""lab document pipeline status

Revision ID: a1b2c3d4e5f6
Revises: 8e3134ab9679
Create Date: 2026-06-13 06:10:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: str | None = '8e3134ab9679'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Async lab pipeline state machine column. server_default makes the NOT NULL
    # add safe on tables with existing rows.
    with op.batch_alter_table('lab_documents', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('status', sa.String(length=32), nullable=False, server_default='uploaded')
        )


def downgrade() -> None:
    with op.batch_alter_table('lab_documents', schema=None) as batch_op:
        batch_op.drop_column('status')
