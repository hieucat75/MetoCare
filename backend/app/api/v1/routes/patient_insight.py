"""Patient Insight API Route — Phase E.

POST /api/v1/patients/{patient_id}/patient-insight

Calls the lab_intelligence pipeline internally, then wraps the output through
generate_patient_insight() to produce a structured PatientInsightReport.

Auth: same as lab_intelligence — requires PATIENT, DOCTOR, or INTERNAL_ADMIN role.
Patients may only access their own records.
"""

from __future__ import annotations

import dataclasses
import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_session, require_roles
from app.domain.clinical_patterns import detect_patterns
from app.domain.clinical_rules import ClinicalFinding, assess_biomarker
from app.domain.derived_metrics import DerivedMetricResult, compute_all_derived
from app.domain.longitudinal import BiomarkerTrend, compute_trends
from app.domain.patient_context import PatientContextEngine
from app.domain.patient_context import PatientContextInput as PatientContextInputDomain
from app.domain.patient_insight import _DISCLAIMER, PatientInsightReport, generate_patient_insight
from app.models.clinical import LabResult
from app.models.patient import PatientProfile
from app.models.user import UserRole
from app.services import consent
from app.services.lab import normalize_and_classify

router = APIRouter(tags=["patient_insight"])


class PatientContextInputModel(BaseModel):
    """Patient context supplement from frontend — merged with PatientProfile DB data."""
    sex: str | None = None
    age: int | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    waist_cm: float | None = None
    medications: list[str] | None = None
    exercise_level: str | None = None
    is_smoker: bool | None = None
    is_vegetarian: bool | None = None


class PatientInsightRequest(BaseModel):
    """Scoped request for patient-facing insight.

    Use ``batch_id`` to restrict analysis to one LabUploadBatch (the primary
    path from the Labs screen).  Omit both filters only for future patient-level
    dashboard summaries.
    """

    batch_id: str | None = None  # scope to one LabUploadBatch (preferred)
    lab_result_ids: list[str] | None = None  # fine-grained fallback
    include_trends: bool = True
    include_patterns: bool = True
    include_derived: bool = True
    # v3: structured context object
    context: PatientContextInputModel | None = None
    # Legacy compat (v1/v2 callers) — merged into context if present
    sex: str | None = None  # "male" | "female" | None
    age: int | None = None  # years
    waist_cm: float | None = None
    # Narrative: include AI narrative in response (additive, default False)
    include_narrative: bool = False


@router.post("/patients/{patient_id}/patient-insight")
def patient_insight(
    patient_id: str,
    body: PatientInsightRequest,
    db: Session = Depends(get_session),
    user: CurrentUser = Depends(
        require_roles(UserRole.PATIENT, UserRole.DOCTOR, UserRole.INTERNAL_ADMIN)
    ),
):
    """Generate a patient-facing insight report from verified lab results.

    Internally runs the lab intelligence pipeline, then passes the results
    through the Patient Insight Layer to produce InsightCards, ActionCards,
    urgent alerts, and a timeline summary in Vietnamese.

    Returns:
        JSON-serialized PatientInsightReport (via dataclasses.asdict).
    """
    # --- Auth check (mirrors lab_intelligence) ---
    if user.role == UserRole.PATIENT.value:
        profile = db.get(PatientProfile, patient_id)
        if profile is None or profile.user_id != user.id:
            raise HTTPException(
                status_code=403,
                detail="Patients may only access their own records.",
            )
    else:
        consent.require_access(db, patient_id=patient_id, requester_id=user.id, scope="lab")

    # --- Fetch verified lab results (batch-scoped or fine-grained) ---
    q = select(LabResult).where(
        LabResult.patient_id == patient_id,
        LabResult.deleted_at.is_(None),
    )
    if body.batch_id:
        # Primary path: Labs screen opens insight for a specific upload batch.
        q = q.where(LabResult.batch_id == body.batch_id)
    elif body.lab_result_ids:
        # Fallback when batch_id is not available.
        q = q.where(LabResult.id.in_(body.lab_result_ids))
    # No filter -> all patient records (reserved for future dashboard endpoint).
    rows = db.execute(q).scalars().all()
    verified = [r for r in rows if r.verified_by_user or r.verified_by_doctor]

    # --- Build PatientContext (Engine 1) ---
    # Merge: v3 context object takes priority; legacy sex/age/waist_cm as fallback
    profile = db.get(PatientProfile, patient_id)
    ctx_input = PatientContextInputDomain(
        sex=(body.context.sex if body.context and body.context.sex else body.sex),
        age=(body.context.age if body.context and body.context.age else body.age),
        height_cm=(body.context.height_cm if body.context else None),
        weight_kg=(body.context.weight_kg if body.context else None),
        waist_cm=(body.context.waist_cm if body.context and body.context.waist_cm else body.waist_cm),
        medications=(body.context.medications if body.context else None),
        exercise_level=(body.context.exercise_level if body.context else None),
        is_smoker=(body.context.is_smoker if body.context else None),
        is_vegetarian=(body.context.is_vegetarian if body.context else None),
    )
    patient_ctx = PatientContextEngine(profile, ctx_input).build()

    # Map frontend sex/age fields to clinical engine parameters (legacy path)
    is_male: bool = (patient_ctx.sex == "male") if patient_ctx.sex is not None else True
    age_years: int | None = patient_ctx.age

    if not verified:
        # Return a minimal valid report with no data
        empty_report = PatientInsightReport(
            patient_id=patient_id,
            generated_at=dt.datetime.now(dt.UTC).isoformat(),
            overall_status="good",
            overall_status_text_vi="Chưa có kết quả đã xác minh để phân tích.",
            top_priorities=[],
            insights=[],
            action_cards=[],
            timeline=[],
            positive_reinforcement=[],
            urgent_alerts=[],
            ai_draft_contract=None,
            disclaimer_vi=_DISCLAIMER,
            context_completeness=patient_ctx.context_completeness,
            missing_context=patient_ctx.missing_context,
        )
        return dataclasses.asdict(empty_report)

    # --- Lab Intelligence pipeline ---
    # IMPORTANT (P0 fix): always use normalized_value_si (canonical mg/dL) for
    # assess_biomarker() and derived-metric inputs. Using r.value (raw OCR value
    # which may be mmol/L) caused 5.7 mmol/L glucose to be treated as 5.7 mg/dL
    # → triggered the critical (≤54 mg/dL) branch → wrongly showed
    # "rất nguy hiểm" in AI Summary for a merely borderline result.
    findings: list[ClinicalFinding] = []
    raw_inputs: dict[str, float] = {}

    for r in verified:
        if not r.canonical_name:
            continue

        # Resolve canonical (SI) value — prefer stored normalized_value_si;
        # fall back to on-the-fly normalization from r.value + r.unit.
        norm_si: float | None = r.normalized_value_si
        if norm_si is None and r.value is not None:
            clf = normalize_and_classify(r.canonical_name, r.value, r.unit or "")
            norm_si = clf.get("normalized_value_si") if clf else None

        if norm_si is None:
            # No usable value — skip this result entirely.
            continue

        # Assertion: never feed raw mmol/L into assess_biomarker
        assert norm_si is not None, (
            f"normalized_value_si must be resolved before calling assess_biomarker "
            f"(canonical={r.canonical_name}, raw_value={r.value}, unit={r.unit})"
        )

        raw_inputs[r.canonical_name] = norm_si
        f = assess_biomarker(
            r.canonical_name,
            norm_si,
            age_years=age_years,
            is_male=is_male,
        )
        if f:
            findings.append(f)

    # Derived metrics
    derived_list: list[DerivedMetricResult] = []
    if body.include_derived:
        derived_list = compute_all_derived(
            raw_inputs,
            age_years=age_years,
            is_male=is_male,
            waist_cm=body.waist_cm,
        )
    derived_map: dict[str, DerivedMetricResult] = {d.canonical: d for d in derived_list}

    # Patterns
    patterns_raw = []
    if body.include_patterns:
        patterns_raw = detect_patterns(
            {
                "findings": {f.canonical: f.__dict__ for f in findings},
                "derived": {
                    k: (v.value if v.value is not None else None) for k, v in derived_map.items()
                },
            }
        )

    # Trends
    trends: list[BiomarkerTrend] = []
    if body.include_trends:
        for c in sorted(set(r.canonical_name for r in verified if r.canonical_name)):
            trends.append(compute_trends(verified, c))

    # --- Patient Insight Layer ---
    report = generate_patient_insight(
        patient_id=patient_id,
        findings=findings,
        patterns=patterns_raw,
        trends=trends,
        derived=derived_map,
        ctx=patient_ctx,
    )

    result = dataclasses.asdict(report)

    # Optionally include narrative if requested (additive — never fails main response)
    if body.include_narrative:
        try:
            from app.services.medical_narrative import generate_narrative  # noqa: PLC0415
            narrative_result = generate_narrative(report, patient_id, body.batch_id)
            if hasattr(narrative_result, "__dataclass_fields__"):
                result["narrative"] = dataclasses.asdict(narrative_result)
            else:
                result["narrative"] = vars(narrative_result)
        except Exception:  # narrative is additive; never fail the main response
            pass

    return result
