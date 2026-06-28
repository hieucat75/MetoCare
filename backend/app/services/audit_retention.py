"""Audit-log retention purge (Data_Model_Overview §4.4, Security framework).

AuditLog is append-only during normal operation; retention is a lifecycle policy
(not content mutation). Each action maps to a category with its own TTL; rows
older than the category TTL are purged. Designed to be run by a scheduled job.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.config import get_settings
from app.models.governance import AuditLog

# Map an audit action to a retention category.
_AUTH_ACTIONS = {"login", "logout", "register", "refresh", "token_revoke", "mfa_enroll"}
_ADMIN_ACTIONS = {"admin_read", "admin_action", "config_change", "role_change"}


def category_for(action: str) -> str:
    if action in _AUTH_ACTIONS:
        return "auth"
    if action in _ADMIN_ACTIONS:
        return "admin"
    # create/read/read_trend/interpret/upload/grant_consent/revoke_consent...
    return "data_access"


def _ttl_days() -> dict[str, int]:
    s = get_settings()
    return {
        "auth": s.audit_retention_auth_days,
        "data_access": s.audit_retention_data_access_days,
        "admin": s.audit_retention_admin_days,
        "default": s.audit_retention_default_days,
    }


def purge_expired(db: Session, *, now: dt.datetime | None = None) -> dict[str, int]:
    """Delete audit rows past their category TTL. Returns counts per category."""
    now = now or utcnow()
    ttl = _ttl_days()
    deleted: dict[str, int] = {}

    for category in ("auth", "data_access", "admin"):
        cutoff = now - dt.timedelta(days=ttl[category])
        actions: set[str]
        if category == "auth":
            actions = _AUTH_ACTIONS
        elif category == "admin":
            actions = _ADMIN_ACTIONS
        else:
            # data_access = everything not classified as auth/admin.
            stmt = delete(AuditLog).where(
                AuditLog.timestamp < cutoff,
                AuditLog.action.notin_(_AUTH_ACTIONS | _ADMIN_ACTIONS),
            )
            res = db.execute(stmt)
            deleted[category] = res.rowcount or 0
            continue

        stmt = delete(AuditLog).where(AuditLog.timestamp < cutoff, AuditLog.action.in_(actions))
        res = db.execute(stmt)
        deleted[category] = res.rowcount or 0

    db.commit()
    return deleted
