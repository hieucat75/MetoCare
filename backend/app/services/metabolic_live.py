"""Live metabolic score — compute on demand from the latest health metrics.

Root-cause fix for the dashboard "Chưa có điểm chuyển hóa" false-empty bug
(see docs/agent/DASHBOARD_RCA_REDESIGN.md).

The stored ``risk_scores`` table is only ever written by the AI-gated
``POST /ai/metabolic-score`` endpoint, which the patient app never calls — so the
dashboard hero (which reads that table) is permanently empty for real patients.

This service computes the metabolic score **read-only, on demand** from the
patient's latest ``health_metrics`` + profile, so the dashboard always reflects
the data that actually exists. It does NOT persist anything (idempotent, always
current) and is decoupled from the AI feature gate.

Unit-aware: lab-promoted rows may store glucose/lipids in mmol/L (Vietnamese
labs) while the domain scorer expects mg/dL — values are converted before
scoring so the result is correct regardless of source.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.metabolic_score import (
    MetabolicInputs,
    MetabolicScoreResult,
    compute,
)
from app.models.clinical import HealthMetric
from app.models.patient import PatientProfile

# Metric types that feed the metabolic score.
_SCORE_METRIC_TYPES: frozenset[str] = frozenset(
    {"fasting_glucose", "hba1c", "triglyceride", "hdl", "blood_pressure_systolic"}
)

# mmol/L → mg/dL conversion factors per analyte (standard molar-mass factors).
_MMOL_TO_MGDL: dict[str, float] = {
    "fasting_glucose": 18.0182,
    "triglyceride": 88.57,
    "hdl": 38.67,
}


def _to_mgdl(metric_type: str, value: float, unit: str | None) -> float:
    """Convert a stored value to mg/dL when the unit is mmol/L; else return as-is.

    Only the analytes in ``_MMOL_TO_MGDL`` are convertible; hba1c (%) and
    systolic BP (mmHg) are unit-invariant and pass through unchanged.
    """
    if unit and "mmol" in unit.lower() and metric_type in _MMOL_TO_MGDL:
        return round(value * _MMOL_TO_MGDL[metric_type], 1)
    return value


def _latest_by_type(db: Session, patient_id: str) -> dict[str, HealthMetric]:
    """Return the most-recent HealthMetric per score-relevant metric_type."""
    rows = list(
        db.execute(
            select(HealthMetric)
            .where(
                HealthMetric.patient_id == patient_id,
                HealthMetric.metric_type.in_(_SCORE_METRIC_TYPES),
                HealthMetric.deleted_at.is_(None),
            )
            .order_by(HealthMetric.measured_at.desc())
        ).scalars()
    )
    latest: dict[str, HealthMetric] = {}
    for row in rows:
        # rows are newest-first → first occurrence per type wins
        latest.setdefault(row.metric_type, row)
    return latest


def compute_live_score(db: Session, *, patient_id: str) -> MetabolicScoreResult | None:
    """Compute the metabolic score from the patient's latest metrics + profile.

    Returns ``None`` only when there are genuinely no usable inputs (no relevant
    metric readings and no waist measurement on the profile). Read-only — nothing
    is persisted.
    """
    latest = _latest_by_type(db, patient_id)
    profile = db.get(PatientProfile, patient_id)

    # Waist + gender come from the profile (waist may also arrive as a metric).
    waist_cm = profile.waist_cm if profile else None
    is_male = (profile.gender == "male") if profile and profile.gender else True

    def _val(metric_type: str) -> float | None:
        m = latest.get(metric_type)
        if m is None:
            return None
        return _to_mgdl(metric_type, m.value, m.unit)

    inputs = MetabolicInputs(
        waist_cm=waist_cm,
        fasting_glucose=_val("fasting_glucose"),
        hba1c=_val("hba1c"),
        triglyceride=_val("triglyceride"),
        hdl=_val("hdl"),
        systolic_bp=_val("blood_pressure_systolic"),
        is_male=is_male,
    )

    # No usable inputs at all → no score (genuine empty state).
    if (
        inputs.waist_cm is None
        and inputs.fasting_glucose is None
        and inputs.hba1c is None
        and inputs.triglyceride is None
        and inputs.hdl is None
        and inputs.systolic_bp is None
    ):
        return None

    return compute(inputs)
