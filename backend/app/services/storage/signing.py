"""HMAC-signed blob-access tokens for the local Object Storage adapter.

The local-disk adapter issues *signed URLs* that point back at the backend's own
blob endpoint (``/api/v1/documents/blob/{token}``). The token is the only
authorization for that endpoint — mirroring how an Azure SAS URL carries its own
signature — so the endpoint itself is unauthenticated but verifies the token.

Design constraints (Master Plan §1.7):
- write-only tokens (``op=put``) can never be used to read (``op=get``) and vice-versa;
- tokens are single-object (bound to one storage key);
- tokens are short-lived (an absolute expiry, checked on every use);
- the signature covers key + op + expiry, so none can be tampered with.
"""

from __future__ import annotations

import base64
import hmac
import json
import time
from dataclasses import dataclass
from hashlib import sha256

# Blob operations a token may authorize. A token is valid for exactly one.
BLOB_OP_PUT = "put"
BLOB_OP_GET = "get"


class BlobTokenError(Exception):
    """Raised when a blob token is malformed, tampered with, or expired."""


@dataclass(frozen=True)
class BlobToken:
    """Decoded, verified blob token payload."""

    key: str
    op: str
    expires_at: int  # unix seconds


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def derive_blob_secret(app_secret: str) -> str:
    """Derive a blob-token signing key distinct from the app/JWT secret.

    Key separation (defense-in-depth): a blob token and a JWT must never share a
    signing key, even though their message spaces differ. Deterministic so the
    signer (storage adapter) and verifier (blob route) agree without extra config.
    """
    return hmac.new(app_secret.encode("utf-8"), b"mdi-blob-token-v1", sha256).hexdigest()


def _sign(secret: str, payload: bytes) -> str:
    mac = hmac.new(secret.encode("utf-8"), payload, sha256).digest()
    return _b64url_encode(mac)


def sign_blob_token(secret: str, *, key: str, op: str, expires_at: int) -> str:
    """Return a signed ``<payload>.<signature>`` token for one blob operation."""
    if op not in (BLOB_OP_PUT, BLOB_OP_GET):
        raise ValueError(f"invalid blob op: {op!r}")
    body = {"k": key, "o": op, "e": int(expires_at)}
    payload = _b64url_encode(json.dumps(body, separators=(",", ":")).encode("utf-8"))
    signature = _sign(secret, payload.encode("ascii"))
    return f"{payload}.{signature}"


def verify_blob_token(secret: str, token: str, *, now: int | None = None) -> BlobToken:
    """Verify signature + expiry and return the decoded token, or raise BlobTokenError."""
    try:
        payload, signature = token.split(".", 1)
    except ValueError as exc:
        raise BlobTokenError("malformed token") from exc

    expected = _sign(secret, payload.encode("ascii"))
    # constant-time comparison to avoid signature-timing oracles
    if not hmac.compare_digest(expected, signature):
        raise BlobTokenError("bad signature")

    try:
        body = json.loads(_b64url_decode(payload))
        key = str(body["k"])
        op = str(body["o"])
        expires_at = int(body["e"])
    except (ValueError, KeyError, TypeError) as exc:
        raise BlobTokenError("corrupt payload") from exc

    if op not in (BLOB_OP_PUT, BLOB_OP_GET):
        raise BlobTokenError("invalid op")

    current = int(time.time()) if now is None else now
    if current >= expires_at:
        raise BlobTokenError("token expired")

    return BlobToken(key=key, op=op, expires_at=expires_at)
