"""Patient profile schemas."""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PatientProfileCreate(BaseModel):
    full_name: str | None = None
    dob: str | None = Field(None, description="ISO date string YYYY-MM-DD")
    phone: str | None = None
    address: str | None = None
    gender: str | None = Field(None, pattern="^(male|female|other)$")
    height_cm: float | None = Field(None, gt=0, le=300)
    weight_kg: float | None = Field(None, gt=0, le=500)
    waist_cm: float | None = Field(None, gt=0, le=300)
    known_conditions: str | None = None
    allergies: str | None = None
    family_history: str | None = None
    lifestyle_profile: str | None = None


class PatientProfileUpdate(BaseModel):
    """Partial update schema for patient profile (T12).

    All fields are optional. Only supplied fields are written.
    Excludes ``address``, ``family_history``, and ``lifestyle_profile``
    (deferred to extended-profile sprint).
    """

    full_name: str | None = None
    dob: str | None = None
    phone: str | None = None
    gender: str | None = None
    height_cm: float | None = Field(None, gt=0, le=300)
    weight_kg: float | None = Field(None, gt=0, le=500)
    waist_cm: float | None = Field(None, gt=0, le=300)
    known_conditions: str | None = None
    allergies: str | None = None


class PatientProfileOut(BaseModel):
    """Standard patient profile view — PHI-limited (T12).

    Intentionally excludes ``address``, ``family_history``, and
    ``lifestyle_profile`` (deferred to the extended-profile endpoint in a
    future sprint, per T12 task card §Medical Safety Notes).
    """

    id: str
    user_id: str
    full_name: str | None
    dob: str | None
    phone: str | None
    gender: str | None
    height_cm: float | None
    weight_kg: float | None
    waist_cm: float | None
    risk_segment: str | None
    known_conditions: str | None
    allergies: str | None

    model_config = {"from_attributes": True}


class PatientCompactOut(BaseModel):
    """Compact view for doctor portal / admin list."""

    id: str
    user_id: str
    full_name: str | None
    gender: str | None
    risk_segment: str | None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# T22 — Pre-Visit Patient Summary
# ---------------------------------------------------------------------------

class VitalsSummary(BaseModel):
    """Recent vitals snapshot for the summary endpoint."""

    latest: list[Any] = Field(default_factory=list)
    trend: str = "insufficient_data"  # improving | stable | worsening | insufficient_data


class MetabolicScoreSummary(BaseModel):
    """Latest metabolic/risk score for the summary endpoint."""

    latest_score: float | None = None
    trend: str = "insufficient_data"
    recorded_at: dt.datetime | None = None


class PatientSummaryOut(BaseModel):
    """Full pre-visit patient summary for the doctor portal (T22).

    Aggregates recent vitals, labs, metabolic score, medications, symptoms,
    nutrition, upcoming appointments, and active care-plan metadata.

    RBAC:
    - DOCTOR — consent-gated (scope='profile')
    - INTERNAL_ADMIN / SUPER_ADMIN — unrestricted
    - PATIENT, AI_SERVICE — always 403
    """

    patient_id: str
    generated_at: dt.datetime

    vitals: VitalsSummary = Field(default_factory=VitalsSummary)
    lab_documents: list[Any] = Field(default_factory=list)
    metabolic_score: MetabolicScoreSummary = Field(default_factory=MetabolicScoreSummary)
    medications: list[Any] = Field(default_factory=list)
    symptoms: list[Any] = Field(default_factory=list)
    nutrition: list[Any] = Field(default_factory=list)
    upcoming_appointments: list[Any] = Field(default_factory=list)
    active_care_plans: list[Any] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=False)
