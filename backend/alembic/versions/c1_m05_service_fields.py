"""c1_m05: extend clinic_services with BRD §5.3 catalog fields

Additive ALTER on the existing `clinic_services` table
(`docs/brd/v2.0/m05-services-pricing.md` §5.3). The table is verifiably
empty at migration time — every clinic-scoped route is gated behind
`require_clinic_saas_enabled` and `CLINIC_SAAS` defaults `False` everywhere
(no environment has ever enabled it, per `docs/clinic-saas/STATUS.md`), so no
direct-write path could have created a row — the same justification already
used for `clinics.status` in `c0_m1_clinic_extend_columns` applies here to
`type` (NOT NULL with a constant `server_default`).

Adds:
- `code` (nullable — required only at the Create-schema layer, per the
  project's "validate at service/schema layer" convention) + partial unique
  index `(clinic_id, code) WHERE code IS NOT NULL`.
- `specialty`, `duration_minutes`, `doctor_ids` — nullable, no backfill
  concern (new columns on an empty table).
- `type` — NOT NULL, `server_default='single'` (single-step ALTER, same
  pattern as `clinics.status`).
- `duration_months`, `included_items`, `benefits`,
  `cancellation_refund_policy` — nullable, `type=package`-only fields.

No column dropped, renamed, or retyped. Both `upgrade()`/`downgrade()`
provided; `downgrade()` is a symmetric removal (no data-loss ambiguity since
nothing here transforms pre-existing data).

Revision ID: c1_m05_service_fields
Revises: c0_m9_audit_log_clinic_id
Create Date: 2026-07-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c1_m05_service_fields"
down_revision = "c0_m9_audit_log_clinic_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clinic_services", sa.Column("code", sa.String(32), nullable=True))
    op.add_column("clinic_services", sa.Column("specialty", sa.String(64), nullable=True))
    op.add_column(
        "clinic_services", sa.Column("duration_minutes", sa.Integer(), nullable=True)
    )
    op.add_column("clinic_services", sa.Column("doctor_ids", sa.JSON(), nullable=True))
    op.add_column(
        "clinic_services",
        sa.Column("type", sa.String(16), nullable=False, server_default="single"),
    )
    op.add_column(
        "clinic_services", sa.Column("duration_months", sa.Integer(), nullable=True)
    )
    op.add_column("clinic_services", sa.Column("included_items", sa.JSON(), nullable=True))
    op.add_column("clinic_services", sa.Column("benefits", sa.JSON(), nullable=True))
    op.add_column(
        "clinic_services", sa.Column("cancellation_refund_policy", sa.JSON(), nullable=True)
    )
    op.create_index(
        "uq_clinic_services_clinic_code",
        "clinic_services",
        ["clinic_id", "code"],
        unique=True,
        postgresql_where=sa.text("code IS NOT NULL"),
        sqlite_where=sa.text("code IS NOT NULL"),
    )
    # Codex second-pass review P1: name uniqueness (BR-M05 §5.3 "Unique
    # trong tenant") was only a service-layer check-then-insert, racy under
    # concurrency — a real DB constraint closes that race. Table verified
    # empty (see module docstring), so a plain unique index is safe to add
    # directly. A plain index (not a named UniqueConstraint) because SQLite
    # can't ALTER/DROP a constraint without batch mode, but an index drops
    # cleanly on both SQLite and Postgres.
    op.create_index(
        "uq_clinic_services_clinic_name",
        "clinic_services",
        ["clinic_id", "name"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_clinic_services_clinic_name", table_name="clinic_services")
    op.drop_index("uq_clinic_services_clinic_code", table_name="clinic_services")
    op.drop_column("clinic_services", "cancellation_refund_policy")
    op.drop_column("clinic_services", "benefits")
    op.drop_column("clinic_services", "included_items")
    op.drop_column("clinic_services", "duration_months")
    op.drop_column("clinic_services", "type")
    op.drop_column("clinic_services", "doctor_ids")
    op.drop_column("clinic_services", "duration_minutes")
    op.drop_column("clinic_services", "specialty")
    op.drop_column("clinic_services", "code")
