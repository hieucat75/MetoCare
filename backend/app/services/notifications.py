"""Notification placeholder (P2 #3).

A real notification system (push/email/SMS) is out of scope for the foundation.
This module records notifications to an in-memory sink and logs them (no PHI in
the payload) so the pipeline can "notify user" at the right step and tests can
assert it happened. Swap the sink for a real transport later without touching
call sites.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

logger = logging.getLogger("mcp.notifications")


@dataclass(frozen=True)
class Notification:
    user_id: str
    event: str
    payload: dict[str, str] = field(default_factory=dict)


_lock = threading.Lock()
_sink: list[Notification] = []


def notify(user_id: str, event: str, **payload: str) -> Notification:
    """Record a notification. Payload must be non-PHI metadata only."""
    note = Notification(user_id=user_id, event=event, payload=dict(payload))
    with _lock:
        _sink.append(note)
    logger.info("notification", extra={"action": event, "resource_type": "notification"})
    return note


def recent(user_id: str | None = None) -> list[Notification]:
    with _lock:
        if user_id is None:
            return list(_sink)
        return [n for n in _sink if n.user_id == user_id]


def reset() -> None:
    with _lock:
        _sink.clear()
