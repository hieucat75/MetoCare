"""AI assistant / triage / metabolic score schemas."""

from __future__ import annotations

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

# ---------------------------------------------------------------------------
# Patient-Safe AI Explanation (PA-05)
# ---------------------------------------------------------------------------

import enum as _enum  # noqa: E402
from datetime import datetime  # noqa: E402


class ExplanationType(_enum.StrEnum):
    metabolic_score = "metabolic_score"
    health_metric = "health_metric"
    lab_result = "lab_result"
    general_summary = "general_summary"


class SafetyLevel(_enum.StrEnum):
    informational = "informational"


class ExplainContext(BaseModel):
    """Optional context fields — all optional, no one is required."""

    metric_type: str | None = None
    value: float | None = None
    unit: str | None = None
    score: int | None = None
    trend: str | None = None


class AiExplainRequest(BaseModel):
    patient_id: str
    explanation_type: ExplanationType
    context: ExplainContext = Field(default_factory=ExplainContext)


_DISCLAIMER = (
    "This explanation is for informational purposes only and is not a medical "
    "diagnosis. Always consult your doctor for medical advice."
)


class AiExplainResponse(BaseModel):
    explanation_type: ExplanationType
    plain_language_summary: str
    safety_level: SafetyLevel = SafetyLevel.informational
    disclaimer: str = _DISCLAIMER
    generated_at: datetime
