"""In-memory LRU response cache with TTL.

Keyed by a hash of (provider, model, system, messages, user_id) so identical
prompts from the same user reuse a prior (already guardrail-checked) response and
avoid a paid call. Thread-safe; bounded by max_entries; entries expire after ttl.
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict
from dataclasses import replace

from .base import LLMMessage, LLMResponse


def make_key(
    *,
    provider: str,
    model: str,
    system: str | None,
    messages: list[LLMMessage],
    user_id: str,
    max_tokens: int,
    temperature: float,
) -> str:
    h = hashlib.sha256()
    parts = [provider, model, system or "", user_id, str(max_tokens), f"{temperature:.3f}"]
    for m in messages:
        parts.append(m.role)
        parts.append(m.content)
    h.update("\x1f".join(parts).encode("utf-8"))
    return h.hexdigest()


class LRUResponseCache:
    def __init__(self, *, max_entries: int = 512, ttl_seconds: int = 300) -> None:
        self._max = max_entries
        self._ttl = ttl_seconds
        self._data: OrderedDict[str, tuple[float, LLMResponse]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str, *, now: float | None = None) -> LLMResponse | None:
        now = now if now is not None else time.monotonic()
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            ts, resp = entry
            if now - ts >= self._ttl:
                del self._data[key]
                return None
            self._data.move_to_end(key)
            # Return a copy flagged as cached (don't mutate the stored response).
            return replace(resp, cached=True)

    def put(self, key: str, resp: LLMResponse, *, now: float | None = None) -> None:
        now = now if now is not None else time.monotonic()
        with self._lock:
            stored = replace(resp, cached=False)
            self._data[key] = (now, stored)
            self._data.move_to_end(key)
            while len(self._data) > self._max:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)
