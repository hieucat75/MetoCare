"""Object Storage backend factory + process-global singleton.

Mirrors ``app/core/ratelimit.py``: a lazily-built singleton selected by
``settings.storage_mode``, with ``set_storage``/``reset_storage`` test seams so
suites can inject an in-memory or temp-dir backend deterministically.
"""

from __future__ import annotations

from app.core.config import get_settings

from .base import StorageBackend, StorageError
from .local import build_local_storage

_STORAGE: StorageBackend | None = None


def get_storage() -> StorageBackend:
    """Return the process-global storage backend, building it on first use."""
    global _STORAGE
    if _STORAGE is None:
        _STORAGE = _build()
    return _STORAGE


def set_storage(backend: StorageBackend | None) -> None:
    """Override the singleton (tests). Pass None to force a rebuild next call."""
    global _STORAGE
    _STORAGE = backend


def reset_storage() -> None:
    """Drop the cached singleton so the next ``get_storage`` rebuilds from config."""
    global _STORAGE
    _STORAGE = None


def _build() -> StorageBackend:
    settings = get_settings()
    mode = (settings.storage_mode or "local").lower()
    if mode == "local":
        return build_local_storage()
    if mode == "azure":
        from .azure_blob import AzureBlobStorage

        return AzureBlobStorage(
            getattr(settings, "storage_azure_connection_string", ""),
            getattr(settings, "storage_azure_container", "documents"),
        )
    raise StorageError(
        f"unsupported storage_mode={mode!r}; supported: local, azure (DIST-RC)"
    )
