"""Per-user cost / rate guard for the LLM gateway.

Sliding 60-second window per user tracking request count (RPM) and token usage
(TPM). Exceeding either hard cap raises LLMRateLimitError (-> HTTP 429). Caps are
config-driven (MCP_LLM_MAX_REQUESTS_PER_MINUTE / MCP_LLM_MAX_TOKENS_PER_MINUTE).

In-memory + thread-safe; a distributed backend (Redis) can replace this without
changing call sites, matching the rate-limit module's pluggability story.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from .errors import LLMRateLimitError

_WINDOW_SECONDS = 60.0


class CostGuard:
    def __init__(self, *, max_rpm: int, max_tpm: int) -> None:
        self._max_rpm = max_rpm
        self._max_tpm = max_tpm
        # user_id -> deque[(ts, tokens)]; one event per recorded request.
        self._events: dict[str, deque[tuple[float, int]]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, user_id: str, now: float) -> deque[tuple[float, int]]:
        dq = self._events[user_id]
        cutoff = now - _WINDOW_SECONDS
        while dq and dq[0][0] < cutoff:
            dq.popleft()
        return dq

    def check(self, user_id: str, *, now: float | None = None) -> None:
        """Raise if the user is already at/over a cap. Call BEFORE the LLM call."""
        now = now if now is not None else time.monotonic()
        with self._lock:
            dq = self._prune(user_id, now)
            if len(dq) >= self._max_rpm:
                raise LLMRateLimitError(
                    "Đã vượt giới hạn số yêu cầu mỗi phút. Vui lòng thử lại sau.",
                    retry_after=int(_WINDOW_SECONDS),
                    kind="rpm",
                )
            tokens = sum(t for _, t in dq)
            if tokens >= self._max_tpm:
                raise LLMRateLimitError(
                    "Đã vượt giới hạn token mỗi phút. Vui lòng thử lại sau.",
                    retry_after=int(_WINDOW_SECONDS),
                    kind="tpm",
                )

    def record(self, user_id: str, tokens: int, *, now: float | None = None) -> None:
        """Record a completed request's token usage. Call AFTER the LLM call."""
        now = now if now is not None else time.monotonic()
        with self._lock:
            self._prune(user_id, now)
            self._events[user_id].append((now, tokens))

    def snapshot(self, user_id: str, *, now: float | None = None) -> tuple[int, int]:
        """Return (requests, tokens) currently in the window — for tests/metrics."""
        now = now if now is not None else time.monotonic()
        with self._lock:
            dq = self._prune(user_id, now)
            return len(dq), sum(t for _, t in dq)

    def reset(self) -> None:
        with self._lock:
            self._events.clear()
