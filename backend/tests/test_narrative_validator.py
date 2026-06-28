"""Tests for narrative_validator.py"""
from __future__ import annotations

import pytest
from app.services.narrative_validator import REQUIRED_SECTIONS, validate_narrative

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_valid_narrative(**overrides) -> dict:
    """Return a well-formed 10-section narrative."""
    base = {
        "section_1_summary": "Tổng quan: các chỉ số đang ở mức cần chú ý.",
        "section_2_what_happened": "Một số chỉ số có thể gợi ý cần theo dõi thêm.",
        "section_3_reasoning": "Hệ thống đã suy luận dựa trên các giá trị được phân loại.",
        "section_4_personal_context": "Điều này có thể có ý nghĩa với tình trạng của bạn.",
        "section_5_if_nothing_changes": "Nếu không thay đổi, nên theo dõi thêm.",
        "section_6_most_important_today": "Nên trao đổi với bác sĩ trong lần khám tiếp theo.",
        "section_7_monthly_plan": ["Theo dõi định kỳ", "Duy trì lối sống lành mạnh", "Tái khám"],
        "section_8_what_ai_doesnt_know": ["Tiền sử bệnh gia đình", "Tình trạng toàn diện"],
        "section_9_doctor_questions": ["Tôi cần xét nghiệm gì thêm?", "Khi nào tái khám?", "Lối sống nào phù hợp?"],
        "section_10_disclaimer": "Giải thích này chỉ hỗ trợ hiểu thông tin sức khỏe, không thay thế đánh giá, chẩn đoán hoặc điều trị từ chuyên gia y tế.",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAllSectionsPresent:
    def test_all_sections_present(self):
        narrative = _make_valid_narrative()
        result = validate_narrative(narrative, "attention")
        assert result["passed"] is True
        assert result["reason"] == "OK"
        assert result["failed_sections"] == []

    def test_valid_narrative_passes(self):
        narrative = _make_valid_narrative()
        result = validate_narrative(narrative, "good")
        assert result["passed"] is True


class TestMissingSection:
    @pytest.mark.parametrize("section", REQUIRED_SECTIONS)
    def test_missing_section(self, section):
        narrative = _make_valid_narrative()
        del narrative[section]
        result = validate_narrative(narrative, "attention")
        assert result["passed"] is False
        assert section in result["failed_sections"]

    def test_empty_string_section(self):
        narrative = _make_valid_narrative(section_1_summary="")
        result = validate_narrative(narrative, "attention")
        assert result["passed"] is False
        assert "section_1_summary" in result["failed_sections"]

    def test_empty_list_section(self):
        narrative = _make_valid_narrative(section_7_monthly_plan=[])
        result = validate_narrative(narrative, "attention")
        assert result["passed"] is False
        assert "section_7_monthly_plan" in result["failed_sections"]

    def test_whitespace_only_section(self):
        narrative = _make_valid_narrative(section_2_what_happened="   ")
        result = validate_narrative(narrative, "attention")
        assert result["passed"] is False
        assert "section_2_what_happened" in result["failed_sections"]


class TestForbiddenDiagnosis:
    def test_forbidden_diagnosis_chuan_doan(self):
        narrative = _make_valid_narrative(
            section_1_summary="Dựa trên kết quả, có thể chẩn đoán đây là tình trạng X."
        )
        result = validate_narrative(narrative, "attention")
        assert result["passed"] is False
        assert "chẩn đoán" in result["reason"]

    def test_forbidden_diagnosis_ban_bi(self):
        narrative = _make_valid_narrative(
            section_2_what_happened="Bạn bị tiểu đường type 2."
        )
        result = validate_narrative(narrative, "attention")
        assert result["passed"] is False

    def test_forbidden_diagnosis_xac_nhan(self):
        narrative = _make_valid_narrative(
            section_3_reasoning="Xác nhận tình trạng này qua các chỉ số."
        )
        result = validate_narrative(narrative, "attention")
        assert result["passed"] is False


class TestForbiddenMedication:
    def test_forbidden_medication_ke_don(self):
        narrative = _make_valid_narrative(
            section_6_most_important_today="Bạn nên kê đơn thuốc metformin."
        )
        result = validate_narrative(narrative, "attention")
        assert result["passed"] is False
        assert "kê đơn" in result["reason"]

    def test_forbidden_medication_dung_thuoc(self):
        narrative = _make_valid_narrative(
            section_4_personal_context="Không nên dừng thuốc đột ngột."
        )
        result = validate_narrative(narrative, "attention")
        assert result["passed"] is False

    def test_forbidden_medication_tang_lieu(self):
        narrative = _make_valid_narrative(
            section_5_if_nothing_changes="Nên tăng liều thuốc hiện tại."
        )
        result = validate_narrative(narrative, "attention")
        assert result["passed"] is False


class TestPanicLanguage:
    def test_panic_non_critical_blocked(self):
        narrative = _make_valid_narrative(
            section_1_summary="Đây là tình trạng nguy hiểm đến tính mạng của bạn."
        )
        result = validate_narrative(narrative, "attention")
        assert result["passed"] is False
        assert "nguy hiểm đến tính mạng" in result["reason"]

    def test_panic_non_critical_cap_cuu_blocked(self):
        narrative = _make_valid_narrative(
            section_6_most_important_today="Cấp cứu ngay lập tức."
        )
        result = validate_narrative(narrative, "good")
        assert result["passed"] is False

    def test_panic_allowed_critical(self):
        """For critical/urgent status, panic language is ALLOWED."""
        narrative = _make_valid_narrative(
            section_1_summary="Đây là tình trạng nguy hiểm đến tính mạng cần can thiệp."
        )
        # critical and urgent statuses allow panic language
        result = validate_narrative(narrative, "critical")
        assert result["passed"] is True

    def test_panic_allowed_urgent(self):
        narrative = _make_valid_narrative(
            section_1_summary="Tình trạng này nguy hiểm đến tính mạng nếu không được điều trị."
        )
        result = validate_narrative(narrative, "urgent")
        assert result["passed"] is True


class TestDisclaimerRequired:
    def test_disclaimer_missing_required_text(self):
        narrative = _make_valid_narrative(
            section_10_disclaimer="Đây chỉ là thông tin tham khảo."
        )
        result = validate_narrative(narrative, "attention")
        assert result["passed"] is False
        assert "section_10_disclaimer" in result["failed_sections"]

    def test_disclaimer_present_passes(self):
        narrative = _make_valid_narrative(
            section_10_disclaimer="Thông tin này không thay thế ý kiến bác sĩ."
        )
        result = validate_narrative(narrative, "attention")
        assert result["passed"] is True
