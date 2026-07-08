"""c0_m8: create clinic_subscriptions

New table (DATA_MODEL.md §8). Deviates from a flat unique `clinic_id`
(TENANT_ARCHITECTURE.md §2.8) in favor of a partial unique index on
`clinic_id` WHERE `status IN ('trial', 'active')` — guarantees at most one
*current* subscription per clinic while preserving expired/cancelled history
rows (the "no hard delete, keep history" principle applied elsewhere in this
design). ON DELETE RESTRICT on both clinic_id and plan_id.

Revision ID: c0_m8_clinic_subscription
Revises: c0_m7_subscription_plan
Create Date: 2026-07-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c0_m8_clinic_subscription"
down_revision = "c0_m7_subscription_plan"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clinic_subscriptions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "clinic_id",
            sa.String(36),
            sa.ForeignKey("clinics.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "plan_id",
            sa.String(36),
            sa.ForeignKey("subscription_plans.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="trial"),
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
    )
    op.create_index(
        "ix_clinic_subscriptions_clinic_id", "clinic_subscriptions", ["clinic_id"]
    )
    op.create_index(
        "uq_clinic_subscriptions_current",
        "clinic_subscriptions",
        ["clinic_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('trial', 'active')"),
        sqlite_where=sa.text("status IN ('trial', 'active')"),
    )


def downgrade() -> None:
    op.drop_index("uq_clinic_subscriptions_current", table_name="clinic_subscriptions")
    op.drop_index("ix_clinic_subscriptions_clinic_id", table_name="clinic_subscriptions")
    op.drop_table("clinic_subscriptions")
