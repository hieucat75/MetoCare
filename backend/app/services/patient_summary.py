"""Patient summary service — aggregates pre-visit data for the doctor portal (T22).

Assembles a consolidated view of a patient's recent clinical data in one
query-efficient pass.  No HTTP concerns; RBAC and consent checks are performed
by the caller (route) before invoking ``build_summary``.

Data aggregated:
  - Latest 5 health metrics (vitals) + directional trend
  - Last 3 lab documents (status metadata only, no PHI content)
  - Most recent metabolic/risk score + trend
  - Active medications (not soft-deleted)
  - Last 5 symptom logs
  - Last 3 nutrition logs
  - Next 2 upcoming booking appointments with this doctor
  - Active care plans (count + titles)
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.models.appointment import BookingAppointment  # noqa: F401 — for type clarity
from app.models.appointment import BookingAppointment as _BookingAppt
from app.models.care import CarePlan
from app.models.clinical import (
    HealthMetric,
    LabDocument,
    Medication,
    RiskScore,
    SymptomLog,
)
from app.models.nutrition import NutritionLog
from app.schemas.patient import (
    MetabolicScoreSummary,
    PatientSummaryOut,
    VitalsSummary,
)
from app.utils.number_format import format_lab_display, format_lab_value

# Re-export output schemas used by the schemas layer
__all__ = ["build_summary"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fetch_vitals(db: Session, patient_id: str) -> VitalsSummary:
    """Return the 5 most-recent HealthMetric rows + a directional trend."""
    rows = list(
        db.execute(
            select(HealthMetric)
            .where(
                HealthMetric.patient_id == patient_id,
                HealthMetric.deleted_at.is_(None),
            )
            .order_by(HealthMetric.measured_at.desc())
            .limit(5)
        ).scalars()
    )

    trend = _compute_vitals_trend(rows)
    latest = [_vital_row(r) for r in rows]
    return VitalsSummary(latest=latest, trend=trend)


def _vital_row(r: HealthMetric) -> dict:
    """Serialize a vital for the doctor summary showing the ORIGINAL value+unit.

    P0 clinical-integrity: doctors must see the value in the unit as recorded
    (e.g. 88 µmol/L), never the canonical/SI-converted number. Falls back to
    value/unit when original_* is NULL (legacy rows).
    """
    orig_value = r.original_value if r.original_value is not None else r.value
    orig_unit = r.original_unit if r.original_unit is not None else r.unit
    return {
        "id": r.id,
        "metric_type": r.metric_type,
        "value": format_lab_value(orig_value, orig_unit),
        "unit": orig_unit,
        "display": format_lab_display(orig_value, orig_unit),
        "measured_at": r.measured_at.isoformat() if r.measured_at else None,
        "status": r.status,
    }


def _compute_vitals_trend(rows: list[HealthMetric]) -> str:
    """Simple trend: compare the mean value of the most-recent 2 vs next 2.

    Returns one of: improving | stable | worsening | insufficient_data.
    """
    if len(rows) < 2:
        return "insufficient_data"

    # Use the first metric type as a proxy (they may differ, so flag insufficient)
    types = {r.metric_type for r in rows}
    if len(types) > 1:
        # Multiple metric types — cannot compare values directly
        return "insufficient_data"

    last = rows[0].value
    previous = rows[1].value
    if previous == 0:
        return "insufficient_data"

    delta_pct = (last - previous) / abs(previous) * 100
    if delta_pct > 5:
        return "worsening"
    if delta_pct < -5:
        return "improving"
    return "stable"


def _fetch_lab_documents(db: Session, patient_id: str) -> list[dict]:
    """Return the 3 most-recent LabDocument rows (status metadata only)."""
    rows = list(
        db.execute(
            select(LabDocument)
            .where(LabDocument.patient_id == patient_id)
            .order_by(LabDocument.created_at.desc())
            .limit(3)
        ).scalars()
    )
    return [
        {
            "id": r.id,
            "ocr_status": r.ocr_status,
            "status": r.status,
            "lab_name": r.lab_name,
            "file_type": r.file_type,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


def _fetch_metabolic_score(db: Session, patient_id: str) -> MetabolicScoreSummary:
    """Return the latest RiskScore + trend from the two most-recent rows."""
    rows = list(
        db.execute(
            select(RiskScore)
            .where(RiskScore.patient_id == patient_id)
            .order_by(RiskScore.created_at.desc())
            .limit(2)
        ).scalars()
    )
    if not rows:
        return MetabolicScoreSummary()

    latest_row = rows[0]
    trend = "insufficient_data"
    if len(rows) >= 2:
        delta = latest_row.metabolic_score - rows[1].metabolic_score
        if delta > 5:
            trend = "worsening"
        elif delta < -5:
            trend = "improving"
        else:
            trend = "stable"

    return MetabolicScoreSummary(
        latest_score=float(latest_row.metabolic_score),
        trend=trend,
        recorded_at=latest_row.created_at,
    )


def _fetch_medications(db: Session, patient_id: str) -> list[dict]:
    """Return all active (not soft-deleted) medication records."""
    rows = list(
        db.execute(
            select(Medication)
            .where(
                Medication.patient_id == patient_id,
                Medication.deleted_at.is_(None),
            )
            .order_by(Medication.created_at.asc())
        ).scalars()
    )
    return [
        {
            "id": r.id,
            "name": r.name,
            "dose": r.dose,
            "note": r.note,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


def _fetch_symptoms(db: Session, patient_id: str) -> list[dict]:
    """Return the 5 most-recent SymptomLog rows."""
    rows = list(
        db.execute(
            select(SymptomLog)
            .where(SymptomLog.patient_id == patient_id)
            .order_by(SymptomLog.reported_at.desc())
            .limit(5)
        ).scalars()
    )
    return [
        {
            "id": r.id,
            "description": r.description,
            "severity": r.severity,
            "reported_at": r.reported_at.isoformat() if r.reported_at else None,
        }
        for r in rows
    ]


def _fetch_nutrition(db: Session, patient_id: str) -> list[dict]:
    """Return the 3 most-recent NutritionLog rows."""
    rows = list(
        db.execute(
            select(NutritionLog)
            .where(NutritionLog.patient_id == patient_id)
            .order_by(NutritionLog.logged_at.desc())
            .limit(3)
        ).scalars()
    )
    return [
        {
            "id": r.id,
            "description": r.description,
            "meal_type": r.meal_type,
            "calories_kcal": r.calories_kcal,
            "logged_at": r.logged_at.isoformat() if r.logged_at else None,
        }
        for r in rows
    ]


def _fetch_upcoming_appointments(
    db: Session,
    patient_id: str,
    doctor_id: str | None,
    now: dt.datetime,
) -> list[dict]:
    """Return the next 2 upcoming booking appointments for this patient.

    If *doctor_id* is provided, filter to that doctor's appointments only.
    Only `pending` and `confirmed` statuses are considered upcoming.
    """
    from app.models.availability import DoctorAvailability

    stmt = (
        select(_BookingAppt, DoctorAvailability.slot_start)
        .join(
            DoctorAvailability,
            _BookingAppt.availability_id == DoctorAvailability.id,
        )
        .where(
            _BookingAppt.patient_id == patient_id,
            _BookingAppt.status.in_(["pending", "confirmed"]),
            DoctorAvailability.slot_start >= now,
        )
        .order_by(DoctorAvailability.slot_start.asc())
        .limit(2)
    )
    if doctor_id is not None:
        stmt = stmt.where(_BookingAppt.doctor_id == doctor_id)

    rows = db.execute(stmt).all()
    result = []
    for appt, slot_start in rows:
        result.append(
            {
                "id": appt.id,
                "doctor_id": appt.doctor_id,
                "status": appt.status,
                "notes": appt.notes,
                "slot_start": slot_start.isoformat() if slot_start else None,
                "created_at": appt.created_at.isoformat() if appt.created_at else None,
            }
        )
    return result


def _fetch_active_care_plans(db: Session, patient_id: str) -> list[dict]:
    """Return titles of active (non-deleted, status=ACTIVE) care plans."""
    rows = list(
        db.execute(
            select(CarePlan)
            .where(
                CarePlan.patient_id == patient_id,
                CarePlan.status == "ACTIVE",
                CarePlan.deleted_at.is_(None),
            )
            .order_by(CarePlan.created_at.desc())
        ).scalars()
    )
    return [{"id": r.id, "title": r.title, "version": r.version} for r in rows]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_summary(
    db: Session,
    *,
    patient_id: str,
    doctor_id: str | None = None,
) -> PatientSummaryOut:
    """Build and return a ``PatientSummaryOut`` for *patient_id*.

    Aggregates in a single function call (no chunking / streaming).
    The caller is responsible for RBAC / consent checks before invoking this.

    Args:
        db:          Active SQLAlchemy session.
        patient_id:  The ``PatientProfile.id`` to summarise.
        doctor_id:   Optional — when provided, scopes upcoming appointments to
                     this doctor only (used for the doctor-facing portal view).

    Returns:
        A fully-populated ``PatientSummaryOut`` pydantic model.
    """
    now = utcnow()

    vitals = _fetch_vitals(db, patient_id)
    lab_documents = _fetch_lab_documents(db, patient_id)
    metabolic_score = _fetch_metabolic_score(db, patient_id)
    medications = _fetch_medications(db, patient_id)
    symptoms = _fetch_symptoms(db, patient_id)
    nutrition = _fetch_nutrition(db, patient_id)
    upcoming_appointments = _fetch_upcoming_appointments(
        db, patient_id=patient_id, doctor_id=doctor_id, now=now
    )
    active_care_plans = _fetch_active_care_plans(db, patient_id)

    return PatientSummaryOut(
        patient_id=patient_id,
        generated_at=now,
        vitals=vitals,
        lab_documents=lab_documents,
        metabolic_score=metabolic_score,
        medications=medications,
        symptoms=symptoms,
        nutrition=nutrition,
        upcoming_appointments=upcoming_appointments,
        active_care_plans=active_care_plans,
    )
