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


# Atomic fixed-window increment: INCR then EXPIRE only on first hit, in one
# round-trip so a counter can never be left without a TTL (avoids permanently
# rate-limiting a client after a mid-operation crash).
_INCR_EXPIRE_LUA = """
local v = redis.call('INCR', KEYS[1])
if v == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return v
"""


class RedisRateLimiter(RateLimiter):
    """Distributed limiter backed by Redis (shared across instances).

    Fixed-window counter. The INCR+EXPIRE is made **atomic** via a cached Lua
    script (falls back to ``SET key 0 NX EX window`` then ``INCR`` if scripting is
    unavailable — that also guarantees a TTL exists). All keys are **namespaced**
    by ``prefix`` so ``reset()`` only ever touches limiter keys (never flushdb).

    `redis` is imported lazily so it stays an OPTIONAL dependency; a client can be
    injected (tests use a fake client — no real Redis needed).
    """

    # Glob metacharacters that would broaden a SCAN match beyond our namespace.
    _UNSAFE_PREFIX_CHARS = set("*?[]^")

    def __init__(
        self, client=None, url: str | None = None, prefix: str = "metocare:ratelimit:"
    ) -> None:
        # A non-empty, glob-safe prefix is REQUIRED: reset() deletes by SCAN match,
        # so an empty prefix (-> "*") or one containing glob metacharacters could
        # wipe unrelated keys in a shared Redis DB.
        if not prefix or self._UNSAFE_PREFIX_CHARS.intersection(prefix):
            raise ValueError(
                "ratelimit_redis_prefix must be non-empty and free of glob metacharacters "
                f"(*?[]^); got {prefix!r}"
            )
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

        self._prefix = prefix
        self._script = None
        register = getattr(self._r, "register_script", None)
        if callable(register):
            try:
                self._script = register(_INCR_EXPIRE_LUA)
            except Exception:  # noqa: BLE001 - scripting optional; fall back below
                self._script = None

    def _full_key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    def _incr_with_ttl(self, rkey: str, window: int) -> int:
        # Preferred: atomic Lua.
        if self._script is not None:
            try:
                return int(self._script(keys=[rkey], args=[window]))
            except Exception:  # noqa: BLE001 - degrade to the SET NX path
                pass
        # Fallback: SET NX EX establishes the TTL atomically on creation, then INCR.
        try:
            self._r.set(rkey, 0, nx=True, ex=window)
        except TypeError:  # client without nx/ex kwargs
            if not self._r.get(rkey):
                self._r.set(rkey, 0)
                self._r.expire(rkey, window)
        return int(self._r.incr(rkey))

    def allow(
        self, key: str, *, capacity: int, refill_per_sec: float, now: float | None = None
    ) -> bool:
        window = max(1, int(capacity / refill_per_sec)) if refill_per_sec else 60
        count = self._incr_with_ttl(self._full_key(key), window)
        return count <= capacity

    def reset(self) -> None:
        # Only delete OUR namespaced keys; never flushdb (would wipe shared data).
        scan = getattr(self._r, "scan_iter", None)
        if not callable(scan):
            return
        deleter = getattr(self._r, "unlink", None) or getattr(self._r, "delete", None)
        if deleter is None:
            return
        for rkey in scan(match=f"{self._prefix}*", count=500):
            deleter(rkey)


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
            _rate_limiter = RedisRateLimiter(
                url=settings.ratelimit_redis_url, prefix=settings.ratelimit_redis_prefix
            )
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
