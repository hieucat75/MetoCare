"""Local-disk Object Storage adapter (dev / CI / current staging).

Objects are stored under ``settings.storage_local_dir``. Signed URLs point back at
the backend's own blob endpoint carrying an HMAC token (``signing.py``); the URL is
**relative** to the API host, so any client resolves it against its configured base
URL (mobile) or test base (TestClient). The Azure adapter returns absolute SAS URLs
instead — callers treat ``SignedUrl.url`` opaquely.
"""

from __future__ import annotations

import os
import shutil
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings

from .base import ObjectNotFound, SignedUrl, StorageBackend, StorageError
from .signing import BLOB_OP_GET, BLOB_OP_PUT, derive_blob_secret, sign_blob_token

# Relative route the local blob endpoint is mounted at (see routes/documents.py).
_BLOB_ROUTE = "/api/v1/documents/blob"


class LocalDiskStorage(StorageBackend):
    """Filesystem-backed storage with self-hosted signed-URL blob access."""

    def __init__(self, root_dir: str, secret: str) -> None:
        self._root = os.path.abspath(root_dir)
        self._secret = secret
        os.makedirs(self._root, exist_ok=True)

    # ── path safety ────────────────────────────────────────────────────────
    def _path(self, key: str) -> str:
        # Server-generated keys are trusted, but defend against traversal anyway.
        if not key or key.startswith("/") or ".." in key.split("/"):
            raise StorageError(f"unsafe storage key: {key!r}")
        full = os.path.abspath(os.path.join(self._root, key))
        if full != self._root and not full.startswith(self._root + os.sep):
            raise StorageError(f"storage key escapes root: {key!r}")
        return full

    # ── signed URLs ──────────────────────────────────────────────────────────
    def _signed(self, key: str, *, op: str, method: str, expires_in: int) -> SignedUrl:
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        token = sign_blob_token(
            self._secret, key=key, op=op, expires_at=int(expires_at.timestamp())
        )
        return SignedUrl(
            url=f"{_BLOB_ROUTE}/{token}", key=key, method=method, expires_at=expires_at
        )

    def signed_put_url(self, key: str, *, expires_in: int) -> SignedUrl:
        return self._signed(key, op=BLOB_OP_PUT, method="PUT", expires_in=expires_in)

    def signed_get_url(self, key: str, *, expires_in: int) -> SignedUrl:
        return self._signed(key, op=BLOB_OP_GET, method="GET", expires_in=expires_in)

    # ── byte I/O ─────────────────────────────────────────────────────────────
    def put_bytes(self, key: str, data: bytes) -> None:
        path = self._path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # atomic-ish write via temp + rename
        tmp = f"{path}.tmp"
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)

    def get_bytes(self, key: str) -> bytes:
        path = self._path(key)
        try:
            with open(path, "rb") as fh:
                return fh.read()
        except FileNotFoundError as exc:
            raise ObjectNotFound(f"no object at {key!r}") from exc

    def exists(self, key: str) -> bool:
        return os.path.isfile(self._path(key))

    def size(self, key: str) -> int:
        try:
            return os.path.getsize(self._path(key))
        except FileNotFoundError as exc:
            raise ObjectNotFound(f"no object at {key!r}") from exc

    def move(self, src_key: str, dst_key: str) -> None:
        src = self._path(src_key)
        dst = self._path(dst_key)
        if not os.path.isfile(src):
            raise ObjectNotFound(f"no object at {src_key!r}")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)

    def delete(self, key: str) -> None:
        try:
            os.remove(self._path(key))
        except FileNotFoundError:
            pass  # delete is idempotent


def build_local_storage() -> LocalDiskStorage:
    settings = get_settings()
    return LocalDiskStorage(
        settings.storage_local_dir, derive_blob_secret(settings.secret_key)
    )
