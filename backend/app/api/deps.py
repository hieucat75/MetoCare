"""API dependencies: JWT authentication + RBAC (Technical_Architecture.md §4.7).

A valid ``Authorization: Bearer <jwt>`` is required for protected endpoints. The
token carries the user id (sub) and role. ``require_roles`` enforces role-based
access, denying by default.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_session  # re-exported for routes
from app.core.ratelimit import get_rate_limiter
from app.core.security import decode_token
from app.models.user import User, UserRole

__all__ = [
    "get_session",
    "current_user",
    "current_user_id",
    "require_roles",
    "require_mfa",
    "enforce_rate_limit",
    "CurrentUser",
]


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(request: Request, action: str) -> None:
    """Token-bucket rate limit per (action, client). Raises 429 when exceeded."""
    settings = get_settings()
    if not settings.ratelimit_enabled:
        return
    capacity = settings.ratelimit_auth_capacity
    window = settings.ratelimit_auth_window_seconds
    refill = capacity / window if window else capacity
    key = f"{action}:{_client_key(request)}"
    if not get_rate_limiter().allow(key, capacity=capacity, refill_per_sec=refill):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests; please slow down.",
            headers={"Retry-After": str(window)},
        )


_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    id: str
    role: str
    mfa: bool = False
    mfa_enrollment_required: bool = False


def current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_session),
) -> CurrentUser:
    if creds is None or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(creds.credentials)
    if payload is None or payload.get("type") != "access" or not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # SEC-F2: re-check the account is still active on every request. A JWT is a
    # bearer credential valid until its (short) expiry; without this an admin
    # "block"/"suspend" or the patient's own account deletion would not take
    # effect against an already-issued access token until it expired. Both of
    # those set User.is_active=False on the (still-present) row, so we reject
    # when the row exists AND is explicitly deactivated. We select only the
    # boolean column (indexed PK lookup, no PHI loaded) and return the SAME
    # generic 401 as an invalid token, so a disabled/deleted account is
    # indistinguishable from a bad token (no account-state enumeration).
    # A missing row is left to the RBAC layer (tokens are only ever minted for a
    # persisted user; there is no hard-delete path in the system).
    user_id = payload["sub"]
    is_active = db.execute(
        select(User.is_active).where(User.id == user_id)
    ).scalar_one_or_none()
    if is_active is False:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Record the opaque user id for access-log correlation (not PHI).
    request.state.user_id = user_id
    return CurrentUser(
        id=user_id,
        role=payload.get("role", ""),
        mfa=bool(payload.get("mfa", False)),
        mfa_enrollment_required=bool(payload.get("mfa_enrollment_required", False)),
    )


def current_user_id(user: CurrentUser = Depends(current_user)) -> str:
    return user.id


def require_roles(*roles: UserRole) -> Callable[[CurrentUser], CurrentUser]:
    """Dependency factory: allow only the given roles (deny by default)."""
    allowed = {r.value for r in roles}

    def _checker(user: CurrentUser = Depends(current_user)) -> CurrentUser:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' is not permitted for this resource.",
            )
        return user

    return _checker


def require_mfa(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    """Require the session to have been MFA-verified (token claim mfa=true).

    No-op while MFA enforcement is disabled (Settings.mfa_enforcement_enabled,
    default false — temporary relaxed policy for the build/test phase). The
    gate stays wired on every sensitive endpoint so setting
    MCP_MFA_ENFORCEMENT_ENABLED=true restores the mandatory-MFA policy.
    """
    if not get_settings().mfa_enforcement_enabled:
        return user
    if not user.mfa:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="MFA verification required for this resource.",
        )
    return user
