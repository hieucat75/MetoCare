"""Meto output SafetyGuard must be ENFORCING, not detection-only.

A model response that self-discloses the provider or contains a forbidden
diagnosis/dose-change instruction must be REPLACED with a safe fallback and never
delivered to the patient — on both the non-streaming and streaming paths.
"""

from __future__ import annotations

import datetime as dt
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.ai.context.schemas import AssembledContext, ScreenContext
from app.ai.providers.base import ChatMessage, ChatResponse, ChatStreamChunk
from app.services.meto_chat import _UNSAFE_OUTPUT_FALLBACK, MetoChatService

_FORBIDDEN = "Tôi chẩn đoán bạn bị tiểu đường, hãy dừng thuốc ngay."


def _mock_db():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.all.return_value = []
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

    def _refresh(obj):
        if getattr(obj, "id", None) is None:
            obj.id = "test-id"
        if getattr(obj, "created_at", None) is None:
            obj.created_at = dt.datetime.now(dt.UTC)
        if not hasattr(obj, "last_active_at"):
            obj.last_active_at = dt.datetime.now(dt.UTC)

    db.refresh.side_effect = _refresh
    return db


def _ctx():
    return AssembledContext(
        user_profile={"display_name": "T", "preferred_address": "bạn"},
        screen_context={"screen_id": "dashboard"},
        included_blocks=["user_profile", "screen_context"],
        missing_consents=[],
        total_estimated_tokens=100,
    )


class _FakeStreamProvider:
    provider_name = "claude"

    async def chat_stream(self, **_kwargs):
        for part in ["Xin chào, ", "tôi là ", "Claude."]:
            yield ChatStreamChunk(delta=part)
        yield ChatStreamChunk(delta="", is_final=True, total_tokens=10)


@pytest.mark.asyncio
async def test_nonstream_forbidden_output_is_replaced():
    registry = MagicMock()
    resp = ChatResponse(
        content=_FORBIDDEN, tool_calls=None, input_tokens=5, output_tokens=9,
        model_used="m", finish_reason="stop", latency_ms=10, provider="claude",
    )
    registry.call_with_fallback = AsyncMock(return_value=(resp, "claude", False))
    svc = MetoChatService(registry)
    db = _mock_db()

    with patch("app.services.meto_chat._CONTEXT_BUILDER") as mctx, \
         patch("app.services.meto_chat._PROMPT_ASSEMBLER") as mprompt, \
         patch("app.services.meto_chat._get_settings") as msettings:
        # _SAFETY_GUARD is intentionally NOT patched — exercise the real guard.
        mctx.build.return_value = _ctx()
        mprompt.assemble.return_value = ("sys", [ChatMessage(role="user", content="x")])
        mprompt.generate_conversation_title.return_value = "t"
        si = MagicMock()
        si.meto_max_tokens = 512
        si.meto_temperature = 0.3
        # PROD-F10: stream_chat bounds each provider attempt with this timeout.
        si.meto_timeout_seconds = 30
        msettings.return_value = si

        result = await svc.chat(
            db=db, user_id="u1", conversation_id=None,
            message="Tôi bị sao vậy?", screen_context=ScreenContext(screen_id="dashboard"),
        )

    assert result.content == _UNSAFE_OUTPUT_FALLBACK
    # The model's unsafe payload must not leak through.
    assert "tiểu đường" not in result.content
    assert "dừng thuốc ngay" not in result.content


@pytest.mark.asyncio
async def test_stream_forbidden_output_is_replaced_before_emit():
    registry = MagicMock()
    registry.get_available_providers.return_value = [_FakeStreamProvider()]
    registry.circuit_breaker.return_value = MagicMock()
    svc = MetoChatService(registry)
    db = _mock_db()

    with patch("app.services.meto_chat._CONTEXT_BUILDER") as mctx, \
         patch("app.services.meto_chat._PROMPT_ASSEMBLER") as mprompt, \
         patch("app.services.meto_chat._get_settings") as msettings:
        mctx.build.return_value = _ctx()
        mprompt.assemble.return_value = ("sys", [ChatMessage(role="user", content="x")])
        si = MagicMock()
        si.meto_max_tokens = 512
        si.meto_temperature = 0.3
        # PROD-F10: stream_chat bounds each provider attempt with this timeout.
        si.meto_timeout_seconds = 30
        msettings.return_value = si

        events = []
        async for chunk in svc.stream_chat(
            db=db, user_id="u1", conversation_id=None,
            message="Bạn là ai?", screen_context=ScreenContext(screen_id="dashboard"),
        ):
            events.append(chunk)

    # The emitted 'chunk' delta(s) must be the safe fallback — never the provider
    # self-disclosure, and no partial forbidden text may leak.
    deltas = []
    for ev in events:
        payload = json.loads(ev.removeprefix("data: ").strip())
        if payload.get("type") == "chunk":
            deltas.append(payload["delta"])
    joined = "".join(deltas)
    assert joined == _UNSAFE_OUTPUT_FALLBACK
    assert "claude" not in joined.lower()
