"""Notification model (T23 — Notification Scaffold).

Represents an in-app notification delivered to a user.

Notification types:
  appointment_reminder     — upcoming appointment reminder
  health_alert             — health metric threshold exceeded
  lab_ready                — lab results are available
  care_plan_update         — care plan was updated by doctor
  system                   — generic platform/system message
  profile_update_requested — admin asked the patient to update their profile
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from ._mixins import UUIDPrimaryKey

_NOW = text("CURRENT_TIMESTAMP")

# Valid notification type values (open-ended for extensibility, enforced at schema)
NOTIFICATION_TYPES = frozenset(
    {
        "appointment_reminder",
        "health_alert",
        "lab_ready",
        "care_plan_update",
        "system",
        "profile_update_requested",
        # Journey 3 categories (§N)
        "medication_reminder",
        "result_ready",
        "ocr_review",
        "doctor_message",
        "security_alert",
    }
)


class Notification(UUIDPrimaryKey, Base):
    """An in-app notification for a platform user.

    Lifecycle:
      created (is_read=False) → read (is_read=True, read_at set)

    Ownership: only the recipient (user_id) may read / mark this notification.
    Creation: INTERNAL_ADMIN / SUPER_ADMIN only.
    """

    __tablename__ = "notifications"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # One of NOTIFICATION_TYPES; String(64) allows future extension
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    read_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=_NOW,
    )
    # Extra context as JSON text — e.g. '{"appointment_id": "..."}'; nullable
    metadata_: Mapped[str | None] = mapped_column(
        "metadata_",
        Text,
        nullable=True,
    )
