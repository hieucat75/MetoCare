"""add booking health snapshot

Revision ID: t4_m6_add_bksp
Revises: t4_m5_add_cpln
Create Date: 2026-06-17 13:25:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 't4_m6_add_bksp'
down_revision: str | None = 't4_m5_add_cpln'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'booking_health_snapshots',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('appointment_id', sa.String(length=36), nullable=False),
        sa.Column('patient_id', sa.String(length=36), nullable=False),
        sa.Column('payload', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['appointment_id'], ['appointments.id'], name='fk_snapshots_appointment_id'),
        sa.ForeignKeyConstraint(['patient_id'], ['patient_profiles.id'], name='fk_snapshots_patient_id'),
    )
    with op.batch_alter_table('booking_health_snapshots', schema=None) as batch_op:
        batch_op.create_index('ix_booking_health_snapshots_appointment_id', ['appointment_id'], unique=False)
        batch_op.create_index('ix_booking_health_snapshots_patient_id', ['patient_id'], unique=False)


def downgrade() -> None:
    bind = op.get_context().bind
    if bind is not None and bind.dialect.name != 'sqlite':
        with op.batch_alter_table('booking_health_snapshots', schema=None) as batch_op:
            batch_op.drop_index('ix_booking_health_snapshots_patient_id')
            batch_op.drop_index('ix_booking_health_snapshots_appointment_id')
    op.drop_table('booking_health_snapshots')
