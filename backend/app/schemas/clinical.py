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
