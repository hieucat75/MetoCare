"""Admin portal schemas: user management, audit log read, system stats."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.crypto import is_fernet_token
from app.models.user import UserRole

# ---------------------------------------------------------------------------
# User admin views
# ---------------------------------------------------------------------------


class UserAdminOut(BaseModel):
    id: str
    # Patients self-register by phone, so email can be NULL (one of email/phone set).
    email: str | None
    phone: str | None = None
    role: str
    full_name: str | None
    is_active: bool
    mfa_enabled: bool
    created_at: dt.datetime | None = None

    model_config = {"from_attributes": True}

    @field_validator("full_name", mode="after")
    @classmethod
    def _never_expose_ciphertext(cls, v: str | None) -> str | None:
        # Defense in depth: never leak Fernet tokens from corrupt rows.
        return None if is_fernet_token(v) else v


class UserStatusUpdate(BaseModel):
    is_active: bool


class UserRoleUpdate(BaseModel):
    role: UserRole


# ---------------------------------------------------------------------------
# Per-user audit log view (T25)
# ---------------------------------------------------------------------------


class UserAuditLogOut(BaseModel):
    id: str
    action: str
    resource_type: str
    resource_id: str | None
    timestamp: dt.datetime | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Audit log read (admin-only)
# ---------------------------------------------------------------------------


class AuditLogOut(BaseModel):
    id: str
    actor_type: str
    actor_id: str | None
    action: str
    resource_type: str
    resource_id: str | None
    outcome: str
    severity: str
    ip_address: str | None
    timestamp: dt.datetime

    model_config = {"from_attributes": True}


class AuditLogFilter(BaseModel):
    actor_id: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    outcome: str | None = None
    severity: str | None = None
    from_dt: dt.datetime | None = None
    to_dt: dt.datetime | None = None
    limit: int = 50
    offset: int = 0


# ---------------------------------------------------------------------------
# Admin actions
# ---------------------------------------------------------------------------


class UnlockRequest(BaseModel):
    email: str


class DoctorCreateRequest(BaseModel):
    # max_length guards the users.email VARCHAR(255) column before the DB does.
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=6)
    full_name: str = Field(min_length=1, max_length=255)
    specialty: str | None = None
    license_no: str | None = None
    bio: str | None = None
    clinic_id: str | None = None


class DoctorAdminOut(BaseModel):
    user_id: str
    doctor_id: str
    email: str | None
    full_name: str
    role: str
    is_active: bool
    mfa_enabled: bool

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# System stats (lightweight, no PHI)
# ---------------------------------------------------------------------------


class SystemStatsOut(BaseModel):
    total_users: int
    total_patients: int
    total_doctors: int
    total_appointments: int
    total_ai_conversations: int
    total_audit_entries: int


class AdminStatsOut(BaseModel):
    """Platform-wide counts for the admin dashboard (matches frontend AdminStats)."""

    total_users: int
    active_patients: int
    active_doctors: int
    total_clinics: int
    ai_sessions_today: int
    pending_reviews: int
    flagged_ai_sessions: int
    audit_events_today: int


# ---------------------------------------------------------------------------
# AI safety monitoring (/admin/ai-sessions — matches frontend AiSession)
# ---------------------------------------------------------------------------

AiSafetyLevel = Literal["safe", "caution", "urgent"]
AiSessionFlag = Literal[
    "none", "urgent_response", "off_topic", "clinical_claim", "review_requested"
]


class AdminAiSessionOut(BaseModel):
    id: str
    patient_id: str
    patient_name: str | None
    explanation_type: str
    safety_level: AiSafetyLevel
    flag: AiSessionFlag
    created_at: dt.datetime
    reviewed_by: str | None = None
    reviewed_at: dt.datetime | None = None

    @field_validator("patient_name", "reviewed_by", mode="after")
    @classmethod
    def _never_expose_ciphertext(cls, v: str | None) -> str | None:
        return None if is_fernet_token(v) else v


class AdminAiSessionListResponse(BaseModel):
    total: int
    flagged_count: int
    items: list[AdminAiSessionOut]
