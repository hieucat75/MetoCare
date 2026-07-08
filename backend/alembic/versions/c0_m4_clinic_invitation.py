"""c0_m4: create clinic_invitations

New table (DATA_MODEL.md §4). Unique token_hash; CHECK (email or phone
present); partial unique indexes on (clinic_id, invited_email) and
(clinic_id, invited_phone) WHERE status='pending' — prevents duplicate live
invites for the same address (schema-level gap flagged beyond
TENANT_ARCHITECTURE.md §2.4). ON DELETE CASCADE on clinic_id.

Revision ID: c0_m4_clinic_invitation
Revises: c0_m3_clinic_membership
Create Date: 2026-07-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c0_m4_clinic_invitation"
down_revision = "c0_m3_clinic_membership"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clinic_invitations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "clinic_id",
            sa.String(36),
            sa.ForeignKey("clinics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("invited_email", sa.String(255), nullable=True),
        sa.Column("invited_phone", sa.String(20), nullable=True),
        sa.Column("roles", sa.JSON(), nullable=False),
        sa.Column("branch_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("token_hash", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "invited_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "accepted_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.UniqueConstraint("token_hash", name="uq_clinic_invitations_token_hash"),
        sa.CheckConstraint(
            "invited_email IS NOT NULL OR invited_phone IS NOT NULL",
            name="ck_clinic_invitations_email_or_phone",
        ),
    )
    op.create_index("ix_clinic_invitations_clinic_id", "clinic_invitations", ["clinic_id"])
    op.create_index(
        "ix_clinic_invitations_token_hash", "clinic_invitations", ["token_hash"]
    )
    op.create_index(
        "uq_clinic_invitations_pending_email",
        "clinic_invitations",
        ["clinic_id", "invited_email"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
        sqlite_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "uq_clinic_invitations_pending_phone",
        "clinic_invitations",
        ["clinic_id", "invited_phone"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
        sqlite_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("uq_clinic_invitations_pending_phone", table_name="clinic_invitations")
    op.drop_index("uq_clinic_invitations_pending_email", table_name="clinic_invitations")
    op.drop_index("ix_clinic_invitations_token_hash", table_name="clinic_invitations")
    op.drop_index("ix_clinic_invitations_clinic_id", table_name="clinic_invitations")
    op.drop_table("clinic_invitations")
