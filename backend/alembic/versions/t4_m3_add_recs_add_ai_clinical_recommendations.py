"""add ai clinical recommendations

Revision ID: t4_m3_add_recs
Revises: t4_m2_ext_sess
Create Date: 2026-06-17 13:10:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 't4_m3_add_recs'
down_revision: str | None = 't4_m2_ext_sess'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'ai_clinical_recommendations',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('session_id', sa.String(length=36), nullable=False),
        sa.Column('patient_id', sa.String(length=36), nullable=False),
        sa.Column('encounter_id', sa.String(length=36), nullable=True),
        sa.Column('recommendation_type', sa.String(length=64), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('key_version', sa.Integer(), nullable=True, server_default='1'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='pending_review'),
        sa.Column('reviewed_by_doctor_id', sa.String(length=36), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ai_confidence', sa.Float(), nullable=True),
        sa.Column('safety_cleared', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('medical_disclaimer', sa.Text(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deleted_by', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['session_id'], ['ai_sessions.id'], name='fk_clinical_recs_session_id'),
        sa.ForeignKeyConstraint(['patient_id'], ['patient_profiles.id'], name='fk_clinical_recs_patient_id'),
        # encounter FK deferred to M4b (after encounters table created in M4)
        sa.ForeignKeyConstraint(['reviewed_by_doctor_id'], ['doctors.id'], name='fk_clinical_recs_reviewed_by_doctor_id'),
        sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name='fk_clinical_recs_deleted_by'),
    )
    with op.batch_alter_table('ai_clinical_recommendations', schema=None) as batch_op:
        batch_op.create_index('ix_ai_clinical_recommendations_session_id', ['session_id'], unique=False)
        batch_op.create_index('ix_ai_clinical_recommendations_patient_id', ['patient_id'], unique=False)
        batch_op.create_index('ix_ai_clinical_recommendations_encounter_id', ['encounter_id'], unique=False)
        batch_op.create_index('ix_ai_clinical_recommendations_reviewed_by_doctor_id', ['reviewed_by_doctor_id'], unique=False)


def downgrade() -> None:
    # Encounter FK is in M4b, which runs downgrade before M3 (M4b.downgrade -> M3.downgrade)
    # So encounter FK is already dropped by the time we reach here.
    # SQLite: batch_alter_table reflection for index drops may fail; just drop the table.
    bind = op.get_context().bind
    if bind is not None and bind.dialect.name != 'sqlite':
        with op.batch_alter_table('ai_clinical_recommendations', schema=None) as batch_op:
            batch_op.drop_index('ix_ai_clinical_recommendations_reviewed_by_doctor_id')
            batch_op.drop_index('ix_ai_clinical_recommendations_encounter_id')
            batch_op.drop_index('ix_ai_clinical_recommendations_patient_id')
            batch_op.drop_index('ix_ai_clinical_recommendations_session_id')
    op.drop_table('ai_clinical_recommendations')
