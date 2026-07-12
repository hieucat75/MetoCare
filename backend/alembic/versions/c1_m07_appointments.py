"""c1_m07: create clinic_appointments

New table (M07_IMPLEMENTATION_PLAN.md §2) — a third, clinic-scoped
appointment table, distinct from both the legacy `appointments`
(`app/models/care.py`, doctor-handoff/encounter-flow entity) and the
marketplace `booking_appointments`/`doctor_availability` (T21 scaffold,
clinic-agnostic, keyed to `users.id`). No consultation/marketplace code path
is touched here.

Double-booking guarantee (AC-M07-02): partial unique index on
`(doctor_id, start_time)` WHERE `status NOT IN ('cancelled', 'no_show') AND
doctor_id IS NOT NULL`, portable across SQLite/Postgres via the existing
`postgresql_where`/`sqlite_where` dual-syntax pattern (`ClinicInvitation`'s
pending-email/phone indexes, c0_m4_clinic_invitation). This catches
exact-start-time collisions; the service layer additionally does a
best-effort overlap pre-check for free-form overlapping-but-different-
start-time bookings (documented gap — true DB-level range-overlap exclusion
via Postgres `EXCLUDE USING gist` is SQLite-incompatible and would break the
upgrade/downgrade/upgrade-on-SQLite verification step).

`reschedule_of_id` is a self-referencing FK (RESTRICT) — "đổi lịch =
Cancelled(cũ) + lịch mới liên kết" (BRD §7.5) is modeled as a backward
pointer from the new row; the chain of appointments *is* the reschedule
history, no separate history table (same discipline as M05's
price-audit-via-AuditLog decision).

Revision ID: c1_m07_appointments
Revises: c1_m06_patient_metadata
Create Date: 2026-07-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c1_m07_appointments"
down_revision = "c1_m06_patient_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clinic_appointments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "clinic_id",
            sa.String(36),
            sa.ForeignKey("clinics.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "branch_id",
            sa.String(36),
            sa.ForeignKey("clinic_branches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "patient_id",
            sa.String(36),
            sa.ForeignKey("patient_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "doctor_id",
            sa.String(36),
            sa.ForeignKey("doctors.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "service_id",
            sa.String(36),
            sa.ForeignKey("clinic_services.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("price_snapshot", sa.Numeric(12, 2), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column(
            "created_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_by_source", sa.String(20), nullable=False),
        # Bare reference, no FK — M11 Care Plan doesn't exist yet (same
        # discipline as AuditLog.resource_id).
        sa.Column("linked_care_plan_item_id", sa.String(36), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column(
            "cancelled_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "reschedule_of_id",
            sa.String(36),
            sa.ForeignKey("clinic_appointments.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
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
        "ix_clinic_appointments_clinic_branch_start",
        "clinic_appointments",
        ["clinic_id", "branch_id", "start_time"],
    )
    op.create_index(
        "ix_clinic_appointments_clinic_doctor_start",
        "clinic_appointments",
        ["clinic_id", "doctor_id", "start_time"],
    )
    op.create_index(
        "ix_clinic_appointments_clinic_status",
        "clinic_appointments",
        ["clinic_id", "status"],
    )
    op.create_index(
        "uq_clinic_appointments_doctor_start",
        "clinic_appointments",
        ["doctor_id", "start_time"],
        unique=True,
        postgresql_where=sa.text(
            "status NOT IN ('cancelled', 'no_show') AND doctor_id IS NOT NULL"
        ),
        sqlite_where=sa.text(
            "status NOT IN ('cancelled', 'no_show') AND doctor_id IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_clinic_appointments_doctor_start", table_name="clinic_appointments")
    op.drop_index("ix_clinic_appointments_clinic_status", table_name="clinic_appointments")
    op.drop_index("ix_clinic_appointments_clinic_doctor_start", table_name="clinic_appointments")
    op.drop_index("ix_clinic_appointments_clinic_branch_start", table_name="clinic_appointments")
    op.drop_table("clinic_appointments")
