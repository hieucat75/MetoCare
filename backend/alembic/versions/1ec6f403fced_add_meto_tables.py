"""add_meto_tables

Revision ID: 1ec6f403fced
Revises: t9_m2_drug_seed
Create Date: 2026-07-01 00:28:56.666118

NOTE: Only creates the four new Meto AI tables. Schema drift in existing tables
is handled by the codebase keeping ORM models in sync with prior migrations.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '1ec6f403fced'
down_revision: str | None = 't9_m2_drug_seed'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'meto_conversations',
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('screen_id', sa.String(64), nullable=True),
        sa.Column('title', sa.String(255), nullable=True),
        sa.Column('status', sa.String(32), nullable=False, server_default='active'),
        sa.Column('message_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('provider_used', sa.String(32), nullable=True),
        sa.Column('last_active_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('meto_conversations') as batch_op:
        batch_op.create_index('ix_meto_conversations_user_id', ['user_id'], unique=False)

    op.create_table(
        'meto_messages',
        sa.Column('conversation_id', sa.String(36), nullable=False),
        sa.Column('role', sa.String(16), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('screen_id', sa.String(64), nullable=True),
        sa.Column('tool_calls', sa.JSON(), nullable=True),
        sa.Column('tool_results', sa.JSON(), nullable=True),
        sa.Column('provider', sa.String(32), nullable=True),
        sa.Column('model', sa.String(64), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('output_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('fallback_used', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['meto_conversations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('meto_messages') as batch_op:
        batch_op.create_index('ix_meto_messages_conversation_id', ['conversation_id'], unique=False)

    op.create_table(
        'meto_audit_logs',
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('conversation_id', sa.String(36), nullable=True),
        sa.Column('action', sa.String(64), nullable=False),
        sa.Column('screen_id', sa.String(64), nullable=True),
        sa.Column('context_types', sa.JSON(), nullable=True),
        sa.Column('provider_used', sa.String(32), nullable=True),
        sa.Column('fallback_used', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('safety_flags_detected', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('escalation_triggered', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('response_time_ms', sa.Integer(), nullable=True),
        sa.Column('token_count_input', sa.Integer(), nullable=True),
        sa.Column('token_count_output', sa.Integer(), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('meto_audit_logs') as batch_op:
        batch_op.create_index('ix_meto_audit_logs_user_id', ['user_id'], unique=False)
        batch_op.create_index('ix_meto_audit_logs_conversation_id', ['conversation_id'], unique=False)

    op.create_table(
        'meto_consents',
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('context_type', sa.String(64), nullable=False),
        sa.Column('granted', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('granted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('meto_consents') as batch_op:
        batch_op.create_index('ix_meto_consents_user_id', ['user_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('meto_consents') as batch_op:
        batch_op.drop_index('ix_meto_consents_user_id')
    op.drop_table('meto_consents')

    with op.batch_alter_table('meto_audit_logs') as batch_op:
        batch_op.drop_index('ix_meto_audit_logs_conversation_id')
        batch_op.drop_index('ix_meto_audit_logs_user_id')
    op.drop_table('meto_audit_logs')

    with op.batch_alter_table('meto_messages') as batch_op:
        batch_op.drop_index('ix_meto_messages_conversation_id')
    op.drop_table('meto_messages')

    with op.batch_alter_table('meto_conversations') as batch_op:
        batch_op.drop_index('ix_meto_conversations_user_id')
    op.drop_table('meto_conversations')
