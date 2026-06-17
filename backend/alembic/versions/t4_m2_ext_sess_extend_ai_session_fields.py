"""extend ai session fields

Revision ID: t4_m2_ext_sess
Revises: t4_m1_ren_conv
Create Date: 2026-06-17 13:05:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 't4_m2_ext_sess'
down_revision: str | None = 't4_m1_ren_conv'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # TODO: Defer M3 data migration (encrypt existing messages) until a separate, tested decrypt path is available.
    
    with op.batch_alter_table('ai_sessions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('encounter_id', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('escalation_reason', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('input_blocked', sa.Boolean(), nullable=False, server_default=sa.text('0')))
        batch_op.add_column(sa.Column('output_blocked', sa.Boolean(), nullable=False, server_default=sa.text('0')))
        batch_op.add_column(sa.Column('total_tokens', sa.Integer(), nullable=True, server_default='0'))
        batch_op.add_column(sa.Column('key_version', sa.Integer(), nullable=True, server_default='1'))
        batch_op.add_column(sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('deleted_by', sa.String(length=36), nullable=True))
        
        # Only add FKs on non-SQLite (SQLite doesn't enforce FKs and batch_alter
        # reflection fails if the referenced table is absent during downgrade)
        import sqlalchemy as _sa
        bind = op.get_context().bind
        if bind is not None and bind.dialect.name != 'sqlite':
            batch_op.create_foreign_key(
                'fk_ai_sessions_encounter_id', 'encounters', ['encounter_id'], ['id']
            )
            batch_op.create_foreign_key(
                'fk_ai_sessions_deleted_by', 'users', ['deleted_by'], ['id']
            )
        batch_op.create_index('ix_ai_sessions_encounter_id', ['encounter_id'], unique=False)


def downgrade() -> None:
    bind = op.get_context().bind
    is_sqlite = bind is not None and bind.dialect.name == 'sqlite'
    with op.batch_alter_table('ai_sessions', schema=None) as batch_op:
        batch_op.drop_index('ix_ai_sessions_encounter_id')
        if not is_sqlite:
            batch_op.drop_constraint('fk_ai_sessions_deleted_by', type_='foreignkey')
            batch_op.drop_constraint('fk_ai_sessions_encounter_id', type_='foreignkey')
        batch_op.drop_column('deleted_by')
        batch_op.drop_column('deleted_at')
        batch_op.drop_column('key_version')
        batch_op.drop_column('total_tokens')
        batch_op.drop_column('output_blocked')
        batch_op.drop_column('input_blocked')
        batch_op.drop_column('escalation_reason')
        batch_op.drop_column('encounter_id')
