"""Clinic appointment management service (Clinic SaaS C1 M07).

Mirrors `clinic_patients.py`'s structure: a domain `ClinicAppointmentError`
for controlled 400s, functions take `db: Session` first positional +
keyword-only args, `audit.record(...)` before the caller's `db.commit()`
(never commit inside the service — that's the route's job).

State machine (`_VALID_TRANSITIONS`) implements the complete BRD table
(m07-appointment.md §7.5) fail-closed — M07 only exposes routes for its own
subset (confirm/cancel/reschedule/no_show/no_show->arrived);
arrived->in_queue->in_consultation->completed are M08/M09's own action
endpoints, which can reuse this same validator
(M07_IMPLEMENTATION_PLAN.md §4).

Double-booking: the DB partial unique index (`c1_m07_appointments` migration)
is the authoritative guarantee for exact-start-time collisions; this module's
overlap pre-check is a best-effort, non-authoritative UX guard for free-form
overlapping-but-different-start-time bookings (documented scope, not a
silent gap — M07_IMPLEMENTATION_PLAN.md §2).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import as_naive_utc, utcnow
from app.models.care import Clinic
from app.models.clinic import (
    ClinicAppointment,
    ClinicAppointmentStatus,
    ClinicBranchStatus,
    ClinicMembership,
    ClinicMembershipStatus,
    ClinicPatientRelationship,
    ClinicPatientRelationshipStatus,
    ClinicService,
    ClinicServiceStatus,
)
from app.services import audit
from app.services.clinic_branch import get_branch
from app.services.clinic_membership import ClinicMembershipError, assert_doctor_ids_belong_to_clinic

_WEEKDAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class ClinicAppointmentError(ValueError):
    """Domain error for invalid appointment state (inactive patient/service,
    doctor not a clinic member, working-hours violation, invalid state
    transition). Routes translate this to a controlled 400 — never a raw
    500, same pattern as `ClinicPatientError`/`ClinicServiceError`."""


def _parse_range(range_str: str) -> tuple[dt.time, dt.time] | None:
    try:
        start_str, end_str = range_str.split("-")
        return (
            dt.datetime.strptime(start_str.strip(), "%H:%M").time(),
            dt.datetime.strptime(end_str.strip(), "%H:%M").time(),
        )
    except (ValueError, AttributeError):
        return None


def _is_within_working_hours(
    working_hours: dict | None, start: dt.datetime, end: dt.datetime
) -> bool:
    """`ClinicBranch.working_hours` is free-form: a weekday key
    (`mon`..`sun`) maps to a single `"HH:MM-HH:MM"` string OR a list of such
    strings for split shifts. A MISSING or empty-string/empty-list value for
    that weekday means "no restriction configured," i.e. permissive — this
    matches every existing test fixture using `working_hours={}`."""
    if not working_hours:
        return True
    raw_ranges = working_hours.get(_WEEKDAY_KEYS[start.weekday()])
    if not raw_ranges:
        return True
    ranges = [raw_ranges] if isinstance(raw_ranges, str) else raw_ranges
    if not ranges:
        return True
    for range_str in ranges:
        parsed = _parse_range(range_str)
        if parsed is None:
            continue
        range_start, range_end = parsed
        if (
            start.date() == end.date()
            and start.time() >= range_start
            and end.time() <= range_end
        ):
            return True
    return False


def _has_overlapping_appointment(
    db: Session, *, doctor_id: str, start_time: dt.datetime, end_time: dt.datetime
) -> bool:
    """Best-effort, non-authoritative pre-check (see module docstring) — a
    separate function so it can be monkeypatched in tests to simulate the
    TOCTOU loser of a concurrent double-booking race, exercising the DB
    unique index as the real safety net."""
    conflict = db.execute(
        select(ClinicAppointment).where(
            ClinicAppointment.doctor_id == doctor_id,
            ClinicAppointment.status.notin_(
                [ClinicAppointmentStatus.CANCELLED, ClinicAppointmentStatus.NO_SHOW]
            ),
            ClinicAppointment.start_time < end_time,
            ClinicAppointment.end_time > start_time,
        )
    ).scalars().first()
    return conflict is not None


def create_appointment(
    db: Session,
    *,
    clinic_id: str,
    actor_id: str,
    branch_id: str,
    patient_id: str,
    doctor_id: str | None,
    service_id: str,
    start_time: dt.datetime,
    created_by_source: str,
    notes: str | None = None,
    override_working_hours_reason: str | None = None,
    is_override_allowed: bool = False,
) -> ClinicAppointment:
    start_time = as_naive_utc(start_time)

    branch = get_branch(db, clinic_id=clinic_id, branch_id=branch_id)
    if branch is None:
        raise ClinicAppointmentError("Không tìm thấy chi nhánh.")
    if branch.status != ClinicBranchStatus.ACTIVE:
        raise ClinicAppointmentError("Chi nhánh hiện không hoạt động.")

    service = db.execute(
        select(ClinicService).where(
            ClinicService.id == service_id, ClinicService.clinic_id == clinic_id
        )
    ).scalar_one_or_none()
    if service is None:
        raise ClinicAppointmentError("Không tìm thấy dịch vụ.")
    if service.status != ClinicServiceStatus.ACTIVE:
        raise ClinicAppointmentError("Dịch vụ hiện không hoạt động.")
    if not service.duration_minutes:
        raise ClinicAppointmentError("Dịch vụ chưa cấu hình thời lượng.")

    relationship = db.execute(
        select(ClinicPatientRelationship).where(
            ClinicPatientRelationship.clinic_id == clinic_id,
            ClinicPatientRelationship.patient_id == patient_id,
        )
    ).scalar_one_or_none()
    if relationship is None or relationship.status != ClinicPatientRelationshipStatus.ACTIVE:
        raise ClinicAppointmentError(
            "Bệnh nhân chưa được liên kết hoạt động với phòng khám này."
        )

    if doctor_id is not None:
        try:
            assert_doctor_ids_belong_to_clinic(db, clinic_id=clinic_id, doctor_ids=[doctor_id])
        except ClinicMembershipError as exc:
            raise ClinicAppointmentError(str(exc)) from exc
        doctor_membership = db.execute(
            select(ClinicMembership).where(
                ClinicMembership.clinic_id == clinic_id,
                ClinicMembership.doctor_profile_id == doctor_id,
                ClinicMembership.status == ClinicMembershipStatus.ACTIVE,
            )
        ).scalars().first()
        if (
            doctor_membership is not None
            and doctor_membership.branch_ids
            and branch_id not in doctor_membership.branch_ids
        ):
            raise ClinicAppointmentError("Bác sĩ không thuộc chi nhánh được chọn.")

    end_time = start_time + dt.timedelta(minutes=service.duration_minutes)

    if not _is_within_working_hours(branch.working_hours, start_time, end_time):
        if not (is_override_allowed and (override_working_hours_reason or "").strip()):
            raise ClinicAppointmentError(
                "Thời gian đặt lịch nằm ngoài giờ làm việc của chi nhánh."
            )

    if doctor_id is not None and _has_overlapping_appointment(
        db, doctor_id=doctor_id, start_time=start_time, end_time=end_time
    ):
        raise ClinicAppointmentError("Bác sĩ đã có lịch hẹn trùng khung giờ này.")

    appointment = ClinicAppointment(
        clinic_id=clinic_id,
        branch_id=branch_id,
        patient_id=patient_id,
        doctor_id=doctor_id,
        service_id=service_id,
        price_snapshot=service.price,
        start_time=start_time,
        end_time=end_time,
        status=ClinicAppointmentStatus.PENDING,
        created_by_user_id=actor_id,
        created_by_source=created_by_source,
        notes=notes,
    )
    db.add(appointment)
    try:
        db.flush()
    except IntegrityError as exc:
        # Single terminal attempt — no retry-after-rollback (M06 rollback-
        # safety lesson: this may be the second half of a composed
        # transaction, e.g. reschedule_appointment, and a rollback here
        # would discard earlier work in the same request too).
        db.rollback()
        raise ClinicAppointmentError(
            "Không thể đặt lịch — khung giờ này đã có lịch hẹn khác cho bác sĩ"
            " (xung đột đồng thời)."
        ) from exc

    audit.record(
        db,
        actor_type="user",
        actor_id=actor_id,
        action="clinic_appointment_create",
        resource_type="clinic_appointment",
        resource_id=appointment.id,
        clinic_id=clinic_id,
    )
    return appointment


def get_own_clinic_appointment(
    db: Session, *, clinic_id: str, appointment_id: str
) -> ClinicAppointment | None:
    return db.execute(
        select(ClinicAppointment).where(
            ClinicAppointment.id == appointment_id, ClinicAppointment.clinic_id == clinic_id
        )
    ).scalar_one_or_none()


def list_appointments(
    db: Session,
    *,
    clinic_id: str,
    branch_ids: list[str] | None = None,
    doctor_id: str | None = None,
    status: str | None = None,
    date_from: dt.datetime | None = None,
    date_to: dt.datetime | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[ClinicAppointment], int]:
    """None of these fields are encrypted (unlike M06's roster), so
    filter/paginate directly in SQL."""
    conditions = [ClinicAppointment.clinic_id == clinic_id]
    if branch_ids is not None:
        conditions.append(ClinicAppointment.branch_id.in_(branch_ids))
    if doctor_id is not None:
        conditions.append(ClinicAppointment.doctor_id == doctor_id)
    if status is not None:
        conditions.append(ClinicAppointment.status == status)
    if date_from is not None:
        conditions.append(ClinicAppointment.start_time >= as_naive_utc(date_from))
    if date_to is not None:
        conditions.append(ClinicAppointment.start_time <= as_naive_utc(date_to))

    total = db.execute(
        select(func.count()).select_from(ClinicAppointment).where(*conditions)
    ).scalar_one()
    items = list(
        db.execute(
            select(ClinicAppointment)
            .where(*conditions)
            .order_by(ClinicAppointment.start_time.desc())
            .offset(skip)
            .limit(limit)
        ).scalars()
    )
    return items, total


# Complete BRD state table (m07-appointment.md §7.5) — fail-closed, every
# transition not listed here is rejected. Cancelled/Completed are terminal
# (no outgoing entries).
_VALID_TRANSITIONS: dict[str, set[str]] = {
    ClinicAppointmentStatus.PENDING: {
        ClinicAppointmentStatus.CONFIRMED,
        ClinicAppointmentStatus.CANCELLED,
    },
    ClinicAppointmentStatus.CONFIRMED: {
        ClinicAppointmentStatus.ARRIVED,
        ClinicAppointmentStatus.CANCELLED,
        ClinicAppointmentStatus.NO_SHOW,
    },
    ClinicAppointmentStatus.NO_SHOW: {ClinicAppointmentStatus.ARRIVED},
    ClinicAppointmentStatus.ARRIVED: {ClinicAppointmentStatus.IN_QUEUE},
    ClinicAppointmentStatus.IN_QUEUE: {ClinicAppointmentStatus.IN_CONSULTATION},
    ClinicAppointmentStatus.IN_CONSULTATION: {ClinicAppointmentStatus.COMPLETED},
}


def transition_status(
    db: Session,
    *,
    appointment: ClinicAppointment,
    new_status: str,
    actor_id: str,
    reason: str | None = None,
) -> ClinicAppointment:
    allowed = _VALID_TRANSITIONS.get(appointment.status, set())
    if new_status not in allowed:
        audit.record(
            db,
            actor_type="user",
            actor_id=actor_id,
            action="clinic_appointment_transition_denied",
            resource_type="clinic_appointment",
            resource_id=appointment.id,
            clinic_id=appointment.clinic_id,
            outcome="denied",
            severity="warning",
            details={"from": appointment.status, "to": new_status},
        )
        # Commit here, not just flush: every calling route only calls
        # db.commit() on the success path (it raises HTTPException from the
        # ClinicAppointmentError below without committing), and
        # get_session()'s `finally: db.close()` implicitly rolls back an
        # uncommitted flush when this exception propagates — without this
        # commit, the denial audit row would be silently discarded every
        # time, undermining BR-M07-01's "mọi transition ghi audit" for
        # exactly the case (a rejected attempt) that most needs a durable
        # trail. Same precedent as clinic_membership.accept_invitation's
        # expired-token path. Safe here: the only call site that chains a
        # second transition_status in the same transaction
        # (reschedule_appointment, cancelling the original after creating
        # the new appointment) pre-validates the original's status is
        # PENDING or CONFIRMED, and both transition to CANCELLED validly, so
        # this denial branch — and therefore this commit — can never fire
        # mid-reschedule.
        db.commit()
        raise ClinicAppointmentError(
            f"Không thể chuyển trạng thái từ '{appointment.status}' sang '{new_status}'."
        )

    old_status = appointment.status
    appointment.status = new_status
    db.flush()
    audit.record(
        db,
        actor_type="user",
        actor_id=actor_id,
        action="clinic_appointment_transition",
        resource_type="clinic_appointment",
        resource_id=appointment.id,
        clinic_id=appointment.clinic_id,
        details={"from": old_status, "to": new_status, "reason": reason},
    )
    return appointment


def confirm_appointment(
    db: Session, *, appointment: ClinicAppointment, actor_id: str
) -> ClinicAppointment:
    return transition_status(
        db, appointment=appointment, new_status=ClinicAppointmentStatus.CONFIRMED, actor_id=actor_id
    )


def cancel_appointment(
    db: Session, *, appointment: ClinicAppointment, actor_id: str, reason: str
) -> ClinicAppointment:
    """BR-M07-04: cancelling within the clinic's configured cancellation
    policy window is flagged (audit detail `policy_violation: true`), never
    blocked — a warning/report flag, not a hard stop."""
    clinic = db.get(Clinic, appointment.clinic_id)
    policy_violation = False
    if clinic is not None and clinic.cancellation_policy:
        min_hours = clinic.cancellation_policy.get("min_hours_before")
        if min_hours is not None:
            start = as_naive_utc(appointment.start_time)
            if start is not None and (start - utcnow()) < dt.timedelta(hours=min_hours):
                policy_violation = True

    transition_status(
        db,
        appointment=appointment,
        new_status=ClinicAppointmentStatus.CANCELLED,
        actor_id=actor_id,
        reason=reason,
    )
    appointment.cancellation_reason = reason
    appointment.cancelled_by_user_id = actor_id
    appointment.cancelled_at = utcnow()
    db.flush()
    if policy_violation:
        audit.record(
            db,
            actor_type="user",
            actor_id=actor_id,
            action="clinic_appointment_cancel_policy_violation",
            resource_type="clinic_appointment",
            resource_id=appointment.id,
            clinic_id=appointment.clinic_id,
            severity="warning",
            details={"policy_violation": True, "reason": reason},
        )
    return appointment


def mark_no_show(
    db: Session, *, appointment: ClinicAppointment, actor_id: str, reason: str | None = None
) -> ClinicAppointment:
    return transition_status(
        db,
        appointment=appointment,
        new_status=ClinicAppointmentStatus.NO_SHOW,
        actor_id=actor_id,
        reason=reason,
    )


def mark_arrived_override(
    db: Session, *, appointment: ClinicAppointment, actor_id: str, reason: str
) -> ClinicAppointment:
    """Only valid from `no_show` per `_VALID_TRANSITIONS` (BRD's explicit
    late-arrival reception override) — a normal `confirmed -> arrived`
    check-in is M08's own routed action, not exposed here."""
    return transition_status(
        db,
        appointment=appointment,
        new_status=ClinicAppointmentStatus.ARRIVED,
        actor_id=actor_id,
        reason=reason,
    )


def reschedule_appointment(
    db: Session,
    *,
    clinic_id: str,
    actor_id: str,
    original: ClinicAppointment,
    new_start_time: dt.datetime,
    reason: str,
    created_by_source: str,
    new_branch_id: str | None = None,
    new_doctor_id: str | None = None,
    override_working_hours_reason: str | None = None,
    is_override_allowed: bool = False,
) -> ClinicAppointment:
    """Creates the new row FIRST (so if `create_appointment`'s
    IntegrityError/rollback fires, only that attempt is discarded — the
    original is untouched, not yet flushed/cancelled), then cancels the OLD
    row. Both within the same transaction; the caller (route) issues the
    single `db.commit()`. Returns the NEW appointment."""
    if original.status not in (
        ClinicAppointmentStatus.PENDING,
        ClinicAppointmentStatus.CONFIRMED,
    ):
        raise ClinicAppointmentError(
            "Chỉ có thể đổi lịch cho lịch hẹn đang ở trạng thái chờ hoặc đã xác nhận."
        )

    branch_id = new_branch_id if new_branch_id is not None else original.branch_id
    doctor_id = new_doctor_id if new_doctor_id is not None else original.doctor_id

    new_appointment = create_appointment(
        db,
        clinic_id=clinic_id,
        actor_id=actor_id,
        branch_id=branch_id,
        patient_id=original.patient_id,
        doctor_id=doctor_id,
        service_id=original.service_id,
        start_time=new_start_time,
        created_by_source=created_by_source,
        notes=original.notes,
        override_working_hours_reason=override_working_hours_reason,
        is_override_allowed=is_override_allowed,
    )
    new_appointment.reschedule_of_id = original.id
    db.flush()

    transition_status(
        db,
        appointment=original,
        new_status=ClinicAppointmentStatus.CANCELLED,
        actor_id=actor_id,
        reason=f"rescheduled: {reason}",
    )
    original.cancellation_reason = f"rescheduled: {reason}"
    original.cancelled_by_user_id = actor_id
    original.cancelled_at = utcnow()
    db.flush()

    return new_appointment


def run_no_show_job(
    db: Session, *, clinic_id: str, actor_id: str, grace_period_minutes: int = 60
) -> int:
    """Idempotent by construction: only CONFIRMED appointments past the
    grace period match; a second call the same day finds zero (already
    transitioned) rows — no separate idempotency-key bookkeeping needed."""
    cutoff = utcnow() - dt.timedelta(minutes=grace_period_minutes)
    candidates = list(
        db.execute(
            select(ClinicAppointment).where(
                ClinicAppointment.clinic_id == clinic_id,
                ClinicAppointment.status == ClinicAppointmentStatus.CONFIRMED,
                ClinicAppointment.start_time < cutoff,
            )
        ).scalars()
    )
    count = 0
    for appointment in candidates:
        transition_status(
            db,
            appointment=appointment,
            new_status=ClinicAppointmentStatus.NO_SHOW,
            actor_id=actor_id,
            reason="auto: end-of-day grace period expired",
        )
        count += 1
    return count
