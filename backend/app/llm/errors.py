"""LLM Gateway error types."""

from __future__ import annotations


class LLMError(Exception):
    """Base class for LLM gateway errors."""


class LLMConfigError(LLMError):
    """Provider is selected but cannot run (e.g. real adapter without key/url).

    Raised by skeleton adapters so a misconfiguration fails loudly instead of
    silently calling nothing — and so dev/test never hit a real provider.
    """


class LLMRateLimitError(LLMError):
    """A per-user cost/rate cap (RPM or TPM) was exceeded. Maps to HTTP 429."""

    def __init__(self, message: str, *, retry_after: int = 60, kind: str = "rpm") -> None:
        super().__init__(message)
        self.retry_after = retry_after
        self.kind = kind  # "rpm" | "tpm"
