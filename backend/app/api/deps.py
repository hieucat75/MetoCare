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

from app.core.config import get_settings
from app.core.database import get_session  # re-exported for routes
from app.core.ratelimit import get_rate_limiter
from app.core.security import decode_token
from app.models.user import UserRole

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


def current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
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
    # Record the opaque user id for access-log correlation (not PHI).
    request.state.user_id = payload["sub"]
    return CurrentUser(
        id=payload["sub"], role=payload.get("role", ""), mfa=bool(payload.get("mfa", False))
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
    """Require the session to have been MFA-verified (token claim mfa=true)."""
    if not user.mfa:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="MFA verification required for this resource.",
        )
    return user
