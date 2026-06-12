"""AI Assistant service — guardrailed responder.

Implements the pipeline shape of ``Technical_Architecture.md`` §4.3 at foundation
level: input guardrail -> (mock) response generation -> output guardrail ->
disclaimer -> safety log. NO LLM is called in mock mode (config MCP_AI_MODE),
so dev/test never hit an external provider and no API key is required.

The point of this service is to PROVE the guardrail wraps every response and
that no code path can emit an unsafe message.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.config import get_settings
from app.domain import guardrails, policies
from app.domain.guardrails import GuardrailDecision


@dataclass
class AIResponse:
    text: str
    intent: str
    risk_level: str
    escalated_to_doctor: bool
    safety_flags: list[str] = field(default_factory=list)
    model_used: str = "mock"
    blocked: bool = False


def _mock_generate(user_text: str, intent: str) -> str:
    """Deterministic, safe canned generation for dev/test. Uses probabilistic
    language and never diagnoses/prescribes. Real generation goes through the
    LLM Gateway in P1 (and still passes the SAME output guardrail)."""
    base = (
        "Cảm ơn bạn đã chia sẻ. Dựa trên thông tin bạn cung cấp, đây là một vài "
        "gợi ý lối sống chung: duy trì vận động nhẹ sau bữa ăn, hạn chế đồ ngọt và "
        "tinh bột nhanh, ngủ đủ giấc. Nếu bạn còn băn khoăn, nên trao đổi với bác sĩ "
        "để được đánh giá phù hợp với tình trạng của bạn."
    )
    return base


def respond(user_text: str, *, intent: str = "health_assistant") -> AIResponse:
    settings = get_settings()

    # ---- 1. Input guardrail (red flags short-circuit to escalation) ----
    in_result = guardrails.check_input(user_text)
    if in_result.decision == GuardrailDecision.ESCALATE:
        return AIResponse(
            text=in_result.safe_message or policies.EMERGENCY_MESSAGE_VI,
            intent=intent,
            risk_level="emergency",
            escalated_to_doctor=True,
            safety_flags=in_result.safety_flags,
            model_used=settings.ai_mode,
        )

    # ---- 2. Generation (mock by default; gateway is P1) ----
    if settings.ai_mode == "mock":
        raw = _mock_generate(user_text, intent)
    else:  # pragma: no cover - real gateway not wired in foundation
        raise NotImplementedError("LLM gateway not configured; set MCP_AI_MODE=mock.")

    # If the user asked about medication/dose, force the safe redirect.
    if any(f.startswith("intent:medication") for f in in_result.safety_flags):
        raw = policies.SAFE_REFUSAL_MEDICATION_VI

    # ---- 3. Output guardrail (Medical Safety Validator) ----
    out_result = guardrails.check_output(raw)
    if out_result.decision == GuardrailDecision.BLOCK:
        return AIResponse(
            text=out_result.safe_message or policies.SAFE_REFUSAL_MEDICATION_VI,
            intent=intent,
            risk_level="low",
            escalated_to_doctor=False,
            safety_flags=in_result.safety_flags + out_result.safety_flags,
            model_used=settings.ai_mode,
            blocked=True,
        )

    # ---- 4. Disclaimer + 5. return (caller logs to AIConversation) ----
    text = guardrails.ensure_disclaimer(raw)
    return AIResponse(
        text=text,
        intent=intent,
        risk_level="low",
        escalated_to_doctor=False,
        safety_flags=in_result.safety_flags,
        model_used=settings.ai_mode,
    )
