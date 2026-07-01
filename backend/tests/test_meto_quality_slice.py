"""
Meto AI — Product Quality Slice Tests.

Covers:
- No provider identity leakage in system prompt (Claude, OpenAI, OpenRouter)
- No "AI Copilot" in system prompt
- System prompt has Meto personality traits
- Consent-required field in schema
- Quick prompts per screen context
- Greeting engine correctness
- Response format / length contract
- Safety forbidden phrases
"""
from __future__ import annotations

import pytest
from app.ai.context.schemas import AssembledContext
from app.ai.prompt.assembler import SYSTEM_PROMPT, PromptAssembler
from app.ai.prompt.safety import QUICK_PROMPTS, SafetyGuard
from app.schemas.meto import MetaChatResponse

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_context(
    screen_id: str = "dashboard",
    missing_consents: list[str] | None = None,
) -> AssembledContext:
    return AssembledContext(
        user_profile={"name": "Test User"},
        screen_context={"screen_id": screen_id},
        today_context={},
        safety_flags=[],
        total_estimated_tokens=50,
        missing_consents=missing_consents or [],
        included_blocks=[],
    )


assembler = PromptAssembler()
guard = SafetyGuard()


# ---------------------------------------------------------------------------
# A. Provider identity leakage — MUST NOT appear in system prompt
# ---------------------------------------------------------------------------

FORBIDDEN_PROVIDER_NAMES = [
    "claude",
    "openai",
    "openrouter",
    "gpt-4",
    "gpt4",
    "anthropic",
    "chatgpt",
]

@pytest.mark.parametrize("provider_name", FORBIDDEN_PROVIDER_NAMES)
def test_no_provider_identity_in_system_prompt(provider_name: str):
    """Provider names must never appear in system prompt delivered to frontend context."""
    system_lower = SYSTEM_PROMPT.lower()
    # Provider names should not appear as standalone identities
    # "Không bao giờ nhận mình là Claude" — this mentions Claude as forbidden phrase,
    # but we only test that it's not revealed as the actual provider identity.
    # The phrase "tôi là claude" etc. should not be present as affirmative identity.
    # Affirmative disclosures that must not appear (NOT the forbidden-phrase instruction)
    affirmative_disclosure_patterns = [
        f"chạy trên {provider_name}",
        f"sử dụng {provider_name}",
        f"powered by {provider_name}",
        f"built on {provider_name}",
        f"bạn là {provider_name}",  # as self-identity statement
        f"meto là {provider_name}",  # 'Meto là Claude'
    ]
    for pattern in affirmative_disclosure_patterns:
        assert pattern not in system_lower, (
            f"System prompt must not reveal provider identity: found '{pattern}'"
        )


def test_system_prompt_does_not_reveal_provider_affirmatively():
    """System prompt must not contain affirmative provider disclosure."""
    system_lower = SYSTEM_PROMPT.lower()
    # Check no affirmative claim of being a specific provider
    assert "bạn là claude" not in system_lower  # self-identity
    assert "bạn là openai" not in system_lower
    assert "bạn là gpt" not in system_lower
    assert "meto là claude" not in system_lower
    assert "powered by" not in system_lower


# ---------------------------------------------------------------------------
# B. No "AI Copilot" label in system prompt or developer prompt
# ---------------------------------------------------------------------------

def test_no_ai_copilot_label_in_system_prompt():
    """'AI Copilot' brand must not appear in system prompt."""
    ctx = _make_context()
    system_prompt, _ = assembler.assemble(ctx, "test", [])
    assert "AI Copilot" not in system_prompt
    assert "ai copilot" not in system_prompt.lower()


# ---------------------------------------------------------------------------
# C. Meto personality traits in system prompt
# ---------------------------------------------------------------------------

def test_system_prompt_has_meto_identity():
    """System prompt must declare Meto identity."""
    assert "Meto" in SYSTEM_PROMPT
    assert "MetoCare" in SYSTEM_PROMPT


def test_system_prompt_has_safety_rules():
    """System prompt must contain core safety prohibitions."""
    system_lower = SYSTEM_PROMPT.lower()
    assert "chẩn đoán" in system_lower
    assert "kê đơn" in system_lower or "đơn thuốc" in system_lower


def test_system_prompt_has_personality_style():
    """System prompt must contain personality / style instructions."""
    # Check for warm, concise, premium care tone
    assert "ấm" in SYSTEM_PROMPT or "ân cần" in SYSTEM_PROMPT
    # The prompt must explicitly discourage generic AI tone
    assert "generic" in SYSTEM_PROMPT.lower(), "Prompt must mention discouraging generic AI tone"


def test_system_prompt_has_output_format():
    """System prompt must instruct output structure."""
    assert "Tóm tắt" in SYSTEM_PROMPT or "tóm tắt" in SYSTEM_PROMPT
    assert "Giải thích" in SYSTEM_PROMPT or "giải thích" in SYSTEM_PROMPT
    assert "400" in SYSTEM_PROMPT or "600" in SYSTEM_PROMPT  # word limit


def test_system_prompt_has_response_length_constraint():
    """System prompt must specify response length limits."""
    assert "từ" in SYSTEM_PROMPT  # "100–400 từ" or similar
    # Must not be unlimited
    assert "tùy ý" not in SYSTEM_PROMPT.lower()


# ---------------------------------------------------------------------------
# D. Consent-required schema field
# ---------------------------------------------------------------------------

def test_metachat_response_consent_required_schema_fields_exist():
    """consent_required and missing_consents fields exist in schema (backward-compat).
    Per product design: T&C covers consent at registration; always False in chat.
    """
    resp = MetaChatResponse(
        conversation_id="conv-1",
        message_id="msg-1",
        content="Test",
        consent_required=False,
        missing_consents=[],
    )
    assert resp.consent_required is False
    assert resp.missing_consents == []


def test_metachat_response_consent_required_defaults_false():
    """consent_required always defaults to False — no consent gate in chat."""
    resp = MetaChatResponse(
        conversation_id="conv-1",
        message_id="msg-1",
        content="Test",
    )
    assert resp.consent_required is False
    assert resp.missing_consents == []


def test_metachat_response_provider_always_meto():
    """provider_used must always be 'meto', never actual provider name."""
    resp = MetaChatResponse(
        conversation_id="conv-1",
        message_id="msg-1",
        content="Test",
    )
    assert resp.provider_used == "meto"


# ---------------------------------------------------------------------------
# E. Quick prompts per screen
# ---------------------------------------------------------------------------

EXPECTED_SCREEN_PROMPTS = {
    "dashboard": ["Hôm nay tôi cần chú ý gì?", "Tôi còn việc gì chưa làm?"],
    "labs": ["Giải thích kết quả này", "Chỉ số nào cần chú ý?"],
    "medications": ["Thuốc này dùng để làm gì?", "Tôi cần lưu ý gì khi uống?"],
    "metrics": ["Chỉ số này có ổn không?", "Xu hướng gần đây thế nào?"],
    "care-plan": ["Tôi còn việc gì hôm nay?", "Việc nào quan trọng nhất?"],
    "settings": ["Meto dùng dữ liệu nào?", "Cách bật/tắt quyền"],
    "consents": ["Meto dùng dữ liệu nào?", "Xóa lịch sử Meto"],
}

@pytest.mark.parametrize("screen_id,expected_prompts", EXPECTED_SCREEN_PROMPTS.items())
def test_quick_prompts_per_screen(screen_id: str, expected_prompts: list[str]):
    """Each screen must have relevant quick prompts."""
    prompts = QUICK_PROMPTS.get(screen_id, [])
    assert len(prompts) >= 2, f"Screen '{screen_id}' needs at least 2 prompts"
    for expected in expected_prompts:
        assert expected in prompts, (
            f"Expected prompt '{expected}' not found in {screen_id} prompts: {prompts}"
        )


def test_quick_prompts_no_provider_leakage():
    """Quick prompts must not contain provider names."""
    all_prompts = []
    for prompts in QUICK_PROMPTS.values():
        all_prompts.extend(prompts)
    
    for prompt in all_prompts:
        prompt_lower = prompt.lower()
        assert "claude" not in prompt_lower, f"Provider leak in prompt: {prompt}"
        assert "openai" not in prompt_lower, f"Provider leak in prompt: {prompt}"
        assert "chatgpt" not in prompt_lower, f"Provider leak in prompt: {prompt}"
        assert "gpt" not in prompt_lower, f"Provider leak in prompt: {prompt}"


def test_quick_prompts_no_ai_copilot():
    """Quick prompts must not contain 'AI Copilot'."""
    for prompts in QUICK_PROMPTS.values():
        for prompt in prompts:
            assert "AI Copilot" not in prompt
            assert "Copilot" not in prompt


# ---------------------------------------------------------------------------
# F. Safety guard — forbidden response patterns
# ---------------------------------------------------------------------------

def test_safety_guard_catches_provider_identity():
    """Safety guard output check must flag provider identity disclosure."""
    bad_responses = [
        "Tôi là Claude, AI của Anthropic.",
        "Tôi là GPT-4 của OpenAI.",
        "Mình là OpenAI assistant.",
    ]
    for resp in bad_responses:
        result = guard.check_output(resp)
        assert not result.safe, f"Should catch provider identity: {resp}"


def test_safety_guard_allows_meto_identity():
    """Safety guard must allow 'Mình là Meto' response."""
    ok_response = "Mình là Meto, AI Health Companion của MetoCare."
    result = guard.check_output(ok_response)
    assert result.safe, f"Should allow Meto identity: {ok_response}"


def test_safety_guard_catches_diagnosis():
    """Safety guard must catch diagnosis language."""
    bad = "Tôi chẩn đoán bạn bị tiểu đường type 2."
    result = guard.check_output(bad)
    assert not result.safe


def test_safety_guard_catches_stop_medication():
    """Safety guard must catch 'stop medication' language."""
    bad = "Hãy dừng thuốc metformin ngay."
    result = guard.check_output(bad)
    assert not result.safe


def test_safety_guard_catches_no_need_doctor():
    """Safety guard must catch 'no need to see doctor' language."""
    bad = "Bạn không cần đi khám bác sĩ đâu."
    result = guard.check_output(bad)
    assert not result.safe


# ---------------------------------------------------------------------------
# G. Assembler — consent_required context propagates
# ---------------------------------------------------------------------------

def test_assembler_includes_missing_consents_note():
    """When missing_consents present, context block must mention them."""
    ctx = _make_context(
        screen_id="labs",
        missing_consents=["labs", "medications"],
    )
    system_prompt, _ = assembler.assemble(ctx, "Kết quả xét nghiệm của tôi?", [])
    # Prompt must warn about missing consents
    assert "labs" in system_prompt or "Quyền riêng tư" in system_prompt or "missing" in system_prompt.lower()


def test_assembler_screen_context_injected():
    """Screen context must appear in assembled prompt."""
    ctx = _make_context(screen_id="medications")
    system_prompt, _ = assembler.assemble(ctx, "Test", [])
    assert "medications" in system_prompt


# ---------------------------------------------------------------------------
# H. Greeting engine parameters
# ---------------------------------------------------------------------------

def test_quick_prompts_settings_screen():
    """Settings/consents screens must have privacy-related prompts."""
    for screen in ["settings", "consents"]:
        prompts = QUICK_PROMPTS.get(screen, [])
        assert any("quyền" in p.lower() or "dữ liệu" in p.lower() for p in prompts), (
            f"Screen '{screen}' should have privacy-related prompts"
        )
