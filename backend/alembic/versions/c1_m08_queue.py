"""c1_m08: create clinic_queue_entries + clinic_queue_counters

Check-in & Queue (M08_IMPLEMENTATION_PLAN.md §2). Additive only — no
existing table is altered; `ClinicAppointmentSource.WALK_IN` is a
Python-only enum addition (String(20) column, no DDL).

Key invariants enforced at the DB layer:
- UNIQUE `appointment_id`: one queue entry per appointment, ever — the
  INSERT is the serialization point for concurrent double check-ins
  (loser gets IntegrityError -> controlled 409, whole tx rolls back).
- Partial unique `(clinic_id, patient_id)` WHERE status active: one active
  queue entry per patient per clinic (ClinicInvitation dual-syntax
  `postgresql_where`/`sqlite_where` pattern).
- `clinic_queue_counters` UNIQUE `(clinic_id, branch_id, scope_key,
  counter_date)` + partial unique on `(clinic_id, scope_key, counter_date)`
  WHERE `branch_id IS NULL`: `branch_id` is nullable (documented deviation
  from plan §2 NOT NULL) because the `clinic_day` reset scope needs one
  clinic-wide counter row shared across branches, and SQL NULLs are
  pairwise distinct under a plain UNIQUE constraint.

Revision ID: c1_m08_queue
Revises: c1_m07_appointments
Create Date: 2026-07-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c1_m08_queue"
down_revision = "c1_m07_appointments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clinic_queue_entries",
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
            "appointment_id",
            sa.String(36),
            sa.ForeignKey("clinic_appointments.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "doctor_id",
            sa.String(36),
            sa.ForeignKey("doctors.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("queue_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="waiting"),
        # sa.false(), not text("0"): Postgres rejects an integer DEFAULT on a
        # boolean column — SQLite-invisible, Postgres-only failure class (PR
        # #93 incident precedent); c0_m3_clinic_membership.is_primary is the
        # in-repo pattern.
        sa.Column("is_priority", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("priority_reason", sa.Text(), nullable=True),
        sa.Column(
            "priority_set_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("missed_call_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column(
            "checked_in_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("called_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consultation_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
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
        "ix_clinic_queue_entries_clinic_branch_date",
        "clinic_queue_entries",
        ["clinic_id", "branch_id", "service_date"],
    )
    op.create_index(
        "ix_clinic_queue_entries_clinic_status",
        "clinic_queue_entries",
        ["clinic_id", "status"],
    )
    op.create_index(
        "uq_clinic_queue_entries_active_patient",
        "clinic_queue_entries",
        ["clinic_id", "patient_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('waiting', 'called', 'in_consultation')"),
        sqlite_where=sa.text("status IN ('waiting', 'called', 'in_consultation')"),
    )

    op.create_table(
        "clinic_queue_counters",
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
            nullable=True,
        ),
        sa.Column("scope_key", sa.String(64), nullable=False),
        sa.Column("counter_date", sa.Date(), nullable=False),
        sa.Column("last_number", sa.Integer(), nullable=False),
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
        sa.UniqueConstraint(
            "clinic_id",
            "branch_id",
            "scope_key",
            "counter_date",
            name="uq_clinic_queue_counters_scope",
        ),
    )
    op.create_index(
        "uq_clinic_queue_counters_clinic_scope",
        "clinic_queue_counters",
        ["clinic_id", "scope_key", "counter_date"],
        unique=True,
        postgresql_where=sa.text("branch_id IS NULL"),
        sqlite_where=sa.text("branch_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_clinic_queue_counters_clinic_scope", table_name="clinic_queue_counters")
    op.drop_table("clinic_queue_counters")
    op.drop_index("uq_clinic_queue_entries_active_patient", table_name="clinic_queue_entries")
    op.drop_index("ix_clinic_queue_entries_clinic_status", table_name="clinic_queue_entries")
    op.drop_index(
        "ix_clinic_queue_entries_clinic_branch_date", table_name="clinic_queue_entries"
    )
    op.drop_table("clinic_queue_entries")
