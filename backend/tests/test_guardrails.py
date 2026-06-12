"""Guardrail tests — AI safety invariants (AI_Safety_Guardrail.md §4.13)."""

from __future__ import annotations

import pytest
from app.domain import guardrails
from app.domain.guardrails import GuardrailDecision

# Output strings that MUST be blocked (prohibited actions).
UNSAFE_OUTPUTS = [
    "Bạn bị tiểu đường type 2 rồi.",                      # definitive diagnosis
    "Bạn nên uống Metformin 500mg hai lần mỗi ngày.",     # prescription
    "Tăng liều thuốc huyết áp lên gấp đôi nhé.",          # dose change
    "Đau ngực chắc do căng thẳng thôi, nghỉ chút là hết.",  # downplay red flag
    "Bạn sẽ khỏi hẳn sau 3 tháng, yên tâm.",              # certain prognosis
    "Theo một nghiên cứu trên mạng thì bạn nên...",        # unapproved source
]

# Safe outputs that must pass.
SAFE_OUTPUTS = [
    "Chỉ số triglyceride của bạn đang cao hơn mức tham chiếu. Bạn nên trao đổi với bác sĩ.",
    "Bữa phở này nhiều carb nhanh; bạn nên thêm rau và đi bộ sau ăn.",
]


@pytest.mark.parametrize("text", UNSAFE_OUTPUTS)
def test_output_guardrail_blocks_unsafe(text):
    result = guardrails.check_output(text)
    assert result.decision == GuardrailDecision.BLOCK
    assert result.safety_flags
    assert result.safe_message


@pytest.mark.parametrize("text", SAFE_OUTPUTS)
def test_output_guardrail_allows_safe(text):
    result = guardrails.check_output(text)
    assert result.decision == GuardrailDecision.ALLOW


def test_input_red_flag_escalates():
    result = guardrails.check_input("Tôi bị đau ngực và khó thở từ sáng.")
    assert result.decision == GuardrailDecision.ESCALATE
    assert any(f.startswith("red_flag") for f in result.safety_flags)


def test_input_medication_query_is_flagged_not_escalated():
    result = guardrails.check_input("Tôi có nên tăng liều thuốc tiểu đường không?")
    # contains "tăng ... liều" -> dose change pattern, flagged as medication intent
    assert result.decision in (GuardrailDecision.ALLOW,)
    assert any("medication" in f for f in result.safety_flags)


def test_ensure_disclaimer_idempotent():
    from app.domain import policies

    once = guardrails.ensure_disclaimer("Một lời khuyên.")
    twice = guardrails.ensure_disclaimer(once)
    assert once == twice
    assert once.count(policies.DISCLAIMER_VI) == 1
