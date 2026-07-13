"""Doctor Portal P0 API — clinical workspace for DOCTOR / MEDICAL_REVIEWER.

Mounted at prefix ``/doctor``. Distinct from ``doctor_review`` (mounted at the
same prefix with ``/doctor/review/*`` subpaths) — no path collision.

Endpoints:
- GET   /doctor/stats
- GET   /doctor/patients
- GET   /doctor/patients/{patient_id}/timeline
- GET   /doctor/queue
- PATCH /doctor/queue/{item_id}/review
- GET   /doctor/appointments
- GET   /doctor/notes

RBAC: DOCTOR and MEDICAL_REVIEWER (patients -> 403). Patient-specific reads stay
consent-gated regardless of role.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_session, require_roles
from app.api.v1.routes.patients import _check_read_access
from app.domain.health_timeline import HealthTimelineEngine
from app.models.clinical import (
    HealthMetric,
    LabResult,
    LabUploadBatch,
    Medication,
    SymptomLog,
)
from app.models.patient import PatientProfile
from app.models.user import UserRole
from app.schemas.doctor_portal import (
    DoctorAppointment,
    DoctorAppointmentListResponse,
    DoctorAppointmentStats,
    DoctorNoteListItem,
    DoctorNoteListResponse,
    DoctorPatient,
    DoctorPatientListResponse,
    DoctorStats,
    QueueItem,
    QueueResponse,
    ReviewDecisionPayload,
    TimelineEvent,
)
from app.services import consultation_note, doctor_portal
from app.services.doctor_portal import (
    InvalidTransition,
    NotFound,
    PermissionDenied,
)

router = APIRouter(prefix="/doctor", tags=["doctor_portal"])

# Both DOCTOR and MEDICAL_REVIEWER may use the doctor portal.
_portal_roles = require_roles(UserRole.DOCTOR, UserRole.MEDICAL_REVIEWER)

_TIMELINE_METRIC_TYPES = ["bp_systolic", "bp_diastolic", "weight_kg"]


# ---------------------------------------------------------------------------
# 1. Stats
# ---------------------------------------------------------------------------


@router.get("/stats", response_model=DoctorStats)
def get_stats(
    user: CurrentUser = Depends(_portal_roles),
    db: Session = Depends(get_session),
) -> DoctorStats:
    return DoctorStats(**doctor_portal.get_stats(db, user.id))


# ---------------------------------------------------------------------------
# 2. Patient roster
# ---------------------------------------------------------------------------


@router.get("/patients", response_model=DoctorPatientListResponse)
def list_patients(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None),
    risk: str | None = Query(default=None),
    sort: str = Query(default="risk"),
    user: CurrentUser = Depends(_portal_roles),
    db: Session = Depends(get_session),
) -> DoctorPatientListResponse:
    total, items = doctor_portal.list_patients(
        db,
        user.id,
        limit=limit,
        offset=offset,
        search=search,
        risk=risk,
        sort=sort,
    )
    return DoctorPatientListResponse(
        total=total, items=[DoctorPatient(**item) for item in items]
    )


# ---------------------------------------------------------------------------
# 3. Timeline (consent-gated)
# ---------------------------------------------------------------------------


@router.get("/patients/{patient_id}/timeline", response_model=list[TimelineEvent])
def get_patient_timeline(
    patient_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    user: CurrentUser = Depends(_portal_roles),
    db: Session = Depends(get_session),
) -> list[TimelineEvent]:
    """Consent-gated clinical timeline (403 without scope='profile', 404 if missing)."""
    # _check_read_access raises 404 (missing patient) or 403 (no consent) exactly
    # like the patient-facing endpoints. MEDICAL_REVIEWER is not a DOCTOR, so the
    # consent branch would not apply; grant reviewers the same consent-gated read
    # by evaluating them through the DOCTOR path.
    _require_timeline_access(db, patient_id=patient_id, user=user)

    events = _build_timeline(db, patient_id=patient_id, limit=limit)
    return events


def _require_timeline_access(db: Session, *, patient_id: str, user: CurrentUser) -> None:
    """Consent-gate the timeline for DOCTOR and MEDICAL_REVIEWER identically.

    ``_check_read_access`` only understands PATIENT/DOCTOR/admin roles; a
    MEDICAL_REVIEWER is treated as a doctor-equivalent clinical reviewer here and
    must satisfy the same consent gate.
    """
    # 404 first for a missing patient (mirrors the profile endpoint's semantics),
    # then the consent gate. Without this, the DOCTOR consent branch would 403 a
    # nonexistent patient — leaking "no access" instead of "not found".
    if db.get(PatientProfile, patient_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")

    effective = user
    if user.role == UserRole.MEDICAL_REVIEWER:
        effective = CurrentUser(id=user.id, role=UserRole.DOCTOR.value, mfa=user.mfa)
    _check_read_access(db, patient_id=patient_id, requester=effective)


def _build_timeline(db: Session, *, patient_id: str, limit: int) -> list[TimelineEvent]:
    """Reuse the health-timeline engine and map its events into the FE shape."""
    lab_batches = (
        db.query(LabUploadBatch)
        .filter(
            LabUploadBatch.patient_id == patient_id,
            LabUploadBatch.deleted_at.is_(None),
        )
        .all()
    )
    lab_results = (
        db.query(LabResult)
        .filter(LabResult.patient_id == patient_id, LabResult.deleted_at.is_(None))
        .all()
    )
    health_metrics = (
        db.query(HealthMetric)
        .filter(
            HealthMetric.patient_id == patient_id,
            HealthMetric.metric_type.in_(_TIMELINE_METRIC_TYPES),
            HealthMetric.deleted_at.is_(None),
        )
        .all()
    )
    medications = (
        db.query(Medication)
        .filter(
            Medication.patient_id == patient_id,
            Medication.deleted_at.is_(None),
            Medication.lifecycle_status != "entered_in_error",
        )
        .all()
    )
    symptom_logs = (
        db.query(SymptomLog).filter(SymptomLog.patient_id == patient_id).all()
    )

    engine = HealthTimelineEngine()
    events = engine.build(
        lab_batches=lab_batches,
        lab_results=lab_results,
        health_metrics=health_metrics,
        medications=medications,
        symptom_logs=symptom_logs,
        limit=limit,
    )

    return [
        TimelineEvent(
            id=e.event_id,
            event_type=doctor_portal.map_timeline_event_type(e.event_type),
            description=e.summary_vi or e.title_vi,
            occurred_at=dt.datetime.combine(e.date, dt.time.min).isoformat(),
            actor=e.source,
            metadata=e.metadata or None,
        )
        for e in events
    ]


# ---------------------------------------------------------------------------
# 4. Unified queue
# ---------------------------------------------------------------------------


@router.get("/queue", response_model=QueueResponse)
def get_queue(
    status_filter: str | None = Query(default=None, alias="status"),
    priority: str | None = Query(default=None),
    item_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(_portal_roles),
    db: Session = Depends(get_session),
) -> QueueResponse:
    result = doctor_portal.get_queue(
        db,
        user.id,
        status=status_filter,
        priority=priority,
        item_type=item_type,
        limit=limit,
        offset=offset,
    )
    return QueueResponse(
        total=result["total"],
        pending_count=result["pending_count"],
        items=[QueueItem(**item) for item in result["items"]],
    )


# ---------------------------------------------------------------------------
# 5. Review dispatch
# ---------------------------------------------------------------------------


@router.patch("/queue/{item_id}/review", response_model=QueueItem)
def review_queue_item(
    item_id: str,
    payload: ReviewDecisionPayload,
    user: CurrentUser = Depends(_portal_roles),
    db: Session = Depends(get_session),
) -> QueueItem:
    try:
        updated = doctor_portal.review_item(
            db,
            item_id=item_id,
            doctor_user_id=user.id,
            decision=payload.decision,
            comment=payload.comment,
            internal_note=payload.internal_note,
        )
        db.commit()
    except NotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except InvalidTransition as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return QueueItem(**updated)


# ---------------------------------------------------------------------------
# 6. Appointments
# ---------------------------------------------------------------------------


@router.get("/appointments", response_model=DoctorAppointmentListResponse)
def list_appointments(
    status_filter: list[str] | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None),
    date_from: dt.date | None = Query(default=None),
    date_to: dt.date | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(_portal_roles),
    db: Session = Depends(get_session),
) -> DoctorAppointmentListResponse:
    total, kpi, items = doctor_portal.list_appointments(
        db,
        user.id,
        status=status_filter,
        search=search,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return DoctorAppointmentListResponse(
        total=total,
        stats=DoctorAppointmentStats(**kpi),
        items=[DoctorAppointment(**item) for item in items],
    )


# ---------------------------------------------------------------------------
# 7. Clinical notes
# ---------------------------------------------------------------------------

_NOTE_PREVIEW_LEN = 80


@router.get("/notes", response_model=DoctorNoteListResponse)
def list_doctor_notes(
    consultation_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(_portal_roles),
    db: Session = Depends(get_session),
) -> DoctorNoteListResponse:
    total, items = consultation_note.list_doctor_notes(
        db,
        doctor_user_id=user.id,
        consultation_id=consultation_id,
        status_=status_filter,
        limit=limit,
        offset=offset,
    )

    patient_ids = {item["patient_id"] for item in items}
    names: dict[str, str | None] = {}
    if patient_ids:
        rows = db.execute(
            select(PatientProfile.id, PatientProfile.full_name).where(
                PatientProfile.id.in_(patient_ids)
            )
        ).all()
        names = dict(rows)

    return DoctorNoteListResponse(
        total=total,
        items=[
            DoctorNoteListItem(
                id=item["id"],
                consultation_id=item["consultation_id"],
                patient_id=item["patient_id"],
                patient_name=names.get(item["patient_id"]),
                note_type=item["note_type"],
                status=item["status"],
                content_preview=item["content"][:_NOTE_PREVIEW_LEN],
                created_at=item["created_at"].isoformat(),
                finalized_at=item["finalized_at"].isoformat() if item["finalized_at"] else None,
            )
            for item in items
        ],
    )
