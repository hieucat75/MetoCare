"""PR-F: add user notification preference columns

Adds notify_medication / notify_lab_results / notify_doctor_messages booleans to
the users table (default True) so the patient Settings page can persist
notification toggles instead of mocking them.

Revision ID: prf_notif_prefs
Revises: prd_med_frequency
Create Date: 2026-06-20 05:30:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'prf_notif_prefs'
down_revision: str | None = 'prd_med_frequency'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('notify_medication', sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch_op.add_column(
            sa.Column('notify_lab_results', sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch_op.add_column(
            sa.Column('notify_doctor_messages', sa.Boolean(), nullable=False, server_default=sa.true())
        )


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('notify_doctor_messages')
        batch_op.drop_column('notify_lab_results')
        batch_op.drop_column('notify_medication')
