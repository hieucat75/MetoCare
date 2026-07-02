"""Doctor-facing schemas for Phase 4A: profile, patient list, dashboard."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


class DoctorProfileOut(BaseModel):
    id: str
    user_id: str | None
    full_name: str
    specialty: str | None
    license_no: str | None
    bio: str | None
    avatar_url: str | None
    consultation_fee: float | None
    is_verified: bool
    is_active: bool
    clinic_id: str | None
    # Marketplace listing fields (T10)
    verification_status: str
    years_experience: int | None = None
    languages: str | None = None
    hospital_name: str | None = None
    consultation_methods: str | None = None
    rating_avg: float = 0.0
    rating_count: int = 0

    model_config = {"from_attributes": True}


class DoctorProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    bio: str | None = None
    avatar_url: str | None = None
    consultation_fee: float | None = Field(default=None, ge=0)
    specialty: str | None = None
    # license_no, clinic_id, user_id are intentionally absent — admin-managed only


class DoctorMarketplaceUpdate(BaseModel):
    """Self-service marketplace listing edits (T10)."""

    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    bio: str | None = None
    avatar_url: str | None = None
    consultation_fee: float | None = Field(default=None, ge=0)
    specialty: str | None = None
    years_experience: int | None = Field(default=None, ge=0, le=80)
    languages: str | None = Field(default=None, max_length=255)
    hospital_name: str | None = Field(default=None, max_length=255)
    consultation_methods: str | None = Field(default=None, max_length=255)


class DoctorVerificationOut(BaseModel):
    """Admin verification-queue row (T10)."""

    id: str
    user_id: str | None
    full_name: str
    specialty: str | None
    license_no: str | None
    hospital_name: str | None
    years_experience: int | None
    verification_status: str
    is_verified: bool
    is_active: bool

    model_config = {"from_attributes": True}


class DoctorPatientItem(BaseModel):
    patient_id: str
    full_name: str | None
    risk_segment: str | None
    last_encounter_at: dt.datetime | None
    pending_items: int


class DoctorAlertItem(BaseModel):
    patient_id: str
    full_name: str | None
    risk_segment: str


class DoctorDashboardOut(BaseModel):
    appointments_today: int
    pending_reviews: int
    pending_approvals: int
    total_patients: int
    recent_alerts: list[DoctorAlertItem]


class DoctorPublicOut(BaseModel):
    """Minimal public profile used by patients searching for a doctor to grant consent."""

    id: str
    full_name: str
    specialty: str | None
    bio: str | None
    avatar_url: str | None
    consultation_fee: float | None
    is_verified: bool
    is_active: bool

    model_config = {"from_attributes": True}
