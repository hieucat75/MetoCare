"""AI assistant + triage + metabolic score routes.

All AI responses pass through the guardrail (input + output) in the service
layer. Triage runs the rule engine first. No external LLM/OCR is called.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from app.core.security import decode_token
from app.domain import metabolic_score, triage
from app.llm import LLMRateLimitError
from app.schemas.ai import (
    ChatRequest,
    ChatResponse,
    ScoreRequest,
    ScoreResponse,
    TriageRequest,
    TriageResponse,
)
from app.services import ai_assistant

router = APIRouter(prefix="/ai", tags=["ai"])


def _cost_subject(request: Request) -> str:
    """Identify the cost-guard subject without requiring auth on /ai/chat.

    Prefer the authenticated user id (token sub); fall back to client IP so the
    per-user rate/cost cap still applies to anonymous callers.
    """
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        payload = decode_token(auth[7:])
        if payload and payload.get("type") == "access" and payload.get("sub"):
            return str(payload["sub"])
    return request.client.host if request.client else "anonymous"


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    try:
        resp = ai_assistant.respond(
            payload.message, intent=payload.intent, user_id=_cost_subject(request)
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
def assess(payload: TriageRequest) -> TriageResponse:
    data = triage.TriageInput(
        symptom_text=payload.symptom_text,
        vitals=[triage.VitalSign(v.metric_type, v.value) for v in payload.vitals],
        reported_severity=payload.reported_severity,
    )
    result = triage.assess(data)
    return TriageResponse(
        risk_level=result.risk_level.value,
        action=result.action.value,
        message=result.message,
        red_flags=result.red_flags,
        escalated_to_doctor=result.escalated_to_doctor,
        rule_forced=result.rule_forced,
    )


@router.post("/metabolic-score", response_model=ScoreResponse)
def score(payload: ScoreRequest) -> ScoreResponse:
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
    return ScoreResponse(
        score=result.score,
        band=result.band.value,
        factors=[{"name": f.name, "points": f.points, "detail": f.detail} for f in result.factors],
        explanation=result.explanation,
    )
