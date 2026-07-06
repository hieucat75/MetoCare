"""Meto AI — Database models for conversations, messages, audit, and consent.

Follows 08_CONVERSATION_ENGINE.md DB schema and 04_SAFETY_PRIVACY.md consent model.
"""

from __future__ import annotations

import datetime as dt
import os as _os
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from ._mixins import TimestampMixin, UUIDPrimaryKey

_db_url = _os.environ.get("MCP_DATABASE_URL", "")
if "sqlite" not in _db_url.lower():
    try:
        from sqlalchemy.dialects.postgresql import JSONB as JSONType
    except ImportError:
        from sqlalchemy import JSON as JSONType  # type: ignore[assignment]
else:
    from sqlalchemy import JSON as JSONType  # type: ignore[assignment]


class MetoConversation(UUIDPrimaryKey, TimestampMixin, Base):
    """One Meto conversation session per user."""

    __tablename__ = "meto_conversations"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Screen where the conversation started
    screen_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Auto-generated title (from first user message)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # active | idle | archived | deleted
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # "claude" | "openai" | "meto" (always returns "meto" externally)
    provider_used: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_active_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.UTC)
    )
    archived_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Admin AI-safety console: set when an admin marks the session reviewed.
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class MetoMessage(UUIDPrimaryKey, TimestampMixin, Base):
    """One message within a Meto conversation."""

    __tablename__ = "meto_messages"

    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("meto_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # "user" | "assistant" | "system"
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    # Plain text content
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Screen context when message was sent
    screen_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # JSON list of tool calls (if any)
    tool_calls: Mapped[Any | None] = mapped_column(JSONType, nullable=True)
    # JSON list of tool results
    tool_results: Mapped[Any | None] = mapped_column(JSONType, nullable=True)
    # Provider that generated the response (assistant messages only)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fallback_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class MetoAuditLog(UUIDPrimaryKey, TimestampMixin, Base):
    """Audit trail for Meto AI operations.

    Per 04_SAFETY_PRIVACY.md: does NOT store message content or raw health data.
    Only stores metadata for compliance/debugging.
    """

    __tablename__ = "meto_audit_logs"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    # "context_accessed" | "tool_called" | "escalated" | "fallback_used" | "chat_request"
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    screen_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # JSON list of context block names used (e.g. ["user_profile_summary", "recent_labs"])
    context_types: Mapped[Any | None] = mapped_column(JSONType, nullable=True)
    provider_used: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fallback_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    safety_flags_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    escalation_triggered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_count_input: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_count_output: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Non-PII metadata (no message content, no raw health data)
    details: Mapped[Any | None] = mapped_column(JSONType, nullable=True)


class MetoConsent(UUIDPrimaryKey, TimestampMixin, Base):
    """Granular consent per user per context type.

    Users must grant explicit consent before Meto can include their health
    data in AI context. This is the gating record for each data type.
    """

    __tablename__ = "meto_consents"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # "health_data" | "medications" | "labs" | "metrics" | "care_plan" | "chat_history"
    context_type: Mapped[str] = mapped_column(String(64), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    granted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
