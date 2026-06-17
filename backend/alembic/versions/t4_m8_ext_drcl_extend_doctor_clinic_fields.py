"""extend doctor clinic fields

Revision ID: t4_m8_ext_drcl
Revises: t4_m7_add_junc
Create Date: 2026-06-17 13:35:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 't4_m8_ext_drcl'
down_revision: str | None = 't4_m7_add_junc'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('doctors', schema=None) as batch_op:
        batch_op.add_column(sa.Column('bio', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('avatar_url', sa.String(length=512), nullable=True))
        batch_op.add_column(sa.Column('consultation_fee', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('is_verified', sa.Boolean(), nullable=False, server_default=sa.text('0')))
        batch_op.add_column(sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')))
        
    with op.batch_alter_table('clinics', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('specialty_tags', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('operating_hours', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')))
        batch_op.add_column(sa.Column('is_verified', sa.Boolean(), nullable=False, server_default=sa.text('0')))


def downgrade() -> None:
    with op.batch_alter_table('clinics', schema=None) as batch_op:
        batch_op.drop_column('is_verified')
        batch_op.drop_column('is_active')
        batch_op.drop_column('operating_hours')
        batch_op.drop_column('specialty_tags')
        batch_op.drop_column('email')
        
    with op.batch_alter_table('doctors', schema=None) as batch_op:
        batch_op.drop_column('is_active')
        batch_op.drop_column('is_verified')
        batch_op.drop_column('consultation_fee')
        batch_op.drop_column('avatar_url')
        batch_op.drop_column('bio')
