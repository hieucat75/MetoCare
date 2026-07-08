"""c0_m7: create subscription_plans

New table (DATA_MODEL.md §7) — platform-wide, not clinic-scoped catalog of
plan tiers + entitlements. Unique `code`. Seeding the 4 standard tiers
(trial/basic/professional/enterprise) is done in `upgrade()` via `op.bulk_insert`
so the FK from `clinic_subscriptions.plan_id` (c0_m8) always has a valid
target immediately after this migration runs — entitlement values are
technical placeholders (DATA_MODEL.md §7 "Open question flagged, not
blocking"), not a final product decision.

Revision ID: c0_m7_subscription_plan
Revises: c0_m6_clinic_patient_rel
Create Date: 2026-07-08
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "c0_m7_subscription_plan"
down_revision = "c0_m6_clinic_patient_rel"
branch_labels = None
depends_on = None

_plans_table = sa.table(
    "subscription_plans",
    sa.column("id", sa.String),
    sa.column("code", sa.String),
    sa.column("name", sa.String),
    sa.column("entitlements", sa.JSON),
)

_SEED_PLANS = [
    {
        "code": "trial",
        "name": "Dùng thử",
        "entitlements": {
            "max_branches": 1,
            "max_doctors": 2,
            "max_active_patients": 100,
            "copilot_quota_per_month": 50,
            "crm_automation_enabled": False,
            "advanced_reports_enabled": False,
            "api_sso_enabled": False,
        },
    },
    {
        "code": "basic",
        "name": "Cơ bản",
        "entitlements": {
            "max_branches": 1,
            "max_doctors": 5,
            "max_active_patients": 500,
            "copilot_quota_per_month": 200,
            "crm_automation_enabled": False,
            "advanced_reports_enabled": False,
            "api_sso_enabled": False,
        },
    },
    {
        "code": "professional",
        "name": "Chuyên nghiệp",
        "entitlements": {
            "max_branches": 3,
            "max_doctors": 20,
            "max_active_patients": 3000,
            "copilot_quota_per_month": 1000,
            "crm_automation_enabled": True,
            "advanced_reports_enabled": True,
            "api_sso_enabled": False,
        },
    },
    {
        "code": "enterprise",
        "name": "Doanh nghiệp",
        "entitlements": {
            "max_branches": 999,
            "max_doctors": 999,
            "max_active_patients": 999999,
            "copilot_quota_per_month": 999999,
            "crm_automation_enabled": True,
            "advanced_reports_enabled": True,
            "api_sso_enabled": True,
        },
    },
]


def upgrade() -> None:
    op.create_table(
        "subscription_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("entitlements", sa.JSON(), nullable=False),
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
        sa.UniqueConstraint("code", name="uq_subscription_plans_code"),
    )
    op.bulk_insert(
        _plans_table,
        [{"id": str(uuid.uuid4()), **plan} for plan in _SEED_PLANS],
    )


def downgrade() -> None:
    op.drop_table("subscription_plans")
