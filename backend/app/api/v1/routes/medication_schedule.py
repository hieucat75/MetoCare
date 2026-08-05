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


class DueOut(BaseModel):
    delivered: int
    items: list[DoseOut]


class MarkDoseIn(BaseModel):
    skip_reason: str | None = Field(default=None, max_length=255)


class AdherenceOut(BaseModel):
    total: int
    taken: int
    skipped: int
    missed: int
    adherence_rate: float | None


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


@router.post("/patients/{patient_id}/schedules/{schedule_id}/pause", response_model=ScheduleOut)
def pause_schedule(
    patient_id: str,
    schedule_id: str,
    user: CurrentUser = Depends(_PatientOnly),
    db: Session = Depends(get_session),
) -> ScheduleOut:
    _require_self(db, user, patient_id)
    try:
        s = sched.pause_schedule(db, patient_id=patient_id, schedule_id=schedule_id)
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
    user: CurrentUser = Depends(_PatientOnly),
    db: Session = Depends(get_session),
) -> ScheduleOut:
    """The missing half of pause. Without it a paused medication never reminded
    again — it read `active` in the list and was silently dead."""
    _require_self(db, user, patient_id)
    try:
        s = sched.resume_schedule(db, patient_id=patient_id, schedule_id=schedule_id)
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


@router.get(
    "/patients/{patient_id}/schedules/{schedule_id}/adherence", response_model=AdherenceOut
)
def schedule_adherence(
    patient_id: str,
    schedule_id: str,
    user: CurrentUser = Depends(_PatientOnly),
    db: Session = Depends(get_session),
) -> AdherenceOut:
    _require_self(db, user, patient_id)
    return AdherenceOut(
        **sched.adherence_summary(db, patient_id=patient_id, schedule_id=schedule_id)
    )
