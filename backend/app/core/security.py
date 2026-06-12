"""Password hashing and token helpers (foundation skeleton).

Uses the standard library only (PBKDF2-HMAC-SHA256) to avoid pulling a native
crypto dependency into the Sprint-0 foundation. Production MUST switch to Argon2
or bcrypt as required by ``docs/Technical_Architecture.md`` §4.7 — this is called
out explicitly so it is not mistaken for a production-ready implementation.

No secret is hardcoded; token signing uses the configured SECRET_KEY.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets

from .config import get_settings

_PBKDF2_ROUNDS = 240_000
_ALGO = "sha256"


def hash_password(password: str) -> str:
    """Return 'pbkdf2_sha256$rounds$salt$hash' (salt+hash base64)."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac(_ALGO, password.encode(), salt, _PBKDF2_ROUNDS)
    salt_b64 = base64.b64encode(salt).decode()
    hash_b64 = base64.b64encode(dk).decode()
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${salt_b64}${hash_b64}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, rounds_s, salt_b64, hash_b64 = encoded.split("$")
        if algo != "pbkdf2_sha256":
            return False
        rounds = int(rounds_s)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        dk = hashlib.pbkdf2_hmac(_ALGO, password.encode(), salt, rounds)
        return hmac.compare_digest(dk, expected)
    except (ValueError, TypeError):
        return False


# --------------------------------------------------------------------------- #
# Minimal signed token (HMAC). NOT a full JWT — P1 replaces with proper JWT lib
# (access + refresh + MFA per Technical_Architecture.md §4.7).
# --------------------------------------------------------------------------- #

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def sign_token(payload: dict) -> str:
    settings = get_settings()
    body = _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    sig = hmac.new(settings.secret_key.encode(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64url(sig)}"


def verify_token(token: str) -> dict | None:
    settings = get_settings()
    try:
        body, sig_part = token.split(".")
        expected = hmac.new(settings.secret_key.encode(), body.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64url(expected), sig_part):
            return None
        padded = body + "=" * (-len(body) % 4)
        return json.loads(base64.urlsafe_b64decode(padded))
    except (ValueError, TypeError):
        return None
