"""PR-D: add medications.frequency

Adds a nullable human-readable schedule column (e.g. "2 lần/ngày") to the
medications table so the patient medication UI can show real data instead of
hardcoded placeholders.

Revision ID: prd_med_frequency
Revises: t27_uq_patient_profile_user_id
Create Date: 2026-06-20 05:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'prd_med_frequency'
down_revision: str | None = 't27_uq_patient_profile_user_id'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable — no server_default needed; existing rows get NULL.
    with op.batch_alter_table('medications', schema=None) as batch_op:
        batch_op.add_column(sa.Column('frequency', sa.String(length=128), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('medications', schema=None) as batch_op:
        batch_op.drop_column('frequency')
