"""Meto AI — Safety Guard.

Pre-checks user messages for red flags and post-checks Meto responses for
forbidden phrases. Follows 04_SAFETY_PRIVACY.md red flag detection spec.

Safety guard MUST run on every request — it cannot be skipped.
"""

from __future__ import annotations

import logging
import re
import unicodedata

from pydantic import BaseModel

from app.domain import policies

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Red flag patterns — Group A: Emergency (call 115 immediately)
# ---------------------------------------------------------------------------

RED_FLAGS_EMERGENCY = [
    # Cardiovascular / chest
    "đau ngực", "chest pain", "tức ngực", "đau thắt ngực",
    "khó thở", "không thở được", "thở dốc",
    "tim đập nhanh bất thường", "tim đập loạn",
    # Neurological
    "ngất xỉu", "bất tỉnh", "mất ý thức",
    "lú lẫn đột ngột", "không biết mình đang ở đâu",
    "liệt một bên", "méo miệng đột ngột",
    "nói không ra tiếng", "đột ngột không nói được",
    # Extreme glucose
    "đường huyết > 400", "glucose > 400",
    "đường huyết < 50", "glucose < 50",
    "run rẩy không kiểm soát",
    # Other emergencies
    "nôn ra máu", "đi cầu ra máu nhiều",
    "đau bụng dữ dội đột ngột",
    # Self-harm (handle with care)
    "tự tử", "tự hại", "muốn chết",
]

# ---------------------------------------------------------------------------
# Red flag patterns — Group B: Urgent (see doctor within 24-48h)
# ---------------------------------------------------------------------------

RED_FLAGS_URGENT = [
    "sốt cao > 39", "sốt cao trên 39",
    "đường huyết > 300", "glucose > 300",
    "huyết áp > 180", "blood pressure > 180",
    "sưng phù chân đột ngột",
    "đau đầu dữ dội bất thường",
    "mờ mắt đột ngột",
    "tức ngực nhẹ",
    "khó thở khi gắng sức",
]

# ---------------------------------------------------------------------------
# Numeric red flags (CLIN PS-6)
#
# The phrase lists above store their numeric thresholds as LITERAL strings
# ("đường huyết > 400"), matched with `phrase in text_lower`. No patient types
# the ">" character: real messages read "đường huyết 450", "HA 190/110",
# "sốt 40 độ" — and those never matched, so a hypo/hyper crisis went to the LLM
# instead of the hardcoded "gọi 115" bypass. The extractor below parses the
# value (and unit, when present) out of the message and compares it against the
# platform thresholds in `domain.policies.RED_FLAG_VITAL_THRESHOLDS` — the same
# numbers `domain/triage.py` already uses. The literal lists are KEPT as a
# fallback, and comparisons are strict (>, <) so a message quoting a threshold
# verbatim keeps the tier its literal phrase assigns.
#
# Bias: a false escalation is safe, a missed one is not. Plausibility windows
# (and the VN cmHg shorthand "12/8" = 120/80) only suppress readings that cannot
# be the vital at all.
# ---------------------------------------------------------------------------

_MMOL_TO_MGDL = 18.0182
# Above this, a bare glucose number can only be mg/dL; at or below it, mmol/L.
_GLUCOSE_MMOL_MAX = 30.0


def _threshold(metric: str, bound: str, fallback: float) -> float:
    return policies.RED_FLAG_VITAL_THRESHOLDS.get(metric, {}).get(bound, fallback)


# Emergency = Meto's own literal tier, tightened by the platform thresholds
# (escalate no later than either source would).
_GLUCOSE_EMERGENCY_HIGH = min(400.0, _threshold("fasting_glucose", "critical_high", 500.0))
_GLUCOSE_EMERGENCY_LOW = max(50.0, _threshold("fasting_glucose", "critical_low", 54.0))
_GLUCOSE_URGENT_HIGH = 300.0  # RED_FLAGS_URGENT "đường huyết > 300"
_SYSTOLIC_HIGH = _threshold("blood_pressure_systolic", "critical_high", 180.0)
_SYSTOLIC_LOW = _threshold("blood_pressure_systolic", "critical_low", 80.0)
_DIASTOLIC_HIGH = _threshold("blood_pressure_diastolic", "critical_high", 120.0)
_DIASTOLIC_LOW = _threshold("blood_pressure_diastolic", "critical_low", 50.0)
_TEMP_URGENT_HIGH = _threshold("temperature", "critical_high", 39.0)
_TEMP_EMERGENCY_HIGH = 41.0  # hyperpyrexia
_TEMP_EMERGENCY_LOW = _threshold("temperature", "critical_low", 35.0)

TIER_EMERGENCY = "emergency"
TIER_URGENT = "recommend_urgent"

# Up to N non-numeric characters may sit between the vital keyword and its value
# ("đường huyết của tôi hôm nay là 450", "HA: 190/110", "sốt cao > 39"). Sentence
# terminators are excluded so a value from the NEXT sentence is never attributed
# to this keyword.
_FILLER = r"[^0-9\n.;!?]{0,24}?"
_GLUCOSE_RE = re.compile(
    r"(?:duong huyet|duong mau|glucose|glycemia|blood sugar|\bdh\b|\bbg\b)"
    + _FILLER
    + r"(\d{1,4}(?:[.,]\d{1,2})?)\s*(mg/dl|mg%|mmol/l|mmol)?"
)
_BP_RE = re.compile(
    r"(?:huyet ap|blood pressure|\bha\b|\bbp\b)"
    + _FILLER
    + r"(\d{2,3})(?:\s*/\s*(\d{2,3}))?"
)
_TEMP_RE = re.compile(
    r"(?:sot|nhiet do|fever|temperature)" + _FILLER + r"(\d{2}(?:[.,]\d)?)"
)
# Cheap negation guard: only the word immediately before the keyword counts, so
# "không sốt 39" is suppressed while "không biết vì sao đường huyết 450" is not.
_NEGATION_RE = re.compile(r"\b(khong|chua|ko)\W{0,3}$")


def _deaccent(text: str) -> str:
    """Lowercase + strip Vietnamese diacritics so one pattern set matches both
    "đường huyết" and "duong huyet" (patients often type without accents)."""
    stripped = unicodedata.normalize("NFD", (text or "").lower())
    stripped = "".join(c for c in stripped if unicodedata.category(c) != "Mn")
    return stripped.replace("đ", "d")


def _to_number(raw: str) -> float | None:
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return None


def _is_negated(text: str, start: int) -> bool:
    return bool(_NEGATION_RE.search(text[max(0, start - 16):start]))


def _glucose_mgdl(value: float, unit: str | None) -> float | None:
    """Normalise a glucose reading to mg/dL. A bare number is read as mmol/L when
    it is small enough that it cannot plausibly be mg/dL."""
    if unit and "mmol" in unit:
        value *= _MMOL_TO_MGDL
    elif not (unit and ("mg" in unit)) and value <= _GLUCOSE_MMOL_MAX:
        value *= _MMOL_TO_MGDL
    return value if 0 < value <= 2000 else None


def detect_numeric_vital_red_flags(text: str) -> list[tuple[str, str]]:
    """Return (tier, human-readable flag) for every numeric red flag in *text*."""
    low = _deaccent(text)
    found: list[tuple[str, str]] = []

    for m in _GLUCOSE_RE.finditer(low):
        if _is_negated(low, m.start()):
            continue
        raw = _to_number(m.group(1))
        if raw is None:
            continue
        mgdl = _glucose_mgdl(raw, m.group(2))
        if mgdl is None:
            continue
        label = f"đường huyết {m.group(1)} (~{mgdl:.0f} mg/dL)"
        if mgdl > _GLUCOSE_EMERGENCY_HIGH or mgdl < _GLUCOSE_EMERGENCY_LOW:
            found.append((TIER_EMERGENCY, label))
        elif mgdl > _GLUCOSE_URGENT_HIGH:
            found.append((TIER_URGENT, label))

    for m in _BP_RE.finditer(low):
        if _is_negated(low, m.start()):
            continue
        systolic = _to_number(m.group(1))
        diastolic = _to_number(m.group(2)) if m.group(2) else None
        if systolic is None:
            continue
        # VN shorthand in cmHg ("huyết áp 12/8" = 120/80, "19/11" = 190/110).
        if systolic < 30 and (diastolic is None or diastolic < 20):
            systolic *= 10
            diastolic = diastolic * 10 if diastolic is not None else None
        if not 40 <= systolic <= 300:
            continue
        label = f"huyết áp {m.group(1)}" + (f"/{m.group(2)}" if m.group(2) else "")
        if (
            systolic > _SYSTOLIC_HIGH
            or systolic < _SYSTOLIC_LOW
            or (diastolic is not None and (diastolic > _DIASTOLIC_HIGH or diastolic < _DIASTOLIC_LOW))
        ):
            found.append((TIER_EMERGENCY, label))

    for m in _TEMP_RE.finditer(low):
        if _is_negated(low, m.start()):
            continue
        temp = _to_number(m.group(1))
        # Outside this window the number is not a body temperature ("sốt 12 ngày").
        if temp is None or not 25.0 <= temp <= 46.0:
            continue
        label = f"nhiệt độ {m.group(1)}"
        if temp > _TEMP_EMERGENCY_HIGH or temp < _TEMP_EMERGENCY_LOW:
            found.append((TIER_EMERGENCY, label))
        elif temp > _TEMP_URGENT_HIGH:
            found.append((TIER_URGENT, label))

    return found


# ---------------------------------------------------------------------------
# Forbidden response patterns — Meto must NEVER say these
# ---------------------------------------------------------------------------

FORBIDDEN_RESPONSE_PATTERNS = [
    r"tôi chẩn đoán",
    r"anh/chị bị bệnh",
    r"kết quả cho thấy anh/chị bị",
    r"hãy dừng thuốc",
    r"ngừng uống thuốc",
    r"không cần đi khám",
    r"thay thế bác sĩ",
    r"meto đủ để",
    # Provider identity disclosure — must never appear in Meto responses
    r"tôi là claude",
    r"mình là claude",
    r"tôi là gpt",
    r"mình là gpt",
    r"tôi là openai",
    r"mình là openai",
    r"tôi là chatgpt",
    r"mình là chatgpt",
    r"powered by (claude|openai|anthropic|openrouter|gpt)",
    # Medication changes
    r"tăng liều.*mg",
    r"giảm liều.*mg",
    r"uống thêm.*mg",
    # -------------------------------------------------------------------
    # CLIN PS-1: broadened backstop patterns (the system prompt is the
    # primary control; this catches responses that slip past it). Patterns
    # are anchored to unsafe *directive/definitive* phrasing so they do not
    # fire on safe advice that defers to a doctor ("bạn nên hỏi bác sĩ về
    # việc tăng liều" is not matched; "hãy tăng liều" is).
    # -------------------------------------------------------------------
    # Definitive diagnosis assertions (2nd/1st person)
    r"chẩn đoán của bạn là",
    r"bạn (đã |đang |chắc chắn |)mắc bệnh",
    r"bạn bị bệnh",
    r"bạn (chắc chắn |chính xác |)bị (tiểu đường|đái tháo đường|ung thư|suy thận|suy tim|tăng huyết áp)",
    r"you are diagnosed with",
    r"this is (a )?diagnosis",
    # Provider / model self-disclosure (broadened, incl. English + provider names)
    r"tôi là (một )?(mô hình|trợ lý ai|trí tuệ nhân tạo)",
    r"mình là (một )?(mô hình|trợ lý ai|trí tuệ nhân tạo)",
    r"i am (an? )?(ai|language model|large language model)",
    r"as an ai",
    r"language model",
    r"\b(anthropic|openrouter|deepseek)\b",
    # Medication / dose change — imperative-anchored (no 'mg' required)
    r"(hãy|bạn nên|bạn hãy|tôi khuyên bạn|khuyên bạn nên|bạn cần)\s+(tự\s+)?(tăng|giảm|gấp đôi|tăng gấp đôi)\s*liều",
    r"(hãy|bạn nên|bạn hãy|tôi khuyên bạn|khuyên bạn nên|bạn cần)\s+(tự\s+)?(ngừng|ngưng|dừng|bỏ|đổi|thay)\s*(uống\s*)?thuốc",
    r"gấp đôi liều",
    r"tự ý (tăng|giảm|ngừng|dừng|bỏ|đổi)",
    r"không cần (đi )?(khám|gặp)",
]

# ---------------------------------------------------------------------------
# Quick-prompts by screen
# ---------------------------------------------------------------------------

QUICK_PROMPTS: dict[str, list[str]] = {
    "dashboard": [
        "Hôm nay tôi cần chú ý gì?",
        "Tôi còn việc gì chưa làm?",
        "Nhắc tôi uống thuốc",
    ],
    "labs": [
        "Giải thích kết quả này",
        "Chỉ số nào cần chú ý?",
        "Tôi nên hỏi bác sĩ điều gì?",
    ],
    "medications": [
        "Thuốc này dùng để làm gì?",
        "Tôi cần lưu ý gì khi uống?",
        "Tôi quên uống thì sao?",
    ],
    "metrics": [
        "Chỉ số này có ổn không?",
        "Xu hướng gần đây thế nào?",
        "Khi nào cần đi khám?",
    ],
    "nutrition": [
        "Hôm nay tôi ăn được gì?",
        "Thực phẩm nào nên tránh?",
        "Chế độ ăn của tôi có ổn không?",
    ],
    "care-plan": [
        "Tôi còn việc gì hôm nay?",
        "Việc nào quan trọng nhất?",
        "Giúp tôi theo kế hoạch",
    ],
    "care_plan": [
        "Tôi còn việc gì hôm nay?",
        "Việc nào quan trọng nhất?",
        "Giúp tôi theo kế hoạch",
    ],
    "profile": [
        "Meto dùng dữ liệu nào?",
        "Cách bật/tắt quyền",
        "Xóa lịch sử Meto",
    ],
    "settings": [
        "Meto dùng dữ liệu nào?",
        "Cách bật/tắt quyền",
        "Xóa lịch sử Meto",
    ],
    "consents": [
        "Meto dùng dữ liệu nào?",
        "Cách bật/tắt quyền",
        "Xóa lịch sử Meto",
    ],
}


# ---------------------------------------------------------------------------
# Safety result
# ---------------------------------------------------------------------------

class SafetyResult(BaseModel):
    safe: bool
    flags: list[str] = []
    escalation_required: bool = False
    escalation_tier: str | None = None  # "recommend_checkup" | "recommend_urgent" | "emergency"
    suggested_response: str | None = None


# ---------------------------------------------------------------------------
# Safety Guard implementation
# ---------------------------------------------------------------------------

class SafetyGuard:
    """Pre-check user messages and post-check Meto responses for safety."""

    def check_input(self, message: str) -> SafetyResult:
        """Check user message for red flags requiring escalation."""
        numeric = detect_numeric_vital_red_flags(message)
        flags = self.detect_red_flags(message)
        if not flags:
            return SafetyResult(safe=True)

        # Determine tier. Numeric findings are checked first at each tier: a
        # value the patient typed is at least as reliable a signal as a phrase.
        msg_lower = message.lower()
        if any(tier == TIER_EMERGENCY for tier, _ in numeric):
            return SafetyResult(
                safe=False,
                flags=flags,
                escalation_required=True,
                escalation_tier="emergency",
                suggested_response=self.get_escalation_response(flags, tier="emergency"),
            )

        for phrase in RED_FLAGS_EMERGENCY:
            if phrase in msg_lower:
                return SafetyResult(
                    safe=False,
                    flags=flags,
                    escalation_required=True,
                    escalation_tier="emergency",
                    suggested_response=self.get_escalation_response(flags, tier="emergency"),
                )

        if any(tier == TIER_URGENT for tier, _ in numeric):
            return SafetyResult(
                safe=False,
                flags=flags,
                escalation_required=True,
                escalation_tier="recommend_urgent",
                suggested_response=self.get_escalation_response(flags, tier="urgent"),
            )

        for phrase in RED_FLAGS_URGENT:
            if phrase in msg_lower:
                return SafetyResult(
                    safe=False,
                    flags=flags,
                    escalation_required=True,
                    escalation_tier="recommend_urgent",
                    suggested_response=self.get_escalation_response(flags, tier="urgent"),
                )

        return SafetyResult(
            safe=False,
            flags=flags,
            escalation_required=True,
            escalation_tier="recommend_checkup",
            suggested_response=self.get_escalation_response(flags, tier="checkup"),
        )

    def check_output(self, response: str) -> SafetyResult:
        """Check Meto response for forbidden phrases."""
        response_lower = response.lower()
        violations: list[str] = []

        for pattern in FORBIDDEN_RESPONSE_PATTERNS:
            if re.search(pattern, response_lower):
                violations.append(f"Forbidden pattern: {pattern}")
                logger.warning("Meto response contains forbidden pattern: %s", pattern)

        if violations:
            return SafetyResult(
                safe=False,
                flags=violations,
                escalation_required=False,
            )

        return SafetyResult(safe=True)

    def detect_red_flags(self, text: str) -> list[str]:
        """Detect red flag phrases in text. Returns matched phrases.

        Includes numeric findings (CLIN PS-6) alongside the literal phrases, so a
        message that only states values still counts as flagged.
        """
        text_lower = text.lower()
        matched: list[str] = []

        for phrase in RED_FLAGS_EMERGENCY:
            if phrase in text_lower:
                matched.append(phrase)

        for phrase in RED_FLAGS_URGENT:
            if phrase in text_lower:
                matched.append(phrase)

        matched.extend(label for _tier, label in detect_numeric_vital_red_flags(text))
        return matched

    def get_escalation_response(self, flags: list[str], tier: str = "emergency") -> str:
        """Generate appropriate escalation response based on tier."""
        if tier == "emergency":
            return (
                "⚠️ **Dấu hiệu này cần được xử lý NGAY LẬP TỨC**\n\n"
                "Bạn đang mô tả triệu chứng có thể nghiêm trọng.\n\n"
                "**Hãy làm ngay:**\n"
                "1. **Gọi 115** hoặc nhờ người đưa đến phòng cấp cứu gần nhất\n"
                "2. Nếu đang một mình, gọi cho người thân trước\n"
                "3. Không tự lái xe\n\n"
                "Meto không đủ khả năng đánh giá tình trạng khẩn cấp — "
                "bạn cần sự hỗ trợ y tế thực sự ngay bây giờ."
            )

        elif tier == "urgent":
            return (
                "Meto thấy triệu chứng bạn mô tả cần được bác sĩ kiểm tra sớm.\n\n"
                "**Việc nên làm:**\n"
                "- Liên hệ bác sĩ hoặc phòng khám trong ngày hôm nay\n"
                "- Nếu không liên hệ được, đến cơ sở y tế gần nhất\n"
                "- Trong khi chờ: nghỉ ngơi, không tự ý thay đổi thuốc\n\n"
                "Đây là thông tin tham khảo — bác sĩ mới có thể đánh giá chính xác tình trạng của bạn."
            )

        else:  # checkup
            return (
                "Meto thấy bạn có một số triệu chứng đáng chú ý.\n\n"
                "Nên chia sẻ điều này với bác sĩ trong lần khám tiếp theo để được đánh giá đầy đủ.\n\n"
                "Nếu triệu chứng trở nên nặng hơn, hãy liên hệ bác sĩ sớm hơn dự kiến."
            )
