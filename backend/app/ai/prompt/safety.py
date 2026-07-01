"""Meto AI — Safety Guard.

Pre-checks user messages for red flags and post-checks Meto responses for
forbidden phrases. Follows 04_SAFETY_PRIVACY.md red flag detection spec.

Safety guard MUST run on every request — it cannot be skipped.
"""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel

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
        flags = self.detect_red_flags(message)
        if not flags:
            return SafetyResult(safe=True)

        # Determine tier
        msg_lower = message.lower()
        for phrase in RED_FLAGS_EMERGENCY:
            if phrase in msg_lower:
                return SafetyResult(
                    safe=False,
                    flags=flags,
                    escalation_required=True,
                    escalation_tier="emergency",
                    suggested_response=self.get_escalation_response(flags, tier="emergency"),
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
        """Detect red flag phrases in text. Returns matched phrases."""
        text_lower = text.lower()
        matched: list[str] = []

        for phrase in RED_FLAGS_EMERGENCY:
            if phrase in text_lower:
                matched.append(phrase)

        for phrase in RED_FLAGS_URGENT:
            if phrase in text_lower:
                matched.append(phrase)

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
