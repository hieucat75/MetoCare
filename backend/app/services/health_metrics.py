"""Health metric service — create / list / trend (Health Records module).

Sensitive-health access is consent-gated + audited. Status (normal/low/high/
critical) is derived from normal range + red-flag vital thresholds so that an
out-of-range reading can feed triage later.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import as_naive_utc, utcnow
from app.domain import policies
from app.models.clinical import HealthMetric
from app.services import audit, consent


def classify_status(
    metric_type: str,
    value: float,
    normal_min: float | None,
    normal_max: float | None,
) -> str:
    th = policies.RED_FLAG_VITAL_THRESHOLDS.get(metric_type)
    if th:
        if "critical_high" in th and value >= th["critical_high"]:
            return "critical"
        if "critical_low" in th and value <= th["critical_low"]:
            return "critical"
    if normal_max is not None and value > normal_max:
        return "high"
    if normal_min is not None and value < normal_min:
        return "low"
    return "normal"


def create_metric(
    db: Session,
    *,
    patient_id: str,
    requester_id: str,
    metric_type: str,
    value: float,
    unit: str | None = None,
    measured_at: dt.datetime | None = None,
    source: str | None = "manual",
    normal_range_min: float | None = None,
    normal_range_max: float | None = None,
) -> HealthMetric:
    consent.require_access(
        db, patient_id=patient_id, requester_id=requester_id, scope="health_metric"
    )
    status = classify_status(metric_type, value, normal_range_min, normal_range_max)
    metric = HealthMetric(
        patient_id=patient_id,
        metric_type=metric_type,
        value=value,
        unit=unit,
        measured_at=as_naive_utc(measured_at) or utcnow(),
        source=source,
        normal_range_min=normal_range_min,
        normal_range_max=normal_range_max,
        status=status,
    )
    db.add(metric)
    db.flush()
    audit.record(
        db,
        actor_type="user",
        actor_id=requester_id,
        action="create",
        resource_type="health_metric",
        resource_id=metric.id,
    )
    db.commit()
    return metric


def list_metrics(
    db: Session,
    *,
    patient_id: str,
    requester_id: str,
    metric_type: str | None = None,
    limit: int = 100,
) -> list[HealthMetric]:
    consent.require_access(
        db, patient_id=patient_id, requester_id=requester_id, scope="health_metric"
    )
    stmt = select(HealthMetric).where(HealthMetric.patient_id == patient_id)
    if metric_type:
        stmt = stmt.where(HealthMetric.metric_type == metric_type)
    stmt = stmt.order_by(HealthMetric.measured_at.desc()).limit(limit)
    rows = list(db.execute(stmt).scalars())
    audit.record(
        db,
        actor_type="user",
        actor_id=requester_id,
        action="read",
        resource_type="health_metric",
        resource_id=patient_id,
    )
    db.commit()
    return rows


def trend(
    db: Session,
    *,
    patient_id: str,
    requester_id: str,
    metric_type: str,
    days: int = 30,
) -> dict:
    """Simple trend aggregation over a window (count/min/max/avg/first/last).

    The TimescaleDB continuous-aggregate version is a P1 concern; this gives a
    portable equivalent for the foundation.
    """
    consent.require_access(
        db, patient_id=patient_id, requester_id=requester_id, scope="health_metric"
    )
    since = utcnow() - dt.timedelta(days=days)
    stmt = (
        select(HealthMetric)
        .where(
            HealthMetric.patient_id == patient_id,
            HealthMetric.metric_type == metric_type,
            HealthMetric.measured_at >= since,
        )
        .order_by(HealthMetric.measured_at.asc())
    )
    rows = list(db.execute(stmt).scalars())
    values = [r.value for r in rows]
    audit.record(
        db,
        actor_type="user",
        actor_id=requester_id,
        action="read_trend",
        resource_type="health_metric",
        resource_id=patient_id,
    )
    db.commit()
    if not values:
        return {"metric_type": metric_type, "days": days, "count": 0}
    return {
        "metric_type": metric_type,
        "days": days,
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "avg": round(sum(values) / len(values), 2),
        "first": values[0],
        "last": values[-1],
        "direction": (
            "up" if values[-1] > values[0]
            else "down" if values[-1] < values[0]
            else "flat"
        ),
    }
