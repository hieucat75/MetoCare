"""Medical Narrative API.

POST /api/v1/patients/{patient_id}/narrative
  - Generates narrative for a batch synchronously
  - Returns NarrativeResult

GET /api/v1/patients/{patient_id}/narrative/{batch_id}
  - Returns cached narrative if available
  - Returns {"status": "pending", "message": "Đang tạo..."} if not yet cached
  - Returns {"status": "unavailable"} if no cached result

Auth: PATIENT (own), DOCTOR, INTERNAL_ADMIN — same pattern as patient_insight.py
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
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
from app.services.claude_client import ANTHROPIC_MODEL
from app.services.lab import normalize_and_classify
from app.services.medical_narrative import generate_narrative
from app.services.narrative_cache import get_cached_narrative, make_narrative_key
from app.services.narrative_prompts import ENGINE_VERSION, PROMPT_VERSION

NARRATIVE_PROVIDER = "anthropic"
NARRATIVE_LANGUAGE = "vi"

router = APIRouter(tags=["narrative"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class NarrativeRequest(BaseModel):
    batch_id: str | None = None
    language: str = "vi"
    force_regenerate: bool = False  # bypass cache
    # Optional patient context (mirrors PatientInsightRequest.context)
    sex: str | None = None
    age: int | None = None
    waist_cm: float | None = None


class NarrativeQualityOut(BaseModel):
    medical_consistency: float
    personalization: float
    readability: float
    actionability: float
    empathy: float
    safety: float
    estimated_read_seconds: int
    hallucination_risk: float
    overall: float


class NarrativeResponse(BaseModel):
    patient_id: str
    batch_id: str | None
    narrative: dict
    source: str
    cached: bool
    prompt_version: str
    engine_version: str
    provider: str
    model: str
    validation_passed: bool
    latency_ms: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    quality_score: NarrativeQualityOut | None = None


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

def _check_read_access(
    db: Session,
    patient_id: str,
    user: CurrentUser,
) -> None:
    """Raise 403 if the user cannot access this patient's data."""
    if user.role == UserRole.PATIENT.value:
        profile = db.get(PatientProfile, patient_id)
        if profile is None or profile.user_id != user.id:
            raise HTTPException(
                status_code=403,
                detail="Patients may only access their own records.",
            )
    else:
        consent.require_access(db, patient_id=patient_id, requester_id=user.id, scope="lab")


# ---------------------------------------------------------------------------
# Internal: build PatientInsightReport (shared with patient_insight.py)
# ---------------------------------------------------------------------------

def _build_report(
    patient_id: str,
    batch_id: str | None,
    sex: str | None,
    age: int | None,
    waist_cm: float | None,
    db: Session,
) -> PatientInsightReport:
    """Run the full insight pipeline and return PatientInsightReport."""
    q = select(LabResult).where(
        LabResult.patient_id == patient_id,
        LabResult.deleted_at.is_(None),
    )
    if batch_id:
        q = q.where(LabResult.batch_id == batch_id)
    rows = db.execute(q).scalars().all()
    verified = [r for r in rows if r.verified_by_user or r.verified_by_doctor]

    profile = db.get(PatientProfile, patient_id)
    ctx_input = PatientContextInputDomain(
        sex=sex,
        age=age,
        waist_cm=waist_cm,
    )
    patient_ctx = PatientContextEngine(profile, ctx_input).build()

    is_male: bool = (patient_ctx.sex == "male") if patient_ctx.sex is not None else True
    age_years: int | None = patient_ctx.age

    if not verified:
        return PatientInsightReport(
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

    findings: list[ClinicalFinding] = []
    raw_inputs: dict[str, float] = {}

    for r in verified:
        if not r.canonical_name:
            continue
        norm_si: float | None = r.normalized_value_si
        if norm_si is None and r.value is not None:
            clf = normalize_and_classify(r.canonical_name, r.value, r.unit or "")
            norm_si = clf.get("normalized_value_si") if clf else None
        if norm_si is None:
            continue
        raw_inputs[r.canonical_name] = norm_si
        f = assess_biomarker(r.canonical_name, norm_si, age_years=age_years, is_male=is_male)
        if f:
            findings.append(f)

    derived_list: list[DerivedMetricResult] = compute_all_derived(
        raw_inputs, age_years=age_years, is_male=is_male, waist_cm=waist_cm
    )
    derived_map: dict[str, DerivedMetricResult] = {d.canonical: d for d in derived_list}

    patterns_raw = detect_patterns(
        {
            "findings": {f.canonical: f.__dict__ for f in findings},
            "derived": {k: (v.value if v.value is not None else None) for k, v in derived_map.items()},
        }
    )

    trends: list[BiomarkerTrend] = []
    for c in sorted(set(r.canonical_name for r in verified if r.canonical_name)):
        trends.append(compute_trends(verified, c))

    return generate_patient_insight(
        patient_id=patient_id,
        findings=findings,
        patterns=patterns_raw,
        trends=trends,
        derived=derived_map,
        ctx=patient_ctx,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/patients/{patient_id}/narrative", response_model=NarrativeResponse)
def generate_narrative_endpoint(
    patient_id: str,
    body: NarrativeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session),
    user: CurrentUser = Depends(
        require_roles(UserRole.PATIENT, UserRole.DOCTOR, UserRole.INTERNAL_ADMIN)
    ),
) -> NarrativeResponse:
    """Generate a patient-friendly Vietnamese narrative from lab results.

    Builds the PatientInsightReport (same pipeline as /patient-insight),
    then generates a 10-section narrative via Claude.

    Falls back to deterministic narrative if Claude is unavailable.
    """
    _check_read_access(db, patient_id, user)

    report = _build_report(
        patient_id=patient_id,
        batch_id=body.batch_id,
        sex=body.sex,
        age=body.age,
        waist_cm=body.waist_cm,
        db=db,
    )

    result = generate_narrative(
        report=report,
        patient_id=patient_id,
        batch_id=body.batch_id,
        use_cache=not body.force_regenerate,
    )

    quality_out: NarrativeQualityOut | None = None
    if result.quality_score is not None:
        qs = result.quality_score
        quality_out = NarrativeQualityOut(
            medical_consistency=qs.medical_consistency,
            personalization=qs.personalization,
            readability=qs.readability,
            actionability=qs.actionability,
            empathy=qs.empathy,
            safety=qs.safety,
            estimated_read_seconds=qs.estimated_read_seconds,
            hallucination_risk=qs.hallucination_risk,
            overall=qs.overall,
        )

    return NarrativeResponse(
        patient_id=result.patient_id,
        batch_id=result.batch_id,
        narrative=result.narrative,
        source=result.source,
        cached=result.cached,
        prompt_version=result.prompt_version,
        engine_version=result.engine_version,
        provider=result.provider,
        model=result.model,
        validation_passed=result.validation_passed,
        latency_ms=result.latency_ms,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        quality_score=quality_out,
    )


@router.get("/patients/{patient_id}/narrative/{batch_id}")
def get_cached_narrative_endpoint(
    patient_id: str,
    batch_id: str,
    db: Session = Depends(get_session),
    user: CurrentUser = Depends(
        require_roles(UserRole.PATIENT, UserRole.DOCTOR, UserRole.INTERNAL_ADMIN)
    ),
) -> dict:
    """Return cached narrative for a patient+batch.

    Returns:
        - {"status": "ready", "data": NarrativeResponse} if cached
        - {"status": "pending", "message": "Đang tạo..."} if not yet generated
    """
    _check_read_access(db, patient_id, user)

    cache_key = make_narrative_key(
        patient_id=patient_id,
        batch_id=batch_id,
        engine_version=ENGINE_VERSION,
        prompt_version=PROMPT_VERSION,
        provider=NARRATIVE_PROVIDER,
        model=ANTHROPIC_MODEL,
        language=NARRATIVE_LANGUAGE,
    )

    cached = get_cached_narrative(cache_key)
    if cached and "narrative" in cached:
        return {
            "status": "ready",
            "data": {
                "patient_id": patient_id,
                "batch_id": batch_id,
                "narrative": cached["narrative"],
                "source": "cache",
                "cached": True,
                "prompt_version": cached.get("prompt_version", PROMPT_VERSION),
                "engine_version": cached.get("engine_version", ENGINE_VERSION),
                "provider": NARRATIVE_PROVIDER,
                "model": ANTHROPIC_MODEL,
                "validation_passed": True,
                "latency_ms": 0,
                "prompt_tokens": cached.get("prompt_tokens", 0),
                "completion_tokens": cached.get("completion_tokens", 0),
            },
        }

    return {
        "status": "pending",
        "message": "Đang tạo giải thích AI, vui lòng thử lại sau vài giây.",
    }
