"""AI assistant + triage + metabolic score + patient-safe explanation routes.

All AI responses pass through the guardrail (input + output) in the service
layer. Triage runs the rule engine first. No external LLM/OCR is called.

Auth: All routes require a valid JWT (Bearer token).
RBAC: PATIENT, DOCTOR, CLINIC_ADMIN, INTERNAL_ADMIN, SUPER_ADMIN allowed on
      general AI consumer routes.
      AI_SERVICE is explicitly excluded — it uses the AISession API instead.
      POST /ai/explain is PATIENT-only.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_session, require_roles
from app.core.feature_flags import FeatureFlag, is_enabled
from app.domain import metabolic_score, triage
from app.llm import LLMRateLimitError
from app.models.patient import PatientProfile
from app.models.user import UserRole
from app.schemas.ai import (
    _DISCLAIMER,
    AiExplainRequest,
    AiExplainResponse,
    ChatRequest,
    ChatResponse,
    ExplanationType,
    ScoreRequest,
    ScoreResponse,
    TriageRequest,
    TriageResponse,
)
from app.services import ai_assistant
from app.services import risk_score as risk_score_svc
from app.services import triage_log as triage_log_svc

router = APIRouter(prefix="/ai", tags=["ai"])

# Roles allowed on all AI consumer routes.
# AI_SERVICE is intentionally excluded — it operates via AISession API.
_AI_CONSUMER_ROLES = (
    UserRole.PATIENT,
    UserRole.DOCTOR,
    UserRole.CLINIC_ADMIN,
    UserRole.INTERNAL_ADMIN,
    UserRole.SUPER_ADMIN,
)

_require_ai_consumer = require_roles(*_AI_CONSUMER_ROLES)


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    user: CurrentUser = Depends(_require_ai_consumer),
) -> ChatResponse:
    if not is_enabled(FeatureFlag.AI_ASSISTANT):
        raise HTTPException(status_code=503, detail="AI assistant is disabled.")
    try:
        resp = ai_assistant.respond(
            payload.message, intent=payload.intent, user_id=user.id
        )
    except LLMRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    return ChatResponse(
        text=resp.text,
        intent=resp.intent,
        risk_level=resp.risk_level,
        escalated_to_doctor=resp.escalated_to_doctor,
        safety_flags=resp.safety_flags,
        blocked=resp.blocked,
        model_used=resp.model_used,
        cached=resp.cached,
    )


@router.post("/triage", response_model=TriageResponse)
def assess(
    payload: TriageRequest,
    user: CurrentUser = Depends(_require_ai_consumer),
    db: Session = Depends(get_session),
) -> TriageResponse:
    data = triage.TriageInput(
        symptom_text=payload.symptom_text,
        vitals=[triage.VitalSign(v.metric_type, v.value) for v in payload.vitals],
        reported_severity=payload.reported_severity,
    )
    result = triage.assess(data)

    # Persist the triage result when the caller is a PATIENT with a PatientProfile.
    # Other roles (DOCTOR, CLINIC_ADMIN, …) are silently skipped.
    if user.role == UserRole.PATIENT.value:
        patient_profile = db.execute(
            select(PatientProfile).where(PatientProfile.user_id == user.id)
        ).scalar_one_or_none()
        if patient_profile is not None:
            triage_log_svc.save_triage(
                db,
                patient_id=patient_profile.id,
                symptom_text=payload.symptom_text,
                result=result,
            )

    return TriageResponse(
        risk_level=result.risk_level.value,
        action=result.action.value,
        message=result.message,
        red_flags=result.red_flags,
        escalated_to_doctor=result.escalated_to_doctor,
        rule_forced=result.rule_forced,
    )


@router.post("/metabolic-score", response_model=ScoreResponse)
def score(
    payload: ScoreRequest,
    user: CurrentUser = Depends(_require_ai_consumer),
    db: Session = Depends(get_session),
) -> ScoreResponse:
    result = metabolic_score.compute(
        metabolic_score.MetabolicInputs(
            waist_cm=payload.waist_cm,
            fasting_glucose=payload.fasting_glucose,
            hba1c=payload.hba1c,
            triglyceride=payload.triglyceride,
            hdl=payload.hdl,
            systolic_bp=payload.systolic_bp,
            is_male=payload.is_male,
        )
    )

    # Persist the score when the caller is a PATIENT with a PatientProfile.
    # Other roles (DOCTOR, CLINIC_ADMIN, …) are silently skipped.
    if user.role == UserRole.PATIENT.value:
        patient_profile = db.execute(
            select(PatientProfile).where(PatientProfile.user_id == user.id)
        ).scalar_one_or_none()
        if patient_profile is not None:
            risk_score_svc.save_score(
                db,
                patient_id=patient_profile.id,
                result=result,
            )

    return ScoreResponse(
        score=result.score,
        band=result.band.value,
        factors=[{"name": f.name, "points": f.points, "detail": f.detail} for f in result.factors],
        explanation=result.explanation,
    )


# ---------------------------------------------------------------------------
# Patient-Safe Explanation Endpoint (PA-05)
# RBAC: PATIENT only — DOCTOR, ADMIN, AI_SERVICE → 403
# ---------------------------------------------------------------------------

_require_patient_only = require_roles(UserRole.PATIENT)

# Mock summaries per explanation_type — pilot mode, no external LLM call.
_MOCK_SUMMARIES: dict[ExplanationType, str] = {
    ExplanationType.metabolic_score: (
        "Your metabolic wellness score reflects how well your key health metrics "
        "are being managed. A lower score indicates healthier metabolic balance, "
        "while a higher score suggests areas that may need attention. Your care "
        "team will review this with you and recommend next steps."
    ),
    ExplanationType.health_metric: (
        "Your health reading is within a range that your care team will review "
        "with you. Small changes — like staying hydrated, eating balanced meals, "
        "and moving regularly — all contribute positively over time. Track your "
        "results regularly so you can spot trends together with your doctor."
    ),
    ExplanationType.lab_result: (
        "Your lab result has been recorded. Lab values are one piece of the "
        "bigger picture of your health. Your doctor will review these results and "
        "discuss what they mean for your specific situation at your next "
        "consultation."
    ),
    ExplanationType.general_summary: (
        "Based on the information you have shared, your overall health data is "
        "being tracked and monitored by your care team. Staying consistent with "
        "your check-ins, medications, and lifestyle goals will help you and your "
        "doctor make the best decisions for your wellbeing."
    ),
}


@router.post("/explain", response_model=AiExplainResponse)
def explain(
    payload: AiExplainRequest,
    user: CurrentUser = Depends(_require_patient_only),
    db: Session = Depends(get_session),
) -> AiExplainResponse:
    """Return a patient-safe, plain-language explanation of health data.

    • PATIENT-only endpoint.
    • Caller must own the PatientProfile identified by patient_id.
    • Mock implementation — no external AI call in pilot mode.
    • Medical disclaimer is always included.
    """
    if not is_enabled(FeatureFlag.AI_ASSISTANT):
        raise HTTPException(status_code=503, detail="AI assistant is disabled.")
    # Ownership check: resolve caller’s PatientProfile and compare to patient_id.
    patient_profile = db.execute(
        select(PatientProfile).where(PatientProfile.user_id == user.id)
    ).scalar_one_or_none()

    if patient_profile is None or str(patient_profile.id) != str(payload.patient_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorised to access this patient’s data.",
        )

    summary = _MOCK_SUMMARIES[payload.explanation_type]

    # Enrich summary with context values when provided.
    ctx = payload.context
    if payload.explanation_type == ExplanationType.health_metric and ctx.metric_type:
        value_str = f"{ctx.value} {ctx.unit}" if ctx.value is not None and ctx.unit else ""
        trend_str = f" The trend is currently {ctx.trend}." if ctx.trend else ""
        summary = (
            f"Your {ctx.metric_type.replace('_', ' ')} reading"
            + (f" of {value_str}" if value_str else "")
            + " is being tracked by your care team."
            + trend_str
            + " Keep monitoring regularly for a clearer picture."
        )
    elif payload.explanation_type == ExplanationType.metabolic_score and ctx.score is not None:
        # Map numeric score to a qualitative band — do NOT expose raw numeric value.
        if ctx.score < 25:
            band_label = "in a healthy range"
        elif ctx.score < 50:
            band_label = "in a fair range — some areas to watch"
        elif ctx.score < 75:
            band_label = "elevated — your care team will want to discuss this"
        else:
            band_label = "high — please speak with your doctor soon"
        trend_str = f" The trend is {ctx.trend}." if ctx.trend else ""
        summary = (
            f"Your metabolic wellness is currently {band_label}."
            + trend_str
            + " Your care team will review this with you and suggest next steps."
        )

    return AiExplainResponse(
        explanation_type=payload.explanation_type,
        plain_language_summary=summary,
        disclaimer=_DISCLAIMER,
        generated_at=datetime.now(tz=UTC),
    )
