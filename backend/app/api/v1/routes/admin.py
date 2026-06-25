"""Admin routes — RBAC-restricted (internal_admin / super_admin only).

Demonstrates role-gated access: a patient/doctor token is rejected with 403.
The audit-log view lets operations review access trails (metadata only).
T25 adds full user-management endpoints (list, detail, role update, deactivate,
per-user audit log).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_session, require_mfa, require_roles
from app.core.ratelimit import get_lockout
from app.models.governance import AuditLog
from app.models.user import UserRole
from app.schemas.admin import (
    DoctorAdminOut,
    DoctorCreateRequest,
    UnlockRequest,
    UserAdminOut,
    UserAuditLogOut,
    UserRoleUpdate,
)
from app.schemas.common import Message
from app.services import admin_users, audit
from app.services.doctor import create_doctor_account

router = APIRouter(prefix="/admin", tags=["admin"])

_admin_only = require_roles(UserRole.INTERNAL_ADMIN, UserRole.SUPER_ADMIN)

@router.get("/audit-logs")
def list_audit_logs(
    limit: int = Query(default=50, ge=1, le=500),
    actor: CurrentUser = Depends(_admin_only),
    _mfa: CurrentUser = Depends(require_mfa),  # admin actions require MFA
    db: Session = Depends(get_session),
) -> list[dict]:
    stmt = select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)
    rows = list(db.execute(stmt).scalars())
    audit.record(
        db,
        actor_type="admin",
        actor_id=actor.id,
        action="admin_read",
        resource_type="audit_log",
    )
    db.commit()
    return [
        {
            "id": r.id,
            "actor_type": r.actor_type,
            "actor_id": r.actor_id,
            "action": r.action,
            "resource_type": r.resource_type,
            "resource_id": r.resource_id,
            "outcome": r.outcome,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
        }
        for r in rows
    ]

@router.post("/unlock-account", response_model=Message)
def unlock_account(
    payload: UnlockRequest,
    actor: CurrentUser = Depends(_admin_only),
    _mfa: CurrentUser = Depends(require_mfa),
    db: Session = Depends(get_session),
) -> Message:
    get_lockout().reset(payload.email.lower())
    audit.record(
        db,
        actor_type="admin",
        actor_id=actor.id,
        action="admin_action",
        resource_type="account_lockout",
        resource_id=payload.email.lower(),
    )
    db.commit()
    return Message(message="account unlocked")


# ---------------------------------------------------------------------------
# T25 — User management
# ---------------------------------------------------------------------------

_super_admin_only = require_roles(UserRole.SUPER_ADMIN)


@router.get("/users", response_model=list[UserAdminOut])
def list_users(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    role: str | None = Query(default=None),
    actor: CurrentUser = Depends(_admin_only),
    _mfa: CurrentUser = Depends(require_mfa),
    db: Session = Depends(get_session),
) -> list[UserAdminOut]:
    """List all users (paginated). INTERNAL_ADMIN or SUPER_ADMIN."""
    users = admin_users.list_users(db, skip=skip, limit=limit, role_filter=role)
    audit.record(
        db,
        actor_type="admin",
        actor_id=actor.id,
        action="admin_read",
        resource_type="user_list",
    )
    db.commit()
    return users


@router.get("/users/{user_id}", response_model=UserAdminOut)
def get_user(
    user_id: str,
    actor: CurrentUser = Depends(_admin_only),
    _mfa: CurrentUser = Depends(require_mfa),
    db: Session = Depends(get_session),
) -> UserAdminOut:
    """Get user detail. INTERNAL_ADMIN or SUPER_ADMIN."""
    user = admin_users.get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    audit.record(
        db,
        actor_type="admin",
        actor_id=actor.id,
        action="admin_read",
        resource_type="user",
        resource_id=user_id,
    )
    db.commit()
    return user


@router.patch("/users/{user_id}/role", response_model=UserAdminOut)
def update_user_role(
    user_id: str,
    payload: UserRoleUpdate,
    actor: CurrentUser = Depends(_super_admin_only),
    _mfa: CurrentUser = Depends(require_mfa),
    db: Session = Depends(get_session),
) -> UserAdminOut:
    """Change a user's role. SUPER_ADMIN only."""
    try:
        user = admin_users.update_user_role(
            db, user_id=user_id, new_role=payload.role.value, requester_id=actor.id
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    audit.record(
        db,
        actor_type="admin",
        actor_id=actor.id,
        action="admin_action",
        resource_type="user_role",
        resource_id=user_id,
    )
    db.commit()
    return user


@router.delete("/users/{user_id}", response_model=UserAdminOut)
def deactivate_user(
    user_id: str,
    actor: CurrentUser = Depends(_admin_only),
    _mfa: CurrentUser = Depends(require_mfa),
    db: Session = Depends(get_session),
) -> UserAdminOut:
    """Deactivate (soft-delete) a user. Cannot deactivate self or another SUPER_ADMIN."""
    try:
        user = admin_users.deactivate_user(db, user_id=user_id, requester_id=actor.id)
    except PermissionError as exc:
        msg = str(exc)
        if "own account" in msg:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from exc
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=msg) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    audit.record(
        db,
        actor_type="admin",
        actor_id=actor.id,
        action="admin_action",
        resource_type="user_deactivate",
        resource_id=user_id,
    )
    db.commit()
    return user


@router.get("/users/{user_id}/audit-log", response_model=list[UserAuditLogOut])
def get_user_audit_log(
    user_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    actor: CurrentUser = Depends(_admin_only),
    _mfa: CurrentUser = Depends(require_mfa),
    db: Session = Depends(get_session),
) -> list[UserAuditLogOut]:
    """Get last N audit log entries for a specific user. INTERNAL_ADMIN or SUPER_ADMIN."""
    # Verify user exists first
    user = admin_users.get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    entries = admin_users.get_user_audit_log(db, user_id=user_id, limit=limit)
    audit.record(
        db,
        actor_type="admin",
        actor_id=actor.id,
        action="admin_read",
        resource_type="user_audit_log",
        resource_id=user_id,
    )
    db.commit()
    return entries


# ---------------------------------------------------------------------------
# POST /admin/doctors — SUPER_ADMIN + MFA only (AC-12, AC-13)
# ---------------------------------------------------------------------------

@router.post(
    "/doctors",
    response_model=DoctorAdminOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a doctor account (SUPER_ADMIN + MFA only)",
)
def create_doctor(
    payload: DoctorCreateRequest,
    actor: CurrentUser = Depends(_super_admin_only),
    _mfa: CurrentUser = Depends(require_mfa),
    db: Session = Depends(get_session),
) -> DoctorAdminOut:
    """Create a User(role=DOCTOR) + Doctor profile in one transaction.

    SUPER_ADMIN + MFA-verified token required. INTERNAL_ADMIN → 403.
    Audited as action=create_doctor_account at severity=warn.
    """
    user, doctor = create_doctor_account(
        db,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        specialty=payload.specialty,
        license_no=payload.license_no,
        bio=payload.bio,
        clinic_id=payload.clinic_id,
        requester_id=actor.id,
    )
    db.commit()
    return DoctorAdminOut(
        user_id=user.id,
        doctor_id=doctor.id,
        email=user.email,
        full_name=user.full_name or doctor.full_name,
        role=user.role,
        is_active=user.is_active,
        mfa_enabled=user.mfa_enabled,
    )
