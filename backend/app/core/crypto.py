"""Field-level encryption for PHI at rest (Data_Model_Overview §4.3,
Security_Compliance_Framework).

Symmetric encryption via Fernet (AES-128-CBC + HMAC). Keys come from settings
(`MCP_ENCRYPTION_KEYS`, comma-separated) — never hardcoded for production. The
first key encrypts; all keys can decrypt, which enables zero-downtime key
rotation (add a new key at the front, re-encrypt, then drop the old one).

`EncryptedString` is a SQLAlchemy TypeDecorator: declare a column with it and
plaintext is transparently encrypted on write and decrypted on read. Ciphertext
is base64 text, so the underlying column is TEXT (variable length).

Note: Fernet is non-deterministic (random IV), so encrypted columns cannot be
queried by value or indexed for equality. Keep lookup keys (e.g. email) plaintext
or use a separate blind index (future work).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from .config import get_settings

logger = logging.getLogger(__name__)

# Fernet tokens are URL-safe base64 whose first byte is the version marker 0x80,
# which always serializes to the "gAAAA" prefix. Real names/emails never match.
_FERNET_TOKEN_RE = re.compile(r"^gAAAA[A-Za-z0-9_-]+={0,2}$")

# Safety bound when unwrapping values that were encrypted more than once
# (e.g. a foreign-key ciphertext later re-encrypted by the PHI migration job).
_MAX_DECRYPT_DEPTH = 3


class EncryptionConfigError(RuntimeError):
    """Raised when no usable encryption key is configured."""


@lru_cache
def _cipher() -> MultiFernet:
    settings = get_settings()
    raw = (settings.encryption_keys or "").strip()
    if not raw:
        raise EncryptionConfigError("MCP_ENCRYPTION_KEYS is not set; cannot encrypt PHI fields.")
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    try:
        return MultiFernet([Fernet(k.encode()) for k in keys])
    except (ValueError, TypeError) as exc:  # malformed key
        raise EncryptionConfigError(f"Invalid MCP_ENCRYPTION_KEYS: {exc}") from exc


def encrypt(plaintext: str) -> str:
    return _cipher().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    return _cipher().decrypt(token.encode()).decode()


def try_decrypt(token: str) -> str | None:
    """Decrypt, returning None if the value is not valid ciphertext."""
    try:
        return decrypt(token)
    except (InvalidToken, ValueError, TypeError):
        return None


def is_fernet_token(value: str | None) -> bool:
    """True if the value is shaped like a Fernet token (decryptable or not).

    Used to tell "legacy plaintext" apart from "ciphertext we cannot decrypt"
    (unknown key). Plaintext PHI (names, emails, notes) never matches the
    gAAAA-prefixed base64 shape.
    """
    return bool(value) and len(value) >= 60 and _FERNET_TOKEN_RE.fullmatch(value) is not None


def rotate(token: str) -> str:
    """Re-encrypt a token with the primary key (for key-rotation jobs)."""
    return _cipher().rotate(token.encode()).decode()


def blind_index(value: str) -> str:
    """Deterministic, keyed hash for equality lookups on encrypted PHI.

    HMAC-SHA256 keyed by SECRET_KEY. Lets a column (e.g. email) be encrypted at
    rest yet still be searchable by exact match via a side index column, without
    exposing plaintext. Normalizes case/whitespace so lookups are stable.

    NOTE: building block only — wiring a `*_bidx` column into the User model
    (and migration) is deferred; see P2_HARDENING_SELF_REVIEW.md.
    """
    normalized = (value or "").strip().lower().encode()
    key = get_settings().secret_key.encode()
    return hmac.new(key, normalized, hashlib.sha256).hexdigest()


class EncryptedString(TypeDecorator):
    """TEXT column whose Python value is plaintext but storage is ciphertext."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return encrypt(str(value))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        # Unwrap nested encryption: a row written with ciphertext already in it
        # (e.g. re-encrypted by the PHI migration job) decrypts back to a token,
        # so keep decrypting until we reach a non-token value.
        current = value
        for _ in range(_MAX_DECRYPT_DEPTH):
            decrypted = try_decrypt(current)
            if decrypted is None:
                break
            current = decrypted
            if not is_fernet_token(current):
                return current
        if is_fernet_token(current):
            # Undecryptable ciphertext (unknown key). Never surface raw tokens
            # to callers/UI — treat the value as unavailable.
            logger.warning("EncryptedString: undecryptable ciphertext; returning None")
            return None
        # Tolerate legacy plaintext rows (pre-encryption) by returning as-is.
        return current
