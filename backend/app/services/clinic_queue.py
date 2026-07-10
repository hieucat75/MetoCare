"""Clinic check-in & queue service (Clinic SaaS C1 M08).

Mirrors `clinic_appointments.py`'s conventions: domain error classes for
controlled route responses, `db: Session` first positional + keyword-only
args, `audit.record(...)` before the caller's `db.commit()` (never commit
inside the service on the success path — that's the route's job).

Appointment-status sync ALWAYS goes through
`clinic_appointments.transition_status` (the shared fail-closed BRD §7.5
validator) — no parallel appointment machine exists here; this module owns
only the queue-ENTRY state machine (`_VALID_QUEUE_TRANSITIONS`).

Concurrency (plan §2/§3):
- Queue-number allocation: `UPDATE ... SET last_number = last_number + 1
  ... RETURNING` (Postgres row lock serializes concurrent check-ins;
  rollback rolls the increment back with the tx) + SAVEPOINT-wrapped INSERT
  and one retry for the first-insert-of-the-day race. Verified working on
  the test SQLite (3.53 >= 3.35, RETURNING supported) — no fallback needed.
- Every entry status transition is an atomic conditional
  `UPDATE ... WHERE id = ? AND status = <expected>` checked via `rowcount`;
  the concurrent loser gets `ClinicQueueConflictError` -> 409.
- Double check-in / duplicate active entry: the DB unique(appointment_id) +
  active-patient partial index are the authoritative guarantee; the
  IntegrityError is translated to a controlled 409 and the whole tx
  (including the chained appointment transitions) rolls back.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import as_naive_utc, utcnow
from app.models.care import Clinic, Doctor
from app.models.clinic import (
    ClinicAppointment,
    ClinicAppointmentSource,
    ClinicAppointmentStatus,
    ClinicQueueCounter,
    ClinicQueueEntry,
    ClinicQueueEntrySource,
    ClinicQueueEntryStatus,
    ClinicService,
)
from app.services import audit, clinic_patients
from app.services import clinic_appointments as appointments_service

# BR-M08-03 / plan §5 ADR-1: tenant `Clinic.queue_config` keys, all optional
# with fail-safe defaults. day_offset_minutes 420 = UTC+7 (VN clinic-local
# operational day, plan §5 ADR-2 — the codebase stores naive UTC).
_DEFAULT_QUEUE_CONFIG: dict = {
    "number_reset_scope": "branch_day",
    "max_missed_calls": 3,
    "checkin_window_hours": 12,
    "day_offset_minutes": 420,
}

_RESET_SCOPE_CLINIC_DAY = "clinic_day"
_RESET_SCOPE_BRANCH_DOCTOR_DAY = "branch_doctor_day"

_ACTIVE_ENTRY_STATUSES = (
    ClinicQueueEntryStatus.WAITING,
    ClinicQueueEntryStatus.CALLED,
    ClinicQueueEntryStatus.IN_CONSULTATION,
)


class ClinicQueueError(ValueError):
    """Domain error for invalid queue state (bad appointment status for
    check-in, window violation, invalid entry transition). Routes translate
    this to a controlled 400 — same pattern as `ClinicAppointmentError`."""


class ClinicQueueConflictError(ClinicQueueError):
    """Concurrency loser: duplicate check-in / duplicate active entry
    (IntegrityError on the DB unique indexes) or a conditional-UPDATE
    rowcount miss (someone else transitioned the entry first). Routes
    translate this to 409, before the parent class's 400."""


# Queue-entry state machine (plan §3) — fail-closed: every transition not
# listed here is rejected (with a durable denial audit, M07 precedent).
_VALID_QUEUE_TRANSITIONS: dict[str, set[str]] = {
    ClinicQueueEntryStatus.WAITING: {
        ClinicQueueEntryStatus.CALLED,
        ClinicQueueEntryStatus.LEFT,
    },
    ClinicQueueEntryStatus.CALLED: {
        ClinicQueueEntryStatus.WAITING,
        ClinicQueueEntryStatus.IN_CONSULTATION,
        ClinicQueueEntryStatus.LEFT,
    },
    ClinicQueueEntryStatus.IN_CONSULTATION: {ClinicQueueEntryStatus.COMPLETED},
}

# Check-in chain by current appointment status (plan §3): each hop goes
# through the shared M07 validator (audited per transition). Any status not
# listed (cancelled/completed/no_show/in_queue/in_consultation) can never
# check in.
_CHECKIN_CHAIN: dict[str, tuple[str, ...]] = {
    ClinicAppointmentStatus.PENDING: (
        ClinicAppointmentStatus.CONFIRMED,
        ClinicAppointmentStatus.ARRIVED,
        ClinicAppointmentStatus.IN_QUEUE,
    ),
    ClinicAppointmentStatus.CONFIRMED: (
        ClinicAppointmentStatus.ARRIVED,
        ClinicAppointmentStatus.IN_QUEUE,
    ),
    # Covers M07's no_show -> arrived reception override output.
    ClinicAppointmentStatus.ARRIVED: (ClinicAppointmentStatus.IN_QUEUE,),
}


# Codex M08 R1 P1: `Clinic.queue_config` is an untyped tenant-editable JSON
# blob — a string/list/negative value for a numeric key must degrade to the
# fail-safe default (never a 500 TypeError mid-check-in). Bounds keep even
# valid ints operationally sane.
_INT_CONFIG_BOUNDS: dict[str, tuple[int, int]] = {
    "max_missed_calls": (1, 20),
    "checkin_window_hours": (1, 48),
    "day_offset_minutes": (-720, 840),
}
_VALID_RESET_SCOPES = ("branch_day", "branch_doctor_day", "clinic_day")


def _coerce_int(value: object, *, default: int, low: int, high: int) -> int:
    # bool is an int subclass — treat it as invalid, not as 0/1. Out-of-range
    # ints revert to the default (Codex M08 R2 P1: clamping a nonsense value
    # like max_missed_calls=0 or day_offset_minutes=99999 silently invents a
    # config the tenant never chose — the stated fail-safe is the default).
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    if not (low <= value <= high):
        return default
    return value


def get_queue_config(clinic: Clinic) -> dict:
    """Merged, TYPE-SANITIZED copy — never mutates the Clinic row's JSON
    (immutability), never trusts its value types (Codex M08 R1 P1). The JSON
    column itself can hold a non-object (string/list/bool — Codex M08 R2 P1),
    so even `raw` is validated before any attribute access."""
    merged = dict(_DEFAULT_QUEUE_CONFIG)
    raw = clinic.queue_config if isinstance(clinic.queue_config, dict) else {}
    for key, (low, high) in _INT_CONFIG_BOUNDS.items():
        if key in raw:
            merged[key] = _coerce_int(raw[key], default=merged[key], low=low, high=high)
    scope = raw.get("number_reset_scope")
    if scope in _VALID_RESET_SCOPES:
        merged["number_reset_scope"] = scope
    return merged


def compute_service_date(config: dict, *, now: dt.datetime | None = None) -> dt.date:
    moment = now if now is not None else utcnow()
    return (moment + dt.timedelta(minutes=config["day_offset_minutes"])).date()


def mask_initials(full_name: str | None) -> str:
    """AC-M08-03 public-display masking: "Nguyễn Văn An" -> "N.V.A"."""
    parts = [part for part in (full_name or "").split() if part]
    if not parts:
        return "?"
    return ".".join(part[0].upper() for part in parts)


# ---------------------------------------------------------------------------
# Queue-number allocation (BR-M08-03)
# ---------------------------------------------------------------------------


def _counter_scope(
    config: dict, *, branch_id: str, doctor_id: str | None
) -> tuple[str | None, str]:
    """(counter branch_id, scope_key) per the tenant reset scope. Unknown
    values fall back to the branch_day default (fail-safe, ADR-1)."""
    scope = config["number_reset_scope"]
    if scope == _RESET_SCOPE_CLINIC_DAY:
        # NULL branch = the single clinic-wide counter row (see model note).
        return None, ""
    if scope == _RESET_SCOPE_BRANCH_DOCTOR_DAY:
        return branch_id, f"doctor:{doctor_id or 'none'}"
    return branch_id, ""


def _insert_counter_row(
    db: Session, *, clinic_id: str, branch_id: str | None, scope_key: str, counter_date: dt.date
) -> bool:
    """First-insert-of-the-day, inside a SAVEPOINT: on the concurrent
    first-insert race the IntegrityError rolls back the savepoint ONLY (M06
    rollback-safety lesson — never `db.rollback()` mid-composed-transaction;
    check-in has already flushed appointment transitions in this same tx).
    Returns False when this call lost the race, so the caller retries the
    UPDATE once. Module-level function so tests can monkeypatch it to
    simulate the race."""
    try:
        with db.begin_nested():
            db.add(
                ClinicQueueCounter(
                    clinic_id=clinic_id,
                    branch_id=branch_id,
                    scope_key=scope_key,
                    counter_date=counter_date,
                    last_number=1,
                )
            )
            db.flush()
        return True
    except IntegrityError:
        return False


def _allocate_queue_number(
    db: Session, *, clinic_id: str, branch_id: str | None, scope_key: str, counter_date: dt.date
) -> int:
    branch_condition = (
        ClinicQueueCounter.branch_id.is_(None)
        if branch_id is None
        else ClinicQueueCounter.branch_id == branch_id
    )
    for _attempt in range(2):
        allocated = db.execute(
            update(ClinicQueueCounter)
            .where(
                ClinicQueueCounter.clinic_id == clinic_id,
                branch_condition,
                ClinicQueueCounter.scope_key == scope_key,
                ClinicQueueCounter.counter_date == counter_date,
            )
            .values(last_number=ClinicQueueCounter.last_number + 1)
            .returning(ClinicQueueCounter.last_number),
            execution_options={"synchronize_session": False},
        ).scalar_one_or_none()
        if allocated is not None:
            return allocated
        if _insert_counter_row(
            db,
            clinic_id=clinic_id,
            branch_id=branch_id,
            scope_key=scope_key,
            counter_date=counter_date,
        ):
            return 1
        # Lost the first-insert race — the row now exists; retry the UPDATE.
    raise ClinicQueueConflictError("Không thể cấp số thứ tự — xung đột đồng thời.")


# ---------------------------------------------------------------------------
# Check-in (US-M08-01/02, BR-M08-01)
# ---------------------------------------------------------------------------


def _advance_appointment_to_in_queue(
    db: Session, *, appointment: ClinicAppointment, actor_id: str
) -> None:
    """Chained hops through the shared M07 validator (each hop audited).
    Module-level so tests can monkeypatch it to simulate the concurrent
    double-check-in TOCTOU loser, exercising unique(appointment_id) as the
    real safety net (same pattern as `_has_overlapping_appointment`)."""
    steps = _CHECKIN_CHAIN.get(appointment.status)
    if steps is None:
        raise ClinicQueueError(
            f"Không thể check-in lịch hẹn ở trạng thái '{appointment.status}'."
        )
    for target in steps:
        appointments_service.transition_status(
            db, appointment=appointment, new_status=target, actor_id=actor_id
        )


def _deny_checkin(
    db: Session, *, appointment: ClinicAppointment, actor_id: str, reason_code: str, message: str
) -> None:
    """Codex M08 R3 P1: a REJECTED check-in attempt must leave a durable,
    PHI-free audit trail (reason code only, never free text), same denial-
    durability discipline as the transition validators. The commit is safe
    for the same reason as M07's precedent: the scheduled check-in route
    flushes nothing before these checks run, and the walk-in path cannot
    reach either denial (its appointment is freshly `pending` — always in
    the chain — with start_time=now — always inside the window)."""
    audit.record(
        db,
        actor_type="user",
        actor_id=actor_id,
        action="clinic_queue_checkin_denied",
        resource_type="clinic_appointment",
        resource_id=appointment.id,
        clinic_id=appointment.clinic_id,
        outcome="denied",
        severity="warning",
        details={"reason": reason_code, "appointment_status": appointment.status},
    )
    db.commit()
    raise ClinicQueueError(message)


def check_in_appointment(
    db: Session,
    *,
    clinic: Clinic,
    appointment: ClinicAppointment,
    actor_id: str,
    source: str = ClinicQueueEntrySource.SCHEDULED,
) -> ClinicQueueEntry:
    config = get_queue_config(clinic)
    now = utcnow()

    if appointment.status not in _CHECKIN_CHAIN:
        _deny_checkin(
            db,
            appointment=appointment,
            actor_id=actor_id,
            reason_code="invalid_status",
            message=f"Không thể check-in lịch hẹn ở trạng thái '{appointment.status}'.",
        )

    # Plan §5 ADR-3: |now - start_time| <= checkin_window_hours. Late
    # arrivals past the window use M07's no-show -> arrived-override
    # (reason required), then check in from `arrived` — which is exactly why
    # an appointment ALREADY at `arrived` is exempt from the window here:
    # that status only exists via a human override with a recorded reason,
    # and re-applying the window would dead-end the documented late-arrival
    # path this error message points at.
    start_time = as_naive_utc(appointment.start_time)
    window = dt.timedelta(hours=config["checkin_window_hours"])
    is_human_overridden_arrival = appointment.status == ClinicAppointmentStatus.ARRIVED
    if not is_human_overridden_arrival and abs(now - start_time) > window:
        _deny_checkin(
            db,
            appointment=appointment,
            actor_id=actor_id,
            reason_code="outside_window",
            message=(
                "Ngoài khung giờ check-in cho lịch hẹn này — dùng quy trình xử lý"
                " đến muộn (no-show -> arrived) nếu bệnh nhân đến trễ."
            ),
        )

    _advance_appointment_to_in_queue(db, appointment=appointment, actor_id=actor_id)

    service_date = compute_service_date(config, now=now)
    counter_branch_id, scope_key = _counter_scope(
        config, branch_id=appointment.branch_id, doctor_id=appointment.doctor_id
    )
    queue_number = _allocate_queue_number(
        db,
        clinic_id=appointment.clinic_id,
        branch_id=counter_branch_id,
        scope_key=scope_key,
        counter_date=service_date,
    )

    entry = ClinicQueueEntry(
        clinic_id=appointment.clinic_id,
        branch_id=appointment.branch_id,
        patient_id=appointment.patient_id,
        appointment_id=appointment.id,
        doctor_id=appointment.doctor_id,
        service_date=service_date,
        queue_number=queue_number,
        status=ClinicQueueEntryStatus.WAITING,
        source=source,
        checked_in_by_user_id=actor_id,
        checked_in_at=now,
    )
    db.add(entry)
    try:
        db.flush()
    except IntegrityError as exc:
        # unique(appointment_id) OR the active-patient partial index. Single
        # terminal attempt (M07 create_appointment precedent): the rollback
        # also discards this request's chained appointment transitions, so
        # the concurrent loser never double-transitions the appointment.
        db.rollback()
        raise ClinicQueueConflictError(
            "Không thể check-in — lịch hẹn đã được check-in hoặc bệnh nhân đang"
            " có lượt chờ hoạt động (xung đột đồng thời)."
        ) from exc

    audit.record(
        db,
        actor_type="user",
        actor_id=actor_id,
        action="clinic_queue_checkin",
        resource_type="clinic_queue_entry",
        resource_id=entry.id,
        clinic_id=appointment.clinic_id,
        details={"queue_number": queue_number, "source": source},
    )
    return entry


def walk_in_check_in(
    db: Session,
    *,
    clinic: Clinic,
    actor_id: str,
    branch_id: str,
    patient_id: str,
    service_id: str,
    doctor_id: str | None = None,
    notes: str | None = None,
) -> ClinicQueueEntry:
    """BR-M08-01: a walk-in creates its own ClinicAppointment (start_time =
    now, source `walk_in`, overlap pre-check skipped per ADR-4 — an
    immediate arrival is not a future slot reservation) and then runs the
    exact same check-in chain. All of create_appointment's tenant
    validations (active relationship, active service, doctor membership,
    cross-clinic ids) apply unchanged — no bypass."""
    appointment = appointments_service.create_appointment(
        db,
        clinic_id=clinic.id,
        actor_id=actor_id,
        branch_id=branch_id,
        patient_id=patient_id,
        doctor_id=doctor_id,
        service_id=service_id,
        start_time=utcnow(),
        created_by_source=ClinicAppointmentSource.WALK_IN,
        notes=notes,
        skip_overlap_precheck=True,
    )
    entry = check_in_appointment(
        db,
        clinic=clinic,
        appointment=appointment,
        actor_id=actor_id,
        source=ClinicQueueEntrySource.WALK_IN,
    )
    audit.record(
        db,
        actor_type="user",
        actor_id=actor_id,
        action="clinic_queue_walkin",
        resource_type="clinic_queue_entry",
        resource_id=entry.id,
        clinic_id=clinic.id,
        details={"queue_number": entry.queue_number},
    )
    return entry


# ---------------------------------------------------------------------------
# Entry transitions (plan §3) — atomic conditional UPDATEs
# ---------------------------------------------------------------------------


def _assert_transition_allowed(
    db: Session, *, entry: ClinicQueueEntry, new_status: str, actor_id: str
) -> None:
    allowed = _VALID_QUEUE_TRANSITIONS.get(entry.status, set())
    if new_status in allowed:
        return
    audit.record(
        db,
        actor_type="user",
        actor_id=actor_id,
        action="clinic_queue_transition_denied",
        resource_type="clinic_queue_entry",
        resource_id=entry.id,
        clinic_id=entry.clinic_id,
        outcome="denied",
        severity="warning",
        details={"from": entry.status, "to": new_status},
    )
    # M07 transition_status denial-durability precedent: routes only commit
    # on the success path, and get_session()'s implicit rollback would
    # silently discard the denial audit row otherwise. Safe here for the
    # same reason as M07: every caller runs this check BEFORE flushing any
    # other change in the request (appointment sync and the conditional
    # entry UPDATE both happen after), so this commit persists the denial
    # audit and nothing else.
    db.commit()
    raise ClinicQueueError(
        f"Không thể chuyển trạng thái hàng chờ từ '{entry.status}' sang '{new_status}'."
    )


def _apply_transition(
    db: Session,
    *,
    entry_id: str,
    expected_status: str,
    values: dict,
    extra_where: list | None = None,
) -> bool:
    """The serialization point for two staff acting on the same entry:
    exactly one conditional UPDATE wins; the loser sees rowcount == 0.
    `extra_where` lets a caller make additional invariants atomic (e.g. the
    missed-call cap — Codex M08 R1 P1). Module-level so tests can monkeypatch
    it to inject a concurrent winner between the route's read and this
    UPDATE."""
    result = db.execute(
        update(ClinicQueueEntry)
        .where(
            ClinicQueueEntry.id == entry_id,
            ClinicQueueEntry.status == expected_status,
            *(extra_where or []),
        )
        .values(**values),
        execution_options={"synchronize_session": False},
    )
    return result.rowcount == 1


def _transition_entry(
    db: Session,
    *,
    entry: ClinicQueueEntry,
    new_status: str,
    actor_id: str,
    extra_values: dict | None = None,
    details_extra: dict | None = None,
    extra_where: list | None = None,
) -> ClinicQueueEntry:
    expected_status = entry.status
    _assert_transition_allowed(db, entry=entry, new_status=new_status, actor_id=actor_id)
    values = {"status": new_status, **(extra_values or {})}
    if not _apply_transition(
        db,
        entry_id=entry.id,
        expected_status=expected_status,
        values=values,
        extra_where=extra_where,
    ):
        raise ClinicQueueConflictError(
            "Lượt chờ vừa được cập nhật bởi người khác — vui lòng tải lại hàng chờ."
        )
    # The conditional UPDATE bypassed the ORM; expire so subsequent
    # attribute access re-reads the row's new values.
    db.expire(entry)
    audit.record(
        db,
        actor_type="user",
        actor_id=actor_id,
        action="clinic_queue_transition",
        resource_type="clinic_queue_entry",
        resource_id=entry.id,
        clinic_id=entry.clinic_id,
        details={"from": expected_status, "to": new_status, **(details_extra or {})},
    )
    return entry


def call_entry(db: Session, *, entry: ClinicQueueEntry, actor_id: str) -> ClinicQueueEntry:
    return _transition_entry(
        db,
        entry=entry,
        new_status=ClinicQueueEntryStatus.CALLED,
        actor_id=actor_id,
        extra_values={"called_at": utcnow()},
    )


def mark_missed_call(
    db: Session, *, entry: ClinicQueueEntry, actor_id: str, max_missed_calls: int
) -> ClinicQueueEntry:
    """BR-M08-04's cap is a hard bound (Codex M08 R1 P1: previously only the
    doctor's `call` was gated, so call→missed cycles could push the count
    past the configured max indefinitely). At the cap, reception's resolution
    paths are `call` again or `leave` — never another missed-call increment.
    Enforced twice: a friendly fail-fast here, and atomically inside the
    conditional UPDATE (`missed_call_count < max`) so a concurrent racer
    can't overshoot between this read and the write."""
    if entry.missed_call_count >= max_missed_calls:
        raise ClinicQueueError(
            "Lượt chờ đã đạt số lần gọi nhỡ tối đa — lễ tân xử lý bằng cách"
            " gọi lại hoặc hủy lượt chờ."
        )
    # SQL-side increment; the conditional WHERE status='called' guarantees at
    # most one missed-call per call cycle wins, so the loaded count + 1 in
    # the audit details cannot double-count under concurrency (BR-M08-04).
    new_count = entry.missed_call_count + 1
    return _transition_entry(
        db,
        entry=entry,
        new_status=ClinicQueueEntryStatus.WAITING,
        actor_id=actor_id,
        extra_values={"missed_call_count": ClinicQueueEntry.missed_call_count + 1},
        details_extra={"missed_call_count": new_count},
        extra_where=[ClinicQueueEntry.missed_call_count < max_missed_calls],
    )


def start_consultation(
    db: Session, *, entry: ClinicQueueEntry, appointment: ClinicAppointment, actor_id: str
) -> ClinicQueueEntry:
    """Queue called -> in_consultation + appointment in_queue ->
    in_consultation (shared validator). Ordering matters: the entry-machine
    validity check runs first (its denial path commits — nothing else may be
    pending), the appointment sync flushes second, and the conditional entry
    UPDATE decides the race last — a rowcount loser raises before commit, so
    the appointment sync rolls back with it (no partial state). No Encounter
    is created here — M09's job (plan §5 ADR-5)."""
    _assert_transition_allowed(
        db, entry=entry, new_status=ClinicQueueEntryStatus.IN_CONSULTATION, actor_id=actor_id
    )
    appointments_service.transition_status(
        db,
        appointment=appointment,
        new_status=ClinicAppointmentStatus.IN_CONSULTATION,
        actor_id=actor_id,
    )
    return _transition_entry(
        db,
        entry=entry,
        new_status=ClinicQueueEntryStatus.IN_CONSULTATION,
        actor_id=actor_id,
        extra_values={"consultation_started_at": utcnow()},
    )


def complete_entry(
    db: Session, *, entry: ClinicQueueEntry, appointment: ClinicAppointment, actor_id: str
) -> ClinicQueueEntry:
    """Operational close-out (clinical notes are M09). Same ordering
    rationale as `start_consultation`."""
    _assert_transition_allowed(
        db, entry=entry, new_status=ClinicQueueEntryStatus.COMPLETED, actor_id=actor_id
    )
    appointments_service.transition_status(
        db,
        appointment=appointment,
        new_status=ClinicAppointmentStatus.COMPLETED,
        actor_id=actor_id,
    )
    return _transition_entry(
        db,
        entry=entry,
        new_status=ClinicQueueEntryStatus.COMPLETED,
        actor_id=actor_id,
        extra_values={"completed_at": utcnow()},
    )


def leave_entry(db: Session, *, entry: ClinicQueueEntry, actor_id: str) -> ClinicQueueEntry:
    """Terminal at the queue-entry level ONLY: BRD §7.5 has no backward
    appointment transition out of arrived/in_queue, so the appointment stays
    at its last valid status (plan §5 ADR-6 — documented limitation, a
    re-queue-after-leave flow needs a BRD/PTH decision)."""
    return _transition_entry(
        db,
        entry=entry,
        new_status=ClinicQueueEntryStatus.LEFT,
        actor_id=actor_id,
        extra_values={"left_at": utcnow()},
    )


def set_priority(
    db: Session, *, entry: ClinicQueueEntry, actor_id: str, is_priority: bool, reason: str
) -> ClinicQueueEntry:
    """BR-M08-02: the system never auto-prioritizes — this human-only action
    requires a reason (schema-enforced + defensively re-checked here, Codex
    M08 R1 P1: a whitespace-only string must not satisfy the mandatory-reason
    rule). Verbatim reason lives on the row; audit records only
    `reason_provided` (M07 PHI-audit discipline).

    Concurrency (Codex M08 R1 P1): a conditional UPDATE predicated on the
    loaded `is_priority` — not ORM read-modify-write — so two staff racing
    the same toggle get exactly one winner (the loser 409s and reloads) and
    the audit's from/to can never record a stale pair."""
    reason = reason.strip()
    if not reason:
        raise ClinicQueueError("Lý do ưu tiên là bắt buộc.")
    old_priority = entry.is_priority
    result = db.execute(
        update(ClinicQueueEntry)
        .where(ClinicQueueEntry.id == entry.id, ClinicQueueEntry.is_priority == old_priority)
        .values(
            is_priority=is_priority,
            priority_reason=reason,
            priority_set_by_user_id=actor_id,
        ),
        execution_options={"synchronize_session": False},
    )
    if result.rowcount != 1:
        raise ClinicQueueConflictError(
            "Cờ ưu tiên vừa được cập nhật bởi người khác — vui lòng tải lại hàng chờ."
        )
    db.expire(entry)
    audit.record(
        db,
        actor_type="user",
        actor_id=actor_id,
        action="clinic_queue_priority",
        resource_type="clinic_queue_entry",
        resource_id=entry.id,
        clinic_id=entry.clinic_id,
        details={"from": old_priority, "to": is_priority, "reason_provided": True},
    )
    return entry


# ---------------------------------------------------------------------------
# Reads (QUEUE-02 / AC-M08-03)
# ---------------------------------------------------------------------------


def get_own_queue_entry(
    db: Session, *, clinic_id: str, entry_id: str
) -> ClinicQueueEntry | None:
    return db.execute(
        select(ClinicQueueEntry).where(
            ClinicQueueEntry.id == entry_id, ClinicQueueEntry.clinic_id == clinic_id
        )
    ).scalar_one_or_none()


def _waiting_minutes(entry: ClinicQueueEntry, *, now: dt.datetime) -> int:
    """BR-M08-05: wait ends at consultation start; a left entry stops at
    left_at; an active entry accrues until now."""
    end = as_naive_utc(entry.consultation_started_at) or as_naive_utc(entry.left_at) or now
    seconds = (end - as_naive_utc(entry.checked_in_at)).total_seconds()
    return max(0, int(seconds // 60))


def _serialize_entry(
    db: Session,
    entry: ClinicQueueEntry,
    appointment: ClinicAppointment,
    *,
    config: dict,
    now: dt.datetime,
) -> dict:
    doctor = db.get(Doctor, entry.doctor_id) if entry.doctor_id else None
    service = db.get(ClinicService, appointment.service_id)
    profile_fields = clinic_patients.get_profile_fields(db, patient_id=entry.patient_id)
    return {
        "id": entry.id,
        "clinic_id": entry.clinic_id,
        "branch_id": entry.branch_id,
        "patient_id": entry.patient_id,
        "appointment_id": entry.appointment_id,
        "doctor_id": entry.doctor_id,
        "service_date": entry.service_date,
        "queue_number": entry.queue_number,
        "status": entry.status,
        "is_priority": entry.is_priority,
        "priority_reason": entry.priority_reason,
        "missed_call_count": entry.missed_call_count,
        "source": entry.source,
        "checked_in_at": entry.checked_in_at,
        "called_at": entry.called_at,
        "consultation_started_at": entry.consultation_started_at,
        "completed_at": entry.completed_at,
        "left_at": entry.left_at,
        "patient_display_name": (profile_fields or {}).get("full_name"),
        "doctor_name": doctor.full_name if doctor else None,
        "service_name": service.name if service else None,
        "appointment_start_time": appointment.start_time,
        "waiting_minutes": _waiting_minutes(entry, now=now),
        "requires_reception_action": (
            entry.status in _ACTIVE_ENTRY_STATUSES
            and entry.missed_call_count >= config["max_missed_calls"]
        ),
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
    }


def get_entry_out(db: Session, *, clinic: Clinic, entry: ClinicQueueEntry) -> dict:
    appointment = db.get(ClinicAppointment, entry.appointment_id)
    return _serialize_entry(
        db, entry, appointment, config=get_queue_config(clinic), now=utcnow()
    )


def list_queue(
    db: Session,
    *,
    clinic: Clinic,
    branch_ids: list[str] | None = None,
    doctor_id: str | None = None,
    service_date: dt.date | None = None,
    status: str | None = None,
) -> tuple[list[dict], int]:
    """Ordering per plan §4: priority first, then queue_number asc, scoped to
    one service_date (default: the clinic-local today). Queue size is
    operationally small (one day, one clinic), so the per-row decrypt of the
    patient display name (M06 path) is acceptable — no pagination mandated."""
    config = get_queue_config(clinic)
    effective_date = service_date if service_date is not None else compute_service_date(config)

    conditions = [
        ClinicQueueEntry.clinic_id == clinic.id,
        ClinicQueueEntry.service_date == effective_date,
    ]
    if branch_ids is not None:
        conditions.append(ClinicQueueEntry.branch_id.in_(branch_ids))
    if doctor_id is not None:
        conditions.append(ClinicQueueEntry.doctor_id == doctor_id)
    if status is not None:
        conditions.append(ClinicQueueEntry.status == status)

    rows = db.execute(
        select(ClinicQueueEntry, ClinicAppointment)
        .join(ClinicAppointment, ClinicQueueEntry.appointment_id == ClinicAppointment.id)
        .where(*conditions)
        .order_by(
            ClinicQueueEntry.is_priority.desc(),
            ClinicQueueEntry.queue_number.asc(),
        )
    ).all()

    now = utcnow()
    items = [
        _serialize_entry(db, entry, appointment, config=config, now=now)
        for entry, appointment in rows
    ]
    return items, len(items)


def display_queue(
    db: Session,
    *,
    clinic: Clinic,
    branch_ids: list[str] | None = None,
    service_date: dt.date | None = None,
    doctor_id: str | None = None,
) -> list[dict]:
    """Public-screen payload (AC-M08-03): queue number + masked initials +
    status + doctor name ONLY — no service, no full name, no patient_id.
    `doctor_id` carries the route's doctor own-scoping (Codex M08 R2 P1)."""
    items, _total = list_queue(
        db,
        clinic=clinic,
        branch_ids=branch_ids,
        service_date=service_date,
        doctor_id=doctor_id,
    )
    return [
        {
            "queue_number": item["queue_number"],
            "patient_initials": mask_initials(item["patient_display_name"]),
            "status": item["status"],
            "doctor_name": item["doctor_name"],
        }
        for item in items
    ]
