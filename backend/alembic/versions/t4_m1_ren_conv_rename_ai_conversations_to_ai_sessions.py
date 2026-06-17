"""rename ai conversations to ai sessions

Revision ID: t4_m1_ren_conv
Revises: a1b2c3d4e5f6
Create Date: 2026-06-17 13:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 't4_m1_ren_conv'
down_revision: str | None = 't4_m0_role'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # B3 Fix: added 'ai_use' allowed value for Consent.consent_type.
    # Note: since the consents.consent_type column is sa.String(48) without DB-level CHECK constraints,
    # the schema already supports any string value including 'ai_use'.
    
    # Rename table
    op.rename_table('ai_conversations', 'ai_sessions')
    
    # Rename column intent -> session_type
    with op.batch_alter_table('ai_sessions', schema=None) as batch_op:
        batch_op.alter_column('intent', new_column_name='session_type', existing_type=sa.String(length=64))


def downgrade() -> None:
    # Rename column session_type -> intent
    with op.batch_alter_table('ai_sessions', schema=None) as batch_op:
        batch_op.alter_column('session_type', new_column_name='intent', existing_type=sa.String(length=64))
        
    # Rename table back
    op.rename_table('ai_sessions', 'ai_conversations')
