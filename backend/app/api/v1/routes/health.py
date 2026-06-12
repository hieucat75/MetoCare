"""Health tracking routes (consent-gated + audited at the service layer)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import current_user_id, get_session
from app.schemas.health import MetricCreate, MetricOut, TrendOut
from app.services import health_metrics

router = APIRouter(prefix="/patients/{patient_id}/metrics", tags=["health-tracking"])


@router.post("", response_model=MetricOut, status_code=201)
def create_metric(
    patient_id: str,
    payload: MetricCreate,
    requester_id: str = Depends(current_user_id),
    db: Session = Depends(get_session),
) -> MetricOut:
    metric = health_metrics.create_metric(
        db,
        patient_id=patient_id,
        requester_id=requester_id,
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
    requester_id: str = Depends(current_user_id),
    db: Session = Depends(get_session),
) -> list[MetricOut]:
    rows = health_metrics.list_metrics(
        db, patient_id=patient_id, requester_id=requester_id, metric_type=metric_type
    )
    return [MetricOut.model_validate(r) for r in rows]


@router.get("/trend", response_model=TrendOut)
def metric_trend(
    patient_id: str,
    metric_type: str = Query(...),
    days: int = Query(default=30, ge=1, le=365),
    requester_id: str = Depends(current_user_id),
    db: Session = Depends(get_session),
) -> TrendOut:
    data = health_metrics.trend(
        db, patient_id=patient_id, requester_id=requester_id, metric_type=metric_type, days=days
    )
    return TrendOut(**data)
