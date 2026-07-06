"""Admin routes — RBAC-restricted (internal_admin / super_admin only).

Demonstrates role-gated access: a patient/doctor token is rejected with 403.
The audit-log view lets operations review access trails (metadata only).
T25 adds full user-management endpoints (list, detail, role update, deactivate,
per-user audit log).
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_session, require_mfa, require_roles
from app.core.ratelimit import get_lockout
from app.models.ai import AIClinicalRecommendation, AISession, RecommendationStatus
from app.models.care import Clinic
from app.models.governance import AuditLog
from app.models.meto import MetoAuditLog
from app.models.user import User, UserRole
from app.schemas.admin import (
    AdminStatsOut,
    DoctorAdminOut,
    DoctorCreateRequest,
    UnlockRequest,
    UserAdminOut,
    UserAuditLogOut,
    UserRoleUpdate,
    UserStatusUpdate,
)
from app.schemas.common import Message
from app.schemas.doctor import DoctorVerificationOut
from app.services import admin_users, audit, doctor_verification
from app.services.doctor import create_doctor_account

router = APIRouter(prefix="/admin", tags=["admin"])

_admin_only = require_roles(UserRole.INTERNAL_ADMIN, UserRole.SUPER_ADMIN)


@router.get("/stats", response_model=AdminStatsOut)
def get_system_stats(
    actor: CurrentUser = Depends(_admin_only),
    _mfa: CurrentUser = Depends(require_mfa),  # admin actions require MFA
    db: Session = Depends(get_session),
) -> AdminStatsOut:
    """Platform-wide counts for the admin dashboard.

    Real data (0 means genuinely empty). Each count is isolated in its own
    try/except so a single failing query never 500s the whole endpoint.
    """
    today_start = dt.datetime.now(dt.UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    def _count(stmt) -> int:
        try:
            return int(db.execute(stmt).scalar_one() or 0)
        except Exception:
            db.rollback()  # clear failed-transaction state so later counts run
            return 0

    stats = AdminStatsOut(
        total_users=_count(select(func.count()).select_from(User)),
        active_patients=_count(
            select(func.count())
            .select_from(User)
            .where(User.role == UserRole.PATIENT, User.is_active.is_(True))
        ),
        active_doctors=_count(
            select(func.count())
            .select_from(User)
            .where(User.role == UserRole.DOCTOR, User.is_active.is_(True))
        ),
        total_clinics=_count(select(func.count()).select_from(Clinic)),
        ai_sessions_today=_count(
            select(func.count())
            .select_from(AISession)
            .where(AISession.created_at >= today_start)
        ),
        pending_reviews=_count(
            select(func.count())
            .select_from(AIClinicalRecommendation)
            .where(AIClinicalRecommendation.status == RecommendationStatus.PENDING_REVIEW)
        ),
        flagged_ai_sessions=_count(
            select(func.count())
            .select_from(MetoAuditLog)
            .where(MetoAuditLog.safety_flags_detected.is_(True))
        ),
        audit_events_today=_count(
            select(func.count()).select_from(AuditLog).where(AuditLog.timestamp >= today_start)
        ),
    )
    audit.record(
        db,
        actor_type="admin",
        actor_id=actor.id,
        action="admin_read",
        resource_type="system_stats",
    )
    db.commit()
    return stats


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


@router.patch("/users/{user_id}", response_model=UserAdminOut)
def update_user_status(
    user_id: str,
    payload: UserStatusUpdate,
    actor: CurrentUser = Depends(_admin_only),
    _mfa: CurrentUser = Depends(require_mfa),
    db: Session = Depends(get_session),
) -> UserAdminOut:
    """Activate or deactivate a user. Deactivation keeps the self/SUPER_ADMIN guards."""
    try:
        if payload.is_active:
            user = admin_users.activate_user(db, user_id=user_id)
        else:
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
        resource_type="user_status",
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
# POST /admin/doctors — INTERNAL_ADMIN / SUPER_ADMIN + MFA (sales onboarding)
# ---------------------------------------------------------------------------


@router.post(
    "/doctors",
    response_model=DoctorAdminOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a doctor account (admin + MFA)",
)
def create_doctor(
    payload: DoctorCreateRequest,
    actor: CurrentUser = Depends(_admin_only),
    _mfa: CurrentUser = Depends(require_mfa),
    db: Session = Depends(get_session),
) -> DoctorAdminOut:
    """Create a User(role=DOCTOR) + Doctor profile in one transaction.

    INTERNAL_ADMIN or SUPER_ADMIN with an MFA-verified token required, so the
    sales/ops team can onboard doctors. Doctor/patient tokens → 403.
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


# ---------------------------------------------------------------------------
# T10 — Doctor verification queue (INTERNAL_ADMIN / SUPER_ADMIN + MFA)
# ---------------------------------------------------------------------------


@router.get(
    "/doctors",
    response_model=list[DoctorVerificationOut],
    summary="List doctors, optionally filtered by verification status",
)
def list_doctors_for_verification(
    status_filter: str | None = Query(default=None, alias="status"),
    actor: CurrentUser = Depends(_admin_only),
    _mfa: CurrentUser = Depends(require_mfa),
    db: Session = Depends(get_session),
) -> list[DoctorVerificationOut]:
    doctors = doctor_verification.list_by_status(db, status_filter)
    audit.record(
        db,
        actor_type="admin",
        actor_id=actor.id,
        action="admin_read",
        resource_type="doctor_verification_queue",
    )
    db.commit()
    return [DoctorVerificationOut.model_validate(d) for d in doctors]


@router.post(
    "/doctors/{doctor_id}/verify",
    response_model=DoctorVerificationOut,
    summary="Approve a doctor → VERIFIED",
)
def verify_doctor(
    doctor_id: str,
    actor: CurrentUser = Depends(_admin_only),
    _mfa: CurrentUser = Depends(require_mfa),
    db: Session = Depends(get_session),
) -> DoctorVerificationOut:
    doctor = doctor_verification.approve(db, doctor_id, actor_id=actor.id)
    return DoctorVerificationOut.model_validate(doctor)


@router.post(
    "/doctors/{doctor_id}/reject",
    response_model=DoctorVerificationOut,
    summary="Reject a doctor → REJECTED",
)
def reject_doctor(
    doctor_id: str,
    actor: CurrentUser = Depends(_admin_only),
    _mfa: CurrentUser = Depends(require_mfa),
    db: Session = Depends(get_session),
) -> DoctorVerificationOut:
    doctor = doctor_verification.reject(db, doctor_id, actor_id=actor.id)
    return DoctorVerificationOut.model_validate(doctor)


@router.post(
    "/doctors/{doctor_id}/suspend",
    response_model=DoctorVerificationOut,
    summary="Suspend a doctor → SUSPENDED",
)
def suspend_doctor(
    doctor_id: str,
    actor: CurrentUser = Depends(_admin_only),
    _mfa: CurrentUser = Depends(require_mfa),
    db: Session = Depends(get_session),
) -> DoctorVerificationOut:
    doctor = doctor_verification.suspend(db, doctor_id, actor_id=actor.id)
    return DoctorVerificationOut.model_validate(doctor)
