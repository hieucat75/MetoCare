"""Admin routes — RBAC-restricted (internal_admin / super_admin only).

Demonstrates role-gated access: a patient/doctor token is rejected with 403.
The audit-log view lets operations review access trails (metadata only).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_session, require_roles
from app.models.governance import AuditLog
from app.models.user import UserRole

router = APIRouter(prefix="/admin", tags=["admin"])

_admin_only = require_roles(UserRole.INTERNAL_ADMIN, UserRole.SUPER_ADMIN)


@router.get("/audit-logs")
def list_audit_logs(
    limit: int = Query(default=50, ge=1, le=500),
    _: CurrentUser = Depends(_admin_only),
    db: Session = Depends(get_session),
) -> list[dict]:
    stmt = select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)
    rows = db.execute(stmt).scalars()
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
