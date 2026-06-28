"""CKP integration tests for medical_narrative.py — Phase 4."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from app.knowledge.registry import reset_registry
from app.services.medical_narrative import NarrativeResult, generate_narrative

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_report(**overrides) -> dict:
    base = {
        "patient_id": "pt-ckp",
        "generated_at": "2026-06-28T00:00:00Z",
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
        "section_1_summary": "Tổng quan sức khỏe ổn định.",
        "section_2_what_happened": "Điều đang xảy ra với các chỉ số.",
        "section_3_reasoning": "Cách AI suy luận từ dữ liệu.",
        "section_4_personal_context": "Ý nghĩa cá nhân.",
        "section_5_if_nothing_changes": "Nên theo dõi.",
        "section_6_most_important_today": "Nên trao đổi với bác sĩ.",
        "section_7_monthly_plan": ["Theo dõi định kỳ", "Lối sống lành mạnh", "Tái khám"],
        "section_8_what_ai_doesnt_know": ["Tiền sử bệnh"],
        "section_9_doctor_questions": ["Câu hỏi 1?", "Câu hỏi 2?", "Câu hỏi 3?"],
        "section_10_disclaimer": (
            "Giải thích này chỉ hỗ trợ hiểu thông tin sức khỏe, "
            "không thay thế đánh giá, chẩn đoán hoặc điều trị từ chuyên gia y tế."
        ),
    }


def _make_mock_response(narrative: dict) -> MagicMock:
    response = MagicMock()
    content_block = MagicMock()
    content_block.text = json.dumps(narrative, ensure_ascii=False)
    response.content = [content_block]
    response.usage = MagicMock()
    response.usage.input_tokens = 800
    response.usage.output_tokens = 400
    return response


@pytest.fixture(autouse=True)
def reset_singletons():
    reset_registry()
    yield
    reset_registry()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCKPKnowledgeCardsIntegration:
    def test_narrative_uses_knowledge_cards(self, tmp_path, monkeypatch):
        """Mock report with ldl_elevated insight → knowledge_cards_used includes 'ldl_elevated'."""
        # Point registry to the real cards directory
        real_cards = Path(__file__).parent.parent / "app" / "knowledge" / "cards"
        monkeypatch.setenv("KNOWLEDGE_BASE_PATH", str(real_cards))

        report = _make_report(
            insights=[{"card_id": "ldl_elevated", "title_vi": "LDL cao"}]
        )

        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_mock_response(
            _make_valid_claude_narrative()
        )

        with (
            patch("app.services.medical_narrative.ANTHROPIC_API_KEY", "test-key"),
            patch("app.services.medical_narrative.get_client", return_value=mock_client),
            patch("app.services.medical_narrative.get_cached_narrative", return_value=None),
            patch("app.services.medical_narrative.save_narrative"),
            patch("app.services.medical_narrative.save_narrative_memory"),
        ):
            result = generate_narrative(report, "pt-ckp-1", "batch-ckp-1", use_cache=False)

        assert isinstance(result, NarrativeResult)
        assert "ldl_elevated" in result.knowledge_cards_used

    def test_narrative_memory_saved_after_generation(self, tmp_path, monkeypatch):
        """generate_narrative() with no cache → memory save is called."""
        real_cards = Path(__file__).parent.parent / "app" / "knowledge" / "cards"
        monkeypatch.setenv("KNOWLEDGE_BASE_PATH", str(real_cards))
        monkeypatch.setenv("NARRATIVE_MEMORY_DIR", str(tmp_path))

        report = _make_report()

        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_mock_response(
            _make_valid_claude_narrative()
        )

        save_memory_calls = []

        def mock_save_memory(patient_id, narrative, report_summary):
            save_memory_calls.append((patient_id, narrative))

        with (
            patch("app.services.medical_narrative.ANTHROPIC_API_KEY", "test-key"),
            patch("app.services.medical_narrative.get_client", return_value=mock_client),
            patch("app.services.medical_narrative.get_cached_narrative", return_value=None),
            patch("app.services.medical_narrative.save_narrative"),
            patch("app.services.medical_narrative.save_narrative_memory", side_effect=mock_save_memory),
        ):
            result = generate_narrative(report, "pt-mem-1", "batch-mem-1", use_cache=False)

        assert result.source == "claude"
        assert len(save_memory_calls) == 1
        assert save_memory_calls[0][0] == "pt-mem-1"

    def test_narrative_memory_loaded_on_second_call(self, tmp_path, monkeypatch):
        """First call saves memory; second call → narrative_memory_used=True."""
        real_cards = Path(__file__).parent.parent / "app" / "knowledge" / "cards"
        monkeypatch.setenv("KNOWLEDGE_BASE_PATH", str(real_cards))

        # Simulate memory already exists (second call scenario)
        existing_memory = {
            "patient_id": "pt-mem-2",
            "last_narrative_summary": "Tổng quan lần trước.",
            "previous_section6": "Tập thể dục.",
            "report_overall_status": "attention",
            "previous_priorities": [],
            "previous_doctor_questions": [],
            "saved_at": "2026-06-27T10:00:00+00:00",
        }

        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_mock_response(
            _make_valid_claude_narrative()
        )

        with (
            patch("app.services.medical_narrative.ANTHROPIC_API_KEY", "test-key"),
            patch("app.services.medical_narrative.get_client", return_value=mock_client),
            patch("app.services.medical_narrative.get_cached_narrative", return_value=None),
            patch("app.services.medical_narrative.save_narrative"),
            patch("app.services.medical_narrative.save_narrative_memory"),
            patch(
                "app.services.medical_narrative.load_narrative_memory",
                return_value=existing_memory,
            ),
        ):
            result = generate_narrative(
                _make_report(), "pt-mem-2", "batch-mem-2", use_cache=False
            )

        assert result.narrative_memory_used is True

    def test_narrative_no_cards_for_unknown_insight(self, tmp_path, monkeypatch):
        """Report with unknown insight card_id → knowledge_cards_used=[]."""
        real_cards = Path(__file__).parent.parent / "app" / "knowledge" / "cards"
        monkeypatch.setenv("KNOWLEDGE_BASE_PATH", str(real_cards))

        report = _make_report(
            insights=[{"card_id": "totally_unknown_biomarker_xyz", "title_vi": "Unknown"}]
        )

        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_mock_response(
            _make_valid_claude_narrative()
        )

        with (
            patch("app.services.medical_narrative.ANTHROPIC_API_KEY", "test-key"),
            patch("app.services.medical_narrative.get_client", return_value=mock_client),
            patch("app.services.medical_narrative.get_cached_narrative", return_value=None),
            patch("app.services.medical_narrative.save_narrative"),
            patch("app.services.medical_narrative.save_narrative_memory"),
        ):
            result = generate_narrative(report, "pt-unk-1", "batch-unk-1", use_cache=False)

        assert result.knowledge_cards_used == []

    def test_narrative_ckp_fallback_still_works(self, tmp_path, monkeypatch):
        """No API key → fallback returns valid NarrativeResult with empty knowledge fields."""
        # Even with CKP imported, fallback must work
        report = _make_report()

        with patch("app.services.medical_narrative.ANTHROPIC_API_KEY", ""):
            result = generate_narrative(report, "pt-fallback", "batch-fallback", use_cache=False)

        assert isinstance(result, NarrativeResult)
        assert result.source == "fallback_empty"
        assert result.knowledge_cards_used == []
        assert result.narrative_memory_used is False
