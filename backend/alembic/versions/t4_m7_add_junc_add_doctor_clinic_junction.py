"""add doctor clinic junction

Revision ID: t4_m7_add_junc
Revises: t4_m6_add_bksp
Create Date: 2026-06-17 13:30:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 't4_m7_add_junc'
down_revision: str | None = 't4_m6_add_bksp'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'doctor_clinic',
        sa.Column('doctor_id', sa.String(length=36), nullable=False),
        sa.Column('clinic_id', sa.String(length=36), nullable=False),
        sa.Column('role_at_clinic', sa.String(length=64), nullable=True),
        sa.Column('is_primary', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('joined_at', sa.Date(), nullable=False, server_default=sa.text('CURRENT_DATE')),
        sa.Column('left_at', sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint('doctor_id', 'clinic_id'),
        sa.ForeignKeyConstraint(['doctor_id'], ['doctors.id'], name='fk_doctor_clinic_doctor_id'),
        sa.ForeignKeyConstraint(['clinic_id'], ['clinics.id'], name='fk_doctor_clinic_clinic_id'),
    )
    
    # Backfill: one row per existing doctor from doctor.clinic_id with is_primary=True
    connection = op.get_bind()
    doctors = connection.execute(sa.text("SELECT id, clinic_id FROM doctors WHERE clinic_id IS NOT NULL")).fetchall()
    for doc in doctors:
        connection.execute(
            sa.text(
                "INSERT INTO doctor_clinic (doctor_id, clinic_id, is_primary, is_active) "
                "VALUES (:doctor_id, :clinic_id, 1, 1)"
            ),
            {"doctor_id": doc[0], "clinic_id": doc[1]}
        )


def downgrade() -> None:
    op.drop_table('doctor_clinic')
