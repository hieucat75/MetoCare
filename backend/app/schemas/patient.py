"""Patient profile schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


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


class PatientSummaryOut(BaseModel):
    """Compact view for doctor portal / admin list."""

    id: str
    user_id: str
    full_name: str | None
    gender: str | None
    risk_segment: str | None

    model_config = {"from_attributes": True}
