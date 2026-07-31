"""Azure Blob Object Storage adapter (Distribution-RC).

Owner decision #4 selects Azure Blob for staging *with quarantine/finalize
controls*, but the credential is a DEFERRED external input (Master Plan §12), and
current staging runs the local adapter (``MCP_STORAGE_MODE=local``). This adapter
is therefore structured but inert until an Azure Storage connection string /
account key is configured; every operation fails loud rather than silently
degrading. The real implementation issues account-key-signed SAS URLs scoped to a
single blob + operation + short expiry — the exact contract ``LocalDiskStorage``
emulates with HMAC tokens.
"""

from __future__ import annotations

from .base import SignedUrl, StorageBackend, StorageError

_DEFERRED = (
    "Azure Blob storage adapter is not configured. It is a Distribution-RC "
    "capability requiring an Azure Storage credential (deferred external input). "
    "Set MCP_STORAGE_MODE=local for the Engineering Release Candidate."
)


class AzureBlobStorage(StorageBackend):
    """Deferred Azure Blob adapter — fails loud until credentials are provided."""

    def __init__(self, connection_string: str, container: str) -> None:
        self._connection_string = connection_string
        self._container = container
        raise StorageError(_DEFERRED)  # real SAS wiring lands with DIST-RC creds

    def signed_put_url(self, key: str, *, expires_in: int) -> SignedUrl:  # pragma: no cover
        raise StorageError(_DEFERRED)

    def signed_get_url(self, key: str, *, expires_in: int) -> SignedUrl:  # pragma: no cover
        raise StorageError(_DEFERRED)

    def put_bytes(self, key: str, data: bytes) -> None:  # pragma: no cover
        raise StorageError(_DEFERRED)

    def get_bytes(self, key: str) -> bytes:  # pragma: no cover
        raise StorageError(_DEFERRED)

    def exists(self, key: str) -> bool:  # pragma: no cover
        raise StorageError(_DEFERRED)

    def size(self, key: str) -> int:  # pragma: no cover
        raise StorageError(_DEFERRED)

    def move(self, src_key: str, dst_key: str) -> None:  # pragma: no cover
        raise StorageError(_DEFERRED)

    def delete(self, key: str) -> None:  # pragma: no cover
        raise StorageError(_DEFERRED)
