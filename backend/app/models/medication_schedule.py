"""Medication scheduling models (Master Plan §1.8, BRD §G).

A structured schedule + materialized dose occurrences that drive the reminder /
adherence loop (Journey 3). Only CONFIRMED medication data may create a schedule
(enforced in the service layer). Instants are stored in UTC and rendered in the
patient's local timezone; dose occurrences carry an idempotency key so a
concurrency-safe scheduler retries without creating duplicate dose events.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from ._mixins import TimestampMixin, UUIDPrimaryKey, _uuid

_JSON_VARIANT = JSON().with_variant(JSONB(astext_type=Text()), "postgresql")

# schedule_type
SCHEDULE_FIXED_DAILY = "fixed_daily"
SCHEDULE_INTERVAL = "interval"
SCHEDULE_DAYS_OF_WEEK = "days_of_week"
SCHEDULE_CYCLIC = "cyclic"
SCHEDULE_PRN = "prn"

# schedule status
SCHED_STATUS_ACTIVE = "active"
SCHED_STATUS_PAUSED = "paused"
SCHED_STATUS_STOPPED = "stopped"
SCHED_STATUS_COMPLETED = "completed"

# dose occurrence state
DOSE_PENDING = "pending"
DOSE_NOTIFIED = "notified"
DOSE_TAKEN = "taken"
DOSE_SKIPPED = "skipped"
DOSE_MISSED = "missed"

# schedule lifecycle event types (§1.8 — the persisted timeline).
#
# `MedicationSchedule.status` is a single CURRENT value, so it can answer "is this
# running now?" and nothing else. Adherence has to answer "was this running on the
# 14th?", and reconstructing that from a current status is not merely imprecise:
# it is wrong in one specific direction. A schedule that is active TODAY reads as
# having been active for the whole window, so a doctor-instructed hold the patient
# obeyed comes back as a block of MISSED doses the moment they resume.
LIFECYCLE_ACTIVATED = "activated"
LIFECYCLE_PAUSED = "paused"
LIFECYCLE_RESUMED = "resumed"
LIFECYCLE_STOPPED = "stopped"
LIFECYCLE_SUPERSEDED = "superseded"

# Events that OPEN an active interval, and events that CLOSE one.
LIFECYCLE_OPENING = frozenset({LIFECYCLE_ACTIVATED, LIFECYCLE_RESUMED})
LIFECYCLE_CLOSING = frozenset({LIFECYCLE_PAUSED, LIFECYCLE_STOPPED, LIFECYCLE_SUPERSEDED})
# Terminal: nothing may follow one of these on the same schedule.
LIFECYCLE_TERMINAL = frozenset({LIFECYCLE_STOPPED, LIFECYCLE_SUPERSEDED})
LIFECYCLE_EVENT_TYPES = LIFECYCLE_OPENING | LIFECYCLE_CLOSING


class MedicationSchedule(UUIDPrimaryKey, TimestampMixin, Base):
    """A structured dosing schedule for a confirmed medication (§1.8)."""

    __tablename__ = "medication_schedules"

    medication_id: Mapped[str] = mapped_column(
        ForeignKey("medications.id"), index=True, nullable=False
    )
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    # IANA tz (e.g. Asia/Ho_Chi_Minh); all instants stored UTC, rendered in this tz.
    patient_timezone: Mapped[str] = mapped_column(
        String(64), default="Asia/Ho_Chi_Minh", server_default="Asia/Ho_Chi_Minh"
    )
    schedule_type: Mapped[str] = mapped_column(String(24), nullable=False)
    # Wall-clock dose times in patient_timezone, e.g. ["08:00","20:00"].
    local_dose_times: Mapped[list | None] = mapped_column(_JSON_VARIANT)
    # Structured recurrence rule (interval days, days-of-week, cyclic on/off, …).
    recurrence: Mapped[dict | None] = mapped_column(_JSON_VARIANT)
    start_date: Mapped[dt.date | None] = mapped_column(Date)
    end_date: Mapped[dt.date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        String(16), default=SCHED_STATUS_ACTIVE, server_default=SCHED_STATUS_ACTIVE, index=True
    )
    source: Mapped[str] = mapped_column(
        String(24), default="manual", server_default="manual"
    )  # manual | prescription_ocr | doctor
    verification_status: Mapped[str | None] = mapped_column(String(24))
    # Deduplicates a schedule per medication+rule; edits create a new version.
    dedupe_key: Mapped[str | None] = mapped_column(String(128), index=True)
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    superseded_by: Mapped[str | None] = mapped_column(
        ForeignKey("medication_schedules.id"), nullable=True
    )
    # THE BACKFILL FLOOR. `start_date` is client-supplied and routinely predates
    # MetoCare: a patient importing an old prescription states the date the
    # PRESCRIPTION began, not the date this app began observing them. Without a
    # floor, "I started this in March" was silently converted into months of
    # MISSED doses and a 0% rate on the patient's very first screen — encoding
    # "we were not watching" as "you did not take it", which is the same
    # fabrication as the pause defect reached from the other end.
    #
    # NULL means "not recorded" and is floored at `created_at` (see
    # `tracking_floor`). Retrospective adherence is OPT-IN: a caller that has
    # actual historical evidence may set this earlier than `created_at`
    # explicitly, and it is echoed in every adherence response so the floor that
    # produced a number is always visible.
    tracking_start_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class DoseOccurrence(UUIDPrimaryKey, TimestampMixin, Base):
    """A single materialized dose event for a schedule (§1.8).

    ``idempotency_key = hash(schedule_id, schedule_version, scheduled_utc)`` with a
    unique constraint so the scheduler can retry without creating duplicate doses.
    """

    __tablename__ = "dose_occurrences"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_dose_idempotency_key"),
    )

    schedule_id: Mapped[str] = mapped_column(
        ForeignKey("medication_schedules.id"), index=True, nullable=False
    )
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    scheduled_utc: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    local_render: Mapped[str | None] = mapped_column(String(32))  # display string in patient tz
    state: Mapped[str] = mapped_column(
        String(16), default=DOSE_PENDING, server_default=DOSE_PENDING, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    source_schedule_version: Mapped[int] = mapped_column(default=1, server_default="1")
    acted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    skip_reason: Mapped[str | None] = mapped_column(String(255))

    # ── correction of an auto-classified MISSED dose ─────────────────────────
    # MISSED is assigned by a clock, not by the patient: nobody asserted it. The
    # patient who took their 08:00 dose and opened the app at 13:00 had no way to
    # say so, and the row was already counted against them. These columns record
    # the correction WITHOUT destroying what was corrected — `corrected_from_state`
    # keeps the machine's original classification next to the human's, so a
    # clinician can always see that a 100% figure contains N late self-reports.
    corrected_from_state: Mapped[str | None] = mapped_column(String(16))
    corrected_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    corrected_by_actor_id: Mapped[str | None] = mapped_column(String(36))
    corrected_by_actor_role: Mapped[str | None] = mapped_column(String(24))
    correction_reason: Mapped[str | None] = mapped_column(String(48))


class MedicationScheduleLifecycleEvent(UUIDPrimaryKey, TimestampMixin, Base):
    """An append-only lifecycle transition for a schedule (§1.8).

    The persisted timeline that `MedicationSchedule.status` cannot be: status is
    the state NOW, and adherence needs the state THEN. Folding these events in
    `effective_at` order yields the half-open active intervals
    ``[opening.effective_at, closing.effective_at)`` that the denominator is
    computed over, so a doctor-instructed hold contributes zero expected doses
    instead of a block of fabricated misses.

    Append-only by contract: rows are never updated or deleted. A mistake is
    corrected by appending the correcting event, so the audit trail of what the
    patient was told to do, and when, survives.

    ``idempotency_key = sha256(schedule_id|event_type|effective_at)`` under a
    unique constraint, so a retried pause (double tap, client retry) records one
    event rather than two overlapping intervals.

    PHI: none. ``reason_code`` is a closed vocabulary and ``note_ref`` is a
    pointer to a record held elsewhere, never free text — a lifecycle trail that
    leaks the clinical reason for a hold is its own disclosure.
    """

    __tablename__ = "medication_schedule_lifecycle_events"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_sched_lifecycle_idempotency_key"),
    )

    # Wider than the mixin's String(36): the migration's backfill derives ids in
    # SQL from `schedule_id|event_type|effective_at` (no uuid function is
    # available on every supported server, and no extension may be assumed), so
    # the column has to hold a composite. Service-written rows are still uuid4.
    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=_uuid)

    schedule_id: Mapped[str] = mapped_column(
        ForeignKey("medication_schedules.id"), index=True, nullable=False
    )
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # The instant the transition TAKES EFFECT, which is not the instant it was
    # recorded: a backdated hold ("the doctor stopped it on Friday") is legitimate
    # and must move the interval boundary, not the row's creation time.
    # No standalone index: the composite `(schedule_id, effective_at)` created in
    # the migration covers every read, and declaring `index=True` here made the
    # ORM metadata (which `create_all` builds the SQLite test schema from)
    # disagree with the migrated Postgres schema — so `alembic autogenerate`
    # would emit spurious drop/create for it forever.
    effective_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    actor_id: Mapped[str | None] = mapped_column(String(36))
    actor_role: Mapped[str] = mapped_column(String(24), default="patient", server_default="patient")
    reason_code: Mapped[str] = mapped_column(
        String(48), default="unspecified", server_default="unspecified"
    )
    note_ref: Mapped[str | None] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
