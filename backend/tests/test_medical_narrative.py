"""Tests for medical_narrative.py"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from app.services.medical_narrative import (
    NarrativeResult,
    _build_fallback_narrative,
    generate_narrative,
)
from app.services.narrative_validator import REQUIRED_SECTIONS

# ---------------------------------------------------------------------------
# Minimal mock PatientInsightReport
# ---------------------------------------------------------------------------

def _make_report(**overrides) -> dict:
    base = {
        "patient_id": "pt-test",
        "generated_at": "2025-01-01T00:00:00Z",
        "overall_status": "attention",
        "overall_status_text_vi": "Cần chú ý.",
        "top_priorities": [],
        "insights": [],
        "action_cards": [],
        "timeline": [],
        "positive_reinforcement": [],
        "urgent_alerts": [],
        "ai_draft_contract": None,
        "disclaimer_vi": "Tham khảo.",
        "priorities": [],
        "patterns_v3": [],
        "context_completeness": 0.5,
        "missing_context": [],
        "preventive_risk_domains": [],
        "next_best_action": None,
        "secondary_actions": [],
        "recommendation_ranking_explanation_vi": "",
    }
    base.update(overrides)
    return base


def _make_valid_claude_narrative() -> dict:
    return {
        "section_1_summary": "Tổng quan AI về tình trạng sức khỏe.",
        "section_2_what_happened": "Điều đang xảy ra với các chỉ số.",
        "section_3_reasoning": "Cách AI suy luận từ dữ liệu.",
        "section_4_personal_context": "Ý nghĩa cá nhân của kết quả.",
        "section_5_if_nothing_changes": "Điều có thể xảy ra nếu không thay đổi.",
        "section_6_most_important_today": "Nên trao đổi với bác sĩ trong lần khám tiếp theo.",
        "section_7_monthly_plan": ["Theo dõi định kỳ", "Duy trì lối sống lành mạnh", "Tái khám"],
        "section_8_what_ai_doesnt_know": ["Tiền sử bệnh", "Thông tin bổ sung"],
        "section_9_doctor_questions": ["Câu hỏi 1?", "Câu hỏi 2?", "Câu hỏi 3?"],
        "section_10_disclaimer": "Giải thích này chỉ hỗ trợ hiểu thông tin sức khỏe, không thay thế đánh giá, chẩn đoán hoặc điều trị từ chuyên gia y tế.",
    }


def _make_mock_anthropic_response(narrative: dict) -> MagicMock:
    response = MagicMock()
    content_block = MagicMock()
    content_block.text = json.dumps(narrative, ensure_ascii=False)
    response.content = [content_block]
    response.usage = MagicMock()
    response.usage.input_tokens = 1000
    response.usage.output_tokens = 500
    return response


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFallbackOnNoApiKey:
    def test_fallback_when_no_api_key(self):
        report = _make_report()
        with patch("app.services.medical_narrative.ANTHROPIC_API_KEY", ""):
            result = generate_narrative(report, "pt-test", "batch-001", use_cache=False)
        assert isinstance(result, NarrativeResult)
        assert result.source == "fallback_empty"
        assert result.cached is False
        # Still has all 10 sections
        for section in REQUIRED_SECTIONS:
            assert section in result.narrative

    def test_fallback_source_is_fallback_empty(self):
        report = _make_report()
        with patch("app.services.medical_narrative.ANTHROPIC_API_KEY", ""):
            result = generate_narrative(report, "pt-001", None, use_cache=False)
        assert "fallback" in result.source


class TestFallbackOnValidatorFail:
    def test_fallback_used_when_validator_fails(self):
        """When Claude returns bad narrative, fallback is used."""
        bad_narrative = {
            "section_1_summary": "Bạn bị tiểu đường — đây là chẩn đoán chính thức.",  # forbidden
            "section_2_what_happened": "Mô tả.",
            "section_3_reasoning": "Lý do.",
            "section_4_personal_context": "Cá nhân.",
            "section_5_if_nothing_changes": "Không thay đổi.",
            "section_6_most_important_today": "Việc quan trọng.",
            "section_7_monthly_plan": ["Kế hoạch 1"],
            "section_8_what_ai_doesnt_know": ["Điều chưa biết"],
            "section_9_doctor_questions": ["Câu hỏi"],
            "section_10_disclaimer": "Giải thích này không thay thế ý kiến bác sĩ.",
        }
        mock_response = _make_mock_anthropic_response(bad_narrative)
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        report = _make_report()
        with patch("app.services.medical_narrative.ANTHROPIC_API_KEY", "sk-test"):
            with patch("app.services.medical_narrative.get_client", return_value=mock_client):
                result = generate_narrative(report, "pt-test", "batch-001", use_cache=False)

        assert result.source == "fallback_validator_fail"
        assert result.validation_passed is False
        # Fallback still has all 10 sections
        for section in REQUIRED_SECTIONS:
            assert section in result.narrative


class TestCacheHit:
    def test_cache_hit_returns_cached(self, tmp_path, monkeypatch):
        """Saving then loading from cache returns source='cache'."""
        from app.services.claude_client import ANTHROPIC_MODEL
        from app.services.narrative_cache import make_narrative_key, save_narrative
        from app.services.narrative_prompts import ENGINE_VERSION, PROMPT_VERSION

        report = _make_report()
        patient_id = "pt-cache-test"
        batch_id = "batch-cache-001"

        # Pre-populate cache at a custom dir
        import app.services.narrative_cache as nc
        original_dir = nc.NARRATIVE_CACHE_DIR
        nc.NARRATIVE_CACHE_DIR = str(tmp_path)
        try:
            cache_key = make_narrative_key(
                patient_id=patient_id,
                batch_id=batch_id,
                engine_version=ENGINE_VERSION,
                prompt_version=PROMPT_VERSION,
                provider="anthropic",
                model=ANTHROPIC_MODEL,
                language="vi",
            )
            valid_narrative = _make_valid_claude_narrative()
            save_narrative(cache_key, {
                "narrative": valid_narrative,
                "prompt_version": PROMPT_VERSION,
                "engine_version": ENGINE_VERSION,
                "provider": "anthropic",
                "model": ANTHROPIC_MODEL,
                "prompt_tokens": 100,
                "completion_tokens": 50,
            })

            # get_cached_narrative already uses nc.NARRATIVE_CACHE_DIR (same reference)
            with patch("app.services.medical_narrative.ANTHROPIC_API_KEY", ""):
                result = generate_narrative(report, patient_id, batch_id, use_cache=True)

            assert result.source == "cache"
            assert result.cached is True
            assert result.narrative == valid_narrative
        finally:
            nc.NARRATIVE_CACHE_DIR = original_dir


class TestNarrativeResultStructure:
    def test_result_has_all_required_fields(self):
        report = _make_report()
        with patch("app.services.medical_narrative.ANTHROPIC_API_KEY", ""):
            result = generate_narrative(report, "pt-test", "batch-001", use_cache=False)

        assert hasattr(result, "patient_id")
        assert hasattr(result, "batch_id")
        assert hasattr(result, "narrative")
        assert hasattr(result, "source")
        assert hasattr(result, "cached")
        assert hasattr(result, "prompt_version")
        assert hasattr(result, "engine_version")
        assert hasattr(result, "provider")
        assert hasattr(result, "model")
        assert hasattr(result, "quality_score")
        assert hasattr(result, "validation_passed")
        assert hasattr(result, "latency_ms")
        assert hasattr(result, "prompt_tokens")
        assert hasattr(result, "completion_tokens")

    def test_result_patient_id_matches(self):
        report = _make_report()
        with patch("app.services.medical_narrative.ANTHROPIC_API_KEY", ""):
            result = generate_narrative(report, "pt-xyz", "batch-abc", use_cache=False)
        assert result.patient_id == "pt-xyz"
        assert result.batch_id == "batch-abc"


class TestNeverRaises:
    def test_exception_in_client_returns_fallback(self):
        """Even if get_client() raises, generate_narrative returns fallback."""
        def bad_get_client():
            raise RuntimeError("Network error simulated")

        report = _make_report()
        with patch("app.services.medical_narrative.ANTHROPIC_API_KEY", "sk-test"):
            with patch("app.services.medical_narrative.get_client", side_effect=bad_get_client):
                result = generate_narrative(report, "pt-err", None, use_cache=False)

        # Check by attributes (avoids class identity issues from module reloads)
        assert result.source == "fallback_error"
        assert result.narrative is not None
        assert result.patient_id == "pt-err"

    def test_json_parse_error_returns_fallback(self):
        """If Claude returns non-JSON, fallback is used."""
        mock_response = MagicMock()
        content_block = MagicMock()
        content_block.text = "This is not JSON at all!"
        mock_response.content = [content_block]
        mock_response.usage = MagicMock()
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        report = _make_report()
        with patch("app.services.medical_narrative.ANTHROPIC_API_KEY", "sk-test"):
            with patch("app.services.medical_narrative.get_client", return_value=mock_client):
                result = generate_narrative(report, "pt-err2", None, use_cache=False)

        assert result.source == "fallback_error"

    def test_none_report_handled(self):
        """None-like report (empty dict) should not crash."""
        with patch("app.services.medical_narrative.ANTHROPIC_API_KEY", ""):
            result = generate_narrative({}, "pt-none", None, use_cache=False)
        # Check by attributes only
        assert hasattr(result, "source")
        assert hasattr(result, "narrative")

    def test_latency_ms_is_non_negative(self):
        report = _make_report()
        with patch("app.services.medical_narrative.ANTHROPIC_API_KEY", ""):
            result = generate_narrative(report, "pt-latency", None, use_cache=False)
        assert result.latency_ms >= 0


class TestFallbackNarrative10Sections:
    def test_fallback_has_all_10_sections(self):
        report = _make_report()
        fallback = _build_fallback_narrative(report)
        for section in REQUIRED_SECTIONS:
            assert section in fallback

    def test_fallback_lists_are_non_empty(self):
        report = _make_report()
        fallback = _build_fallback_narrative(report)
        assert len(fallback["section_7_monthly_plan"]) > 0
        assert len(fallback["section_8_what_ai_doesnt_know"]) > 0
        assert len(fallback["section_9_doctor_questions"]) > 0

    def test_fallback_disclaimer_has_required_text(self):
        report = _make_report()
        fallback = _build_fallback_narrative(report)
        assert "không thay thế" in fallback["section_10_disclaimer"].lower()

    def test_fallback_no_forbidden_phrases(self):
        from app.services.narrative_validator import validate_narrative
        report = _make_report()
        fallback = _build_fallback_narrative(report)
        result = validate_narrative(fallback, "attention")
        assert result["passed"] is True, f"Fallback failed validation: {result['reason']}"

    def test_fallback_urgent_status(self):
        report = _make_report(overall_status="urgent")
        fallback = _build_fallback_narrative(report)
        assert isinstance(fallback, dict)
        for section in REQUIRED_SECTIONS:
            assert section in fallback

    def test_fallback_with_insights(self):
        report = _make_report(insights=[{
            "card_id": "c1",
            "title_vi": "Chỉ số quan trọng",
            "rationale_vi": "Lý do quan trọng",
            "doctor_questions": ["Câu hỏi 1?"],
        }])
        fallback = _build_fallback_narrative(report)
        assert len(fallback["section_9_doctor_questions"]) >= 1


class TestSuccessfulClaudeGeneration:
    def test_claude_success_returns_claude_source(self):
        valid_narrative = _make_valid_claude_narrative()
        mock_response = _make_mock_anthropic_response(valid_narrative)
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        report = _make_report()
        with patch("app.services.medical_narrative.ANTHROPIC_API_KEY", "sk-test"):
            with patch("app.services.medical_narrative.get_client", return_value=mock_client):
                result = generate_narrative(report, "pt-ok", "batch-ok", use_cache=False)

        assert result.source == "claude"
        assert result.validation_passed is True
        assert result.narrative == valid_narrative
        assert result.prompt_tokens == 1000
        assert result.completion_tokens == 500

    def test_claude_strips_markdown_fences(self):
        valid_narrative = _make_valid_claude_narrative()
        raw = "```json\n" + json.dumps(valid_narrative, ensure_ascii=False) + "\n```"

        mock_response = MagicMock()
        content_block = MagicMock()
        content_block.text = raw
        mock_response.content = [content_block]
        mock_response.usage = MagicMock()
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        report = _make_report()
        with patch("app.services.medical_narrative.ANTHROPIC_API_KEY", "sk-test"):
            with patch("app.services.medical_narrative.get_client", return_value=mock_client):
                result = generate_narrative(report, "pt-fence", "batch-fence", use_cache=False)

        assert result.source == "claude"
        assert result.narrative == valid_narrative

    def test_quality_score_present_on_success(self):
        valid_narrative = _make_valid_claude_narrative()
        mock_response = _make_mock_anthropic_response(valid_narrative)
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        report = _make_report()
        with patch("app.services.medical_narrative.ANTHROPIC_API_KEY", "sk-test"):
            with patch("app.services.medical_narrative.get_client", return_value=mock_client):
                result = generate_narrative(report, "pt-qs", None, use_cache=False)

        assert result.quality_score is not None
        assert 0.0 <= result.quality_score.overall <= 1.0
