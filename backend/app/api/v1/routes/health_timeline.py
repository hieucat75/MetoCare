"""Health Timeline API — E20.

GET /api/v1/patients/{patient_id}/health-timeline

Returns unified chronological health events from:
- LabUploadBatch + LabResult
- HealthMetric (BP, weight)
- Medication
- SymptomLog

Query params:
- from_date: YYYY-MM-DD
- to_date: YYYY-MM-DD
- event_type: filter by event type
- limit: max events (default 50, max 200)

Auth: PATIENT (own record), DOCTOR (any), INTERNAL_ADMIN (any).
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, current_user, get_session
from app.api.v1.routes.patients import _check_read_access
from app.domain.health_timeline import HealthTimelineEngine
from app.models.clinical import HealthMetric, LabResult, LabUploadBatch, Medication, SymptomLog

router = APIRouter(tags=["health_timeline"])


# ── Response models ───────────────────────────────────────────────────────────

class TimelineEventResponse(BaseModel):
    event_id: str
    event_type: str
    date: dt.date
    title_vi: str
    summary_vi: str
    source: str
    importance: str
    related_markers: list[str]
    metadata: dict
    evidence_level: str


class TimelineSummaryResponse(BaseModel):
    improved_areas: list[str]
    worsened_areas: list[str]
    stable_areas: list[str]
    biggest_change_vi: str
    missing_longitudinal_vi: list[str]
    data_span_days: int
    total_events: int


class HealthTimelineResponse(BaseModel):
    timeline_events: list[TimelineEventResponse]
    timeline_summary: TimelineSummaryResponse
    missing_sources: list[str]
    generated_at: dt.datetime


# ── Route ─────────────────────────────────────────────────────────────────────

@router.get(
    "/{patient_id}/health-timeline",
    response_model=HealthTimelineResponse,
    summary="Unified health timeline for a patient (E20)",
)
def get_health_timeline(
    patient_id: str,
    from_date: dt.date | None = Query(default=None, description="Filter events from this date (YYYY-MM-DD)"),
    to_date: dt.date | None = Query(default=None, description="Filter events to this date (YYYY-MM-DD)"),
    event_type: str | None = Query(default=None, description="Filter by event type"),
    limit: int = Query(default=50, ge=1, le=200, description="Max events to return"),
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> HealthTimelineResponse:
    """Return unified chronological health timeline for *patient_id*.

    Aggregates data from:
    - ``LabUploadBatch`` + ``LabResult`` → lab events
    - ``HealthMetric`` (metric_type=bp_systolic/bp_diastolic/weight_kg) → BP + weight events
    - ``Medication`` → medication started events
    - ``SymptomLog`` → symptom events

    Access rules:
    - **PATIENT** — own record only.
    - **DOCTOR** — consent-gated (scope='profile').
    - **INTERNAL_ADMIN / SUPER_ADMIN** — unrestricted.
    - **AI_SERVICE / CLINIC_ADMIN** — always 403.
    """
    # RBAC check — reuses the same helper as other patient endpoints
    _check_read_access(db, patient_id=patient_id, requester=user)

    # ── Query all source tables ───────────────────────────────────────────────

    # LabUploadBatch — apply date filter at DB level if possible
    batch_q = db.query(LabUploadBatch).filter(
        LabUploadBatch.patient_id == patient_id,
        LabUploadBatch.deleted_at.is_(None),
    )
    if from_date:
        batch_q = batch_q.filter(
            (LabUploadBatch.test_date >= from_date) | LabUploadBatch.test_date.is_(None)
        )
    if to_date:
        batch_q = batch_q.filter(
            (LabUploadBatch.test_date <= to_date) | LabUploadBatch.test_date.is_(None)
        )
    lab_batches = batch_q.all()

    # LabResult — fetch all for the patient (engine groups by batch_id)
    lab_results = (
        db.query(LabResult)
        .filter(
            LabResult.patient_id == patient_id,
            LabResult.deleted_at.is_(None),
        )
        .all()
    )

    # HealthMetric — BP + weight types
    metric_types = ["bp_systolic", "bp_diastolic", "weight_kg"]
    metric_q = db.query(HealthMetric).filter(
        HealthMetric.patient_id == patient_id,
        HealthMetric.metric_type.in_(metric_types),
        HealthMetric.deleted_at.is_(None),
    )
    if from_date:
        metric_q = metric_q.filter(HealthMetric.measured_at >= dt.datetime.combine(from_date, dt.time.min))
    if to_date:
        metric_q = metric_q.filter(HealthMetric.measured_at <= dt.datetime.combine(to_date, dt.time.max))
    health_metrics = metric_q.all()

    # Medication
    medication_q = db.query(Medication).filter(
        Medication.patient_id == patient_id,
        Medication.deleted_at.is_(None),
    )
    medications = medication_q.all()

    # SymptomLog — no soft-delete, filter by patient only
    symptom_q = db.query(SymptomLog).filter(
        SymptomLog.patient_id == patient_id,
    )
    if from_date:
        symptom_q = symptom_q.filter(SymptomLog.reported_at >= dt.datetime.combine(from_date, dt.time.min))
    if to_date:
        symptom_q = symptom_q.filter(SymptomLog.reported_at <= dt.datetime.combine(to_date, dt.time.max))
    symptom_logs = symptom_q.all()

    # ── Missing sources detection ─────────────────────────────────────────────
    missing_sources: list[str] = []
    if not lab_batches:
        missing_sources.append("lab_results")
    if not health_metrics:
        missing_sources.append("health_metrics")
    if not medications:
        missing_sources.append("medications")
    if not symptom_logs:
        missing_sources.append("symptom_logs")

    # ── Run engine ────────────────────────────────────────────────────────────
    engine = HealthTimelineEngine()
    events = engine.build(
        lab_batches=lab_batches,
        lab_results=lab_results,
        health_metrics=health_metrics,
        medications=medications,
        symptom_logs=symptom_logs,
        from_date=from_date,
        to_date=to_date,
        event_type_filter=event_type,
        limit=limit,
    )
    summary = engine.summarize(events, lab_results)

    # ── Build response ────────────────────────────────────────────────────────
    timeline_events = [
        TimelineEventResponse(
            event_id=e.event_id,
            event_type=e.event_type,
            date=e.date,
            title_vi=e.title_vi,
            summary_vi=e.summary_vi,
            source=e.source,
            importance=e.importance,
            related_markers=e.related_markers,
            metadata=e.metadata,
            evidence_level=e.evidence_level,
        )
        for e in events
    ]

    timeline_summary = TimelineSummaryResponse(
        improved_areas=summary.improved_areas,
        worsened_areas=summary.worsened_areas,
        stable_areas=summary.stable_areas,
        biggest_change_vi=summary.biggest_change_vi,
        missing_longitudinal_vi=summary.missing_longitudinal_vi,
        data_span_days=summary.data_span_days,
        total_events=summary.total_events,
    )

    return HealthTimelineResponse(
        timeline_events=timeline_events,
        timeline_summary=timeline_summary,
        missing_sources=missing_sources,
        generated_at=dt.datetime.now(tz=dt.UTC),
    )
