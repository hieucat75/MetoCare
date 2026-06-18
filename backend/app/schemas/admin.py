"""Admin portal schemas: user management, audit log read, system stats."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel

from app.models.user import UserRole

# ---------------------------------------------------------------------------
# User admin views
# ---------------------------------------------------------------------------

class UserAdminOut(BaseModel):
    id: str
    email: str
    role: str
    full_name: str | None
    is_active: bool
    mfa_enabled: bool
    created_at: dt.datetime | None = None

    model_config = {"from_attributes": True}


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
