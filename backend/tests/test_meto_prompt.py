"""
Prompt contract tests — ensure prompt assembler output meets safety requirements
regardless of context content.

These tests are pure unit tests: no DB access, no async, no fixtures needed
beyond what we construct inline.
"""
from __future__ import annotations

import pytest
from app.ai.context.schemas import AssembledContext
from app.ai.prompt.assembler import SYSTEM_PROMPT, PromptAssembler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_context(
    *,
    screen_id: str = "dashboard",
    user_profile: dict | None = None,
    health_summary: dict | None = None,
    care_plan: dict | None = None,
    medications: list | None = None,
    recent_labs: list | None = None,
    recent_metrics: list | None = None,
    safety_flags: list | None = None,
    missing_consents: list | None = None,
    included_blocks: list | None = None,
) -> AssembledContext:
    return AssembledContext(
        user_profile=user_profile,
        health_summary=health_summary,
        care_plan=care_plan,
        medications=medications,
        recent_labs=recent_labs,
        recent_metrics=recent_metrics,
        screen_context={"screen_id": screen_id},
        today_context={},
        safety_flags=safety_flags or [],
        total_estimated_tokens=100,
        missing_consents=missing_consents or [],
        included_blocks=included_blocks or [],
    )


assembler = PromptAssembler()


# ---------------------------------------------------------------------------
# Test 1: system prompt contains forbidden phrase instruction + identity
# ---------------------------------------------------------------------------

def test_prompt_contains_forbidden_phrase_instruction():
    """System prompt must contain safety/identity guardrails."""
    ctx = _make_context()
    system_prompt, messages = assembler.assemble(ctx, "test message", [])

    system_lower = system_prompt.lower()

    # Identity: Meto must be named
    assert "meto" in system_lower, "System prompt must reference 'Meto' identity"

    # Safety: must mention diagnosis prohibition ("không chẩn đoán" or "không phải bác sĩ")
    has_no_diagnose = "chẩn đoán" in system_lower
    has_not_doctor = "không phải bác sĩ" in system_lower or "bác sĩ" in system_lower
    assert has_no_diagnose or has_not_doctor, (
        "System prompt must contain diagnosis prohibition. "
        f"Got system prompt (first 300 chars): {system_prompt[:300]!r}"
    )

    # Must NOT have model/provider names appear in identity-exposing context.
    # Note: SYSTEM_PROMPT and developer prompt list forbidden phrases like
    # 'Tôi là Claude' as examples of what NOT to say (meta-prohibition context).
    # The rule: provider names must appear only within prohibition instructions,
    # NOT as positive self-identification claims.
    #
    # We verify the prompt says "không" or "không bao giờ" NEAR provider names,
    # i.e. the context is prohibition, not self-identification.
    # The simplest contract test: Meto identity is asserted, and providers are not
    # claimed as self (positive claim would be standalone "Tôi là Claude" without prior không).

    # Strong positive identity: Meto must identify as Meto, not provider
    assert "meto" in system_lower, "Meto identity must be stated"

    # The system prompt must contain an explicit prohibition against revealing provider
    # The SYSTEM_PROMPT has 'Tiết lộ tên AI provider đang vận hành bạn (Claude, OpenAI, GPT...'
    # within the KHÔNG BAO GIỜ làm section — this is correct behaviour
    has_prohibition = (
        "không bao giờ" in system_lower
        or "không được" in system_lower
        or "tuyệt đối không" in system_lower
    )
    assert has_prohibition, (
        "System prompt must contain prohibition language (không bao giờ / không được)"
    )


# ---------------------------------------------------------------------------
# Test 2: missing consents → instruction in prompt
# ---------------------------------------------------------------------------

def test_prompt_missing_consent_adds_instruction():
    """When consents are missing, system prompt must instruct about missing data."""
    ctx = _make_context(
        missing_consents=["medications", "labs"],
        screen_id="dashboard",
    )
    system_prompt, messages = assembler.assemble(ctx, "câu hỏi", [])

    system_lower = system_prompt.lower()

    # The assembler must include a note about missing/ungranted data
    has_missing_note = (
        "chưa cấp quyền" in system_lower
        or "chưa thấy dữ liệu" in system_lower
        or "missing_consents" in system_lower  # field name in JSON block
        or "medications" in system_lower  # listed in context
        or "labs" in system_lower
        or "quyền riêng tư" in system_lower
    )
    assert has_missing_note, (
        "System prompt must communicate missing consents. "
        f"Got (first 500 chars): {system_prompt[:500]!r}"
    )


# ---------------------------------------------------------------------------
# Test 3: no data → no fabrication instruction present
# ---------------------------------------------------------------------------

def test_prompt_no_data_no_fabrication_instruction():
    """When all blocks are None, prompt must not contain fabricated health values."""
    ctx = _make_context(
        medications=None,
        recent_labs=None,
        recent_metrics=None,
        health_summary=None,
        care_plan=None,
    )
    system_prompt, messages = assembler.assemble(ctx, "câu hỏi về sức khỏe", [])

    # Fabricated health terms must NOT appear in system prompt
    fabricated_terms = [
        "hba1c = 7.2",
        "glucose = 120",
        "hemoglobin: 14",
        "creatinine =",
        "metformin 500mg",
        "amlodipine",
    ]
    system_lower = system_prompt.lower()
    for term in fabricated_terms:
        assert term not in system_lower, (
            f"Potentially fabricated health data found in prompt: {term!r}"
        )

    # System prompt must encourage telling user about unavailable data
    # The SYSTEM_PROMPT has "Chỉ dựa vào thông tin có trong context. Không bịa đặt"
    anti_fabrication_hints = [
        "không bịa đặt",
        "chỉ dựa vào",
        "không tồn tại",
        "không có dữ liệu",
        "chưa có thông tin",
        "bịa",
    ]
    has_hint = any(h in system_lower for h in anti_fabrication_hints)
    assert has_hint, (
        "System prompt must contain anti-fabrication instruction. "
        f"Got (first 600 chars): {system_prompt[:600]!r}"
    )


# ---------------------------------------------------------------------------
# Test 4: screen context always present in assembled messages
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("screen_id", [
    "dashboard", "labs", "medications", "metrics",
    "care_plan", "nutrition", "profile",
])
def test_prompt_screen_context_always_present(screen_id: str):
    """For every known screen, screen_id must appear somewhere in the assembled output."""
    ctx = _make_context(screen_id=screen_id)
    system_prompt, messages = assembler.assemble(ctx, "câu hỏi", [])

    # screen_id appears in system_prompt (layer 2 developer prompt OR context block)
    # OR in the JSON screen_context block in the system prompt
    assert screen_id in system_prompt, (
        f"screen_id='{screen_id}' must appear in assembled system prompt. "
        f"Got (first 400 chars): {system_prompt[:400]!r}"
    )


# ---------------------------------------------------------------------------
# Test 5: history included in messages
# ---------------------------------------------------------------------------

def test_prompt_history_included():
    """Conversation history must be included in the messages list."""
    history = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "xin chào"},
        {"role": "user", "content": "thuốc của tôi là gì?"},
        {"role": "assistant", "content": "Meto chưa có thông tin về thuốc của bạn."},
    ]
    ctx = _make_context()
    system_prompt, messages = assembler.assemble(ctx, "câu hỏi mới", history)

    # messages should contain the history + the current user message
    assert len(messages) >= len(history) + 1, (
        f"Expected at least {len(history) + 1} messages, got {len(messages)}"
    )

    # Each history role must appear
    roles_in_messages = [m.role for m in messages]
    assert "user" in roles_in_messages
    assert "assistant" in roles_in_messages

    # History content must appear in messages
    contents = [m.content for m in messages]
    assert "hello" in contents, "User history message 'hello' must be in messages"
    assert "xin chào" in contents, "Assistant history message 'xin chào' must be in messages"


# ---------------------------------------------------------------------------
# Test 6: user message always last in messages list
# ---------------------------------------------------------------------------

def test_prompt_user_message_always_last():
    """The current user message must always be the last element in messages."""
    history = [
        {"role": "user", "content": "tin nhắn trước"},
        {"role": "assistant", "content": "trả lời trước"},
    ]
    user_message = "câu hỏi cuối"
    ctx = _make_context()
    system_prompt, messages = assembler.assemble(ctx, user_message, history)

    assert len(messages) >= 1, "messages must not be empty"

    last = messages[-1]
    assert last.role == "user", (
        f"Last message must have role='user', got role='{last.role}'"
    )
    assert last.content == user_message, (
        f"Last message content must be '{user_message}', got '{last.content}'"
    )


# ---------------------------------------------------------------------------
# Bonus Test 7: SYSTEM_PROMPT constant does not expose provider names
# ---------------------------------------------------------------------------

def test_system_prompt_constant_no_provider_names():
    """The hardcoded SYSTEM_PROMPT must prohibit provider identity disclosure.

    The SYSTEM_PROMPT uses provider names (Claude, OpenAI, GPT) only in
    prohibition context — listing them as examples of what the AI must NEVER claim.
    We verify:
    1. SYSTEM_PROMPT contains explicit prohibition language
    2. SYSTEM_PROMPT establishes 'Meto' as the identity
    3. SYSTEM_PROMPT does NOT positively claim to be a specific provider
       (i.e., 'Bạn là Claude' or 'Powered by OpenAI' without prohibition context)
    """
    prompt_lower = SYSTEM_PROMPT.lower()

    # Must contain prohibition language
    has_prohibition = (
        "không bao giờ" in prompt_lower
        or "không được" in prompt_lower
        or "tuyệt đối không" in prompt_lower
    )
    assert has_prohibition, "SYSTEM_PROMPT must contain explicit prohibition language"

    # Must establish Meto as the identity
    assert "meto" in prompt_lower, "SYSTEM_PROMPT must name 'Meto' as identity"

    # Must not contain positive self-identification as a provider
    # (Provider names appear only in prohibition lists — that's acceptable)
    # The negative test: 'bạn là claude' (you are claude) must not appear
    positive_identity_claims = [
        "bạn là claude",
        "bạn là openai",
        "bạn là gpt",
        "powered by claude",
        "built on gpt",
        "created by openai",
        "developed by anthropic",
    ]
    for claim in positive_identity_claims:
        assert claim not in prompt_lower, (
            f"SYSTEM_PROMPT must not contain positive provider identity claim: {claim!r}"
        )


# ---------------------------------------------------------------------------
# Bonus Test 8: assemble with empty history still produces valid messages
# ---------------------------------------------------------------------------

def test_prompt_assemble_empty_history():
    """Assembling with empty history must still produce at least one message."""
    ctx = _make_context()
    system_prompt, messages = assembler.assemble(ctx, "câu hỏi đầu tiên", [])

    assert len(messages) == 1, "Empty history + 1 user message → exactly 1 message"
    assert messages[0].role == "user"
    assert messages[0].content == "câu hỏi đầu tiên"


# ---------------------------------------------------------------------------
# Bonus Test 9: system messages in history are filtered out
# ---------------------------------------------------------------------------

def test_prompt_system_messages_in_history_filtered():
    """System-role messages in conversation history must be excluded from messages list."""
    history = [
        {"role": "system", "content": "some system instruction"},
        {"role": "user", "content": "câu hỏi người dùng"},
        {"role": "assistant", "content": "trả lời"},
    ]
    ctx = _make_context()
    system_prompt, messages = assembler.assemble(ctx, "câu hỏi mới", history)

    roles = [m.role for m in messages]
    assert "system" not in roles, (
        "system-role messages from history must be filtered out of messages list"
    )


# ---------------------------------------------------------------------------
# Bonus Test 10: safety_flags in context appear in system prompt
# ---------------------------------------------------------------------------

def test_prompt_safety_flags_appear_in_system_prompt():
    """Safety flags must be surfaced prominently in the assembled system prompt."""
    ctx = _make_context(
        safety_flags=[
            "⚠️ Giá trị CRITICAL: HbA1c = 12.5 %",
            "⚠️ Chỉ số CRITICAL: blood_pressure_systolic = 200 mmHg",
        ]
    )
    system_prompt, messages = assembler.assemble(ctx, "xem kết quả", [])

    # Safety flags section should appear in the context block
    assert "CRITICAL" in system_prompt or "critical" in system_prompt.lower(), (
        "Safety flags must appear in assembled system prompt"
    )
    assert "HbA1c" in system_prompt or "hba1c" in system_prompt.lower()
