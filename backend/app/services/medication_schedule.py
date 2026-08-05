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
        if off < 1:
            # off_days=0 (or omitted, which defaulted to 0) made `_day_applies`
            # compute cycle == on, so `(day - start) % on < on` is true on EVERY
            # day and the schedule silently became daily. That is the same failure
            # the anchor validation above exists to prevent — a cyclical regimen
            # reminding through its rest week — reached through a different hole,
            # so closing only the anchor left the class open.
            #
            # A cycle with no rest period is not a cycle; it is `fixed_daily`, and
            # a client that means daily should say so rather than describe a
            # 21-on/0-off cycle and be silently agreed with.
            raise InvalidSchedule(
                "Lịch theo chu kỳ cần `off_days` >= 1 (số ngày nghỉ). "
                "Nếu uống mỗi ngày, hãy dùng lịch hằng ngày (`fixed_daily`)."
            )


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


# ── deterministic period reconciliation (P1-3) ──────────────────────────────

# The evaluation window is bounded so a request cannot walk an unbounded calendar.
# 400 days covers "the last year" with room for a leap year and a timezone edge.
MAX_ADHERENCE_PERIOD_DAYS = 400

# Bumped when the denominator SEMANTICS change, not when the code moves. Stored on
# every response so a rate can be traced to the rules that produced it — a
# denominator that changes meaning without a version is indistinguishable from a
# patient whose behaviour changed.
ADHERENCE_CALCULATION_VERSION = "adherence-2.0.0"


def expected_occurrences_in_window(
    schedule: MedicationSchedule,
    *,
    window_start: dt.date,
    window_end: dt.date,
) -> list[tuple[dt.datetime, str]]:
    """Every occurrence the schedule PRESCRIBES in an explicit local-date window.

    This is `compute_occurrences` without the two clamps that make it a
    forward-materializer: no `max(start, today_local)` and no
    `grace_start <= utc <= horizon_end` filter. Those clamps are correct for
    deciding what to remind about; they are exactly wrong for deciding what was
    prescribed, because they make the answer depend on WHEN you ask.

    That dependency was the defect: materialization only ever ran from a request
    handler, so a patient dormant for 30 days had rows for the 7 days after their
    last visit and nothing else. A twice-daily schedule running 35 days has 70
    prescribed doses; such a patient had 14 rows, and adherence was computed over
    those 14. The denominator measured app engagement, not therapy.

    Phase rules are shared with `compute_occurrences` via `_day_applies`, so the
    anchor, DST and cyclic/interval semantics cannot drift between "what we
    remind" and "what we count".
    """
    if schedule.schedule_type == SCHEDULE_PRN:
        # PRN has no prescribed schedule — there is nothing to be adherent TO.
        return []
    times = [t for t in (_parse_hhmm(x) for x in (schedule.local_dose_times or [])) if t]
    if not times:
        return []
    if needs_anchor_repair(schedule):
        # Same fail-closed rule as compute_occurrences: without a stable anchor a
        # phase-dependent schedule would degrade to daily, which here would invent
        # missed doses on rest days.
        return []

    anchor = schedule.start_date
    if anchor is None:
        # Phase-INDEPENDENT types only (fixed_daily / days_of_week). Anchor the
        # phase calculation at the window start; every day qualifies regardless.
        anchor = window_start

    tz = _tz(schedule.patient_timezone)
    start = max(window_start, schedule.start_date or window_start)
    end = min(window_end, schedule.end_date) if schedule.end_date else window_end

    out: list[tuple[dt.datetime, str]] = []
    day = start
    while day <= end:
        if _day_applies(schedule, day, anchor):
            for t in times:
                local_dt = dt.datetime.combine(day, t, tzinfo=tz)
                out.append(
                    (local_dt.astimezone(dt.UTC), f"{day.isoformat()} {t.strftime('%H:%M')}")
                )
        day += dt.timedelta(days=1)
    return out


def reconcile_period(
    db: Session,
    schedule: MedicationSchedule,
    *,
    period_start: dt.date,
    period_end: dt.date,
    now: dt.datetime | None = None,
) -> dict:
    """Materialize every expected occurrence in the window, then resolve overdue.

    Idempotent and concurrency-safe by construction: rows are inserted with
    `ON CONFLICT DO NOTHING` on `idempotency_key`, which is
    `sha256(schedule_id|version|scheduled_utc)`. Two concurrent reconciliations
    of the same period converge on the same row set, and repeating one creates
    nothing.

    Backfill applies ONLY to a schedule that is currently active and not
    superseded. A paused or stopped schedule deliberately accrues nothing for the
    period it was not running: pausing means the patient is legitimately not
    taking the drug, so inventing missed doses there is the same fabrication as
    deleting real ones, in reverse. Rows materialized while it WAS live are
    untouched and still counted, so genuine history survives a later pause.

    Returns PHI-free counters for observability.
    """
    now = now or _now_utc()
    stats = {
        "created": 0,
        "resolved_missed": 0,
        "conflicts": 0,
        "backfilled": False,
    }
    if schedule.status != SCHED_STATUS_ACTIVE or schedule.superseded_by is not None:
        return stats

    expected = expected_occurrences_in_window(
        schedule, window_start=period_start, window_end=period_end
    )
    if not expected:
        return stats
    stats["backfilled"] = True

    existing = {
        k
        for (k,) in db.execute(
            select(DoseOccurrence.idempotency_key).where(
                DoseOccurrence.schedule_id == schedule.id
            )
        )
    }
    for utc_dt, local_render in expected:
        key = _idempotency_key(schedule.id, schedule.version, utc_dt)
        if key in existing:
            stats["conflicts"] += 1
            continue
        ins = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
        result = db.execute(
            ins(DoseOccurrence)
            .values(
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
        created = result.rowcount or 0
        stats["created"] += created
        if not created:
            # Another transaction inserted it between the read and the write.
            stats["conflicts"] += 1

    # Resolve anything now past its grace window. Backfilled history is due by
    # definition, so without this every reconciled row would count as `future`.
    cutoff = now - _MISSED_AFTER
    for dose in db.execute(
        select(DoseOccurrence).where(
            DoseOccurrence.schedule_id == schedule.id,
            DoseOccurrence.state.in_((DOSE_PENDING, DOSE_NOTIFIED)),
        )
    ).scalars():
        scheduled = dose.scheduled_utc
        if scheduled is not None and scheduled.tzinfo is None:
            scheduled = scheduled.replace(tzinfo=dt.UTC)
        if scheduled is not None and scheduled <= cutoff:
            dose.state = DOSE_MISSED
            stats["resolved_missed"] += 1
    db.flush()
    return stats


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


def due_doses_query(
    *,
    patient_id: str,
    now: dt.datetime,
    states: tuple[str, ...],
):
    """The ONE definition of "a dose that may be shown or acted on".

    A DoseOccurrence is a materialised row; nothing about the row itself says
    whether its schedule or its drug is still in force. Four separate conditions
    have to hold, and each read path was re-stating them by hand:

      - the schedule is ACTIVE (not paused, not stopped),
      - the schedule is the CURRENT version (an edit supersedes the old one, and
        its already-materialised doses outlive it),
      - the medication is not soft-deleted,
      - the medication is still lifecycle-active (not stopped / discontinued /
        on_hold / entered_in_error).

    They had already drifted. `deliver_due_reminders` and the dashboard carried
    all four; `GET /reminders/due` carried NONE of them on the rows it returns —
    it gated only the `delivered` counter, so the `items` payload still listed
    doses for paused schedules and for drugs the patient or their doctor had
    stopped. That is the CLIN PS-5 failure the other two sites exist to prevent,
    reached through the endpoint whose entire job is to render the reminder list:
    the patient is told by name to take a medication they discontinued.

    Restating a four-part safety predicate at each call site guarantees the next
    reader restates it incompletely too, so it lives here and every path calls it.
    """
    return (
        select(DoseOccurrence)
        .join(MedicationSchedule, MedicationSchedule.id == DoseOccurrence.schedule_id)
        .join(Medication, Medication.id == MedicationSchedule.medication_id)
        .where(
            DoseOccurrence.patient_id == patient_id,
            DoseOccurrence.state.in_(states),
            DoseOccurrence.scheduled_utc <= now,
            MedicationSchedule.status == SCHED_STATUS_ACTIVE,
            MedicationSchedule.superseded_by.is_(None),
            Medication.deleted_at.is_(None),
            Medication.lifecycle_status == _MED_ACTIVE_STATUS,
        )
        .order_by(DoseOccurrence.scheduled_utc)
    )


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
            due_doses_query(patient_id=patient_id, now=now, states=(DOSE_PENDING,))
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
    actor_user_id: str | None = None,
    reason: str | None = None,
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
    # Same grace the sweep uses. With cutoff=now, a patient who took their 20:00
    # dose and then tapped "Hoàn thành" on the finished course at 20:10 had that
    # dose flipped to MISSED — and, the schedule now being stopped, it dropped out
    # of `due_doses_query` so they could not correct it. On a 14-dose course that
    # is 93% instead of 100%, every time. The sweep's 4h window exists precisely
    # because "due" and "missed" are not the same instant; this path must agree.
    cutoff = (now or _now_utc()) - _MISSED_AFTER
    # D. Include MISSED when purging a REPUDIATED record. Selecting only
    #    pending/notified meant the sweep (which flips anything >4h overdue to
    #    MISSED on every dashboard read) had already moved most doses out of
    #    reach, so the purge deleted only the few still-recent ones and left the
    #    older misses in adherence — the docstring's justification unmet, and
    #    WHICH doses vanished depended on when the patient last opened the app.
    states = (
        (DOSE_PENDING, DOSE_NOTIFIED, DOSE_MISSED)
        if purge_history
        else (DOSE_PENDING, DOSE_NOTIFIED)
    )
    deleted_ids: list[str] = []
    missed_ids: list[str] = []
    for dose in db.execute(
        select(DoseOccurrence).where(
            DoseOccurrence.schedule_id == schedule_id,
            DoseOccurrence.state.in_(states),
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
            missed_ids.append(dose.id)
            dose.state = DOSE_MISSED
        else:
            deleted_ids.append(dose.id)
            db.delete(dose)

    # AUDIT. Dose rows are clinical evidence of adherence and these two branches
    # are the only places they are destroyed or reclassified — yet `mark_dose`
    # audited every patient action and this audited none, so a purge was
    # unfalsifiable after the fact. `entered_in_error` is patient-settable on
    # their own record, so the destructive path is patient-reachable.
    #
    # PHI-MINIMISED: counts and row ids only. No drug name, no dose time, no
    # value — an audit trail that leaks what it records is its own problem.
    if deleted_ids or missed_ids:
        audit.record(
            db,
            actor_type="user" if actor_user_id else "system",
            actor_id=actor_user_id,
            action="cancel_open_doses",
            resource_type="medication_schedule",
            resource_id=schedule_id,
            outcome="success",
            severity="warning" if purge_history else "info",
            details={
                "deleted_count": len(deleted_ids),
                "resolved_missed_count": len(missed_ids),
                "purge_history": purge_history,
                "reason": reason or ("repudiated_record" if purge_history else "lifecycle"),
            },
        )


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


def resume_schedule(db: Session, *, patient_id: str, schedule_id: str) -> MedicationSchedule:
    """Return a PAUSED schedule to active. The missing half of pause.

    There was no way back. `active -> paused` cascades through
    `_cascade_stop_schedules`, which STOPS every schedule and cancels its future
    doses; `paused -> active` is an allowed medication transition but nothing ever
    un-stopped a schedule, `edit_schedule` refuses a stopped row ("Lịch đã kết
    thúc"), and no route existed. So a patient who paused metformin for a week
    around a procedure and resumed it saw a medication that read `active` and was
    never reminded again — silently, with no error and no way to fix it in the UI.

    Safety properties:
      - only a paused schedule resumes; a STOPPED one is terminal, because stop
        is how a discontinued drug is guaranteed never to remind again and
        reviving it would defeat that;
      - the underlying medication must be active again, or resuming would restart
        reminders for a drug that is still discontinued;
      - HISTORY is untouched. Past taken/skipped/missed doses stay exactly as they
        are; only future occurrences are re-materialized;
      - `materialize_due` is idempotent on `idempotency_key`, so resuming twice
        cannot produce duplicate reminders.
    """
    schedule = _load_owned_schedule(db, patient_id=patient_id, schedule_id=schedule_id)
    if schedule.status == SCHED_STATUS_ACTIVE:
        return schedule  # already running; resuming twice is not an error
    if schedule.status != SCHED_STATUS_PAUSED:
        raise InvalidSchedule(
            "Chỉ có thể tiếp tục lịch đang tạm dừng. Lịch đã kết thúc thì tạo lịch mới."
        )
    if schedule.superseded_by is not None:
        raise InvalidSchedule("Lịch này đã được thay thế bằng phiên bản mới.")
    # Re-run the confirmed-only gate: the drug must be active again.
    _load_owned_medication(db, patient_id=patient_id, medication_id=schedule.medication_id)
    if needs_anchor_repair(schedule):
        raise InvalidSchedule(
            "Lịch thiếu ngày bắt đầu — vui lòng cập nhật ngày bắt đầu trước khi tiếp tục."
        )

    schedule.status = SCHED_STATUS_ACTIVE
    db.flush()
    materialize_due(db, schedule)
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
    start_date: dt.date | None = None,
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
        # An edit inherits the old anchor unless one is supplied. Supplying it is
        # the REPAIR path for a legacy NULL-anchor row: without it such a row was
        # permanently unfixable, because validation raised on the inherited NULL
        # and every PATCH 422'd. It still cannot be silently anchored to today —
        # the caller has to state the date.
        start_date if start_date is not None else old.start_date,
    )
    new = MedicationSchedule(
        medication_id=old.medication_id,
        patient_id=old.patient_id,
        patient_timezone=old.patient_timezone,
        schedule_type=new_type,
        local_dose_times=local_dose_times if local_dose_times is not None else old.local_dose_times,
        recurrence=recurrence if recurrence is not None else old.recurrence,
        start_date=start_date if start_date is not None else old.start_date,
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


def adherence_summary(
    db: Session,
    *,
    patient_id: str,
    schedule_id: str,
    period_start: dt.date | None = None,
    period_end: dt.date | None = None,
    now: dt.datetime | None = None,
) -> dict:
    """Adherence over an explicitly RECONCILED period.

    The denominator used to be "rows that happen to exist", and rows only ever
    came into existence when a request handler ran `materialize_due` — so the
    rate measured how often the patient opened the app, not how much of their
    therapy they took. A twice-daily schedule running 35 days prescribes 70
    doses; a patient dormant since day 6 had 14 rows and the rate was computed
    over those 14. Someone who disengaged entirely could show a BETTER rate than
    someone who engaged and missed a few — the exact inversion a clinician would
    act on before escalating therapy.

    Now every expected occurrence in the window is reconciled into existence
    first (idempotently), then counted. The result depends only on the schedule
    and the clock.

    Semantics, stated because they are a clinical contract, not an implementation
    detail:

      expected  — occurrences the schedule prescribes in the window
      taken     — expected occurrences recorded TAKEN
      skipped   — expected occurrences recorded SKIPPED (a deliberate decision,
                  which is NOT a missed dose, and is counted separately)
      missed    — expected occurrences whose grace window expired unacted
      future    — prescribed but not yet due; excluded from the rate, since a
                  dose that has not come around cannot have been missed
      excluded_cancelled — occurrences from superseded schedule versions:
                  preserved historically, outside the active denominator

      adherence_rate = taken / (taken + skipped + missed)

    Skipped sits in the denominator deliberately: a patient who skips half their
    doses is not adherent, however intentional each skip was.

    `reconciled=False` means the period could not be reconciled (PRN, missing
    anchor, paused or stopped) and the caller MUST NOT render a confident
    percentage.
    """
    now = now or _now_utc()
    schedule = db.get(MedicationSchedule, schedule_id)
    if schedule is None or schedule.patient_id != patient_id:
        raise ScheduleNotFound("Không tìm thấy lịch.")

    tz = _tz(schedule.patient_timezone)
    today_local = now.astimezone(tz).date()
    if period_end is None:
        # Default to the schedule's OWN span, not a window anchored on today. A
        # course that finished in June has its adherence answered by June; a
        # today-anchored default would report zeros for every completed course
        # and read as "no data" rather than "here is how the course went".
        period_end = min(today_local, schedule.end_date or today_local)
    if period_start is None:
        default_start = period_end - dt.timedelta(days=29)
        period_start = (
            max(schedule.start_date, default_start)
            if schedule.start_date
            else default_start
        )
    if period_start > period_end:
        raise InvalidSchedule("Khoảng thời gian không hợp lệ (bắt đầu sau kết thúc).")
    if (period_end - period_start).days + 1 > MAX_ADHERENCE_PERIOD_DAYS:
        # Bounded: an unbounded window would let one request walk an arbitrary
        # calendar and materialize an arbitrary number of rows.
        raise InvalidSchedule(
            f"Khoảng thời gian tối đa là {MAX_ADHERENCE_PERIOD_DAYS} ngày."
        )

    stats = reconcile_period(
        db, schedule, period_start=period_start, period_end=period_end, now=now
    )

    window_start_utc = dt.datetime.combine(
        period_start, dt.time.min, tzinfo=tz
    ).astimezone(dt.UTC)
    window_end_utc = dt.datetime.combine(
        period_end + dt.timedelta(days=1), dt.time.min, tzinfo=tz
    ).astimezone(dt.UTC)

    rows = list(
        db.execute(
            select(
                DoseOccurrence.state,
                DoseOccurrence.scheduled_utc,
                DoseOccurrence.source_schedule_version,
            ).where(
                DoseOccurrence.schedule_id == schedule_id,
                DoseOccurrence.patient_id == patient_id,
            )
        )
    )

    def _aware(x: dt.datetime) -> dt.datetime:
        # SQLite returns naive datetimes; treat a naive stored instant as UTC so
        # the comparison with the aware cutoff never raises.
        return x if x.tzinfo is not None else x.replace(tzinfo=dt.UTC)

    cutoff = now - _MISSED_AFTER
    taken = skipped = missed = future = excluded = 0
    for state, when, version in rows:
        if when is None:
            continue
        when = _aware(when)
        if not (window_start_utc <= when < window_end_utc):
            continue
        if version is not None and version != schedule.version:
            # A superseded version's occurrence: real history, but not part of
            # the CURRENT prescription's denominator.
            excluded += 1
            continue
        if state == DOSE_TAKEN:
            taken += 1
        elif state == DOSE_SKIPPED:
            skipped += 1
        elif state == DOSE_MISSED or when <= cutoff:
            missed += 1
        else:
            future += 1

    denominator = taken + skipped + missed
    rate = round(taken / denominator, 3) if denominator else None
    return {
        "expected_count": denominator + future,
        "taken_count": taken,
        "skipped_count": skipped,
        "missed_count": missed,
        "future_count": future,
        "excluded_cancelled_count": excluded,
        "adherence_rate": rate,
        "period_start": period_start,
        "period_end": period_end,
        "timezone": schedule.patient_timezone,
        "calculation_version": ADHERENCE_CALCULATION_VERSION,
        "reconciled": bool(stats["backfilled"]) or denominator > 0,
        # Legacy keys, same numbers under the old names, so existing callers do
        # not silently start reading None while the frontend is updated.
        "total": denominator + future,
        "taken": taken,
        "skipped": skipped,
        "missed": missed,
    }
