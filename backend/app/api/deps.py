"""API dependencies.

Foundation auth is a stand-in: the requester identity comes from the
``X-User-Id`` header. P1 replaces this with JWT verification + RBAC per
Technical_Architecture.md §4.7. The DB session dependency is the real one.
"""

from __future__ import annotations

from fastapi import Header, HTTPException, status

from app.core.database import get_session  # re-exported for routes

__all__ = ["get_session", "current_user_id"]


def current_user_id(x_user_id: str | None = Header(default=None)) -> str:
    """Return the requesting user's id from the X-User-Id header.

    NOTE: placeholder authentication for the Sprint-0 foundation only.
    """
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-User-Id (foundation auth placeholder).",
        )
    return x_user_id
