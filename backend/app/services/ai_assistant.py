"""AI Assistant service — guardrailed responder over the LLM Gateway.

Pipeline (Technical_Architecture.md §4.3 / AI_Safety_Guardrail.md):
  input guardrail -> (red flag? escalate) -> (medication intent? safe redirect)
  -> LLM Gateway.complete (provider + cost guard + cache + OUTPUT guardrail +
     disclaimer) -> map to AIResponse.

Generation now goes through ``app.llm`` via the provider factory (mock by default
= no external call). The output guardrail lives in the gateway so NO path can emit
an unvalidated response; the input guardrail and medication redirect stay here
because they decide whether to call the model at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain import guardrails, policies
from app.domain.guardrails import GuardrailDecision
from app.llm import LLMMessage, get_gateway


@dataclass
class AIResponse:
    text: str
    intent: str
    risk_level: str
    escalated_to_doctor: bool
    safety_flags: list[str] = field(default_factory=list)
    model_used: str = "mock"
    blocked: bool = False
    cached: bool = False


def respond(
    user_text: str,
    *,
    intent: str = "health_assistant",
    user_id: str = "anonymous",
) -> AIResponse:
    # ---- 1. Input guardrail (red flags short-circuit to escalation) ----
    in_result = guardrails.check_input(user_text)
    if in_result.decision == GuardrailDecision.ESCALATE:
        return AIResponse(
            text=in_result.safe_message or policies.EMERGENCY_MESSAGE_VI,
            intent=intent,
            risk_level="emergency",
            escalated_to_doctor=True,
            safety_flags=in_result.safety_flags,
            model_used="guardrail",
        )

    # ---- 2. Medication/dose questions never reach the model ----
    if any(f.startswith("intent:medication") for f in in_result.safety_flags):
        return AIResponse(
            text=policies.SAFE_REFUSAL_MEDICATION_VI,
            intent=intent,
            risk_level="low",
            escalated_to_doctor=False,
            safety_flags=in_result.safety_flags,
            model_used="guardrail",
        )

    # ---- 3. Generation via the LLM Gateway (output guardrail enforced there) ----
    gateway = get_gateway()
    result = gateway.complete(
        user_id=user_id,
        messages=[LLMMessage(role="user", content=user_text)],
        system=policies.SYSTEM_SAFETY_PROMPT_VI,
    )

    return AIResponse(
        text=result.text,
        intent=intent,
        risk_level="low",
        escalated_to_doctor=False,
        safety_flags=in_result.safety_flags + result.safety_flags,
        model_used=result.model,
        blocked=result.blocked,
        cached=result.cached,
    )
