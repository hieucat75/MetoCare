"""AI Safety Guardrail engine — input + output validation.

Implements the two-sided rule engine required by ``docs/AI_Safety_Guardrail.md``
(§3 decision, §3.2 prohibited actions, §3.3 escalation, §4.9 safety prompt,
§4.13 evaluation checklist).

Invariants enforced here (NO code path may bypass these):
- The AI must never output a definitive diagnosis, a prescription, a dose change,
  a downplayed red flag, a certain prognosis, or cite unapproved sources.
- Every released AI output must carry the mandatory disclaimer.
- A red flag in the *input* short-circuits to emergency escalation.

Pure standard library. No framework / DB / network imports — so it is unit
testable in isolation and cannot accidentally call an LLM.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum

from . import policies


class GuardrailDecision(StrEnum):
    ALLOW = "allow"
    BLOCK = "block"
    ESCALATE = "escalate"


@dataclass
class GuardrailResult:
    """Outcome of an input or output guardrail check."""

    decision: GuardrailDecision
    safety_flags: list[str] = field(default_factory=list)
    # Replacement / safe message to surface instead of the raw text when blocked.
    safe_message: str | None = None
    # Human-readable reasons for logging / audit.
    reasons: list[str] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return self.decision == GuardrailDecision.ALLOW


def _normalize(text: str) -> str:
    """Lowercase + keep Vietnamese diacritics (patterns are written with them)."""
    return unicodedata.normalize("NFC", text or "").lower().strip()


def _matches_any(text: str, patterns: tuple[str, ...]) -> list[str]:
    hits: list[str] = []
    for pat in patterns:
        if re.search(pat, text):
            hits.append(pat)
    return hits


# --------------------------------------------------------------------------- #
# Input guardrail
# --------------------------------------------------------------------------- #

def check_input(user_text: str) -> GuardrailResult:
    """Inspect user input BEFORE the LLM reasoning layer.

    - Red flag symptom in text  -> ESCALATE (emergency), independent of any LLM.
    - Medication / dose / diagnosis *question* -> ALLOW but flag so the responder
      redirects to a doctor (handled by the responder, not blocked here).
    """
    text = _normalize(user_text)
    flags: list[str] = []
    reasons: list[str] = []

    # Hard red flags first (false-negative target = 0).
    for symptom, keywords in policies.RED_FLAG_SYMPTOMS.items():
        if any(kw in text for kw in keywords):
            flags.append(f"red_flag:{symptom}")
            reasons.append(f"Phát hiện red flag '{symptom}' trong input.")

    if flags:
        return GuardrailResult(
            decision=GuardrailDecision.ESCALATE,
            safety_flags=flags,
            safe_message=policies.EMERGENCY_MESSAGE_VI,
            reasons=reasons,
        )

    # Non-emergency sensitive intents — allowed, but flagged for redirect.
    if _matches_any(text, policies.DOSE_CHANGE_PATTERNS) or re.search(
        r"\b(liều|thuốc|đơn thuốc)\b", text
    ):
        flags.append("intent:medication_query")
        reasons.append("Người dùng hỏi về thuốc/liều → cần chuyển hướng bác sĩ.")

    if re.search(r"\b(tôi bị gì|bệnh gì|có phải.*bị|chẩn đoán)\b", text):
        flags.append("intent:diagnosis_query")
        reasons.append("Người dùng hỏi chẩn đoán → dùng ngôn ngữ khả năng, không khẳng định.")

    return GuardrailResult(
        decision=GuardrailDecision.ALLOW, safety_flags=flags, reasons=reasons
    )


# --------------------------------------------------------------------------- #
# Output guardrail (Medical Safety Validator)
# --------------------------------------------------------------------------- #

_OUTPUT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("prohibited:definitive_diagnosis", policies.DIAGNOSIS_ASSERTION_PATTERNS),
    ("prohibited:prescribe_medication", policies.PRESCRIPTION_PATTERNS),
    ("prohibited:change_medication_dose", policies.DOSE_CHANGE_PATTERNS),
    ("prohibited:downplay_red_flag", policies.DOWNPLAY_PATTERNS),
    ("prohibited:certain_prognosis", policies.PROGNOSIS_PATTERNS),
    ("prohibited:fabricate_data_or_guideline", policies.UNAPPROVED_SOURCE_PATTERNS),
)


def check_output(ai_text: str) -> GuardrailResult:
    """Validate AI output BEFORE it is released to the user.

    Any prohibited pattern => BLOCK and substitute a safe message. This is the
    last line of defense; it must run on every AI response.
    """
    text = _normalize(ai_text)
    flags: list[str] = []
    reasons: list[str] = []

    for flag, patterns in _OUTPUT_RULES:
        hits = _matches_any(text, patterns)
        if hits:
            flags.append(flag)
            reasons.append(f"Output khớp pattern cấm ({flag}): {hits!r}")

    if flags:
        return GuardrailResult(
            decision=GuardrailDecision.BLOCK,
            safety_flags=flags,
            safe_message=policies.SAFE_REFUSAL_MEDICATION_VI
            if any("medication" in f or "diagnosis" in f for f in flags)
            else (
                "Mình xin lỗi, phần này cần bác sĩ đánh giá trực tiếp. "
                + policies.DISCLAIMER_VI
            ),
            reasons=reasons,
        )

    return GuardrailResult(decision=GuardrailDecision.ALLOW, reasons=["Output hợp lệ."])


def ensure_disclaimer(text: str) -> str:
    """Guarantee the mandatory disclaimer is present (idempotent)."""
    if policies.DISCLAIMER_VI in (text or ""):
        return text
    sep = " " if text and not text.endswith(("\n", " ")) else ""
    return f"{text}{sep}{policies.DISCLAIMER_VI}"
