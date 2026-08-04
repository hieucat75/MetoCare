"""
Streaming path tests for Meto AI.
Uses AsyncMock for provider streaming.

These tests patch at the provider level since in MCP_AI_MODE=mock no real
providers are registered. We inject a mock provider into the registry.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from app.ai.context.schemas import AssembledContext, ScreenContext
from app.ai.providers.base import ChatMessage, ChatStreamChunk
from app.ai.registry import ProviderRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_assembled_context(
    *,
    screen_id: str = "dashboard",
    missing_consents: list | None = None,
) -> AssembledContext:
    return AssembledContext(
        user_profile={"display_name": "Test User", "preferred_address": "bạn"},
        health_summary=None,
        care_plan=None,
        medications=None,
        recent_labs=None,
        recent_metrics=None,
        screen_context={"screen_id": screen_id},
        today_context={},
        safety_flags=[],
        total_estimated_tokens=150,
        missing_consents=missing_consents or [],
        included_blocks=["user_profile", "screen_context"],
    )


def _make_mock_streaming_provider(chunks: list[ChatStreamChunk]) -> MagicMock:
    """Create a mock ConversationProvider that yields the given chunks from chat_stream."""
    async def _gen(*args, **kwargs):
        for chunk in chunks:
            yield chunk

    provider = MagicMock()
    provider.provider_name = "mock_stream"
    provider.chat_stream = _gen
    return provider


def _make_registry_with_provider(provider) -> ProviderRegistry:
    """Return a ProviderRegistry with one mock provider registered."""
    registry = ProviderRegistry()
    # Bypass real routing: patch get_available_providers to return our provider
    registry.get_available_providers = MagicMock(return_value=[provider])
    return registry


async def _collect_chunks(stream) -> list[dict]:
    """Collect all SSE data chunks from stream_chat into parsed dicts."""
    results = []
    async for raw in stream:
        if not raw.startswith("data: "):
            continue
        body = raw[len("data: "):].strip()
        if body:
            try:
                results.append(json.loads(body))
            except json.JSONDecodeError:
                results.append({"raw": body})
    return results


# ---------------------------------------------------------------------------
# Test 1: normal stream yields chunk + done
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_chat_normal_yields_chunks(db, patient):
    """Normal streaming: at least one type='chunk' delta, then type='done' with conversation_id."""
    from app.ai.prompt.safety import SafetyResult
    from app.services.meto_chat import MetoChatService

    chunks = [
        ChatStreamChunk(delta="Xin chào ", is_final=False),
        ChatStreamChunk(delta="bạn! ", is_final=False),
        ChatStreamChunk(delta="Meto đây.", is_final=False),
        ChatStreamChunk(delta="", is_final=True, total_tokens=50),
    ]
    provider = _make_mock_streaming_provider(chunks)
    registry = _make_registry_with_provider(provider)
    svc = MetoChatService(registry)

    with (
        patch("app.services.meto_chat._CONTEXT_BUILDER") as mock_ctx,
        patch("app.services.meto_chat._SAFETY_GUARD") as mock_safety,
        patch("app.services.meto_chat._PROMPT_ASSEMBLER") as mock_prompt,
        patch("app.services.meto_chat._get_settings") as mock_settings,
    ):
        mock_ctx.build.return_value = _make_assembled_context()
        mock_safety.check_input.return_value = SafetyResult(safe=True)
        mock_safety.check_output.return_value = SafetyResult(safe=True)
        mock_prompt.assemble.return_value = (
            "system prompt",
            [ChatMessage(role="user", content="xin chào")],
        )
        mock_prompt._get_quick_prompts.return_value = []

        settings_mock = MagicMock()
        settings_mock.meto_max_tokens = 2048
        settings_mock.meto_temperature = 0.3
        # PROD-F10: stream_chat bounds each provider attempt with this timeout.
        settings_mock.meto_timeout_seconds = 30
        mock_settings.return_value = settings_mock

        collected = await _collect_chunks(
            svc.stream_chat(
                db=db,
                user_id=patient["user_id"],
                conversation_id=None,
                message="Xin chào Meto",
                screen_context=ScreenContext(screen_id="dashboard"),
            )
        )

    # At least one 'chunk' with non-empty delta
    chunk_events = [c for c in collected if c.get("type") == "chunk"]
    assert len(chunk_events) >= 1, f"Expected at least one chunk event, got: {collected}"

    non_empty = [c for c in chunk_events if c.get("delta")]
    assert len(non_empty) >= 1, "At least one chunk must have non-empty delta"

    # Final 'done' event with conversation_id
    done_events = [c for c in collected if c.get("type") == "done"]
    assert len(done_events) == 1, f"Expected exactly one done event, got: {collected}"
    assert done_events[0].get("conversation_id"), "done event must include conversation_id"


# ---------------------------------------------------------------------------
# Test 2: emergency message skips provider
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_chat_emergency_skips_provider(db, patient):
    """Emergency input: safety guard intercepts, provider.chat_stream NOT called."""
    from app.ai.prompt.safety import SafetyResult
    from app.services.meto_chat import MetoChatService

    provider = MagicMock()
    provider.provider_name = "mock_stream"
    chat_stream_called = []

    async def _tracked_stream(*args, **kwargs):
        chat_stream_called.append(True)
        raise AssertionError("chat_stream should not be called for emergency")
        yield  # make it an async generator

    provider.chat_stream = _tracked_stream

    registry = _make_registry_with_provider(provider)
    svc = MetoChatService(registry)

    emergency_message = "Tôi đang đau ngực dữ dội và khó thở"

    with (
        patch("app.services.meto_chat._CONTEXT_BUILDER") as mock_ctx,
        patch("app.services.meto_chat._SAFETY_GUARD") as mock_safety,
        patch("app.services.meto_chat._PROMPT_ASSEMBLER") as mock_prompt,
        patch("app.services.meto_chat._get_settings") as mock_settings,
    ):
        mock_ctx.build.return_value = _make_assembled_context()

        escalation_msg = "⚠️ Gọi 115 ngay! Đây có thể là dấu hiệu cấp cứu."
        mock_safety.check_input.return_value = SafetyResult(
            safe=False,
            flags=["đau ngực", "khó thở"],
            escalation_required=True,
            escalation_tier="emergency",
            suggested_response=escalation_msg,
        )
        mock_safety.get_escalation_response.return_value = escalation_msg
        mock_prompt._get_quick_prompts.return_value = []

        settings_mock = MagicMock()
        settings_mock.meto_max_tokens = 2048
        settings_mock.meto_temperature = 0.3
        # PROD-F10: stream_chat bounds each provider attempt with this timeout.
        settings_mock.meto_timeout_seconds = 30
        mock_settings.return_value = settings_mock

        collected = await _collect_chunks(
            svc.stream_chat(
                db=db,
                user_id=patient["user_id"],
                conversation_id=None,
                message=emergency_message,
                screen_context=ScreenContext(screen_id="dashboard"),
            )
        )

    # Provider must NOT have been called
    assert not chat_stream_called, "chat_stream must NOT be called for emergency messages"

    # Must have yielded escalation content
    all_text = " ".join(
        c.get("delta", "") for c in collected if c.get("type") == "chunk"
    )
    assert len(all_text) > 0 or any(c.get("type") == "done" for c in collected), (
        "Emergency path must yield at least done event"
    )


# ---------------------------------------------------------------------------
# Test 3: provider error yields error chunk
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_chat_provider_error_yields_error_chunk(db, patient):
    """Provider raises during stream → type='error' chunk with friendly message."""
    from app.ai.exceptions import ProviderUnavailableError
    from app.ai.prompt.safety import SafetyResult
    from app.services.meto_chat import MetoChatService

    async def _failing_stream(*args, **kwargs):
        raise ProviderUnavailableError("mock", "simulated failure")
        yield  # async generator syntax

    provider = MagicMock()
    provider.provider_name = "mock_failing"
    provider.chat_stream = _failing_stream

    registry = _make_registry_with_provider(provider)
    svc = MetoChatService(registry)

    with (
        patch("app.services.meto_chat._CONTEXT_BUILDER") as mock_ctx,
        patch("app.services.meto_chat._SAFETY_GUARD") as mock_safety,
        patch("app.services.meto_chat._PROMPT_ASSEMBLER") as mock_prompt,
        patch("app.services.meto_chat._get_settings") as mock_settings,
    ):
        mock_ctx.build.return_value = _make_assembled_context()
        mock_safety.check_input.return_value = SafetyResult(safe=True)
        mock_safety.check_output.return_value = SafetyResult(safe=True)
        mock_prompt.assemble.return_value = (
            "system",
            [ChatMessage(role="user", content="test")],
        )
        mock_prompt._get_quick_prompts.return_value = []

        settings_mock = MagicMock()
        settings_mock.meto_max_tokens = 2048
        settings_mock.meto_temperature = 0.3
        # PROD-F10: stream_chat bounds each provider attempt with this timeout.
        settings_mock.meto_timeout_seconds = 30
        mock_settings.return_value = settings_mock

        collected = await _collect_chunks(
            svc.stream_chat(
                db=db,
                user_id=patient["user_id"],
                conversation_id=None,
                message="Câu hỏi thử lỗi",
                screen_context=ScreenContext(screen_id="dashboard"),
            )
        )

    # Must include a type='error' or a done after error content
    error_events = [c for c in collected if c.get("type") == "error"]
    assert len(error_events) >= 1, (
        f"Expected at least one error event when provider fails. Got: {collected}"
    )

    # Error message must be user-friendly (Vietnamese), not an internal exception trace
    error_msg = error_events[0].get("message", "")
    assert len(error_msg) > 0, "Error event must contain a message"

    # Must NOT contain internal exception class names
    forbidden_internals = ["ProviderUnavailableError", "Traceback", "Exception", "stack trace"]
    msg_lower = error_msg.lower()
    for term in forbidden_internals:
        assert term.lower() not in msg_lower, (
            f"Error message must not expose internals: {term!r} found in {error_msg!r}"
        )


# ---------------------------------------------------------------------------
# Test 4: no provider name in streamed chunks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_chat_no_provider_name_in_chunks(db, patient):
    """All streamed delta text must not contain provider names."""
    from app.ai.prompt.safety import SafetyResult
    from app.services.meto_chat import MetoChatService

    response_text = "Kết quả xét nghiệm của bạn cho thấy đường huyết đang ổn định."
    words = response_text.split()

    chunks = [
        ChatStreamChunk(delta=word + " ", is_final=False)
        for word in words
    ] + [ChatStreamChunk(delta="", is_final=True, total_tokens=30)]

    provider = _make_mock_streaming_provider(chunks)
    registry = _make_registry_with_provider(provider)
    svc = MetoChatService(registry)

    with (
        patch("app.services.meto_chat._CONTEXT_BUILDER") as mock_ctx,
        patch("app.services.meto_chat._SAFETY_GUARD") as mock_safety,
        patch("app.services.meto_chat._PROMPT_ASSEMBLER") as mock_prompt,
        patch("app.services.meto_chat._get_settings") as mock_settings,
    ):
        mock_ctx.build.return_value = _make_assembled_context()
        mock_safety.check_input.return_value = SafetyResult(safe=True)
        mock_safety.check_output.return_value = SafetyResult(safe=True)
        mock_prompt.assemble.return_value = (
            "system",
            [ChatMessage(role="user", content="câu hỏi")],
        )
        mock_prompt._get_quick_prompts.return_value = []

        settings_mock = MagicMock()
        settings_mock.meto_max_tokens = 2048
        settings_mock.meto_temperature = 0.3
        # PROD-F10: stream_chat bounds each provider attempt with this timeout.
        settings_mock.meto_timeout_seconds = 30
        mock_settings.return_value = settings_mock

        collected = await _collect_chunks(
            svc.stream_chat(
                db=db,
                user_id=patient["user_id"],
                conversation_id=None,
                message="Kết quả của tôi thế nào?",
                screen_context=ScreenContext(screen_id="labs"),
            )
        )

    # Combine all delta text
    combined = " ".join(
        c.get("delta", "") for c in collected if c.get("type") == "chunk"
    ).lower()

    # Provider names must not leak into chunks
    forbidden = ["claude", "openai", "anthropic", "gpt", "9router", "gemini"]
    for name in forbidden:
        assert name not in combined, (
            f"Provider name '{name}' leaked into streamed content: {combined!r}"
        )


# ---------------------------------------------------------------------------
# Test 5: fallback during stream
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_chat_fallback_during_stream(db, patient):
    """Primary provider fails; fallback provider succeeds and done chunk has fallback_used=True.

    Now that stream_chat iterates ALL providers with fallback logic,
    we can test the real fallback path: primary fails → fallback yields chunks
    → done chunk has fallback_used: True.
    """
    from app.ai.prompt.safety import SafetyResult
    from app.services.meto_chat import MetoChatService

    # Primary provider: fails immediately
    async def _primary_fail(*args, **kwargs):
        raise RuntimeError("Primary provider unavailable")
        yield  # async generator

    primary = MagicMock()
    primary.provider_name = "primary_mock"
    primary.chat_stream = _primary_fail

    # Fallback provider: yields chunks successfully
    fallback_chunks = [
        ChatStreamChunk(delta="Fallback ", is_final=False),
        ChatStreamChunk(delta="đang hoạt động.", is_final=False),
        ChatStreamChunk(delta="", is_final=True, total_tokens=20),
    ]

    async def _fallback_stream(*args, **kwargs):
        for c in fallback_chunks:
            yield c

    fallback = MagicMock()
    fallback.provider_name = "fallback_mock"
    fallback.chat_stream = _fallback_stream

    # Registry returns BOTH providers so fallback logic kicks in
    registry = ProviderRegistry()
    registry.get_available_providers = MagicMock(return_value=[primary, fallback])

    svc = MetoChatService(registry)

    with (
        patch("app.services.meto_chat._CONTEXT_BUILDER") as mock_ctx,
        patch("app.services.meto_chat._SAFETY_GUARD") as mock_safety,
        patch("app.services.meto_chat._PROMPT_ASSEMBLER") as mock_prompt,
        patch("app.services.meto_chat._get_settings") as mock_settings,
    ):
        mock_ctx.build.return_value = _make_assembled_context()
        mock_safety.check_input.return_value = SafetyResult(safe=True)
        mock_safety.check_output.return_value = SafetyResult(safe=True)
        mock_prompt.assemble.return_value = (
            "system",
            [ChatMessage(role="user", content="test")],
        )
        mock_prompt._get_quick_prompts.return_value = []

        settings_mock = MagicMock()
        settings_mock.meto_max_tokens = 2048
        settings_mock.meto_temperature = 0.3
        # PROD-F10: stream_chat bounds each provider attempt with this timeout.
        settings_mock.meto_timeout_seconds = 30
        mock_settings.return_value = settings_mock

        collected = await _collect_chunks(
            svc.stream_chat(
                db=db,
                user_id=patient["user_id"],
                conversation_id=None,
                message="Huyết áp tôi thế nào?",
                screen_context=ScreenContext(screen_id="metrics"),
            )
        )

    # Primary failed, fallback succeeded → chunks from fallback
    chunk_events = [c for c in collected if c.get("type") == "chunk"]
    assert len(chunk_events) >= 1, f"Expected chunks from fallback provider, got: {collected}"

    # done chunk must have fallback_used=True
    done_events = [c for c in collected if c.get("type") == "done"]
    assert len(done_events) == 1, f"Expected exactly one done event, got: {collected}"
    assert done_events[0].get("fallback_used") is True, (
        f"done chunk must have fallback_used=True when fallback was used. Got: {done_events[0]}"
    )
    assert done_events[0].get("conversation_id"), "done event must include conversation_id"
