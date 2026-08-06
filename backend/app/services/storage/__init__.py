"""Object Storage abstraction package (Master Plan §1.1 / §1.7)."""

from __future__ import annotations

from .base import (
    CONTAINER_ACCEPTED,
    CONTAINER_QUARANTINE,
    ObjectNotFound,
    SignedUrl,
    StorageBackend,
    StorageError,
    build_object_key,
    container_of,
    ext_for_mime,
    patient_of,
)
from .factory import get_storage, reset_storage, set_storage
from .signing import (
    BLOB_OP_GET,
    BLOB_OP_PUT,
    BlobToken,
    BlobTokenError,
    derive_blob_secret,
    sign_blob_token,
    verify_blob_token,
)

__all__ = [
    "CONTAINER_ACCEPTED",
    "CONTAINER_QUARANTINE",
    "ObjectNotFound",
    "SignedUrl",
    "StorageBackend",
    "StorageError",
    "build_object_key",
    "container_of",
    "ext_for_mime",
    "patient_of",
    "get_storage",
    "reset_storage",
    "set_storage",
    "BLOB_OP_GET",
    "BLOB_OP_PUT",
    "BlobToken",
    "BlobTokenError",
    "derive_blob_secret",
    "sign_blob_token",
    "verify_blob_token",
]
