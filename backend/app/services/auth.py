"""Auth service — register, authenticate, mint tokens.

No PHI here; operates on User accounts. Passwords are Argon2-hashed; tokens are
short-lived JWTs carrying the user id (sub) and role for RBAC.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.models.patient import PatientProfile
from app.models.user import User, UserRole
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


def issue_token(user: User) -> str:
    return create_access_token(subject=user.id, role=user.role.value)
