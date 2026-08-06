"""J3/M7 — persisted medication-schedule lifecycle intervals + backfill floor.

P0: a doctor-instructed pause was retroactively converted into missed doses.
`medication_schedules` carried only a CURRENT `status`, so adherence asked "is
this active now?" and got "yes" for a schedule the patient had been told to hold
and had since resumed — backfilling the whole hold as MISSED.

Adds:
  * `medication_schedule_lifecycle_events` — the append-only timeline that
    `status` cannot be. Folded in `effective_at` order it yields the active
    intervals the denominator is computed over.
  * `medication_schedules.tracking_start_at` — the backfill floor. `start_date`
    is client-supplied and routinely predates MetoCare, so an imported old
    prescription used to backfill months of MISSED doses.
  * `dose_occurrences.corrected_*` — a MISSED dose is assigned by a clock, not
    asserted by anyone; these record a correction without destroying what was
    corrected.

Backfill: every existing schedule gets one `activated` event at its `created_at`
and, if it is currently paused or stopped, the matching closing event at
`updated_at`. That is the most conservative reconstruction available from the
columns that exist — it can UNDER-state a historical pause (an old pause whose
`updated_at` has since moved), never invent one, so no patient gains fabricated
non-adherence from the migration itself.

`idempotency_key` is the raw composite `schedule_id|event_type|effective_at`
rather than a hash: it is unique by construction, fits the column, and needs no
database extension, so the backfill cannot fail on a server without pgcrypto.
The service hashes its own keys; the two never collide because a hex digest and
a composite containing '|' and a timestamp are disjoint strings.

Reversible: downgrade drops the table and the added columns and touches nothing
else, so it loses the reconstructed timeline and no other data.

Revision ID: j3_m7_sched_lifecycle
Revises: j4_m10_p15_residual_phi
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "j3_m7_sched_lifecycle"
down_revision: str | None = "j4_m10_p15_residual_phi"
branch_labels = None
depends_on = None

_LIFECYCLE_TABLE = "medication_schedule_lifecycle_events"


def _backfill_events(event_type: str, instant_col: str, reason: str, where: str) -> None:
    """Insert one lifecycle event per matching schedule, deterministically keyed."""
    key = (
        f"(s.id || '|{event_type}|' || CAST(s.{instant_col} AS VARCHAR))"
    )
    op.execute(
        sa.text(
            f"INSERT INTO {_LIFECYCLE_TABLE} "
            "(id, schedule_id, patient_id, event_type, effective_at, actor_id, "
            " actor_role, reason_code, idempotency_key, created_at, updated_at) "
            f"SELECT {key}, s.id, s.patient_id, '{event_type}', s.{instant_col}, NULL, "
            f"  'system', '{reason}', {key}, s.{instant_col}, s.{instant_col} "
            f"FROM medication_schedules s WHERE {where}"
        )
    )


def upgrade() -> None:
    op.create_table(
        _LIFECYCLE_TABLE,
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column(
            "schedule_id",
            sa.String(length=36),
            sa.ForeignKey("medication_schedules.id"),
            nullable=False,
        ),
        sa.Column(
            "patient_id",
            sa.String(length=36),
            sa.ForeignKey("patient_profiles.id"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=True),
        sa.Column(
            "actor_role", sa.String(length=24), nullable=False, server_default="patient"
        ),
        sa.Column(
            "reason_code",
            sa.String(length=48),
            nullable=False,
            server_default="unspecified",
        ),
        sa.Column("note_ref", sa.String(length=64), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
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
        sa.UniqueConstraint("idempotency_key", name="uq_sched_lifecycle_idempotency_key"),
    )
    op.create_index("ix_sched_lifecycle_schedule_id", _LIFECYCLE_TABLE, ["schedule_id"])
    op.create_index("ix_sched_lifecycle_patient_id", _LIFECYCLE_TABLE, ["patient_id"])
    op.create_index("ix_sched_lifecycle_event_type", _LIFECYCLE_TABLE, ["event_type"])
    # The read pattern is always "every event for THIS schedule, in effective
    # order" — once per schedule per adherence request.
    op.create_index(
        "ix_sched_lifecycle_schedule_effective",
        _LIFECYCLE_TABLE,
        ["schedule_id", "effective_at"],
    )

    op.add_column(
        "medication_schedules",
        sa.Column("tracking_start_at", sa.DateTime(timezone=True), nullable=True),
    )
    for col in (
        sa.Column("corrected_from_state", sa.String(length=16), nullable=True),
        sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("corrected_by_actor_id", sa.String(length=36), nullable=True),
        sa.Column("corrected_by_actor_role", sa.String(length=24), nullable=True),
        sa.Column("correction_reason", sa.String(length=48), nullable=True),
    ):
        op.add_column("dose_occurrences", col)

    # ── backfill ─────────────────────────────────────────────────────────────
    # For a row that already exists, "when did MetoCare start observing this?"
    # IS created_at. Nothing is guessed.
    op.execute(
        "UPDATE medication_schedules SET tracking_start_at = created_at "
        "WHERE tracking_start_at IS NULL"
    )
    _backfill_events("activated", "created_at", "backfill_created", "1=1")
    # Closing event for schedules no longer running. `updated_at` can only be at
    # or after the true transition, so this under-states a hold, never invents
    # one. Rows whose updated_at == created_at get no closing event: there is no
    # evidence of when they stopped, and inventing one would be the defect.
    for status in ("paused", "stopped"):
        _backfill_events(
            status,
            "updated_at",
            "backfill_status",
            f"s.status = '{status}' AND s.updated_at > s.created_at",
        )


def downgrade() -> None:
    for name in (
        "correction_reason",
        "corrected_by_actor_role",
        "corrected_by_actor_id",
        "corrected_at",
        "corrected_from_state",
    ):
        op.drop_column("dose_occurrences", name)
    op.drop_column("medication_schedules", "tracking_start_at")
    for idx in (
        "ix_sched_lifecycle_schedule_effective",
        "ix_sched_lifecycle_event_type",
        "ix_sched_lifecycle_patient_id",
        "ix_sched_lifecycle_schedule_id",
    ):
        op.drop_index(idx, table_name=_LIFECYCLE_TABLE)
    op.drop_table(_LIFECYCLE_TABLE)
