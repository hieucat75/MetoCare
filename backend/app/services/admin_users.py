"""Admin user management service (T25).

Provides helpers for listing, retrieving, updating role, deactivating users,
and reading per-user audit logs. Used exclusively by admin-only routes.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.governance import AuditLog
from app.models.user import User, UserRole


def list_users(
    db: Session,
    skip: int = 0,
    limit: int = 50,
    role_filter: str | None = None,
) -> list[User]:
    """Return a paginated list of all users, optionally filtered by role."""
    stmt = select(User).order_by(User.created_at.desc()).offset(skip).limit(limit)
    if role_filter is not None:
        stmt = stmt.where(User.role == role_filter)
    return list(db.execute(stmt).scalars())


def get_user(db: Session, user_id: str) -> User | None:
    """Return a single user by id, or None if not found."""
    return db.get(User, user_id)


def update_user_role(
    db: Session,
    user_id: str,
    new_role: str,
    requester_id: str,
) -> User:
    """Change a user's role.  Caller must already have verified SUPER_ADMIN access.

    Raises:
        ValueError: if the target user does not exist.
    """
    user = db.get(User, user_id)
    if user is None:
        raise ValueError(f"User {user_id} not found")
    user.role = UserRole(new_role)
    db.flush()
    return user


def deactivate_user(
    db: Session,
    user_id: str,
    requester_id: str,
) -> User:
    """Set is_active=False for the given user.

    Raises:
        ValueError: if the target user does not exist, or requester tries to
                    deactivate themselves (400-equivalent), or tries to
                    deactivate a SUPER_ADMIN (403-equivalent).
    """
    if user_id == requester_id:
        raise PermissionError("Cannot deactivate your own account")

    user = db.get(User, user_id)
    if user is None:
        raise ValueError(f"User {user_id} not found")

    if user.role == UserRole.SUPER_ADMIN:
        raise PermissionError("Cannot deactivate a SUPER_ADMIN account")

    user.is_active = False
    db.flush()
    return user


def activate_user(db: Session, user_id: str) -> User:
    """Set is_active=True for the given user (re-activation has no role guards).

    Raises:
        ValueError: if the target user does not exist.
    """
    user = db.get(User, user_id)
    if user is None:
        raise ValueError(f"User {user_id} not found")
    user.is_active = True
    db.flush()
    return user


def get_user_audit_log(
    db: Session,
    user_id: str,
    limit: int = 20,
) -> list[AuditLog]:
    """Return the most recent *limit* AuditLog entries where actor_id=user_id."""
    stmt = (
        select(AuditLog)
        .where(AuditLog.actor_id == user_id)
        .order_by(AuditLog.timestamp.desc())
        .limit(limit)
    )
    return list(db.execute(stmt).scalars())
