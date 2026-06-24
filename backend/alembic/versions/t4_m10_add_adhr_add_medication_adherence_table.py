"""add medication adherence table

Revision ID: t4_m10_add_adhr
Revises: t4_m9_add_sdel
Create Date: 2026-06-24 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 't4_m10_add_adhr'
down_revision: str | None = 'hmbk_backfill'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'medication_adherence' in inspector.get_table_names():
        return
    op.create_table(
        'medication_adherence',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('medication_id', sa.String(36),
                  sa.ForeignKey('medications.id'), nullable=False, index=True),
        sa.Column('patient_id', sa.String(36),
                  sa.ForeignKey('patient_profiles.id'), nullable=False, index=True),
        sa.Column('scheduled_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('taken_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('skipped', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('medication_adherence')
