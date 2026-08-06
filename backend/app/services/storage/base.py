"""Object Storage abstraction (Master Plan §1.1 / §1.7).

A thin ``StorageBackend`` interface with adapters:
- ``LocalDiskStorage`` (dev / CI / current staging) — see ``local.py``
- ``AzureBlobStorage`` (Distribution-RC) — see ``azure_blob.py``

The backend never lets a client choose a storage key. Keys are server-generated
and namespaced by ``container`` (``quarantine`` vs ``accepted``) and owning
``patient_id`` so a signed URL can never be pointed at another patient's object.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime

# Storage containers (key prefixes). A freshly uploaded object lands in
# ``quarantine`` and is only ever copied to ``accepted`` after validation+scan.
CONTAINER_QUARANTINE = "quarantine"
CONTAINER_ACCEPTED = "accepted"
_CONTAINERS = frozenset({CONTAINER_QUARANTINE, CONTAINER_ACCEPTED})

# Extension whitelist mirrors the magic-byte MIME whitelist (JPEG/PNG/PDF).
_EXT_BY_MIME = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "application/pdf": "pdf",
}


class StorageError(Exception):
    """Raised for storage backend failures (missing object, misconfiguration…)."""


class ObjectNotFound(StorageError):
    """Raised when a requested storage key does not exist."""


@dataclass(frozen=True)
class SignedUrl:
    """A short-lived, single-object, single-operation signed URL."""

    url: str
    key: str
    method: str  # "PUT" | "GET"
    expires_at: datetime


def ext_for_mime(mime: str) -> str:
    """Map a validated MIME type to a file extension, defaulting to ``bin``."""
    return _EXT_BY_MIME.get(mime, "bin")


def build_object_key(*, container: str, patient_id: str, ext: str) -> str:
    """Generate a server-side storage key: ``<container>/<patient>/<yyyymm>/<uuid>.<ext>``.

    The key embeds the owning patient so ownership can be re-derived, and a random
    UUID so it is unguessable. Clients never supply keys.
    """
    if container not in _CONTAINERS:
        raise ValueError(f"invalid storage container: {container!r}")
    now = datetime.now(UTC)
    return f"{container}/{patient_id}/{now:%Y%m}/{uuid.uuid4().hex}.{ext}"


def container_of(key: str) -> str:
    """Return the container prefix of a storage key."""
    return key.split("/", 1)[0]


def patient_of(key: str) -> str | None:
    """Return the patient id embedded in a storage key, or None if malformed."""
    parts = key.split("/")
    return parts[1] if len(parts) >= 2 else None


class StorageBackend(ABC):
    """Adapter interface for durable binary storage with signed-URL access."""

    @abstractmethod
    def signed_put_url(self, key: str, *, expires_in: int) -> SignedUrl:
        """Issue a write-only, single-object, short-lived upload URL."""

    @abstractmethod
    def signed_get_url(self, key: str, *, expires_in: int) -> SignedUrl:
        """Issue a read-only, single-object, short-lived download URL.

        Callers MUST perform the ownership/authorization check before calling this.
        """

    @abstractmethod
    def put_bytes(self, key: str, data: bytes) -> None:
        """Server-side write (used by tests / server-originated objects)."""

    @abstractmethod
    def get_bytes(self, key: str) -> bytes:
        """Server-side read (used by finalize validation and OCR workers)."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Return True if the object exists."""

    @abstractmethod
    def size(self, key: str) -> int:
        """Return the object size in bytes, or raise ObjectNotFound."""

    @abstractmethod
    def move(self, src_key: str, dst_key: str) -> None:
        """Move/rename an object (quarantine → accepted)."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete an object; a no-op if it does not exist."""
