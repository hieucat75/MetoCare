"""Tests for InsightCard v2 fields: biomarker_explainer, reasoning_steps, urgency, evidence."""
from __future__ import annotations

from app.domain.insight_detail_content import INSIGHT_DETAIL, get_insight_detail


class TestInsightDetailContent:
    def test_all_cards_have_v2_fields(self):
        required_v2 = ["biomarker_explainer_vi", "reasoning_steps", "urgency_label", "evidence_level"]
        for card_id, content in INSIGHT_DETAIL.items():
            for field in required_v2:
                assert field in content, f"Card '{card_id}' missing field '{field}'"
                assert content[field], f"Card '{card_id}' field '{field}' is empty"

    def test_reasoning_steps_are_list(self):
        for card_id, content in INSIGHT_DETAIL.items():
            steps = content.get("reasoning_steps", [])
            assert isinstance(steps, list), f"Card '{card_id}' reasoning_steps should be list"
            assert len(steps) >= 2, f"Card '{card_id}' needs at least 2 reasoning steps"

    def test_urgency_label_valid(self):
        valid = {"routine", "1_month", "soon", "immediately"}
        for card_id, content in INSIGHT_DETAIL.items():
            label = content.get("urgency_label", "")
            assert label in valid, f"Card '{card_id}' has invalid urgency_label: '{label}'"

    def test_evidence_level_valid(self):
        valid = {"strong", "moderate", "emerging"}
        for card_id, content in INSIGHT_DETAIL.items():
            level = content.get("evidence_level", "")
            assert level in valid, f"Card '{card_id}' has invalid evidence_level: '{level}'"

    def test_ldl_elevated_has_related_insights(self):
        d = get_insight_detail("ldl_elevated")
        assert d is not None
        assert "related_insights" in d
        assert len(d["related_insights"]) > 0

    def test_biomarker_explainer_patient_friendly(self):
        """Explainer should not contain untranslated clinical jargon without explanation."""
        d = get_insight_detail("ldl_elevated")
        assert d is not None
        text = d["biomarker_explainer_vi"]
        # Should mention LDL and explain in plain language
        assert "LDL" in text
        assert len(text) > 100  # should be substantive

    def test_all_cards_have_urgency_vi(self):
        for card_id, content in INSIGHT_DETAIL.items():
            assert "urgency_vi" in content, f"Card '{card_id}' missing urgency_vi"
            assert content["urgency_vi"], f"Card '{card_id}' urgency_vi is empty"

    def test_all_cards_have_evidence_label_vi(self):
        for card_id, content in INSIGHT_DETAIL.items():
            assert "evidence_label_vi" in content, f"Card '{card_id}' missing evidence_label_vi"
            assert content["evidence_label_vi"], f"Card '{card_id}' evidence_label_vi is empty"


class TestInsightCardV2Fields:
    """Test that InsightCard dataclass has v2 fields."""

    def test_insightcard_has_v2_fields(self):
        from app.domain.patient_insight import InsightCard
        card = InsightCard(
            card_id="test",
            title_vi="Test",
            explanation_vi="test",
            importance="low",
            supporting_biomarkers=[],
            trend="stable",
            recommended_action="continue_monitoring",
            action_text_vi="test",
        )
        # v2 fields should exist with defaults
        assert hasattr(card, "biomarker_explainer_vi")
        assert hasattr(card, "reasoning_steps")
        assert hasattr(card, "related_insights")
        assert hasattr(card, "urgency_label")
        assert hasattr(card, "evidence_level")
        assert hasattr(card, "derived_indicators")
        assert card.derived_indicators == []
        assert card.reasoning_steps == []
        assert card.related_insights == []
        assert card.biomarker_explainer_vi == ""
        assert card.urgency_label == ""
        assert card.evidence_level == ""

    def test_insightcard_v2_patterns_vi_default(self):
        from app.domain.patient_insight import InsightCard
        card = InsightCard(
            card_id="test2",
            title_vi="Test",
            explanation_vi="test",
            importance="medium",
            supporting_biomarkers=[],
            trend="stable",
            recommended_action="repeat_lab",
            action_text_vi="test",
        )
        assert hasattr(card, "patterns_vi")
        assert card.patterns_vi == []
