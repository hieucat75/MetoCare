"""Password hashing (Argon2) and JWT access tokens.

- Passwords: Argon2id via argon2-cffi (Technical_Architecture.md §4.7).
- Tokens: signed JWT (HS256) with subject, role and expiry. No secret is
  hardcoded; signing uses the configured SECRET_KEY (inject via secret manager
  in production). Asymmetric keys (RS256) are a later option for multi-service.
"""

from __future__ import annotations

import datetime as dt

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from .config import get_settings

_hasher = PasswordHasher()
_ALGO = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return _hasher.verify(encoded, password)
    except (VerifyMismatchError, ValueError, TypeError):
        return False


def needs_rehash(encoded: str) -> bool:
    """True if the stored hash should be upgraded (cost params changed)."""
    try:
        return _hasher.check_needs_rehash(encoded)
    except (ValueError, TypeError):
        return False


def create_access_token(
    *,
    subject: str,
    role: str,
    mfa: bool = False,
    expires_minutes: int | None = None,
    extra: dict | None = None,
) -> str:
    settings = get_settings()
    ttl = expires_minutes or settings.access_token_ttl_minutes
    now = dt.datetime.now(dt.UTC)
    payload = {
        "sub": subject,
        "role": role,
        "mfa": mfa,  # True iff the session was MFA-verified at login
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(minutes=ttl)).timestamp()),
        "type": "access",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGO)


def create_refresh_token(*, subject: str, jti: str, expires_minutes: int | None = None) -> str:
    settings = get_settings()
    ttl = expires_minutes or settings.refresh_token_ttl_minutes
    now = dt.datetime.now(dt.UTC)
    payload = {
        "sub": subject,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(minutes=ttl)).timestamp()),
        "type": "refresh",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGO)


def decode_token(token: str) -> dict | None:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[_ALGO])
    except jwt.PyJWTError:
        return None
