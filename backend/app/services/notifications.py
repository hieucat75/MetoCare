"""Notification sink — legacy stub used by lab_pipeline.py and triage tests.

Records notifications to an in-memory sink (no PHI in payload).
Swap for a real transport (push/email/SMS) in a future sprint.

NOTE: The real in-app notification CRUD is in app.services.notification (T23).
This module remains for lab_pipeline/test compatibility until those callers are
updated to use the DB-backed service.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class _Notification:
    user_id: str
    event: str
    metadata: dict[str, Any] = field(default_factory=dict)


_sink: list[_Notification] = []


def notify(user_id: str, event: str, **metadata: Any) -> None:
    """Record a notification event."""
    note = _Notification(user_id=str(user_id), event=event, metadata=metadata)
    _sink.append(note)
    logger.info("notification", extra={"event": event, "user_id": str(user_id)})


def sent() -> list[_Notification]:
    """Return all recorded notifications (for tests)."""
    return list(_sink)


def recent(user_id: str) -> list[_Notification]:
    """Return notifications for a specific user (legacy test helper)."""
    uid = str(user_id)
    return [n for n in _sink if n.user_id == uid]


def reset() -> None:
    """Clear the sink (call in test teardown)."""
    _sink.clear()


# Alias for callers that use clear()
clear = reset
