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

from ._mixins import TimestampMixin, UUIDPrimaryKey

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
