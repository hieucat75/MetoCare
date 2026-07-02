"""add terms_consents table

Revision ID: a1_terms_consents
Revises: 1ec6f403fced
Create Date: 2026-07-02 00:00:00.000000

Terms of Use / Privacy Policy acceptance recorded at registration.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1_terms_consents"
down_revision: str | None = "1ec6f403fced"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "terms_consents",
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("terms_version", sa.String(32), nullable=False),
        sa.Column("privacy_version", sa.String(32), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("app_version", sa.String(32), nullable=True),
        sa.Column("locale", sa.String(32), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("device_platform", sa.String(64), nullable=True),
        sa.Column("accepted_source", sa.String(32), nullable=True),
        sa.Column("accepted_language", sa.String(32), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(36), nullable=False),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "terms_version", name="uq_terms_consent_user_version"),
    )
    with op.batch_alter_table("terms_consents", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_terms_consents_user_id"), ["user_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("terms_consents", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_terms_consents_user_id"))
    op.drop_table("terms_consents")
