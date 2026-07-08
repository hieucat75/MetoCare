"""c0_m1: extend clinics with Clinic SaaS Phase C0 tenant columns

Additive-only ALTER on the existing `clinics` table (DATA_MODEL.md §1):
legal_name, tax_code, license_no, clinic_type, status (NOT NULL,
server_default='trial'), branding, cancellation_policy, queue_config,
overbooking_policy, deactivated_at, restored_at. `status` is NOT NULL with a
static server_default, so no separate backfill step is needed (same
one-step pattern precedented in t13_p0_note_draft_status.py, MIGRATION_STRATEGY.md §3).

Revision ID: c0_m1_clinic_extend_columns
Revises: t13_p0_note_draft_status
Create Date: 2026-07-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c0_m1_clinic_extend_columns"
down_revision = "t13_p0_note_draft_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clinics", sa.Column("legal_name", sa.String(255), nullable=True))
    op.add_column("clinics", sa.Column("tax_code", sa.String(20), nullable=True))
    op.add_column("clinics", sa.Column("license_no", sa.String(64), nullable=True))
    op.add_column("clinics", sa.Column("clinic_type", sa.String(32), nullable=True))
    op.add_column(
        "clinics",
        sa.Column("status", sa.String(16), nullable=False, server_default="trial"),
    )
    op.add_column("clinics", sa.Column("branding", sa.JSON(), nullable=True))
    op.add_column("clinics", sa.Column("cancellation_policy", sa.JSON(), nullable=True))
    op.add_column("clinics", sa.Column("queue_config", sa.JSON(), nullable=True))
    op.add_column("clinics", sa.Column("overbooking_policy", sa.JSON(), nullable=True))
    op.add_column(
        "clinics", sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "clinics", sa.Column("restored_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("clinics", "restored_at")
    op.drop_column("clinics", "deactivated_at")
    op.drop_column("clinics", "overbooking_policy")
    op.drop_column("clinics", "queue_config")
    op.drop_column("clinics", "cancellation_policy")
    op.drop_column("clinics", "branding")
    op.drop_column("clinics", "status")
    op.drop_column("clinics", "clinic_type")
    op.drop_column("clinics", "license_no")
    op.drop_column("clinics", "tax_code")
    op.drop_column("clinics", "legal_name")
