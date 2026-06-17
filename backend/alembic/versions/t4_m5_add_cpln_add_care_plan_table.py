"""add care plan table

Revision ID: t4_m5_add_cpln
Revises: t4_m4b_enc_fk
Create Date: 2026-06-17 13:20:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 't4_m5_add_cpln'
down_revision: str | None = 't4_m4b_enc_fk'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'care_plans',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('patient_id', sa.String(length=36), nullable=False),
        sa.Column('encounter_id', sa.String(length=36), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='DRAFT'),
        sa.Column('approved_by_doctor_id', sa.String(length=36), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ai_generated', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deleted_by', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['patient_id'], ['patient_profiles.id'], name='fk_care_plans_patient_id'),
        sa.ForeignKeyConstraint(['encounter_id'], ['encounters.id'], name='fk_care_plans_encounter_id'),
        sa.ForeignKeyConstraint(['approved_by_doctor_id'], ['doctors.id'], name='fk_care_plans_approved_by_doctor_id'),
        sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name='fk_care_plans_deleted_by'),
    )
    with op.batch_alter_table('care_plans', schema=None) as batch_op:
        batch_op.create_index('ix_care_plans_patient_id', ['patient_id'], unique=False)
        batch_op.create_index('ix_care_plans_encounter_id', ['encounter_id'], unique=False)
        batch_op.create_index('ix_care_plans_approved_by_doctor_id', ['approved_by_doctor_id'], unique=False)


def downgrade() -> None:
    bind = op.get_context().bind
    if bind is not None and bind.dialect.name != 'sqlite':
        with op.batch_alter_table('care_plans', schema=None) as batch_op:
            batch_op.drop_index('ix_care_plans_approved_by_doctor_id')
            batch_op.drop_index('ix_care_plans_encounter_id')
            batch_op.drop_index('ix_care_plans_patient_id')
    op.drop_table('care_plans')
