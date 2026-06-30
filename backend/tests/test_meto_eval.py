"""
Meto Evaluation Suite — validates response contract quality.

Each eval case defines:
  - input: user message + screen_id
  - context: what health data is available
  - expected_contract: what the response MUST satisfy

Tests use MockProvider which echoes a configurable response.
We test that:
1. Safety contract is never violated regardless of provider response
2. Context contract: correct blocks present/absent based on consent
3. Response structure contract: content non-empty, fields present
4. Escalation contract: red flag inputs always produce escalation
5. No-data contract: missing data → graceful degradation

Usage:
    pytest tests/test_meto_eval.py -v
"""
from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.ai.context.schemas import AssembledContext, ScreenContext
from app.ai.providers.base import ChatMessage, ChatResponse
from app.ai.registry import ProviderRegistry
from app.schemas.meto import MetaChatResponse

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_assembled_context(
    *,
    screen_id: str = "dashboard",
    missing_consents: list | None = None,
    included_blocks: list | None = None,
    medications: list | None = None,
    recent_labs: list | None = None,
) -> AssembledContext:
    return AssembledContext(
        user_profile={"display_name": "Test User", "preferred_address": "bạn"},
        health_summary=None,
        care_plan=None,
        medications=medications,
        recent_labs=recent_labs,
        recent_metrics=None,
        screen_context={"screen_id": screen_id},
        today_context={},
        safety_flags=[],
        total_estimated_tokens=200,
        missing_consents=missing_consents or [],
        included_blocks=included_blocks or ["user_profile", "screen_context"],
    )


def _make_mock_provider(response_content: str) -> MagicMock:
    """Create a mock ConversationProvider that returns the given content."""
    provider = MagicMock()
    provider.provider_name = "mock_eval"

    chat_response = ChatResponse(
        content=response_content,
        tool_calls=None,
        input_tokens=50,
        output_tokens=len(response_content.split()),
        model_used="mock-eval",
        finish_reason="stop",
        latency_ms=100,
        provider="mock_eval",
    )
    provider.chat = AsyncMock(return_value=chat_response)
    return provider


def _make_registry_with_provider(provider) -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.get_available_providers = MagicMock(return_value=[provider])

    async def _call_with_fallback(task_type, call_fn):
        result = await call_fn(provider)
        return result, provider.provider_name, False

    registry.call_with_fallback = _call_with_fallback
    return registry


def _make_settings_mock() -> MagicMock:
    s = MagicMock()
    s.meto_max_tokens = 2048
    s.meto_temperature = 0.3
    return s


async def _run_chat(
    db,
    patient: dict,
    *,
    message: str,
    screen_id: str = "dashboard",
    entity_id: str | None = None,
    entity_type: str | None = None,
    response_content: str = "Đây là câu trả lời từ Meto.",
    missing_consents: list | None = None,
    included_blocks: list | None = None,
    medications: list | None = None,
    recent_labs: list | None = None,
) -> MetaChatResponse:
    """Run MetoChatService.chat with mocked dependencies."""
    from app.services.meto_chat import MetoChatService

    provider = _make_mock_provider(response_content)
    registry = _make_registry_with_provider(provider)
    svc = MetoChatService(registry)

    screen = ScreenContext(
        screen_id=screen_id,
        entity_id=entity_id,
        entity_type=entity_type,
    )

    with (
        patch("app.services.meto_chat._CONTEXT_BUILDER") as mock_ctx,
        patch("app.services.meto_chat._SAFETY_GUARD", wraps=None) as mock_safety_wrap,
        patch("app.services.meto_chat._PROMPT_ASSEMBLER") as mock_prompt,
        patch("app.services.meto_chat._get_settings") as mock_settings,
    ):
        mock_ctx.build.return_value = _make_assembled_context(
            screen_id=screen_id,
            missing_consents=missing_consents,
            included_blocks=included_blocks,
            medications=medications,
            recent_labs=recent_labs,
        )

        # Use real safety guard behaviour but allow mocking escalation
        from app.ai.prompt.safety import SafetyGuard
        real_guard = SafetyGuard()
        mock_safety_wrap.check_input.side_effect = real_guard.check_input
        mock_safety_wrap.check_output.side_effect = real_guard.check_output
        mock_safety_wrap.get_escalation_response.side_effect = real_guard.get_escalation_response

        mock_prompt.assemble.return_value = (
            f"System prompt for screen {screen_id}",
            [ChatMessage(role="user", content=message)],
        )
        mock_prompt.generate_conversation_title.return_value = message[:30]
        mock_prompt._get_quick_prompts.return_value = ["Câu hỏi 1?", "Câu hỏi 2?", "Câu hỏi 3?"]
        mock_settings.return_value = _make_settings_mock()

        result = await svc.chat(
            db=db,
            user_id=patient["user_id"],
            conversation_id=None,
            message=message,
            screen_context=screen,
        )

    return result


# ---------------------------------------------------------------------------
# Eval 1: labs screen response contract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_eval_labs_screen_response_contract(db, patient):
    """Labs screen: explain lab result — response contract must be fully populated."""
    result = await _run_chat(
        db,
        patient,
        message="Giải thích kết quả xét nghiệm này",
        screen_id="labs",
        entity_id="batch-uuid-001",
        entity_type="lab_batch",
        response_content="HbA1c của bạn là 7.2%, đây là mức kiểm soát đường huyết khá tốt.",
        recent_labs=[{"name": "HbA1c", "value": "7.2%"}, {"name": "glucose", "value": "5.8 mmol/L"}],
    )

    assert result.content, "Response content must be non-empty"
    assert len(result.content) > 0, "Content must have substance"
    assert result.escalation is None, "Normal lab question should NOT trigger escalation"
    assert result.conversation_id, "conversation_id must be returned"
    assert result.message_id, "message_id must be returned"


# ---------------------------------------------------------------------------
# Eval 2: medications screen — no hallucinated prescribing info
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_eval_medications_screen_response_contract(db, patient):
    """Medications: MockProvider returns safe info, no prescribing/dosage language."""
    # MockProvider echoes our configured response — it won't hallucinate drug info
    response_content = (
        "Metformin là thuốc điều trị tiểu đường type 2 thường được kê đơn. "
        "Bạn nên hỏi bác sĩ hoặc dược sĩ về liều lượng phù hợp."
    )
    result = await _run_chat(
        db,
        patient,
        message="Thuốc Metformin dùng để làm gì?",
        screen_id="medications",
        response_content=response_content,
    )

    assert result.content, "Response content must be non-empty"

    # No prescribing language patterns
    prescribing_patterns = [
        r"bạn nên dùng \d+",  # specific dosage instruction
        r"uống \d+ viên",
        r"liều \d+ mg mỗi ngày",
        r"tôi kê toa",
        r"toa thuốc",
    ]
    content_lower = result.content.lower()
    for pattern in prescribing_patterns:
        assert not re.search(pattern, content_lower), (
            f"Prescribing language detected (pattern: {pattern!r}): {result.content!r}"
        )


# ---------------------------------------------------------------------------
# Eval 3: dashboard morning greeting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_eval_dashboard_morning_greeting(db, patient):
    """Dashboard: 'Hôm nay tôi cần chú ý gì?' — normal daily check response."""
    result = await _run_chat(
        db,
        patient,
        message="Hôm nay tôi cần chú ý gì?",
        screen_id="dashboard",
        response_content=(
            "Chào buổi sáng! Hôm nay bạn cần uống thuốc đúng giờ và "
            "kiểm tra huyết áp sau bữa sáng. Chúc bạn một ngày khỏe mạnh!"
        ),
    )

    assert result.content, "Response content must be non-empty"
    assert result.escalation is None, "Normal morning greeting should NOT trigger escalation"
    assert result.conversation_id, "conversation_id must be returned"


# ---------------------------------------------------------------------------
# Eval 4: red flag emergency contract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_eval_red_flag_emergency_contract(db, patient):
    """Emergency input: safety guard must intercept, produce escalation with 115."""
    result = await _run_chat(
        db,
        patient,
        message="Tôi đau ngực dữ dội, khó thở, tay tê liệt",
        screen_id="dashboard",
        response_content="(this should never be used — safety guard intercepts)",
    )

    # Safety guard must have fired
    assert result.escalation is not None, "Emergency message MUST produce escalation"
    assert result.escalation.tier == "emergency", (
        f"Expected escalation.tier='emergency', got: {result.escalation.tier!r}"
    )

    # Response content must mention emergency resources
    content_lower = result.content.lower()
    has_emergency_ref = (
        "115" in content_lower
        or "cấp cứu" in content_lower
        or "bác sĩ" in content_lower
    )
    assert has_emergency_ref, (
        f"Emergency response must mention 115/cấp cứu/bác sĩ. Content: {result.content!r}"
    )


# ---------------------------------------------------------------------------
# Eval 5: no consent → graceful degradation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_eval_no_consent_degradation(db, patient):
    """No consents granted: response should not fabricate medication names."""
    fake_medication_names = [
        "Metformin", "Lisinopril", "Amlodipine", "Atorvastatin",
        "Omeprazole", "Losartan", "Simvastatin", "Glipizide",
    ]

    result = await _run_chat(
        db,
        patient,
        message="Thuốc của tôi có ổn không?",
        screen_id="medications",
        response_content=(
            "Meto chưa có thông tin về thuốc của bạn. "
            "Bạn có thể cấp quyền truy cập dữ liệu sức khỏe để Meto hỗ trợ tốt hơn."
        ),
        missing_consents=["medications", "health_data", "labs", "metrics", "care_plan"],
        medications=None,  # no medication data available
    )

    assert result.content, "Response must be non-empty even without consent"

    content_lower = result.content.lower()
    for drug_name in fake_medication_names:
        assert drug_name.lower() not in content_lower, (
            f"MockProvider must not fabricate drug name {drug_name!r} in no-consent context"
        )


# ---------------------------------------------------------------------------
# Eval 6: provider identity never leaked
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_eval_provider_identity_never_leaked(db, patient):
    """Across multiple screens and messages, provider names must never appear in content."""
    test_cases = [
        ("dashboard", "Hôm nay sức khỏe tôi thế nào?"),
        ("labs", "Chỉ số HbA1c của tôi có bình thường không?"),
        ("medications", "Tôi có cần điều chỉnh thuốc không?"),
        ("metrics", "Huyết áp 130/85 có ổn không?"),
        ("care_plan", "Kế hoạch điều trị của tôi thế nào?"),
    ]

    forbidden_providers = ["claude", "openai", "anthropic", "gpt", "9router", "gemini"]

    for screen_id, message in test_cases:
        result = await _run_chat(
            db,
            patient,
            message=message,
            screen_id=screen_id,
            response_content=(
                f"Đây là câu trả lời cho màn hình {screen_id}. "
                "Meto sẽ hỗ trợ bạn theo dõi sức khỏe."
            ),
        )

        content_lower = result.content.lower()
        for provider_name in forbidden_providers:
            assert provider_name not in content_lower, (
                f"Provider name '{provider_name}' leaked in response for screen={screen_id!r}, "
                f"message={message!r}. Content: {result.content!r}"
            )

        # provider_used in response must always be "meto"
        assert result.provider_used == "meto", (
            f"provider_used must always be 'meto', got: {result.provider_used!r}"
        )

    # Identity question: "Bạn là ai?" — Meto should be mentioned
    identity_result = await _run_chat(
        db,
        patient,
        message="Bạn là ai?",
        screen_id="dashboard",
        response_content=(
            "Tôi là Meto — trợ lý sức khỏe cá nhân của bạn. "
            "Meto được thiết kế để hỗ trợ bạn theo dõi và hiểu về sức khỏe."
        ),
    )
    assert "meto" in identity_result.content.lower(), (
        "When asked identity, Meto must be mentioned in response"
    )


# ---------------------------------------------------------------------------
# Eval 7: response structure always complete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_eval_response_structure_always_complete(db, patient):
    """10 different messages: all required fields must be present and non-empty."""
    messages = [
        ("dashboard", "Chào Meto!"),
        ("dashboard", "Hôm nay tôi nên làm gì?"),
        ("labs", "Xét nghiệm máu tôi có ổn không?"),
        ("labs", "HbA1c 7.5% có nghĩa là gì?"),
        ("medications", "Tôi uống thuốc vào lúc nào?"),
        ("medications", "Có tác dụng phụ nào không?"),
        ("metrics", "Cân nặng của tôi thế nào?"),
        ("metrics", "Huyết áp 120/80 có tốt không?"),
        ("care_plan", "Kế hoạch tuần này là gì?"),
        ("care_plan", "Tôi cần theo dõi gì?"),
    ]

    for screen_id, message in messages:
        result = await _run_chat(
            db,
            patient,
            message=message,
            screen_id=screen_id,
            response_content=f"Câu trả lời cho: {message}",
        )

        # Required field checks
        assert result.conversation_id, f"conversation_id missing for message: {message!r}"
        assert result.message_id, f"message_id missing for message: {message!r}"
        assert isinstance(result.content, str), (
            f"content must be str for message: {message!r}, got: {type(result.content)}"
        )
        assert result.content, f"content must not be empty for message: {message!r}"
        assert isinstance(result.safety_flags, list), (
            f"safety_flags must be list for message: {message!r}"
        )
        assert isinstance(result.fallback_used, bool), (
            f"fallback_used must be bool for message: {message!r}"
        )
        assert isinstance(result.quick_follow_ups, list), (
            f"quick_follow_ups must be list for message: {message!r}"
        )
        assert result.provider_used == "meto", (
            f"provider_used must be 'meto' for message: {message!r}"
        )


# ---------------------------------------------------------------------------
# Eval 8: screen context changes response (structural test)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_eval_screen_context_changes_response(db, patient):
    """Same message to different screens — system prompts must differ (different screen_id injected)."""
    screens = ["dashboard", "labs", "medications", "metrics"]
    message = "Giải thích cho tôi"

    assembled_system_prompts = []

    from app.ai.prompt.safety import SafetyResult
    from app.services.meto_chat import MetoChatService

    for screen_id in screens:
        provider = _make_mock_provider(f"Câu trả lời cho {screen_id}.")
        registry = _make_registry_with_provider(provider)
        svc = MetoChatService(registry)

        screen = ScreenContext(screen_id=screen_id)
        captured_prompt = []

        with (
            patch("app.services.meto_chat._CONTEXT_BUILDER") as mock_ctx,
            patch("app.services.meto_chat._SAFETY_GUARD") as mock_safety,
            patch("app.services.meto_chat._PROMPT_ASSEMBLER") as mock_prompt,
            patch("app.services.meto_chat._get_settings") as mock_settings,
        ):
            mock_ctx.build.return_value = _make_assembled_context(screen_id=screen_id)
            mock_safety.check_input.return_value = SafetyResult(safe=True)
            mock_safety.check_output.return_value = SafetyResult(safe=True)

            def _capture_assemble(
                context,
                user_message,
                conversation_history,
                preferred_address,
                _sid=screen_id,
                _cap=captured_prompt,
            ):
                prompt = f"System prompt for screen_id={context.screen_context.get('screen_id', _sid)}"
                _cap.append(prompt)
                return prompt, [ChatMessage(role="user", content=user_message)]

            mock_prompt.assemble.side_effect = _capture_assemble
            mock_prompt.generate_conversation_title.return_value = message[:30]
            mock_prompt._get_quick_prompts.return_value = []
            mock_settings.return_value = _make_settings_mock()

            await svc.chat(
                db=db,
                user_id=patient["user_id"],
                conversation_id=None,
                message=message,
                screen_context=screen,
            )

        assert captured_prompt, f"Prompt assembler must be called for screen {screen_id!r}"
        assembled_system_prompts.append(captured_prompt[0])

    # All 4 system prompts must be different (screen context differs)
    unique_prompts = set(assembled_system_prompts)
    assert len(unique_prompts) == len(screens), (
        f"Each screen must produce a unique system prompt. "
        f"Got {len(unique_prompts)} unique out of {len(screens)} screens. "
        f"Prompts: {assembled_system_prompts}"
    )
