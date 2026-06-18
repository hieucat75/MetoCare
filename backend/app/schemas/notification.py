"""Notification schemas (T23 — Notification Scaffold).

Covers:
  NotificationCreate  — admin creates a notification for a user
  NotificationOut     — serialised view of a Notification row
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, ConfigDict


class NotificationCreate(BaseModel):
    """Payload for POST /notifications (admin creates for a user)."""

    user_id: str
    type: str
    title: str
    body: str
    metadata: dict[str, Any] | None = None


class NotificationOut(BaseModel):
    """Serialised Notification row returned to the client."""

    id: str
    user_id: str
    type: str
    title: str
    body: str
    is_read: bool
    read_at: dt.datetime | None
    created_at: dt.datetime
    # metadata_ is the ORM column name; exposed as metadata_ in JSON as well
    metadata_: str | None

    model_config = ConfigDict(from_attributes=True)
