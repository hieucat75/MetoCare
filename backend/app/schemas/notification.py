"""Notification schemas (T23 — Notification Scaffold).

Covers:
  NotificationCreate  — admin creates a notification for a user
  NotificationOut     — serialised view of a Notification row
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class NotificationCreate(BaseModel):
    """Payload for POST /notifications (admin creates for a user)."""

    user_id: str
    type: str
    # 256 is not cosmetic. `notifications.title` was VARCHAR(256) until the PHI
    # migration widened it to TEXT (ciphertext does not fit 256), and that
    # migration's downgrade narrows it back. A single row longer than 256 makes
    # `ALTER COLUMN title TYPE VARCHAR(256)` fail outright — Postgres raises
    # rather than truncating — so one over-long admin notification would block the
    # rollback path entirely. Bounding the input keeps downgrade always available.
    title: str = Field(max_length=256)
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
