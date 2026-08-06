"""Medication schedule / reminder / adherence API (Master Plan §2, BRD §G).

Patient-owned: the path ``patient_id`` must equal the caller's own
``PatientProfile.id``. Reminders use the Notification Delivery transports
(deterministic + in-app always available at ENG-RC).
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, enforce_rate_limit, get_session, require_roles
from app.models.medication_schedule import DoseOccurrence, MedicationSchedule
from app.models.patient import PatientProfile
from app.models.user import UserRole
from app.services import medication_schedule as sched

router = APIRouter(tags=["medication_schedule"])

_PatientOnly = require_roles(UserRole.PATIENT)


# ── schemas ──────────────────────────────────────────────────────────────────
class ScheduleCreateIn(BaseModel):
    schedule_type: str
    local_dose_times: list[str] | None = None
    recurrence: dict | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    patient_timezone: str | None = None
    source: str = "manual"

    @field_validator("patient_timezone")
    @classmethod
    def _valid_tz(cls, v: str | None) -> str | None:
        # Reject an unknown IANA tz up front (review P2 — otherwise it is stored and
        # later silently falls back, firing reminders at the wrong wall-clock time).
        if v:
            try:
                ZoneInfo(v)
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise ValueError(f"Múi giờ không hợp lệ: {v}") from exc
        return v


class ScheduleEditIn(BaseModel):
    schedule_type: str | None = None
    local_dose_times: list[str] | None = None
    recurrence: dict | None = None
    end_date: dt.date | None = None
    # The sanctioned repair for a legacy interval/cyclic row with a NULL anchor.
    # Without it such a row was unfixable: edit inherits `old.start_date`, which
    # is NULL, so validation raised and every PATCH returned 422 — and the only
    # escape (POST a second schedule) left TWO active schedules for one drug.
    start_date: dt.date | None = None


class ScheduleOut(BaseModel):
    id: str
    medication_id: str
    schedule_type: str
    local_dose_times: list | None
    status: str
    version: int
    patient_timezone: str
    start_date: dt.date | None
    end_date: dt.date | None
    # A legacy interval/cyclic row with no anchor produces NO doses and still
    # reports status="active". Without surfacing it the schedule looks healthy and
    # is silently dead — the same shape as the pause/resume defect.
    needs_anchor_repair: bool = False


class DoseOut(BaseModel):
    id: str
    schedule_id: str
    scheduled_utc: dt.datetime
    local_render: str | None
    state: str
    # Present only on a corrected dose. The machine's original classification is
    # kept beside the human's, so a 100% figure that contains late self-reports
    # is distinguishable from one that never needed correcting.
    corrected_from_state: str | None = None
    corrected_at: dt.datetime | None = None
    correction_reason: str | None = None


class CorrectDoseIn(BaseModel):
    """Record what actually happened to a dose the system classified as missed.

    Wording is deliberate throughout this flow: it records, it does not advise.
    Whether to take a late dose is a clinical decision this app does not make.
    """

    state: str = Field(description="taken | skipped")
    reason_code: str = Field(default="other", max_length=48)

    @field_validator("state")
    @classmethod
    def _valid_state(cls, v: str) -> str:
        if v not in sched.CORRECTION_STATES:
            raise ValueError("state phải là 'taken' hoặc 'skipped'.")
        return v


class DueOut(BaseModel):
    delivered: int
    items: list[DoseOut]


class MarkDoseIn(BaseModel):
    skip_reason: str | None = Field(default=None, max_length=255)


class AdherenceOut(BaseModel):
    """Adherence over an explicitly reconciled period.

    `expected_count` is what the SCHEDULE prescribes in the window, not what
    happens to be persisted. Before reconciliation the denominator was "rows that
    exist", and rows only appeared when a request handler ran materialization —
    so the rate measured app engagement rather than therapy, and a patient who
    disengaged entirely could outscore one who engaged and missed a few doses.

    `adherence_rate = taken / (taken + skipped + missed)`. `future_count` is
    excluded from the rate: a dose that has not come around cannot have been
    missed.

    `reconciled=False` means the period could NOT be reconciled (PRN, missing
    anchor, paused or stopped). The UI must render an unavailable state, never a
    confident percentage — a number derived from a failed reconciliation is
    exactly the misleading figure this work removes.

    `calculation_version` changes when the SEMANTICS change, so a rate can always
    be traced to the rules that produced it.
    """

    expected_count: int
    taken_count: int
    skipped_count: int
    missed_count: int
    future_count: int
    # Doses the patient was INSTRUCTED not to take. Separate from cancelled
    # because they are a different clinical event: a hold the patient obeyed is
    # not a withdrawn prescription, and a client that renders them as one tells a
    # compliant patient they were non-adherent.
    excluded_paused_count: int
    excluded_cancelled_count: int
    adherence_rate: float | None
    period_start: dt.date
    period_end: dt.date
    timezone: str
    calculation_version: str
    reconciled: bool
    # WHY the period could not be reconciled, when it could not. `reconciled`
    # alone tells a client to hide the number but not what to say instead.
    reconciliation_reason: str
    # The backfill floor actually applied (P1-4), so a figure can always be
    # traced to the period it was computed over rather than the one requested.
    tracking_start_at: dt.datetime | None
    # {"version": …, "missed_after_hours": …}. An adherence-event classification
    # window, NOT dosing advice.
    grace_policy: dict

    # Legacy field names, same numbers. Kept so an un-updated client keeps working
    # instead of silently reading nulls; remove once the frontend has migrated.
    total: int
    taken: int
    skipped: int
    missed: int


# ── helpers ──────────────────────────────────────────────────────────────────
def _require_self(db: Session, user: CurrentUser, patient_id: str) -> str:
    profile = db.execute(
        select(PatientProfile).where(PatientProfile.user_id == user.id)
    ).scalars().first()
    if profile is None or profile.id != patient_id:
        raise HTTPException(status_code=403, detail="Không có quyền với hồ sơ này.")
    return profile.id


def _sched_out(s: MedicationSchedule) -> ScheduleOut:
    return ScheduleOut(
        id=s.id,
        medication_id=s.medication_id,
        schedule_type=s.schedule_type,
        local_dose_times=s.local_dose_times,
        status=s.status,
        version=s.version,
        patient_timezone=s.patient_timezone,
        start_date=s.start_date,
        end_date=s.end_date,
        needs_anchor_repair=sched.needs_anchor_repair(s),
    )


def _dose_out(d: DoseOccurrence) -> DoseOut:
    return DoseOut(
        id=d.id,
        schedule_id=d.schedule_id,
        scheduled_utc=d.scheduled_utc,
        local_render=d.local_render,
        state=d.state,
        corrected_from_state=d.corrected_from_state,
        corrected_at=d.corrected_at,
        correction_reason=d.correction_reason,
    )


def _map_err(exc: sched.ScheduleError) -> HTTPException:
    if isinstance(exc, sched.ScheduleNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, sched.ScheduleAccessDenied):
        return HTTPException(status_code=403, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))


# ── routes ───────────────────────────────────────────────────────────────────
@router.post(
    "/patients/{patient_id}/medications/{medication_id}/schedule", response_model=ScheduleOut
)
def create_schedule(
    patient_id: str,
    medication_id: str,
    body: ScheduleCreateIn,
    request: Request,
    user: CurrentUser = Depends(_PatientOnly),
    db: Session = Depends(get_session),
) -> ScheduleOut:
    enforce_rate_limit(request, "medication_schedule")
    _require_self(db, user, patient_id)
    try:
        schedule = sched.create_schedule(
            db,
            patient_id=patient_id,
            medication_id=medication_id,
            schedule_type=body.schedule_type,
            local_dose_times=body.local_dose_times,
            recurrence=body.recurrence,
            start_date=body.start_date,
            end_date=body.end_date,
            patient_timezone=body.patient_timezone,
            source=body.source,
            actor_user_id=user.id,
        )
        sched.materialize_due(db, schedule)
    except sched.ScheduleError as exc:
        db.rollback()
        raise _map_err(exc) from exc
    db.commit()
    return _sched_out(schedule)


@router.get(
    "/patients/{patient_id}/medications/{medication_id}/schedule",
    response_model=list[ScheduleOut],
)
def list_schedules(
    patient_id: str,
    medication_id: str,
    user: CurrentUser = Depends(_PatientOnly),
    db: Session = Depends(get_session),
) -> list[ScheduleOut]:
    _require_self(db, user, patient_id)
    rows = db.execute(
        select(MedicationSchedule)
        .where(
            MedicationSchedule.patient_id == patient_id,
            MedicationSchedule.medication_id == medication_id,
        )
        .order_by(MedicationSchedule.created_at.desc())
    ).scalars()
    return [_sched_out(s) for s in rows]


@router.patch("/patients/{patient_id}/schedules/{schedule_id}", response_model=ScheduleOut)
def edit_schedule(
    patient_id: str,
    schedule_id: str,
    body: ScheduleEditIn,
    request: Request,
    user: CurrentUser = Depends(_PatientOnly),
    db: Session = Depends(get_session),
) -> ScheduleOut:
    enforce_rate_limit(request, "medication_schedule")
    _require_self(db, user, patient_id)
    try:
        new = sched.edit_schedule(
            db,
            patient_id=patient_id,
            schedule_id=schedule_id,
            schedule_type=body.schedule_type,
            local_dose_times=body.local_dose_times,
            recurrence=body.recurrence,
            end_date=body.end_date,
            start_date=body.start_date,
            actor_user_id=user.id,
        )
        sched.materialize_due(db, new)
    except sched.ScheduleError as exc:
        db.rollback()
        raise _map_err(exc) from exc
    db.commit()
    return _sched_out(new)


class LifecycleIn(BaseModel):
    """When a hold takes effect, and why — not free text.

    `effective_at` may be backdated (a doctor stopped the drug on Friday and the
    patient records it on Monday) or future-dated (a hold before a procedure).
    `reason_code` is a closed vocabulary: a lifecycle trail that carries the
    clinical reason for a hold in free text is its own disclosure.
    """

    effective_at: dt.datetime | None = None
    reason_code: str = Field(default="unspecified", max_length=48, pattern=r"^[a-z0-9_]+$")


@router.post("/patients/{patient_id}/schedules/{schedule_id}/pause", response_model=ScheduleOut)
def pause_schedule(
    patient_id: str,
    schedule_id: str,
    body: LifecycleIn | None = None,
    user: CurrentUser = Depends(_PatientOnly),
    db: Session = Depends(get_session),
) -> ScheduleOut:
    _require_self(db, user, patient_id)
    body = body or LifecycleIn()
    try:
        s = sched.pause_schedule(
            db,
            patient_id=patient_id,
            schedule_id=schedule_id,
            effective_at=body.effective_at,
            reason_code=body.reason_code,
            actor_user_id=user.id,
        )
    except sched.ScheduleError as exc:
        db.rollback()
        raise _map_err(exc) from exc
    db.commit()
    return _sched_out(s)


@router.post(
    "/patients/{patient_id}/schedules/{schedule_id}/resume", response_model=ScheduleOut
)
def resume_schedule(
    patient_id: str,
    schedule_id: str,
    body: LifecycleIn | None = None,
    user: CurrentUser = Depends(_PatientOnly),
    db: Session = Depends(get_session),
) -> ScheduleOut:
    """The missing half of pause. Without it a paused medication never reminded
    again — it read `active` in the list and was silently dead."""
    _require_self(db, user, patient_id)
    body = body or LifecycleIn()
    try:
        s = sched.resume_schedule(
            db,
            patient_id=patient_id,
            schedule_id=schedule_id,
            effective_at=body.effective_at,
            actor_user_id=user.id,
        )
    except sched.ScheduleError as exc:
        db.rollback()
        raise _map_err(exc) from exc
    db.commit()
    return _sched_out(s)


@router.get("/patients/{patient_id}/reminders/due", response_model=DueOut)
def reminders_due(
    patient_id: str,
    user: CurrentUser = Depends(_PatientOnly),
    db: Session = Depends(get_session),
) -> DueOut:
    _require_self(db, user, patient_id)
    # Sweep overdue doses to MISSED so adherence stays honest (review P1).
    sched.sweep_missed(db, patient_id=patient_id)
    # Materialize any newly-due doses across the patient's active schedules first.
    for s in db.execute(
        select(MedicationSchedule).where(
            MedicationSchedule.patient_id == patient_id,
            MedicationSchedule.status == "active",
        )
    ).scalars():
        sched.materialize_due(db, s)
    delivered = sched.deliver_due_reminders(db, patient_id=patient_id, user_id=user.id)
    db.commit()
    now = dt.datetime.now(dt.UTC)
    # Use the SHARED predicate. This list previously had no schedule/medication
    # join at all: `delivered` was gated but the rows returned to the client were
    # not, so the reminder list still named medications the patient had stopped.
    due = list(
        db.execute(
            sched.due_doses_query(
                patient_id=patient_id, now=now, states=("pending", "notified")
            )
        ).scalars()
    )
    return DueOut(delivered=delivered, items=[_dose_out(d) for d in due])


@router.post("/patients/{patient_id}/doses/{dose_id}/taken", response_model=DoseOut)
def mark_taken(
    patient_id: str,
    dose_id: str,
    request: Request,
    user: CurrentUser = Depends(_PatientOnly),
    db: Session = Depends(get_session),
) -> DoseOut:
    enforce_rate_limit(request, "medication_dose")
    _require_self(db, user, patient_id)
    try:
        dose = sched.mark_dose(
            db, patient_id=patient_id, dose_id=dose_id, state="taken", actor_user_id=user.id
        )
    except sched.ScheduleError as exc:
        db.rollback()
        raise _map_err(exc) from exc
    db.commit()
    return _dose_out(dose)


@router.post("/patients/{patient_id}/doses/{dose_id}/skipped", response_model=DoseOut)
def mark_skipped(
    patient_id: str,
    dose_id: str,
    body: MarkDoseIn,
    request: Request,
    user: CurrentUser = Depends(_PatientOnly),
    db: Session = Depends(get_session),
) -> DoseOut:
    enforce_rate_limit(request, "medication_dose")
    _require_self(db, user, patient_id)
    try:
        dose = sched.mark_dose(
            db,
            patient_id=patient_id,
            dose_id=dose_id,
            state="skipped",
            skip_reason=body.skip_reason,
            actor_user_id=user.id,
        )
    except sched.ScheduleError as exc:
        db.rollback()
        raise _map_err(exc) from exc
    db.commit()
    return _dose_out(dose)


@router.get("/patients/{patient_id}/doses/missed", response_model=list[DoseOut])
def list_missed_doses(
    patient_id: str,
    schedule_id: str | None = None,
    limit: int = 100,
    user: CurrentUser = Depends(_PatientOnly),
    db: Session = Depends(get_session),
) -> list[DoseOut]:
    """Doses the system classified as MISSED, so the patient can correct them.

    Before this route existed, `due_doses_query` was only ever called with
    (pending, notified): a MISSED dose appeared in no list at all, so the client
    could not obtain its id and the patient had no way to say "I took that". An
    adherence figure a patient cannot correct is not a measurement of the
    patient.

    Deliberately NOT filtered to currently-active schedules: a dose missed under
    a schedule that has since been stopped is exactly the one a patient most
    wants to fix, and it still counts toward the period it belongs to.
    """
    _require_self(db, user, patient_id)
    rows = sched.list_missed_doses(
        db, patient_id=patient_id, schedule_id=schedule_id, limit=limit
    )
    return [_dose_out(d) for d in rows]


@router.post("/patients/{patient_id}/doses/{dose_id}/correct", response_model=DoseOut)
def correct_dose(
    patient_id: str,
    dose_id: str,
    body: CorrectDoseIn,
    request: Request,
    user: CurrentUser = Depends(_PatientOnly),
    db: Session = Depends(get_session),
) -> DoseOut:
    """Record what actually happened to a dose the system marked missed.

    MISSED is assigned by a clock; nobody asserted it. This is the patient
    asserting. It never advises whether to take a late dose — that is a clinical
    decision this app does not make — and it never silently overwrites: only a
    MISSED dose may be corrected, the original classification is preserved on the
    row, and the change is written to the immutable audit trail with actor, role
    and reason.
    """
    enforce_rate_limit(request, "medication_dose")
    _require_self(db, user, patient_id)
    try:
        dose = sched.correct_dose(
            db,
            patient_id=patient_id,
            dose_id=dose_id,
            state=body.state,
            reason_code=body.reason_code,
            actor_user_id=user.id,
            actor_role="patient",
        )
    except sched.ScheduleError as exc:
        db.rollback()
        raise _map_err(exc) from exc
    db.commit()
    return _dose_out(dose)


@router.get(
    "/patients/{patient_id}/schedules/{schedule_id}/adherence", response_model=AdherenceOut
)
def schedule_adherence(
    patient_id: str,
    schedule_id: str,
    period_start: dt.date | None = None,
    period_end: dt.date | None = None,
    user: CurrentUser = Depends(_PatientOnly),
    db: Session = Depends(get_session),
) -> AdherenceOut:
    """Adherence for a period. Reconciles the window before counting, so the
    answer does not depend on how often the patient opened the app."""
    _require_self(db, user, patient_id)
    try:
        summary = sched.adherence_summary(
            db,
            patient_id=patient_id,
            schedule_id=schedule_id,
            period_start=period_start,
            period_end=period_end,
        )
    except sched.ScheduleError as exc:
        db.rollback()
        raise _map_err(exc) from exc
    # Reconciliation WRITES (it materializes the period), so the request must
    # commit or the backfill is discarded and the next call redoes it.
    db.commit()
    return AdherenceOut(**summary)
