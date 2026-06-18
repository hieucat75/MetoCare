"""AI assistant + triage + metabolic score routes.

All AI responses pass through the guardrail (input + output) in the service
layer. Triage runs the rule engine first. No external LLM/OCR is called.

Auth: All 3 routes require a valid JWT (Bearer token).
RBAC: PATIENT, DOCTOR, CLINIC_ADMIN, INTERNAL_ADMIN, SUPER_ADMIN allowed.
      AI_SERVICE is explicitly excluded — it uses the AISession API instead.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_session, require_roles
from app.domain import metabolic_score, triage
from app.llm import LLMRateLimitError
from app.models.patient import PatientProfile
from app.models.user import UserRole
from app.schemas.ai import (
    ChatRequest,
    ChatResponse,
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
