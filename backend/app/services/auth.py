"""Auth service — register, authenticate, mint tokens.

No PHI here; operates on User accounts. Passwords are Argon2-hashed; tokens are
short-lived JWTs carrying the user id (sub) and role for RBAC.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import as_naive_utc, utcnow
from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.auth_tokens import RefreshToken
from app.models.patient import PatientProfile
from app.models.user import MFA_REQUIRED_ROLES, User, UserRole
from app.services import audit


class AuthError(Exception):
    """Authentication / registration failure."""


def register(
    db: Session,
    *,
    email: str,
    password: str,
    full_name: str | None = None,
    role: UserRole = UserRole.PATIENT,
) -> User:
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing is not None:
        raise AuthError("email already registered")

    user = User(
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
        role=role,
    )
    db.add(user)
    db.flush()

    # Every patient account gets a PatientProfile so health data has an owner.
    if role == UserRole.PATIENT:
        db.add(PatientProfile(user_id=user.id, full_name=full_name))

    audit.record(
        db,
        actor_type="user",
        actor_id=user.id,
        action="register",
        resource_type="user",
        resource_id=user.id,
    )
    db.commit()
    return user


def authenticate(db: Session, *, email: str, password: str) -> User:
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        raise AuthError("invalid email or password")
    if not user.is_active:
        raise AuthError("account is disabled")
    audit.record(
        db,
        actor_type="user",
        actor_id=user.id,
        action="login",
        resource_type="user",
        resource_id=user.id,
    )
    db.commit()
    return user


def issue_tokens(db: Session, user: User, *, mfa: bool = False) -> tuple[str, str]:
    """Issue an access token + a persisted, revocable refresh token."""
    enrollment_required = user.role in MFA_REQUIRED_ROLES and not user.mfa_enabled
    access = create_access_token(
        subject=user.id,
        role=user.role.value,
        mfa=mfa,
        mfa_enrollment_required=enrollment_required,
    )
    jti = uuid.uuid4().hex
    ttl = get_settings().refresh_token_ttl_minutes
    db.add(
        RefreshToken(
            user_id=user.id,
            jti=jti,
            expires_at=utcnow() + dt.timedelta(minutes=ttl),
            mfa=mfa,
        )
    )
    db.commit()
    refresh = create_refresh_token(subject=user.id, jti=jti)
    return access, refresh


def refresh_session(db: Session, refresh_token: str) -> tuple[str, str, User]:
    """Validate + rotate a refresh token. Old token is revoked (single use)."""
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh" or not payload.get("jti"):
        raise AuthError("invalid refresh token")
    rt = db.execute(
        select(RefreshToken).where(RefreshToken.jti == payload["jti"])
    ).scalar_one_or_none()
    if rt is None or rt.revoked_at is not None:
        raise AuthError("refresh token revoked")
    if as_naive_utc(rt.expires_at) < utcnow():
        raise AuthError("refresh token expired")
    user = db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise AuthError("user not found")

    rt.revoked_at = utcnow()  # rotation: invalidate the used token
    db.flush()
    audit.record(
        db,
        actor_type="user",
        actor_id=user.id,
        action="refresh",
        resource_type="refresh_token",
        resource_id=rt.id,
    )
    db.commit()
    access, new_refresh = issue_tokens(db, user, mfa=rt.mfa)
    return access, new_refresh, user


def revoke_refresh(db: Session, refresh_token: str, *, actor_id: str | None = None) -> bool:
    payload = decode_token(refresh_token)
    if not payload or not payload.get("jti"):
        return False
    rt = db.execute(
        select(RefreshToken).where(RefreshToken.jti == payload["jti"])
    ).scalar_one_or_none()
    if rt is None or rt.revoked_at is not None:
        return False
    rt.revoked_at = utcnow()
    db.flush()
    audit.record(
        db,
        actor_type="user",
        actor_id=actor_id or rt.user_id,
        action="logout",
        resource_type="refresh_token",
        resource_id=rt.id,
    )
    db.commit()
    return True
