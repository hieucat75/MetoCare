"""Tests for Meto AI SafetyGuard — input & output safety checks.

Covers:
- Emergency red flags ("đau ngực", "khó thở") → escalation_required=True, tier="emergency"
- Urgent red flags → escalation_required=True, tier="recommend_urgent"
- Normal health question → safe=True, no escalation
- Forbidden response phrases → check_output safe=False
- Clean response → check_output safe=True
"""

from __future__ import annotations

import pytest
from app.ai.prompt.safety import SafetyGuard, SafetyResult


@pytest.fixture
def guard() -> SafetyGuard:
    return SafetyGuard()


# ---------------------------------------------------------------------------
# check_input — Emergency tier
# ---------------------------------------------------------------------------

class TestCheckInputEmergency:
    def test_dau_nguc_is_emergency(self, guard: SafetyGuard):
        result = guard.check_input("tôi đang bị đau ngực dữ dội")
        assert result.escalation_required is True
        assert result.escalation_tier == "emergency"
        assert "đau ngực" in result.flags

    def test_kho_tho_is_emergency(self, guard: SafetyGuard):
        result = guard.check_input("tôi khó thở từ sáng đến giờ")
        assert result.escalation_required is True
        assert result.escalation_tier == "emergency"
        assert "khó thở" in result.flags

    def test_bat_tinh_is_emergency(self, guard: SafetyGuard):
        result = guard.check_input("bà ngoại tôi vừa bất tỉnh")
        assert result.escalation_required is True
        assert result.escalation_tier == "emergency"

    def test_suggested_response_is_populated(self, guard: SafetyGuard):
        result = guard.check_input("đau ngực")
        assert result.suggested_response is not None
        assert "115" in result.suggested_response or "cấp cứu" in result.suggested_response.lower()

    def test_tu_tu_is_emergency(self, guard: SafetyGuard):
        result = guard.check_input("tôi muốn tự tử")
        assert result.escalation_required is True
        assert result.escalation_tier == "emergency"


# ---------------------------------------------------------------------------
# check_input — Urgent tier
# ---------------------------------------------------------------------------

class TestCheckInputUrgent:
    def test_high_blood_pressure_is_urgent(self, guard: SafetyGuard):
        result = guard.check_input("huyết áp > 180 mmHg bất thường không?")
        assert result.escalation_required is True
        assert result.escalation_tier == "recommend_urgent"

    def test_high_glucose_is_urgent(self, guard: SafetyGuard):
        result = guard.check_input("đường huyết > 300 hôm nay")
        assert result.escalation_required is True
        assert result.escalation_tier == "recommend_urgent"

    def test_urgent_suggested_response_mentions_doctor(self, guard: SafetyGuard):
        result = guard.check_input("sốt cao > 39 không hạ được")
        assert result.escalation_required is True
        assert result.suggested_response is not None
        assert "bác sĩ" in result.suggested_response.lower()


# ---------------------------------------------------------------------------
# check_input — Safe messages
# ---------------------------------------------------------------------------

class TestCheckInputSafe:
    def test_normal_lab_question_is_safe(self, guard: SafetyGuard):
        result = guard.check_input("giải thích xét nghiệm này cho tôi")
        assert result.safe is True
        assert result.escalation_required is False
        assert result.flags == []

    def test_medication_question_is_safe(self, guard: SafetyGuard):
        result = guard.check_input("thuốc metformin uống lúc nào tốt nhất?")
        assert result.safe is True
        assert result.escalation_required is False

    def test_empty_message_is_safe(self, guard: SafetyGuard):
        result = guard.check_input("")
        assert result.safe is True
        assert result.escalation_required is False

    def test_greeting_is_safe(self, guard: SafetyGuard):
        result = guard.check_input("xin chào Meto")
        assert result.safe is True

    def test_hba1c_question_is_safe(self, guard: SafetyGuard):
        result = guard.check_input("HbA1c của tôi là 6.5%, mức này ổn chưa?")
        assert result.safe is True


# ---------------------------------------------------------------------------
# check_output — Forbidden phrases
# ---------------------------------------------------------------------------

class TestCheckOutputForbidden:
    def test_chan_doan_is_forbidden(self, guard: SafetyGuard):
        response = "Tôi chẩn đoán bạn bị tiểu đường type 2."
        result = guard.check_output(response)
        assert result.safe is False
        assert len(result.flags) >= 1

    def test_dung_thuoc_is_forbidden(self, guard: SafetyGuard):
        response = "Hãy dừng thuốc metformin ngay hôm nay."
        result = guard.check_output(response)
        assert result.safe is False

    def test_tang_lieu_mg_is_forbidden(self, guard: SafetyGuard):
        response = "Bạn nên tăng liều 500mg mỗi ngày."
        result = guard.check_output(response)
        assert result.safe is False

    def test_giam_lieu_mg_is_forbidden(self, guard: SafetyGuard):
        response = "Hãy giảm liều 250mg xuống còn 100mg."
        result = guard.check_output(response)
        assert result.safe is False

    def test_khong_can_kham_is_forbidden(self, guard: SafetyGuard):
        response = "không cần đi khám bác sĩ, chỉ số của bạn bình thường."
        result = guard.check_output(response)
        assert result.safe is False


# ---------------------------------------------------------------------------
# check_output — Clean responses
# ---------------------------------------------------------------------------

class TestCheckOutputClean:
    def test_normal_response_is_safe(self, guard: SafetyGuard):
        response = (
            "Kết quả HbA1c 6.5% của bạn nằm trong ngưỡng tiền tiểu đường. "
            "Bạn nên chia sẻ kết quả này với bác sĩ để có kế hoạch điều trị phù hợp."
        )
        result = guard.check_output(response)
        assert result.safe is True
        assert result.flags == []

    def test_escalation_response_is_safe(self, guard: SafetyGuard):
        # The hardcoded escalation response itself must pass output check
        escalation = guard.get_escalation_response(["đau ngực"], tier="emergency")
        result = guard.check_output(escalation)
        assert result.safe is True

    def test_explanation_response_is_safe(self, guard: SafetyGuard):
        response = (
            "Xét nghiệm creatinine đo chức năng thận của bạn. "
            "Giá trị bình thường là 0.6–1.2 mg/dL. "
            "Khi nào gặp bác sĩ: nếu giá trị vượt 1.5 mg/dL, hãy tái khám sớm."
        )
        result = guard.check_output(response)
        assert result.safe is True


# ---------------------------------------------------------------------------
# detect_red_flags — unit test for helper method
# ---------------------------------------------------------------------------

class TestDetectRedFlags:
    def test_detects_multiple_flags(self, guard: SafetyGuard):
        text = "tôi bị đau ngực và khó thở từ tối qua"
        flags = guard.detect_red_flags(text)
        assert "đau ngực" in flags
        assert "khó thở" in flags

    def test_no_flags_in_clean_text(self, guard: SafetyGuard):
        text = "hbA1c của tôi là 6.8%"
        flags = guard.detect_red_flags(text)
        assert flags == []

    def test_case_insensitive_detection(self, guard: SafetyGuard):
        # Red flags are stored lowercase; input is lowercased before check
        flags = guard.detect_red_flags("Đau Ngực rất nặng")
        assert "đau ngực" in flags


# ---------------------------------------------------------------------------
# SafetyResult model
# ---------------------------------------------------------------------------

class TestSafetyResult:
    def test_safe_result_defaults(self):
        result = SafetyResult(safe=True)
        assert result.safe is True
        assert result.flags == []
        assert result.escalation_required is False
        assert result.escalation_tier is None

    def test_unsafe_result(self):
        result = SafetyResult(
            safe=False,
            flags=["đau ngực"],
            escalation_required=True,
            escalation_tier="emergency",
        )
        assert result.safe is False
        assert "đau ngực" in result.flags
        assert result.escalation_tier == "emergency"
