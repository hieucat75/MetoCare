"""add encounter table

Revision ID: t4_m4_add_encs
Revises: t4_m3_add_recs
Create Date: 2026-06-17 13:15:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 't4_m4_add_encs'
down_revision: str | None = 't4_m3_add_recs'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'encounters',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('patient_id', sa.String(length=36), nullable=False),
        sa.Column('doctor_id', sa.String(length=36), nullable=True),
        sa.Column('appointment_id', sa.String(length=36), nullable=True),
        sa.Column('encounter_type', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='pending_review'),
        sa.Column('chief_complaint', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('encounter_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deleted_by', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['patient_id'], ['patient_profiles.id'], name='fk_encounters_patient_id'),
        sa.ForeignKeyConstraint(['doctor_id'], ['doctors.id'], name='fk_encounters_doctor_id'),
        sa.ForeignKeyConstraint(['appointment_id'], ['appointments.id'], name='fk_encounters_appointment_id'),
        sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name='fk_encounters_deleted_by'),
    )
    with op.batch_alter_table('encounters', schema=None) as batch_op:
        batch_op.create_index('ix_encounters_patient_id', ['patient_id'], unique=False)
        batch_op.create_index('ix_encounters_doctor_id', ['doctor_id'], unique=False)
        batch_op.create_index('ix_encounters_appointment_id', ['appointment_id'], unique=False)


def downgrade() -> None:
    # Drop indexes only on non-SQLite (SQLite drops indexes with the table)
    bind = op.get_context().bind
    if bind is not None and bind.dialect.name != 'sqlite':
        with op.batch_alter_table('encounters', schema=None) as batch_op:
            batch_op.drop_index('ix_encounters_appointment_id')
            batch_op.drop_index('ix_encounters_doctor_id')
            batch_op.drop_index('ix_encounters_patient_id')
    op.drop_table('encounters')
