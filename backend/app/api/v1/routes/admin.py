"""Admin routes — RBAC-restricted (internal_admin / super_admin only).

Demonstrates role-gated access: a patient/doctor token is rejected with 403.
The audit-log view lets operations review access trails (metadata only).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_session, require_mfa, require_roles
from app.core.ratelimit import get_lockout
from app.models.governance import AuditLog
from app.models.user import UserRole
from app.schemas.common import Message
from app.services import audit

router = APIRouter(prefix="/admin", tags=["admin"])

_admin_only = require_roles(UserRole.INTERNAL_ADMIN, UserRole.SUPER_ADMIN)


class UnlockRequest(BaseModel):
    email: str


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
