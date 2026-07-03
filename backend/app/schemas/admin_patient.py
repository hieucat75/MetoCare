"""Admin — Patient Records Management schemas.

Views for the admin-only patient list/detail endpoints. Distinct from
``app.schemas.patient`` (patient's own view) — these expose account status
and cross-cutting fields (consent, consultations, audit trail) that only
INTERNAL_ADMIN / SUPER_ADMIN may see.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel

from app.schemas.patient import PatientSummaryOut


class AdminPatientListItemOut(BaseModel):
    id: str  # patient_profile id
    user_id: str
    full_name: str | None
    phone: str | None
    gender: str | None
    birth_year: int | None
    age: int | None
    is_active: bool
    lab_result_count: int
    medication_count: int
    has_data_quality_flag: bool
    consent_status: str  # "valid" | "revoked" | "none"
    created_at: dt.datetime | None
    last_activity_at: dt.datetime | None


class AdminPatientListOut(BaseModel):
    total: int
    items: list[AdminPatientListItemOut]


class AdminPatientConsultationOut(BaseModel):
    id: str
    doctor_id: str
    doctor_name: str | None
    clinic_name: str | None
    status: str
    created_at: dt.datetime | None


class AdminPatientConsentOut(BaseModel):
    terms_version: str
    privacy_version: str
    accepted_at: dt.datetime
    revoked_at: dt.datetime | None

    model_config = {"from_attributes": True}


class AdminPatientAuditEntryOut(BaseModel):
    id: str
    action: str
    resource_type: str
    outcome: str
    timestamp: dt.datetime

    model_config = {"from_attributes": True}


class AdminPatientDetailOut(BaseModel):
    id: str
    user_id: str
    email: str | None
    full_name: str | None
    phone: str | None
    dob: str | None
    age: int | None
    gender: str | None
    address: str | None
    height_cm: float | None
    weight_kg: float | None
    waist_cm: float | None
    risk_segment: str | None
    known_conditions: str | None
    allergies: str | None
    family_history: str | None
    lifestyle_profile: str | None
    is_active: bool
    created_at: dt.datetime | None
    last_activity_at: dt.datetime | None
    consent_status: str
    consent: AdminPatientConsentOut | None
    consultations: list[AdminPatientConsultationOut]
    audit_log: list[AdminPatientAuditEntryOut]
    summary: PatientSummaryOut


class PatientStatusUpdate(BaseModel):
    is_active: bool
