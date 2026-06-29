"""Health tracking routes (consent-gated + audited at the service layer).

RBAC hardening (T9):
  POST   /metrics        — PATIENT(own), DOCTOR, INTERNAL_ADMIN, SUPER_ADMIN
  GET    /metrics        — PATIENT(own), DOCTOR, CLINIC_ADMIN, INTERNAL_ADMIN, SUPER_ADMIN
  GET    /metrics/trend  — PATIENT(own), DOCTOR, CLINIC_ADMIN, INTERNAL_ADMIN, SUPER_ADMIN

AI_SERVICE is blocked from all three routes.
PATIENT ownership is enforced at the route level: a PATIENT token for user X
may only access patient profiles whose user_id == X. DOCTOR/ADMIN bypass
ownership (the service-layer consent gate handles their access separately).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_session, require_roles
from app.models.patient import PatientProfile
from app.models.user import UserRole
from app.schemas.health import MetricCreate, MetricOut, MetricUpdate, TrendOut
from app.services import health_metrics
from app.services import narrative_cache as nc

router = APIRouter(prefix="/patients/{patient_id}/metrics", tags=["health-tracking"])

# ---------------------------------------------------------------------------
# Role sets
# ---------------------------------------------------------------------------
_WRITE_ROLES = (
    UserRole.PATIENT,
    UserRole.DOCTOR,
    UserRole.INTERNAL_ADMIN,
    UserRole.SUPER_ADMIN,
)

_READ_ROLES = (
    UserRole.PATIENT,
    UserRole.DOCTOR,
    UserRole.CLINIC_ADMIN,
    UserRole.INTERNAL_ADMIN,
    UserRole.SUPER_ADMIN,
)


def _enforce_patient_ownership(
    patient_id: str,
    user: CurrentUser,
    db: Session,
) -> None:
    """Raise 403 when a PATIENT token tries to access another patient's data."""
    if user.role != UserRole.PATIENT:
        return  # DOCTOR / ADMIN bypass ownership check (consent gate in service)
    profile = db.get(PatientProfile, patient_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Patient not found.")
    if profile.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="PATIENT may only access their own health metrics.",
        )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("", response_model=MetricOut, status_code=201)
def create_metric(
    patient_id: str,
    payload: MetricCreate,
    user: CurrentUser = Depends(require_roles(*_WRITE_ROLES)),
    db: Session = Depends(get_session),
) -> MetricOut:
    _enforce_patient_ownership(patient_id, user, db)
    metric = health_metrics.create_metric(
        db,
        patient_id=patient_id,
        requester_id=user.id,
        metric_type=payload.metric_type,
        value=payload.value,
        unit=payload.unit,
        measured_at=payload.measured_at,
        source=payload.source,
        normal_range_min=payload.normal_range_min,
        normal_range_max=payload.normal_range_max,
    )
    return MetricOut.model_validate(metric)


@router.get("", response_model=list[MetricOut])
def list_metrics(
    patient_id: str,
    metric_type: str | None = Query(default=None),
    user: CurrentUser = Depends(require_roles(*_READ_ROLES)),
    db: Session = Depends(get_session),
) -> list[MetricOut]:
    _enforce_patient_ownership(patient_id, user, db)
    rows = health_metrics.list_metrics(
        db, patient_id=patient_id, requester_id=user.id, metric_type=metric_type
    )
    return [MetricOut.model_validate(r) for r in rows]


@router.patch("/{metric_id}", response_model=MetricOut)
def update_metric(
    patient_id: str,
    metric_id: str,
    payload: MetricUpdate,
    user: CurrentUser = Depends(require_roles(*_WRITE_ROLES)),
    db: Session = Depends(get_session),
) -> MetricOut:
    """Partial-update an existing HealthMetric (PATCH semantics).

    Only the fields present in *payload* are applied.  id and created_at are
    never modified.  status is re-derived from the updated value + ranges.
    """
    _enforce_patient_ownership(patient_id, user, db)
    try:
        metric = health_metrics.update_metric(
            db,
            metric_id=metric_id,
            patient_id=patient_id,
            requester_id=user.id,
            **payload.model_dump(exclude_none=True),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    # Invalidate narrative cache so AI copilot reflects the edit
    nc.invalidate_patient(patient_id)
    return MetricOut.model_validate(metric)


@router.delete("/{metric_id}", status_code=204)
def delete_metric(
    patient_id: str,
    metric_id: str,
    user: CurrentUser = Depends(require_roles(*_WRITE_ROLES)),
    db: Session = Depends(get_session),
) -> None:
    """Soft-delete a HealthMetric (sets deleted_at / deleted_by, never hard-deletes)."""
    _enforce_patient_ownership(patient_id, user, db)
    try:
        health_metrics.delete_metric(
            db,
            metric_id=metric_id,
            patient_id=patient_id,
            requester_id=user.id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    # Invalidate narrative cache so AI copilot reflects the deletion
    nc.invalidate_patient(patient_id)


@router.get("/trend", response_model=TrendOut)
def metric_trend(
    patient_id: str,
    metric_type: str = Query(...),
    days: int = Query(default=30, ge=1, le=365),
    user: CurrentUser = Depends(require_roles(*_READ_ROLES)),
    db: Session = Depends(get_session),
) -> TrendOut:
    _enforce_patient_ownership(patient_id, user, db)
    data = health_metrics.trend(
        db,
        patient_id=patient_id,
        requester_id=user.id,
        metric_type=metric_type,
        days=days,
    )
    return TrendOut(**data)
