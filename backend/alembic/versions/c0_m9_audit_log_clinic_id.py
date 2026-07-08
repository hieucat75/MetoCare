"""c0_m9: extend audit_logs with clinic_id

Additive ALTER on the existing `audit_logs` table (DATA_MODEL.md §9):
nullable `clinic_id` (no FK — mirrors the existing bare reference-id
convention on `resource_id`/`actor_id`; AuditLog intentionally never
references entities that might later be pruned/archived independent of the
append-only log) + composite index (clinic_id, timestamp), which matches the
actual query pattern ("this clinic's audit trail, ordered by time") better
than a single-column index alone. No backfill: existing rows correctly get
NULL (they predate any clinic concept).

This is the last migration in the Phase C0 batch — new single head.

Revision ID: c0_m9_audit_log_clinic_id
Revises: c0_m8_clinic_subscription
Create Date: 2026-07-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c0_m9_audit_log_clinic_id"
down_revision = "c0_m8_clinic_subscription"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audit_logs", sa.Column("clinic_id", sa.String(36), nullable=True))
    op.create_index(
        "ix_audit_logs_clinic_timestamp", "audit_logs", ["clinic_id", "timestamp"]
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_clinic_timestamp", table_name="audit_logs")
    op.drop_column("audit_logs", "clinic_id")
