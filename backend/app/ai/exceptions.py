"""Meto AI — Custom exceptions.

All AI-layer exceptions inherit from MetoAIError so callers can catch broadly
or narrowly as needed.
"""

from __future__ import annotations


class MetoAIError(Exception):
    """Base exception for all Meto AI errors."""


class ProviderUnavailableError(MetoAIError):
    """Raised when a provider is down or circuit-breaker is open."""

    def __init__(self, provider: str, reason: str = "") -> None:
        self.provider = provider
        super().__init__(f"Provider '{provider}' unavailable: {reason}" if reason else f"Provider '{provider}' unavailable")


class ProviderTimeoutError(MetoAIError):
    """Raised when a provider call exceeds the configured timeout."""

    def __init__(self, provider: str, timeout_seconds: float = 0) -> None:
        self.provider = provider
        msg = f"Provider '{provider}' timed out"
        if timeout_seconds:
            msg += f" after {timeout_seconds}s"
        super().__init__(msg)


class ContentModerationError(MetoAIError):
    """Raised when content violates safety policies."""

    def __init__(self, reason: str = "", flagged_text: str | None = None) -> None:
        self.flagged_text = flagged_text
        super().__init__(f"Content moderation failed: {reason}")


class ContextTooLargeError(MetoAIError):
    """Raised when assembled context exceeds provider's token limit."""

    def __init__(self, estimated_tokens: int, max_tokens: int) -> None:
        self.estimated_tokens = estimated_tokens
        self.max_tokens = max_tokens
        super().__init__(
            f"Context too large: {estimated_tokens} tokens exceeds limit {max_tokens}"
        )


class SafetyGuardError(MetoAIError):
    """Raised when the safety guard blocks a message or response."""

    def __init__(self, reason: str = "", flags: list[str] | None = None) -> None:
        self.flags = flags or []
        super().__init__(f"Safety guard blocked: {reason}")


class CircuitBreakerOpenError(MetoAIError):
    """Raised when the circuit breaker is open for a provider."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(f"Circuit breaker OPEN for provider '{provider}'")


class ProviderResponseError(MetoAIError):
    """Raised when a provider returns an unexpected or malformed response."""

    def __init__(self, provider: str, status_code: int | None = None, detail: str = "") -> None:
        self.provider = provider
        self.status_code = status_code
        msg = f"Provider '{provider}' returned error"
        if status_code:
            msg += f" (HTTP {status_code})"
        if detail:
            msg += f": {detail}"
        super().__init__(msg)
