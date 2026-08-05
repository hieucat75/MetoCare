"""Medication schedule + dose-occurrence service (Master Plan §1.8, BRD §G).

Owns the reminder/adherence loop: create a schedule for a CONFIRMED medication →
materialize dose occurrences (idempotent, concurrency-safe) → deliver reminders →
patient marks taken/skipped → adherence. Instants are computed in the patient's
IANA timezone and stored in UTC. PRN medications never materialize timed doses;
paused/stopped schedules materialize none; editing a schedule creates a new
version (supersession) and cancels the old schedule's future pending doses.
"""

from __future__ import annotations

import datetime as dt
import uuid
from hashlib import sha256
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models.clinical import Medication
from app.models.medication_schedule import (
    DOSE_MISSED,
    DOSE_NOTIFIED,
    DOSE_PENDING,
    DOSE_SKIPPED,
    DOSE_TAKEN,
    SCHED_STATUS_ACTIVE,
    SCHED_STATUS_PAUSED,
    SCHED_STATUS_STOPPED,
    SCHEDULE_CYCLIC,
    SCHEDULE_DAYS_OF_WEEK,
    SCHEDULE_FIXED_DAILY,
    SCHEDULE_INTERVAL,
    SCHEDULE_PRN,
    DoseOccurrence,
    MedicationSchedule,
)
from app.services import audit, notification_transport

_DEFAULT_TZ = "Asia/Ho_Chi_Minh"
# The ONLY medication lifecycle state that may drive reminders (CLIN PS-5) — a
# deleted or retired drug must never be reminded, by name, to the patient.
_MED_ACTIVE_STATUS = "active"
# Mirrors medication.DELETED_LIFECYCLE_STATUS. Kept as a literal rather than an
# import: app.services.medication imports THIS module (lazily) for the cascade,
# so a module-level import back would be circular.
_MED_DELETED_STATUS = "entered_in_error"
_DEFAULT_HORIZON_DAYS = 7
# A pending/notified dose this long past its time counts as MISSED (review P1 —
# so adherence isn't inflated by ignored doses staying out of the denominator).
_MISSED_AFTER = dt.timedelta(hours=4)
_VALID_TYPES = frozenset(
    {SCHEDULE_FIXED_DAILY, SCHEDULE_INTERVAL, SCHEDULE_DAYS_OF_WEEK, SCHEDULE_CYCLIC, SCHEDULE_PRN}
)

# Types whose recurrence is computed RELATIVE TO AN ANCHOR DAY. For these,
# `start_date` is not decoration — it is the phase of the cycle, and without it
# every recurrence test is evaluated against a moving "today", which makes
# `(day - anchor) % n == 0` true on every single day. An alternate-day regimen
# then reminds daily, and 21-on/7-off reminds through the rest week.
#
# fixed_daily needs no anchor (every day qualifies by definition) and
# days_of_week is anchored to the weekday itself, not to a start day. PRN never
# materialises timed doses at all.
_ANCHOR_REQUIRED_TYPES = frozenset({SCHEDULE_INTERVAL, SCHEDULE_CYCLIC})


def needs_anchor_repair(schedule) -> bool:
    """True when a stored schedule is phase-dependent but has no anchor.

    Such a row can never materialise a dose (compute_occurrences fails closed),
    so the patient must be told to re-enter a start date rather than left with a
    schedule that silently never reminds.
    """
    return schedule.schedule_type in _ANCHOR_REQUIRED_TYPES and schedule.start_date is None


class ScheduleError(Exception):
    pass


class ScheduleNotFound(ScheduleError):
    pass


class ScheduleAccessDenied(ScheduleError):
    pass


class InvalidSchedule(ScheduleError):
    pass


def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _tz(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or _DEFAULT_TZ)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(_DEFAULT_TZ)


def _parse_hhmm(raw: str) -> dt.time | None:
    try:
        h, m = raw.strip().split(":")
        return dt.time(int(h), int(m))
    except (ValueError, AttributeError):
        return None



def _validate_schedule_shape(
    schedule_type: str,
    local_dose_times: list[str] | None,
    recurrence: dict | None,
    start_date: dt.date | None = None,
) -> None:
    """Reject a schedule whose recurrence cannot be honoured.

    Previously only `schedule_type` and "the times list is non-empty" were checked,
    so two silent failures were possible and both are clinically wrong:

    * a CYCLIC schedule missing/typo'd `on_days` fell through `cycle <= 0` to
      "every day applies" — a steroid pulse or cyclical hormone regimen would
      remind the patient by name to take the drug on every REST day;
    * INTERVAL with a missing `interval_days` defaulted to n=1, i.e. daily;
    * unparseable "HH:MM" strings were dropped in compute_occurrences, leaving an
      ACTIVE schedule that can never remind while the patient believes it is set.

    A malformed schedule must be refused at the boundary, never degraded.
    """
    if schedule_type == SCHEDULE_PRN:
        return

    times = local_dose_times or []
    if not times:
        raise InvalidSchedule("Lịch không phải PRN cần ít nhất một giờ uống.")
    bad = [t for t in times if _parse_hhmm(t) is None]
    if bad:
        raise InvalidSchedule(
            f"Giờ uống không hợp lệ: {', '.join(str(b) for b in bad)}. Dùng định dạng HH:MM."
        )

    rec = recurrence or {}
    if schedule_type in _ANCHOR_REQUIRED_TYPES and start_date is None:
        raise InvalidSchedule(
            "Lịch theo chu kỳ hoặc cách ngày cần ngày bắt đầu (`start_date`) — "
            "nếu không, hệ thống không biết chu kỳ bắt đầu từ ngày nào."
        )
    if schedule_type == SCHEDULE_INTERVAL:
        try:
            n = int(rec.get("interval_days"))
        except (TypeError, ValueError):
            raise InvalidSchedule(
                "Lịch cách ngày cần `interval_days` là số nguyên >= 1."
            ) from None
        if n < 1:
            raise InvalidSchedule("`interval_days` phải >= 1.")

    elif schedule_type == SCHEDULE_DAYS_OF_WEEK:
        days = rec.get("days")
        if not isinstance(days, list) or not days:
            raise InvalidSchedule("Lịch theo thứ cần `days` không rỗng (0=Thứ 2 … 6=Chủ nhật).")
        if any(not isinstance(d, int) or d < 0 or d > 6 for d in days):
            raise InvalidSchedule("`days` chỉ nhận số nguyên 0–6 (0=Thứ 2 … 6=Chủ nhật).")

    elif schedule_type == SCHEDULE_CYCLIC:
        try:
            on = int(rec.get("on_days"))
            off = int(rec.get("off_days", 0))
        except (TypeError, ValueError):
            raise InvalidSchedule(
                "Lịch theo chu kỳ cần `on_days` (và `off_days`) là số nguyên."
            ) from None
        if on < 1:
            raise InvalidSchedule("`on_days` phải >= 1.")
        if off < 0:
            raise InvalidSchedule("`off_days` không được âm.")


def _idempotency_key(schedule_id: str, version: int, scheduled_utc: dt.datetime) -> str:
    raw = f"{schedule_id}|{version}|{scheduled_utc.astimezone(dt.UTC).isoformat()}"
    return sha256(raw.encode("utf-8")).hexdigest()


def _day_applies(schedule: MedicationSchedule, day: dt.date, start: dt.date) -> bool:
    rec = schedule.recurrence or {}
    st = schedule.schedule_type
    if st == SCHEDULE_FIXED_DAILY:
        return True
    if st == SCHEDULE_INTERVAL:
        try:
            n = int(rec.get("interval_days", 0))
        except (TypeError, ValueError):
            return False
        if n < 1:
            return False  # malformed legacy row — never degrade to daily
        return (day - start).days % n == 0
    if st == SCHEDULE_DAYS_OF_WEEK:
        return day.weekday() in set(rec.get("days", []))  # 0=Mon
    if st == SCHEDULE_CYCLIC:
        on = int(rec.get("on_days", 0))
        off = int(rec.get("off_days", 0))
        cycle = on + off
        if cycle <= 0 or on < 1:
            # Malformed legacy row. Reminding EVERY day (the old behaviour) would
            # tell a patient on a cyclical regimen to dose on rest days; producing
            # no dose is visibly wrong instead of silently wrong. New rows cannot
            # reach here — _validate_schedule_shape refuses them at the boundary.
            return False
        return (day - start).days % cycle < on
    return False


# ── occurrence computation (pure) ────────────────────────────────────────────
def compute_occurrences(
    schedule: MedicationSchedule,
    *,
    horizon_days: int = _DEFAULT_HORIZON_DAYS,
    now: dt.datetime | None = None,
) -> list[tuple[dt.datetime, str]]:
    """Return (scheduled_utc, local_render) for doses due within the horizon.

    Empty for PRN, non-active, or timeless schedules. Only materializes from ~now
    forward (a small grace window) — never backfills history.
    """
    if schedule.schedule_type == SCHEDULE_PRN or schedule.status != SCHED_STATUS_ACTIVE:
        return []
    times = [t for t in (_parse_hhmm(x) for x in (schedule.local_dose_times or [])) if t]
    if not times:
        return []

    now = now or _now_utc()
    tz = _tz(schedule.patient_timezone)
    horizon_end_utc = now + dt.timedelta(days=horizon_days)
    grace_start_utc = now - dt.timedelta(minutes=5)

    today_local = now.astimezone(tz).date()
    if schedule.schedule_type in _ANCHOR_REQUIRED_TYPES and schedule.start_date is None:
        # FAIL CLOSED. Defaulting to today makes the anchor move with the clock,
        # so `(day - anchor) % n` is 0 for today on EVERY day and the schedule
        # degrades to daily — the single most dangerous failure mode here, since
        # it tells a patient on an alternate-day or cyclical regimen to dose on
        # rest days. New rows cannot reach this (create/edit both refuse), but a
        # legacy row can; producing no dose is visibly wrong, dosing every day is
        # silently wrong. `needs_anchor_repair` surfaces it to the UI.
        return []
    # Non-anchor types (fixed_daily, days_of_week) are phase-INDEPENDENT: every
    # day, or every matching weekday, qualifies regardless of when the schedule
    # began, so falling back to today is safe for them and only for them.
    start = schedule.start_date or today_local
    last_local = horizon_end_utc.astimezone(tz).date()
    end = min(schedule.end_date, last_local) if schedule.end_date else last_local

    out: list[tuple[dt.datetime, str]] = []
    day = max(start, today_local)
    while day <= end:
        if _day_applies(schedule, day, start):
            for t in times:
                local_dt = dt.datetime.combine(day, t, tzinfo=tz)
                utc_dt = local_dt.astimezone(dt.UTC)
                if grace_start_utc <= utc_dt <= horizon_end_utc:
                    out.append((utc_dt, f"{day.isoformat()} {t.strftime('%H:%M')}"))
        day += dt.timedelta(days=1)
    return out


# ── schedule lifecycle ───────────────────────────────────────────────────────
def _load_owned_medication(db: Session, *, patient_id: str, medication_id: str) -> Medication:
    med = db.get(Medication, medication_id)
    if med is None or med.deleted_at is not None:
        raise ScheduleNotFound("Không tìm thấy thuốc.")
    if med.patient_id != patient_id:
        raise ScheduleAccessDenied("Không có quyền với thuốc này.")
    # §1.8 confirmed-only: only an active canonical medication can be scheduled
    # (canonical rows are already patient-confirmed; entered_in_error/stopped can't).
    if med.lifecycle_status != "active":
        raise InvalidSchedule("Chỉ có thể lập lịch cho thuốc đang dùng (active).")
    return med


def create_schedule(
    db: Session,
    *,
    patient_id: str,
    medication_id: str,
    schedule_type: str,
    local_dose_times: list[str] | None = None,
    recurrence: dict | None = None,
    start_date: dt.date | None = None,
    end_date: dt.date | None = None,
    patient_timezone: str | None = None,
    source: str = "manual",
    actor_user_id: str | None = None,
) -> MedicationSchedule:
    if schedule_type not in _VALID_TYPES:
        raise InvalidSchedule(f"schedule_type không hợp lệ: {schedule_type}")
    _load_owned_medication(db, patient_id=patient_id, medication_id=medication_id)
    _validate_schedule_shape(schedule_type, local_dose_times, recurrence, start_date)

    schedule = MedicationSchedule(
        medication_id=medication_id,
        patient_id=patient_id,
        patient_timezone=patient_timezone or _DEFAULT_TZ,
        schedule_type=schedule_type,
        local_dose_times=local_dose_times if schedule_type != SCHEDULE_PRN else None,
        recurrence=recurrence,
        start_date=start_date,
        end_date=end_date,
        status=SCHED_STATUS_ACTIVE,
        source=source,
        version=1,
    )
    db.add(schedule)
    db.flush()
    audit.record(
        db,
        actor_type="patient",
        actor_id=patient_id,
        action="medication_schedule.create",
        resource_type="medication_schedule",
        resource_id=schedule.id,
    )
    return schedule


def materialize_due(
    db: Session,
    schedule: MedicationSchedule,
    *,
    horizon_days: int = _DEFAULT_HORIZON_DAYS,
    now: dt.datetime | None = None,
) -> int:
    """Idempotently materialize dose occurrences within the horizon. Concurrency-
    safe via the unique idempotency_key + INSERT … ON CONFLICT DO NOTHING — a
    retry (or a second worker) never creates a duplicate dose. Returns rows added."""
    occurrences = compute_occurrences(schedule, horizon_days=horizon_days, now=now)
    if not occurrences:
        return 0
    ins = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    created = 0
    for utc_dt, local_render in occurrences:
        key = _idempotency_key(schedule.id, schedule.version, utc_dt)
        stmt = (
            ins(DoseOccurrence)
            .values(
                id=str(uuid.uuid4()),
                schedule_id=schedule.id,
                patient_id=schedule.patient_id,
                scheduled_utc=utc_dt,
                local_render=local_render,
                state=DOSE_PENDING,
                idempotency_key=key,
                source_schedule_version=schedule.version,
            )
            .on_conflict_do_nothing(index_elements=["idempotency_key"])
        )
        result = db.execute(stmt)
        created += result.rowcount or 0
    return created


def deliver_due_reminders(
    db: Session,
    *,
    patient_id: str,
    user_id: str,
    now: dt.datetime | None = None,
) -> int:
    """Deliver reminders for pending doses whose time has arrived; mark them
    notified. Returns the number of reminders delivered."""
    now = now or _now_utc()
    # CLIN PS-5: self-heal any schedule whose medication was retired/deleted
    # before the lifecycle cascade existed, so legacy rows stop reminding too.
    reconcile_schedules_with_medication_state(db, patient_id=patient_id)
    # Only remind for doses whose schedule is still ACTIVE and not superseded — a
    # paused/stopped/superseded schedule must never remind (review P1: no reminder
    # to take a discontinued medication) — AND whose MEDICATION is still an active,
    # non-deleted canonical row (CLIN PS-5: the schedule is a separate row, so the
    # schedule-level gate alone let a stopped drug keep reminding).
    due = list(
        db.execute(
            select(DoseOccurrence)
            .join(MedicationSchedule, MedicationSchedule.id == DoseOccurrence.schedule_id)
            .join(Medication, Medication.id == MedicationSchedule.medication_id)
            .where(
                DoseOccurrence.patient_id == patient_id,
                DoseOccurrence.state == DOSE_PENDING,
                DoseOccurrence.scheduled_utc <= now,
                MedicationSchedule.status == SCHED_STATUS_ACTIVE,
                MedicationSchedule.superseded_by.is_(None),
                Medication.deleted_at.is_(None),
                Medication.lifecycle_status == _MED_ACTIVE_STATUS,
            )
        ).scalars()
    )
    delivered = 0
    for dose in due:
        # Concurrency-safe claim: only the transaction that flips pending→notified
        # actually delivers, so two concurrent /reminders/due can't double-remind.
        claimed = db.execute(
            update(DoseOccurrence)
            .where(DoseOccurrence.id == dose.id, DoseOccurrence.state == DOSE_PENDING)
            .values(state=DOSE_NOTIFIED)
        )
        if not (claimed.rowcount or 0):
            continue
        med = _med_for_schedule(db, dose.schedule_id)
        name = med.name if med else "thuốc"
        notification_transport.deliver(
            db,
            user_id=user_id,
            category="medication_reminder",
            title="Đến giờ uống thuốc",
            body=f"Đã đến giờ uống {name} ({dose.local_render}).",
            deep_link=f"/medications/dose/{dose.id}",
            metadata={"dose_id": dose.id, "schedule_id": dose.schedule_id},  # PHI-free
        )
        delivered += 1
    db.flush()
    return delivered


def _med_for_schedule(db: Session, schedule_id: str) -> Medication | None:
    schedule = db.get(MedicationSchedule, schedule_id)
    return db.get(Medication, schedule.medication_id) if schedule else None


def mark_dose(
    db: Session,
    *,
    patient_id: str,
    dose_id: str,
    state: str,
    skip_reason: str | None = None,
    actor_user_id: str | None = None,
) -> DoseOccurrence:
    """Record taken/skipped for a dose (the dose occurrence is the adherence record)."""
    if state not in (DOSE_TAKEN, DOSE_SKIPPED):
        raise InvalidSchedule("Trạng thái liều không hợp lệ.")
    dose = db.get(DoseOccurrence, dose_id)
    if dose is None:
        raise ScheduleNotFound("Không tìm thấy liều.")
    if dose.patient_id != patient_id:
        raise ScheduleAccessDenied("Không có quyền với liều này.")
    if dose.state in (DOSE_TAKEN, DOSE_SKIPPED):
        raise InvalidSchedule("Liều đã được ghi nhận.")
    dose.state = state
    dose.acted_at = _now_utc()
    dose.skip_reason = skip_reason if state == DOSE_SKIPPED else None
    db.flush()
    audit.record(
        db,
        actor_type="patient",
        actor_id=patient_id,
        action=f"medication_dose.{state}",
        resource_type="dose_occurrence",
        resource_id=dose.id,
    )
    return dose


def _cancel_open_doses(
    db: Session,
    schedule_id: str,
    *,
    now: dt.datetime | None = None,
    purge_history: bool = False,
) -> None:
    """Resolve or cancel still-open (pending/notified, unacted) doses for a schedule.

    Doses whose time has ALREADY PASSED are transitioned to MISSED and kept; only
    doses that have not yet come around are deleted. Acted (taken/skipped) doses
    are historical and never touched.

    This used to be opt-in via a `future_only` flag that exactly one caller set.
    Every other caller — pause, stop, the lifecycle cascade, the read-path
    reconcile — hard-deleted every open dose, including days-old ones the sweep
    had not yet resolved (the sweep only runs when the patient opens the app). So
    a patient who missed three days and then tapped "Tạm dừng" had that
    non-adherence deleted, and pause -> edit -> resume made the reset repeatable.
    A clinician reading adherence before escalating therapy would be acting on
    fabricated data, so the safe behaviour is now the default.

    ``purge_history=True`` is the ONE exception, and it is not a convenience
    flag: it is for a medication record that has been REPUDIATED — soft-deleted
    or marked ``entered_in_error``, i.e. "this record should never have existed".
    There the past-due doses are not real non-adherence either; counting them
    would invent missed doses for a drug the patient was never actually on. A
    lifecycle EXIT (stop / pause / discontinue / on_hold) is the opposite case —
    the therapy was real and so is the history — and never purges.
    """
    cutoff = now or _now_utc()
    for dose in db.execute(
        select(DoseOccurrence).where(
            DoseOccurrence.schedule_id == schedule_id,
            DoseOccurrence.state.in_((DOSE_PENDING, DOSE_NOTIFIED)),
        )
    ).scalars():
        scheduled = dose.scheduled_utc
        if scheduled is not None and scheduled.tzinfo is None:
            scheduled = scheduled.replace(tzinfo=dt.UTC)
        if scheduled is not None and scheduled <= cutoff and not purge_history:
            # Already due and unacted: resolve to MISSED and KEEP it. Deleting it
            # would erase real non-adherence from the denominator — a patient who
            # missed three days and then tapped "Tạm dừng" saw their adherence
            # jump instead of drop, and pause -> edit made that repeatable.
            dose.state = DOSE_MISSED
        else:
            db.delete(dose)


def stop_schedules_for_medication(
    db: Session, *, medication_id: str, purge_history: bool = False
) -> int:
    """Stop every non-stopped schedule of a medication — the lifecycle cascade
    (CLIN PS-5).

    Called from the medication service whenever a drug leaves ``active`` (stop /
    pause / on_hold / discontinue / entered_in_error / soft-delete), inside the
    SAME transaction, so a drug the patient or their doctor stopped can never be
    reminded again. Reuses ``_cancel_open_doses``, so already-materialised doses
    disappear from the reminder feed and the dashboard as well. Returns the number
    of schedules stopped. No ownership check: the caller already authorised the
    lifecycle transition on the owning medication.
    """
    schedules = list(
        db.execute(
            select(MedicationSchedule).where(
                MedicationSchedule.medication_id == medication_id,
                MedicationSchedule.status != SCHED_STATUS_STOPPED,
            )
        ).scalars()
    )
    for schedule in schedules:
        schedule.status = SCHED_STATUS_STOPPED
        _cancel_open_doses(db, schedule.id, purge_history=purge_history)
    if schedules:
        db.flush()
    return len(schedules)


def reconcile_schedules_with_medication_state(db: Session, *, patient_id: str) -> int:
    """Stop schedules whose medication is no longer active (CLIN PS-5, read-path
    guard).

    The cascade above fixes every NEW lifecycle exit; this repairs rows that were
    already broken when the cascade did not exist yet. Runs before each reminder
    delivery / dashboard read, so no already-materialised dose of a discontinued
    drug can survive as an action. Returns the number of schedules stopped.
    """
    stale = list(
        db.execute(
            select(MedicationSchedule, Medication.deleted_at, Medication.lifecycle_status)
            .join(Medication, Medication.id == MedicationSchedule.medication_id)
            .where(
                MedicationSchedule.patient_id == patient_id,
                MedicationSchedule.status != SCHED_STATUS_STOPPED,
                or_(
                    Medication.deleted_at.isnot(None),
                    Medication.lifecycle_status != _MED_ACTIVE_STATUS,
                ),
            )
        ).all()
    )
    for schedule, deleted_at, lifecycle_status in stale:
        schedule.status = SCHED_STATUS_STOPPED
        # Same repudiated-vs-exit rule as the cascade (see _cancel_open_doses).
        _cancel_open_doses(
            db,
            schedule.id,
            purge_history=(
                deleted_at is not None or lifecycle_status == _MED_DELETED_STATUS
            ),
        )
    if stale:
        db.flush()
    return len(stale)


def _load_owned_schedule(db: Session, *, patient_id: str, schedule_id: str) -> MedicationSchedule:
    schedule = db.get(MedicationSchedule, schedule_id)
    if schedule is None:
        raise ScheduleNotFound("Không tìm thấy lịch.")
    if schedule.patient_id != patient_id:
        raise ScheduleAccessDenied("Không có quyền với lịch này.")
    return schedule


def pause_schedule(db: Session, *, patient_id: str, schedule_id: str) -> MedicationSchedule:
    schedule = _load_owned_schedule(db, patient_id=patient_id, schedule_id=schedule_id)
    schedule.status = SCHED_STATUS_PAUSED
    _cancel_open_doses(db, schedule_id)  # paused → no future materialized doses
    db.flush()
    return schedule


def stop_schedule(db: Session, *, patient_id: str, schedule_id: str) -> MedicationSchedule:
    schedule = _load_owned_schedule(db, patient_id=patient_id, schedule_id=schedule_id)
    schedule.status = SCHED_STATUS_STOPPED
    _cancel_open_doses(db, schedule_id)
    db.flush()
    return schedule


def edit_schedule(
    db: Session,
    *,
    patient_id: str,
    schedule_id: str,
    local_dose_times: list[str] | None = None,
    recurrence: dict | None = None,
    schedule_type: str | None = None,
    end_date: dt.date | None = None,
    actor_user_id: str | None = None,
) -> MedicationSchedule:
    """Edit = create a NEW version (supersession). Past occurrences are immutable;
    the old schedule's FUTURE pending doses are cancelled and regenerated from the
    new version (§1.8). Returns the new schedule."""
    old = _load_owned_schedule(db, patient_id=patient_id, schedule_id=schedule_id)
    # Can't edit a terminal/superseded schedule into a fresh active version
    # (review P2 — no resurrection), and the underlying medication must still be
    # active/confirmed (re-run the confirmed-only gate).
    if old.status == SCHED_STATUS_STOPPED or old.superseded_by is not None:
        raise InvalidSchedule("Lịch đã kết thúc — không thể sửa.")
    _load_owned_medication(db, patient_id=patient_id, medication_id=old.medication_id)
    new_type = schedule_type or old.schedule_type
    if new_type not in _VALID_TYPES:
        raise InvalidSchedule(f"schedule_type không hợp lệ: {new_type}")
    # Validate the RESOLVED shape (edit is a partial patch, so unspecified fields
    # fall back to the old version's values). Editing must not be a way to reach a
    # malformed schedule that create_schedule would have refused.
    _validate_schedule_shape(
        new_type,
        local_dose_times if local_dose_times is not None else old.local_dose_times,
        recurrence if recurrence is not None else old.recurrence,
        # An edit inherits the old anchor; a type change INTO interval/cyclic on a
        # row that never had one must be refused, not silently anchored to today.
        old.start_date,
    )
    new = MedicationSchedule(
        medication_id=old.medication_id,
        patient_id=old.patient_id,
        patient_timezone=old.patient_timezone,
        schedule_type=new_type,
        local_dose_times=local_dose_times if local_dose_times is not None else old.local_dose_times,
        recurrence=recurrence if recurrence is not None else old.recurrence,
        start_date=old.start_date,
        end_date=end_date if end_date is not None else old.end_date,
        status=SCHED_STATUS_ACTIVE,
        source=old.source,
        version=old.version + 1,
    )
    db.add(new)
    db.flush()
    old.superseded_by = new.id
    old.status = SCHED_STATUS_STOPPED
    # Resolve anything already overdue to MISSED *before* cancelling, so real
    # non-adherence is recorded rather than deleted, then drop only the doses that
    # had not yet come around. History on the superseded version stays immutable
    # and keeps counting toward the medication's adherence.
    sweep_missed(db, patient_id=old.patient_id)
    _cancel_open_doses(db, old.id)
    db.flush()
    return new


def sweep_missed(
    db: Session, *, patient_id: str, now: dt.datetime | None = None
) -> int:
    """Transition pending/notified doses that are overdue by more than the grace
    window to MISSED (review P1). Returns the count transitioned."""
    now = now or _now_utc()
    cutoff = now - _MISSED_AFTER
    overdue = list(
        db.execute(
            select(DoseOccurrence).where(
                DoseOccurrence.patient_id == patient_id,
                DoseOccurrence.state.in_((DOSE_PENDING, DOSE_NOTIFIED)),
                DoseOccurrence.scheduled_utc < cutoff,
            )
        ).scalars()
    )
    for dose in overdue:
        dose.state = DOSE_MISSED
    db.flush()
    return len(overdue)


def adherence_summary(db: Session, *, patient_id: str, schedule_id: str) -> dict:
    """Adherence over materialized doses for a schedule.

    The denominator is every RESOLVED-or-should-be-resolved dose: taken + skipped +
    missed, where "missed" includes doses already swept to MISSED plus pending/
    notified doses now overdue past the grace window (review P1 — a rate must never
    be inflated by ignored doses sitting outside the denominator). Not-yet-due
    pending doses are excluded from the rate but counted in ``total``.
    """
    now = _now_utc()
    cutoff = now - _MISSED_AFTER
    rows = list(
        db.execute(
            select(DoseOccurrence.state, DoseOccurrence.scheduled_utc).where(
                DoseOccurrence.schedule_id == schedule_id,
                DoseOccurrence.patient_id == patient_id,
            )
        )
    )
    def _aware(x: dt.datetime) -> dt.datetime:
        # SQLite returns naive datetimes; treat a naive stored instant as UTC so
        # the comparison with the aware cutoff never raises.
        return x if x.tzinfo is not None else x.replace(tzinfo=dt.UTC)

    taken = sum(1 for st, _ in rows if st == DOSE_TAKEN)
    skipped = sum(1 for st, _ in rows if st == DOSE_SKIPPED)
    missed = sum(
        1
        for st, when in rows
        if st == DOSE_MISSED
        or (st in (DOSE_PENDING, DOSE_NOTIFIED) and when is not None and _aware(when) < cutoff)
    )
    resolved = taken + skipped + missed
    rate = round(taken / resolved, 3) if resolved else None
    return {
        "total": len(rows),
        "taken": taken,
        "skipped": skipped,
        "missed": missed,
        "adherence_rate": rate,
    }
