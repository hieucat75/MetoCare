"""add encounter FK to ai_sessions (after encounters table created)

Revision ID: t4_m4b_enc_fk
Revises: t4_m4_add_encs
Create Date: 2026-06-17 14:30:00.000000

Purpose:
    C5 fix — the encounter_id FK was incorrectly placed in M2, before the 'encounters'
    table existed (created in M4). This migration runs after M4 and adds the FK safely.

Migration order after fix:
    M1 → M2 (columns only, no encounter FK) → M3 → M4 (creates encounters) →
    M4b (adds encounter FK) → M5 → M6 → M7 → M8 → M9
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 't4_m4b_enc_fk'
down_revision: str | None = 't4_m4_add_encs'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_context().bind
    if bind is not None and bind.dialect.name != 'sqlite':
        with op.batch_alter_table('ai_sessions', schema=None) as batch_op:
            batch_op.create_foreign_key(
                'fk_ai_sessions_encounter_id', 'encounters', ['encounter_id'], ['id']
            )


def downgrade() -> None:
    bind = op.get_context().bind
    if bind is not None and bind.dialect.name != 'sqlite':
        with op.batch_alter_table('ai_sessions', schema=None) as batch_op:
            batch_op.drop_constraint('fk_ai_sessions_encounter_id', type_='foreignkey')
