"""Meto AI — Request/Response schemas.

All API contracts for the Meto chat endpoints. These are the public-facing
schemas; provider names are never exposed (always "meto").
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class MetoChatRequest(BaseModel):
    """Request body for POST /meto/chat and /meto/chat/stream."""

    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: str | None = None
    screen_id: str = "dashboard"
    entity_id: str | None = None
    entity_type: str | None = None
    stream: bool = False


class EscalationInfo(BaseModel):
    tier: str  # "recommend_checkup" | "recommend_urgent" | "emergency"
    message: str
    emergency_contacts: list[str] | None = None


class MetaChatResponse(BaseModel):
    """Response body for POST /meto/chat."""

    conversation_id: str
    message_id: str
    content: str
    safety_flags: list[str] = []
    escalation: EscalationInfo | None = None
    # Always "meto" — provider name is never exposed
    provider_used: str = "meto"
    fallback_used: bool = False
    quick_follow_ups: list[str] = []
    # Per product design: T&C covers consent at registration.
    # These fields are kept for backward-compat but always return False/empty.
    # Consent management is in Settings only, never gates the chat flow.
    consent_required: bool = False
    missing_consents: list[str] = []


class ConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str | None = None
    screen_id: str | None = None
    message_count: int
    last_active_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.UTC))
    status: str


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    conversation_id: str
    role: str
    content: str
    screen_id: str | None = None
    created_at: dt.datetime
    input_tokens: int = 0
    output_tokens: int = 0
    fallback_used: bool = False


class ConsentStatus(BaseModel):
    context_type: str
    granted: bool
    granted_at: dt.datetime | None = None


class ConsentUpdateRequest(BaseModel):
    context_type: str
    granted: bool
