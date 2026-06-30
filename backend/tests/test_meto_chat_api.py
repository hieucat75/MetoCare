"""Tests for Meto AI chat API and service orchestration."""

from __future__ import annotations

import datetime as dt
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.ai.context.schemas import ScreenContext
from app.ai.providers.base import ChatMessage, ChatResponse
from app.ai.registry import ProviderRegistry
from app.schemas.meto import EscalationInfo, MetaChatResponse

# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

def _make_mock_registry(response_content: str = "Meto response") -> ProviderRegistry:
    """Create a mock ProviderRegistry that returns a canned response."""
    registry = MagicMock(spec=ProviderRegistry)
    mock_response = ChatResponse(
        content=response_content,
        tool_calls=None,
        input_tokens=20,
        output_tokens=15,
        model_used="mock-v1",
        finish_reason="stop",
        latency_ms=100,
        provider="mock",
    )
    registry.call_with_fallback = AsyncMock(return_value=(mock_response, "claude", False))
    registry.get_available_providers.return_value = []
    return registry


def _make_mock_db():
    """Create a minimal SQLAlchemy Session mock."""
    db = MagicMock()
    # Default: no conversations found
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.all.return_value = []
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

    # Make add/commit/refresh work
    db.add.return_value = None
    db.commit.return_value = None

    def _refresh(obj):
        if not hasattr(obj, "id") or obj.id is None:
            obj.id = "test-conv-id"
        if not hasattr(obj, "created_at") or obj.created_at is None:
            obj.created_at = dt.datetime.now(dt.UTC)
        if not hasattr(obj, "last_active_at"):
            obj.last_active_at = dt.datetime.now(dt.UTC)

    db.refresh.side_effect = _refresh
    return db


# ---------------------------------------------------------------------------
# Tests: MetoChatService
# ---------------------------------------------------------------------------

class TestMetoChatService:
    """Test chat service with mocked provider and DB."""

    @pytest.mark.asyncio
    async def test_chat_returns_response(self):
        from app.services.meto_chat import MetoChatService

        registry = _make_mock_registry("Kết quả HbA1c của bạn ổn.")
        svc = MetoChatService(registry)
        db = _make_mock_db()
        screen = ScreenContext(screen_id="labs")

        with patch("app.services.meto_chat._CONTEXT_BUILDER") as mock_ctx, \
             patch("app.services.meto_chat._SAFETY_GUARD") as mock_safety, \
             patch("app.services.meto_chat._PROMPT_ASSEMBLER") as mock_prompt, \
             patch("app.services.meto_chat._get_settings") as mock_settings:

            # Mock context builder
            from app.ai.context.schemas import AssembledContext
            mock_ctx.build.return_value = AssembledContext(
                user_profile={"display_name": "Test User", "preferred_address": "bạn"},
                health_summary=None,
                care_plan=None,
                medications=None,
                recent_labs=None,
                recent_metrics=None,
                screen_context={"screen_id": "labs"},
                today_context={},
                safety_flags=[],
                total_estimated_tokens=200,
                missing_consents=[],
                included_blocks=["user_profile", "screen_context"],
            )

            # Mock safety guard — all safe
            from app.ai.prompt.safety import SafetyResult
            mock_safety.check_input.return_value = SafetyResult(safe=True)
            mock_safety.check_output.return_value = SafetyResult(safe=True)

            # Mock prompt assembler
            mock_prompt.assemble.return_value = ("system", [ChatMessage(role="user", content="test")])
            mock_prompt.generate_conversation_title.return_value = "Test conversation"
            mock_prompt._get_quick_prompts.return_value = ["Chip 1", "Chip 2"]

            # Mock settings
            mock_settings_instance = MagicMock()
            mock_settings_instance.meto_max_tokens = 2048
            mock_settings_instance.meto_temperature = 0.3
            mock_settings.return_value = mock_settings_instance

            result = await svc.chat(
                db=db,
                user_id="user-123",
                conversation_id=None,
                message="HbA1c của tôi thế nào?",
                screen_context=screen,
            )

        assert isinstance(result, MetaChatResponse)
        assert result.content == "Kết quả HbA1c của bạn ổn."
        assert result.provider_used == "meto"  # Never exposes actual provider
        assert result.fallback_used is False

    @pytest.mark.asyncio
    async def test_emergency_message_returns_escalation_without_calling_ai(self):
        from app.services.meto_chat import MetoChatService

        registry = _make_mock_registry()
        svc = MetoChatService(registry)
        db = _make_mock_db()
        screen = ScreenContext(screen_id="dashboard")

        with patch("app.services.meto_chat._CONTEXT_BUILDER") as mock_ctx, \
             patch("app.services.meto_chat._SAFETY_GUARD") as mock_safety:

            from app.ai.context.schemas import AssembledContext
            mock_ctx.build.return_value = AssembledContext(
                user_profile=None,
                health_summary=None,
                care_plan=None,
                medications=None,
                recent_labs=None,
                recent_metrics=None,
                screen_context={"screen_id": "dashboard"},
                today_context={},
                safety_flags=[],
                total_estimated_tokens=100,
                missing_consents=[],
                included_blocks=[],
            )

            from app.ai.prompt.safety import SafetyResult
            # Simulate emergency detection
            mock_safety.check_input.return_value = SafetyResult(
                safe=False,
                flags=["đau ngực"],
                escalation_required=True,
                escalation_tier="emergency",
                suggested_response="⚠️ Gọi 115 ngay!",
            )
            mock_safety.get_escalation_response.return_value = "⚠️ Gọi 115 ngay!"

            result = await svc.chat(
                db=db,
                user_id="user-123",
                conversation_id=None,
                message="Đau ngực rất nặng",
                screen_context=screen,
            )

        # AI provider should NOT have been called
        registry.call_with_fallback.assert_not_called()

        assert result.escalation is not None
        assert result.escalation.tier == "emergency"
        assert "115" in result.content
        assert result.provider_used == "meto"

    def test_provider_name_always_meto(self):
        """Ensure provider_used is always 'meto' in responses."""
        response = MetaChatResponse(
            conversation_id="conv-1",
            message_id="msg-1",
            content="Test response",
            provider_used="meto",
            fallback_used=False,
        )
        assert response.provider_used == "meto"


# ---------------------------------------------------------------------------
# Tests: Schemas validation
# ---------------------------------------------------------------------------

class TestMetoChatSchemas:
    def test_chat_request_valid(self):
        from app.schemas.meto import MetoChatRequest
        req = MetoChatRequest(message="Xét nghiệm tôi thế nào?")
        assert req.screen_id == "dashboard"
        assert req.stream is False

    def test_chat_request_max_length(self):
        from app.schemas.meto import MetoChatRequest
        with pytest.raises(Exception):
            MetoChatRequest(message="x" * 4001)

    def test_chat_request_min_length(self):
        from app.schemas.meto import MetoChatRequest
        with pytest.raises(Exception):
            MetoChatRequest(message="")

    def test_chat_response_defaults(self):
        response = MetaChatResponse(
            conversation_id="conv-1",
            message_id="msg-1",
            content="Hello",
        )
        assert response.safety_flags == []
        assert response.escalation is None
        assert response.provider_used == "meto"
        assert response.fallback_used is False
        assert response.quick_follow_ups == []

    def test_escalation_info(self):
        esc = EscalationInfo(
            tier="emergency",
            message="Gọi 115 ngay",
            emergency_contacts=["115"],
        )
        assert esc.tier == "emergency"
        assert "115" in esc.emergency_contacts


# ---------------------------------------------------------------------------
# Tests: Prompt assembler
# ---------------------------------------------------------------------------

class TestPromptAssembler:
    def setup_method(self):
        from app.ai.prompt.assembler import PromptAssembler
        self.assembler = PromptAssembler()

    def test_assemble_returns_system_and_messages(self):
        from app.ai.context.schemas import AssembledContext

        ctx = AssembledContext(
            user_profile={"display_name": "Nguyễn Văn A", "preferred_address": "anh"},
            health_summary=None,
            care_plan=None,
            medications=None,
            recent_labs=None,
            recent_metrics=None,
            screen_context={"screen_id": "dashboard"},
            today_context={},
            safety_flags=[],
            total_estimated_tokens=200,
            missing_consents=[],
            included_blocks=["user_profile", "screen_context"],
        )

        system, messages = self.assembler.assemble(
            context=ctx,
            user_message="Tôi cần làm gì hôm nay?",
            conversation_history=[],
            preferred_address="anh",
        )

        assert isinstance(system, str)
        assert len(system) > 100
        assert "Meto" in system
        assert len(messages) >= 1
        assert messages[-1].role == "user"
        assert "hôm nay" in messages[-1].content

    def test_assemble_system_contains_forbidden_phrases(self):
        """System prompt must contain prohibition on diagnosis."""
        from app.ai.prompt.assembler import SYSTEM_PROMPT

        assert "chẩn đoán" in SYSTEM_PROMPT.lower() or "không" in SYSTEM_PROMPT.lower()
        assert "meto" in SYSTEM_PROMPT.lower()

    def test_history_included_in_messages(self):
        from app.ai.context.schemas import AssembledContext

        ctx = AssembledContext(
            user_profile=None,
            health_summary=None,
            care_plan=None,
            medications=None,
            recent_labs=None,
            recent_metrics=None,
            screen_context={"screen_id": "dashboard"},
            today_context={},
            safety_flags=[],
            total_estimated_tokens=100,
            missing_consents=[],
            included_blocks=[],
        )

        history = [
            {"role": "user", "content": "Câu hỏi 1"},
            {"role": "assistant", "content": "Trả lời 1"},
        ]

        _, messages = self.assembler.assemble(
            context=ctx,
            user_message="Câu hỏi 2",
            conversation_history=history,
        )

        # Should contain history + new message
        assert len(messages) == 3
        assert messages[0].role == "user"
        assert messages[1].role == "assistant"
        assert messages[2].role == "user"
        assert messages[2].content == "Câu hỏi 2"

    def test_generate_conversation_title_short(self):
        title = self.assembler.generate_conversation_title("HbA1c?")
        assert title == "HbA1c?"

    def test_generate_conversation_title_long(self):
        long_msg = "Kết quả xét nghiệm máu của tôi tuần trước có các chỉ số bất thường, "
        long_msg += "đặc biệt là glucose và cholesterol. Bác sĩ nói tôi cần theo dõi thêm."
        title = self.assembler.generate_conversation_title(long_msg)
        assert len(title) <= 55  # 50 chars + "..."
        assert title.endswith("...")
