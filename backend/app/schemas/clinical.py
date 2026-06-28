"""Clinical data schemas: Medication, RiskScore, SymptomLog."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Medication  (record-only — AI must NEVER modify dose)
# ---------------------------------------------------------------------------


class MedicationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    dose: str | None = Field(None, max_length=128)
    note: str | None = Field(None, max_length=1024)


class MedicationUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    dose: str | None = Field(None, max_length=128)
    note: str | None = Field(None, max_length=1024)


class MedicationOut(BaseModel):
    id: str
    patient_id: str
    name: str
    dose: str | None
    note: str | None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Risk Score
# ---------------------------------------------------------------------------


class RiskScoreOut(BaseModel):
    id: str
    patient_id: str
    metabolic_score: int
    band: str
    top_risks: str | None  # serialised JSON string from domain layer

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Symptom Log
# ---------------------------------------------------------------------------


class SymptomLogCreate(BaseModel):
    description: str = Field(..., min_length=1, max_length=2048)
    severity: int | None = Field(None, ge=0, le=10)
    reported_at: dt.datetime | None = None


class SymptomLogOut(BaseModel):
    id: str
    patient_id: str
    description: str
    severity: int | None
    reported_at: dt.datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# AISession & AIClinicalRecommendation
# ---------------------------------------------------------------------------


class AISessionOut(BaseModel):
    id: str
    patient_id: str
    encounter_id: str | None
    session_type: str
    messages: str | None
    key_version: int | None
    risk_level: str | None
    escalated_to_doctor: bool
    escalation_reason: str | None
    model_used: str | None
    safety_flags: str | None
    input_blocked: bool
    output_blocked: bool
    total_tokens: int | None
    created_at: dt.datetime
    updated_at: dt.datetime

    model_config = {"from_attributes": True}


class AIClinicalRecommendationOut(BaseModel):
    id: str
    session_id: str
    patient_id: str
    encounter_id: str | None
    recommendation_type: str
    content: str | None
    key_version: int | None
    status: str
    reviewed_by_doctor_id: str | None
    reviewed_at: dt.datetime | None
    ai_confidence: float | None
    safety_cleared: bool
    medical_disclaimer: str | None
    created_at: dt.datetime
    updated_at: dt.datetime

    model_config = {"from_attributes": True}


class AIClinicalRecommendationReview(BaseModel):
    action: str = Field(..., pattern="^(accept|reject)$")
    notes: str | None = None
