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


# ---------------------------------------------------------------------------
# CLIN PS-1: broadened output-safety detector — must catch unsafe phrasings the
# original literal list missed, WITHOUT flagging safe advice that defers to a
# doctor.
# ---------------------------------------------------------------------------

class TestCheckOutputBroadened:
    @pytest.mark.parametrize(
        "response",
        [
            # Diagnosis claims (phrasings beyond "tôi chẩn đoán")
            "Chẩn đoán của bạn là đái tháo đường type 2.",
            "Bạn chắc chắn bị tiểu đường rồi.",
            "This is a diagnosis of diabetes.",
            # Medication change — imperative, no 'mg' present (the PS-1 example)
            "Bạn nên tăng liều insulin gấp đôi.",
            "Hãy tăng liều lên nhé.",
            "Bạn cần ngừng thuốc metformin.",
            "Bạn có thể tự ý giảm liều nếu thấy mệt.",
            "Uống gấp đôi liều buổi sáng.",
            # Dose instruction
            "Hãy giảm liều xuống một nửa.",
            # Provider / model impersonation (VN + English)
            "Thực ra tôi là một mô hình ngôn ngữ lớn.",
            "As an AI, I cannot feel emotions.",
            "Tôi là trợ lý AI được huấn luyện bởi Anthropic.",
            "I am an AI language model.",
        ],
    )
    def test_unsafe_phrasings_are_blocked(self, guard: SafetyGuard, response: str):
        result = guard.check_output(response)
        assert result.safe is False, f"should have blocked: {response!r}"
        assert result.flags

    @pytest.mark.parametrize(
        "response",
        [
            # Safe: defers the dose decision to the doctor (must NOT be flagged)
            "Bạn nên hỏi bác sĩ về việc có cần tăng liều hay không.",
            "Việc điều chỉnh liều nên do bác sĩ quyết định.",
            "Nếu thấy mệt, bạn không nên tự tăng liều mà hãy báo bác sĩ.",
            # Safe: explains without diagnosing or impersonating
            "Chỉ số HbA1c 6.5% nằm ở ngưỡng tiền tiểu đường; hãy trao đổi với bác sĩ.",
            "Meto là trợ lý sức khỏe của bạn, luôn sẵn sàng nhắc lịch uống thuốc.",
        ],
    )
    def test_safe_deferrals_are_not_flagged(self, guard: SafetyGuard, response: str):
        result = guard.check_output(response)
        assert result.safe is True, f"false positive on safe advice: {response!r}"

    def test_streaming_and_nonstreaming_use_the_same_detector(self, guard: SafetyGuard):
        """Parity is structural: both meto_chat paths call this same
        SafetyGuard.check_output, so a phrase blocked here is blocked in both."""
        unsafe = "Hãy tăng liều gấp đôi ngay hôm nay."
        assert guard.check_output(unsafe).safe is False
        # deterministic across repeated (stream-chunk-buffered) calls
        assert guard.check_output(unsafe).safe is guard.check_output(unsafe).safe


# ---------------------------------------------------------------------------
# CLIN PS-6 — numeric red flags (patients type numbers, not ">" thresholds)
# ---------------------------------------------------------------------------

class TestNumericRedFlags:
    """A real patient writes "đường huyết 450", never "đường huyết > 400".
    Literal-substring matching never fires on those, so the message went to the
    LLM instead of the hardcoded "gọi 115" bypass."""

    @pytest.mark.parametrize(
        "message",
        [
            # severe hyperglycaemia
            "đường huyết 450",
            "Đường huyết của tôi hôm nay là 450 mg/dL",
            "duong huyet 450 khong ha duoc",  # no diacritics
            "ĐH 500 sau ăn",  # common abbreviation
            "glucose 480",
            "đường huyết 25 mmol/L",
            # severe hypoglycaemia
            "đường huyết 40",
            "duong huyet 2.5 mmol/l, nguoi run",
            # hypertensive crisis
            "HA 190/110",
            "huyết áp 190/110 đo lúc sáng",
            "huyet ap 200/120",
            "huyết áp 220",
            # high fever
            "sốt 40 độ",
            "sot 40 do tu toi qua",
            "nhiệt độ 39.8",
        ],
    )
    def test_numeric_vital_message_escalates(self, guard: SafetyGuard, message: str):
        result = guard.check_input(message)
        assert result.escalation_required is True, f"MISSED red flag: {message!r}"
        assert result.escalation_tier in ("emergency", "recommend_urgent")
        assert result.suggested_response

    def test_glucose_450_triggers_emergency(self, guard: SafetyGuard):
        result = guard.check_input("đường huyết 450 sau khi ăn, tôi thấy mệt")
        assert result.escalation_tier == "emergency"

    def test_glucose_25_mmol_triggers_emergency(self, guard: SafetyGuard):
        """25 mmol/L ≈ 450 mg/dL — unit-aware, not a bare number comparison."""
        result = guard.check_input("đường huyết 25 mmol/L")
        assert result.escalation_tier == "emergency"

    def test_bp_190_110_triggers_emergency(self, guard: SafetyGuard):
        result = guard.check_input("HA 190/110")
        assert result.escalation_tier == "emergency"

    def test_fever_40_triggers_escalation(self, guard: SafetyGuard):
        result = guard.check_input("sốt 40 độ hai ngày nay")
        assert result.escalation_required is True

    @pytest.mark.parametrize(
        "message",
        [
            "đường huyết 110 lúc đói có ổn không?",
            "đường huyết 5.6 mmol/L sáng nay",
            "huyết áp 120/80 có tốt không?",
            "huyết áp 12/8 của tôi thế nào?",  # VN cmHg shorthand for 120/80
            "nhiệt độ 36.8 độ",
            "tôi bị sốt 3 ngày nay rồi",  # a duration, not a temperature
            "HbA1c của tôi là 6.5%, mức này ổn chưa?",
            "tôi uống thuốc huyết áp 10 năm nay",
        ],
    )
    def test_normal_numbers_do_not_escalate(self, guard: SafetyGuard, message: str):
        result = guard.check_input(message)
        assert result.safe is True, f"FALSE escalation for: {message!r}"

    def test_normal_glucose_does_not_escalate(self, guard: SafetyGuard):
        assert guard.check_input("đường huyết 110 sáng nay").safe is True

    def test_existing_literal_thresholds_still_match(self, guard: SafetyGuard):
        """The literal phrase list is kept as a fallback — no regression."""
        assert guard.check_input("đường huyết > 300 hôm nay").escalation_tier == (
            "recommend_urgent"
        )
        assert guard.check_input("huyết áp > 180 mmHg bất thường không?").escalation_tier == (
            "recommend_urgent"
        )
