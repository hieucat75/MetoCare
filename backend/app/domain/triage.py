"""Triage rule engine — hybrid rule-first model.

Implements ``docs/AI_Safety_Guardrail.md`` §4.6 and ``Technical_Architecture.md``
§4.4: a hard rule-based red-flag engine runs **before** any LLM reasoning; the
LLM only clarifies; a classifier assigns one of 4 risk levels; an escalation
engine routes the case. The LLM never decides escalation on its own.

Pure standard library. Deterministic. Unit-test target: false-negative on the
red-flag set = 0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from . import policies


class RiskLevel(StrEnum):
    LOW = "low"          # Thấp — tự theo dõi + coaching
    MODERATE = "moderate"  # Vừa — gợi ý đặt lịch bác sĩ
    HIGH = "high"        # Cao — cần gặp bác sĩ sớm + doctor handoff
    EMERGENCY = "emergency"  # Khẩn cấp — escalate cấp cứu


class EscalationAction(StrEnum):
    SELF_MONITOR = "self_monitor"
    SUGGEST_BOOKING = "suggest_booking"
    DOCTOR_HANDOFF = "doctor_handoff"
    EMERGENCY_ESCALATION = "emergency_escalation"


# Risk level -> routing action (Technical_Architecture.md §4.4 / Guardrail §3.3).
_ROUTING: dict[RiskLevel, EscalationAction] = {
    RiskLevel.LOW: EscalationAction.SELF_MONITOR,
    RiskLevel.MODERATE: EscalationAction.SUGGEST_BOOKING,
    RiskLevel.HIGH: EscalationAction.DOCTOR_HANDOFF,
    RiskLevel.EMERGENCY: EscalationAction.EMERGENCY_ESCALATION,
}

_MESSAGE: dict[RiskLevel, str] = {
    RiskLevel.LOW: (
        "Hiện chưa thấy dấu hiệu cần lo ngay. Bạn tiếp tục theo dõi chỉ số và "
        "duy trì lối sống lành mạnh nhé. " + policies.DISCLAIMER_VI
    ),
    RiskLevel.MODERATE: (
        "Có vài điểm nên được bác sĩ xem qua. Bạn nên cân nhắc đặt lịch khám "
        "trong thời gian tới. " + policies.DISCLAIMER_VI
    ),
    RiskLevel.HIGH: (
        "Một số dấu hiệu cho thấy bạn nên gặp bác sĩ sớm. Mình sẽ chuẩn bị tóm "
        "tắt dữ liệu để bác sĩ theo dõi (doctor handoff). " + policies.DISCLAIMER_VI
    ),
    RiskLevel.EMERGENCY: policies.EMERGENCY_MESSAGE_VI,
}


@dataclass
class VitalSign:
    metric_type: str
    value: float


@dataclass
class TriageInput:
    symptom_text: str = ""
    vitals: list[VitalSign] = field(default_factory=list)
    # Optional self-reported severity (0-10) used only to nudge LOW->MODERATE.
    reported_severity: int | None = None


@dataclass
class TriageResult:
    risk_level: RiskLevel
    action: EscalationAction
    message: str
    red_flags: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    # True when a hard rule (not the soft classifier) forced the level.
    rule_forced: bool = False

    @property
    def escalated_to_doctor(self) -> bool:
        return self.action in (
            EscalationAction.DOCTOR_HANDOFF,
            EscalationAction.EMERGENCY_ESCALATION,
        )


def _detect_symptom_red_flags(text: str) -> list[str]:
    import unicodedata

    norm = unicodedata.normalize("NFC", text or "").lower()
    found: list[str] = []
    for symptom, keywords in policies.RED_FLAG_SYMPTOMS.items():
        if any(kw in norm for kw in keywords):
            found.append(symptom)
    return found


def _detect_vital_red_flags(vitals: list[VitalSign]) -> list[str]:
    found: list[str] = []
    for v in vitals:
        thresholds = policies.RED_FLAG_VITAL_THRESHOLDS.get(v.metric_type)
        if not thresholds:
            continue
        if "critical_high" in thresholds and v.value >= thresholds["critical_high"]:
            found.append(f"vital_high:{v.metric_type}")
        if "critical_low" in thresholds and v.value <= thresholds["critical_low"]:
            found.append(f"vital_low:{v.metric_type}")
    return found


def assess(data: TriageInput) -> TriageResult:
    """Run the rule engine first, then the soft classifier.

    Step 1 (HARD, independent of LLM): any red-flag symptom or critical vital
            => EMERGENCY. This is the false-negative=0 guarantee.
    Step 2 (SOFT classifier): map remaining signals to LOW/MODERATE/HIGH.
    """
    reasons: list[str] = []
    red_flags = _detect_symptom_red_flags(data.symptom_text)
    red_flags += _detect_vital_red_flags(data.vitals)

    if red_flags:
        reasons.append(f"Hard red flag → EMERGENCY: {red_flags}")
        return TriageResult(
            risk_level=RiskLevel.EMERGENCY,
            action=_ROUTING[RiskLevel.EMERGENCY],
            message=_MESSAGE[RiskLevel.EMERGENCY],
            red_flags=red_flags,
            reasons=reasons,
            rule_forced=True,
        )

    # ---- Soft classifier (conservative; ties round UP in severity) ----
    level = RiskLevel.LOW

    # Borderline-but-not-critical vitals nudge the level.
    for v in data.vitals:
        th = policies.RED_FLAG_VITAL_THRESHOLDS.get(v.metric_type)
        if not th:
            continue
        # Within 85% of a critical-high threshold => HIGH-ish concern.
        ch = th.get("critical_high")
        if ch and v.value >= 0.85 * ch:
            level = RiskLevel.HIGH
            reasons.append(f"{v.metric_type}={v.value} gần ngưỡng nguy hiểm → HIGH")
        elif ch and v.value >= 0.70 * ch and level == RiskLevel.LOW:
            level = RiskLevel.MODERATE
            reasons.append(f"{v.metric_type}={v.value} cao → MODERATE")

    if data.reported_severity is not None:
        if data.reported_severity >= 7 and level == RiskLevel.LOW:
            level = RiskLevel.MODERATE
            reasons.append("Mức độ tự báo cao (>=7) → MODERATE")

    if not reasons:
        reasons.append("Không có red flag; tín hiệu trong ngưỡng theo dõi → LOW")

    return TriageResult(
        risk_level=level,
        action=_ROUTING[level],
        message=_MESSAGE[level],
        red_flags=[],
        reasons=reasons,
        rule_forced=False,
    )
