"""add soft delete columns

Revision ID: t4_m9_add_sdel
Revises: t4_m8_ext_drcl
Create Date: 2026-06-17 13:40:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 't4_m9_add_sdel'
down_revision: str | None = 't4_m8_ext_drcl'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('lab_results', schema=None) as batch_op:
        batch_op.add_column(sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('deleted_by', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key('fk_lab_results_deleted_by', 'users', ['deleted_by'], ['id'])
        
    with op.batch_alter_table('medications', schema=None) as batch_op:
        batch_op.add_column(sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('deleted_by', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key('fk_medications_deleted_by', 'users', ['deleted_by'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('medications', schema=None) as batch_op:
        batch_op.drop_constraint('fk_medications_deleted_by', type_='foreignkey')
        batch_op.drop_column('deleted_by')
        batch_op.drop_column('deleted_at')
        
    with op.batch_alter_table('lab_results', schema=None) as batch_op:
        batch_op.drop_constraint('fk_lab_results_deleted_by', type_='foreignkey')
        batch_op.drop_column('deleted_by')
        batch_op.drop_column('deleted_at')
