"""Rate limiting + account lockout (in-memory, pluggable for Redis later).

The interface is deliberately backend-agnostic so a Redis implementation can drop
in without touching call sites. For the foundation only the in-memory backend is
implemented; selecting `redis` raises until that work lands (P2/infra).

No heavy dependency is added. Uses a token-bucket per (action, client) key plus a
separate failure-counter lockout per account.
"""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod

from .config import get_settings


class RateLimiter(ABC):
    @abstractmethod
    def allow(
        self, key: str, *, capacity: int, refill_per_sec: float, now: float | None = None
    ) -> bool:
        """Return True if a token is available (and consume it), else False."""

    @abstractmethod
    def reset(self) -> None:
        ...


class InMemoryRateLimiter(RateLimiter):
    """Token bucket. Thread-safe enough for a single-process foundation."""

    def __init__(self) -> None:
        self._buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, last_ts)
        self._lock = threading.Lock()

    def allow(
        self, key: str, *, capacity: int, refill_per_sec: float, now: float | None = None
    ) -> bool:
        now = now if now is not None else time.monotonic()
        with self._lock:
            tokens, last = self._buckets.get(key, (float(capacity), now))
            tokens = min(capacity, tokens + (now - last) * refill_per_sec)
            if tokens >= 1.0:
                self._buckets[key] = (tokens - 1.0, now)
                return True
            self._buckets[key] = (tokens, now)
            return False

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


class LockoutManager:
    """Counts consecutive failures per key; locks after a threshold for a cooldown."""

    def __init__(self) -> None:
        self._fails: dict[str, tuple[int, float]] = {}  # key -> (count, first_fail_ts)
        self._lock = threading.Lock()

    def record_failure(self, key: str, *, now: float | None = None) -> int:
        now = now if now is not None else time.monotonic()
        with self._lock:
            count, first = self._fails.get(key, (0, now))
            count += 1
            self._fails[key] = (count, first)
            return count

    def is_locked(
        self, key: str, *, max_failures: int, cooldown_seconds: int, now: float | None = None
    ) -> bool:
        now = now if now is not None else time.monotonic()
        with self._lock:
            entry = self._fails.get(key)
            if entry is None:
                return False
            count, first = entry
            if count < max_failures:
                return False
            if now - first >= cooldown_seconds:
                # Cooldown elapsed; clear and allow again.
                del self._fails[key]
                return False
            return True

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._fails.clear()
            else:
                self._fails.pop(key, None)


class RedisRateLimiter(RateLimiter):
    """Distributed limiter backed by Redis (shared across instances).

    Uses a fixed-window counter (INCR + EXPIRE) — an approximation of the token
    bucket that is atomic and cheap in Redis. `redis` is imported lazily so it
    stays an OPTIONAL dependency (not in hard requirements); a client can also be
    injected (used by tests with a fake client, no real Redis needed).
    """

    def __init__(self, client=None, url: str | None = None) -> None:
        if client is not None:
            self._r = client
        else:  # pragma: no cover - requires the optional redis package + server
            try:
                import redis  # noqa: PLC0415  (lazy/optional import by design)
            except ImportError as exc:
                raise RuntimeError(
                    "MCP_RATELIMIT_BACKEND=redis requires the optional 'redis' package."
                ) from exc
            if not url:
                raise RuntimeError("MCP_RATELIMIT_REDIS_URL is required for the redis backend.")
            self._r = redis.Redis.from_url(url)

    def allow(
        self, key: str, *, capacity: int, refill_per_sec: float, now: float | None = None
    ) -> bool:
        window = max(1, int(capacity / refill_per_sec)) if refill_per_sec else 60
        count = int(self._r.incr(key))
        if count == 1:
            self._r.expire(key, window)
        return count <= capacity

    def reset(self) -> None:
        # Best-effort; in production keys expire on their own.
        flush = getattr(self._r, "flushdb", None)
        if callable(flush):
            flush()


# --------------------------------------------------------------------------- #
# Factory (pluggable backend by config). Singletons for the process.
# --------------------------------------------------------------------------- #

_rate_limiter: RateLimiter | None = None
_lockout = LockoutManager()


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        settings = get_settings()
        backend = settings.ratelimit_backend
        if backend == "memory":
            _rate_limiter = InMemoryRateLimiter()
        elif backend == "redis":
            _rate_limiter = RedisRateLimiter(url=settings.ratelimit_redis_url)
        else:
            raise ValueError(f"Unknown MCP_RATELIMIT_BACKEND: {backend!r}")
    return _rate_limiter


def set_rate_limiter(limiter: RateLimiter | None) -> None:
    """Override the process limiter (used by tests)."""
    global _rate_limiter
    _rate_limiter = limiter


def get_lockout() -> LockoutManager:
    return _lockout


def reset_all() -> None:
    """Test helper: clear all rate-limit + lockout state."""
    if _rate_limiter is not None:
        _rate_limiter.reset()
    _lockout.reset()
