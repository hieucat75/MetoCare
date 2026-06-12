"""Shared column mixins for ORM models."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import DateTime, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

# Portable SQL: CURRENT_TIMESTAMP works on both SQLite and PostgreSQL, so the
# generated Alembic migration runs unchanged on either backend (func.now() would
# freeze to now() in the migration and break on SQLite).
_NOW = text("CURRENT_TIMESTAMP")


def _uuid() -> str:
    return str(uuid.uuid4())


class UUIDPrimaryKey:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW, nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW, onupdate=func.now(), nullable=False
    )
