"""AI assistant / triage / metabolic score schemas."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str
    intent: str = "health_assistant"


class ChatResponse(BaseModel):
    text: str
    intent: str
    risk_level: str
    escalated_to_doctor: bool
    safety_flags: list[str]
    blocked: bool
    model_used: str = "mock"
    cached: bool = False


class VitalIn(BaseModel):
    metric_type: str
    value: float


class TriageRequest(BaseModel):
    symptom_text: str = ""
    vitals: list[VitalIn] = Field(default_factory=list)
    reported_severity: int | None = None


class TriageResponse(BaseModel):
    risk_level: str
    action: str
    message: str
    red_flags: list[str]
    escalated_to_doctor: bool
    rule_forced: bool


class ScoreRequest(BaseModel):
    waist_cm: float | None = None
    fasting_glucose: float | None = None
    hba1c: float | None = None
    triglyceride: float | None = None
    hdl: float | None = None
    systolic_bp: float | None = None
    is_male: bool = True


class ScoreFactorOut(BaseModel):
    name: str
    points: int
    detail: str


class ScoreResponse(BaseModel):
    score: int
    band: str
    factors: list[ScoreFactorOut]
    explanation: str


# ---------------------------------------------------------------------------
# Doctor Review Workflow
# ---------------------------------------------------------------------------


class DoctorReviewDecision(BaseModel):
    verdict: Literal["accepted", "rejected", "request_info"]
    notes: str | None = None


class AIClinicalRecommendationOut(BaseModel):
    id: str
    session_id: str
    patient_id: str
    recommendation_type: str
    status: str
    ai_confidence: float | None
    safety_cleared: bool
    reviewed_by_doctor_id: str | None
    reviewed_at: dt.datetime | None

    model_config = {"from_attributes": True}

