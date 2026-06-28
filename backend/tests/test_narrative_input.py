"""Tests for narrative_input.py"""
from __future__ import annotations

from app.services.narrative_input import build_narrative_input

# ---------------------------------------------------------------------------
# Minimal mock report (dict form — most flexible for testing)
# ---------------------------------------------------------------------------

def _make_minimal_report(**overrides) -> dict:
    base = {
        "patient_id": "pt-001",
        "generated_at": "2025-01-01T00:00:00Z",
        "overall_status": "attention",
        "overall_status_text_vi": "Cần chú ý một số chỉ số.",
        "top_priorities": [],
        "insights": [],
        "action_cards": [],
        "timeline": [],
        "positive_reinforcement": [],
        "urgent_alerts": [],
        "ai_draft_contract": None,
        "disclaimer_vi": "Đây là thông tin tham khảo.",
        "priorities": [],
        "patterns_v3": [],
        "context_completeness": 0.7,
        "missing_context": [],
        "preventive_risk_domains": [],
        "next_best_action": None,
        "secondary_actions": [],
        "recommendation_ranking_explanation_vi": "",
    }
    base.update(overrides)
    return base


def _make_insight(idx: int = 0) -> dict:
    return {
        "card_id": f"card_{idx}",
        "title_vi": f"Chỉ số {idx} cần chú ý",
        "explanation_vi": f"Giải thích {idx}",
        "importance": "high",
        "supporting_biomarkers": ["glucose"],
        "trend": "stable",
        "recommended_action": "discuss_with_doctor",
        "action_text_vi": "Gặp bác sĩ",
        "severity_label": "cần chú ý",
        "rationale_vi": f"Lý do {idx}",
        "evidence_level": "strong",
        "urgency_vi": "Sớm",
    }


def _make_urgent_alert(idx: int = 0) -> dict:
    return {
        "alert_id": f"alert_{idx}",
        "title_vi": f"Cảnh báo {idx}",
        "detail_vi": f"Chi tiết {idx}",
        "biomarkers": ["glucose"],
        "action_vi": "Gặp bác sĩ",
    }


def _make_priority(idx: int = 0) -> dict:
    return {
        "rank": idx + 1,
        "issue_id": f"issue_{idx}",
        "title_vi": f"Vấn đề {idx}",
        "explanation_vi": f"Giải thích vấn đề {idx}",
        "urgency": "routine",
        "urgency_vi": "Định kỳ",
    }


def _make_preventive_domain(level: str = "needs_monitoring") -> dict:
    return {
        "domain_id": "cardiometabolic",
        "display_name_vi": "Tim mạch chuyển hóa",
        "level": level,
        "level_vi": "Cần theo dõi",
        "description_vi": "Mô tả domain",
        "contributing_factors": [],
        "missing_data": [],
        "confidence": "high",
        "evidence_level": "established",
        "safety_note_vi": "An toàn.",
    }


def _make_next_best_action() -> dict:
    return {
        "action_id": "nba_1",
        "title_vi": "Hành động tốt nhất",
        "why_vi": "Vì lý do này",
        "expected_benefit_vi": "Lợi ích mong đợi",
        "timeframe_vi": "Trong 1 tháng",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBuildFromReport:
    def test_build_returns_dict(self):
        report = _make_minimal_report()
        result = build_narrative_input(report)
        assert isinstance(result, dict)

    def test_has_all_expected_keys(self):
        report = _make_minimal_report()
        result = build_narrative_input(report)
        expected_keys = {
            "language", "overall_status", "overall_summary", "urgent_alerts",
            "top_insights", "clinical_patterns", "preventive_domains",
            "next_best_action", "missing_context", "context_completeness",
            "positive_areas", "top_priorities",
        }
        assert expected_keys.issubset(result.keys())

    def test_overall_status_preserved(self):
        report = _make_minimal_report(overall_status="urgent")
        result = build_narrative_input(report)
        assert result["overall_status"] == "urgent"

    def test_language_default_vi(self):
        report = _make_minimal_report()
        result = build_narrative_input(report)
        assert result["language"] == "vi"

    def test_language_custom(self):
        report = _make_minimal_report()
        result = build_narrative_input(report, language="en")
        assert result["language"] == "en"

    def test_context_completeness_rounded(self):
        report = _make_minimal_report(context_completeness=0.7777)
        result = build_narrative_input(report)
        assert result["context_completeness"] == 0.78

    def test_next_best_action_included(self):
        report = _make_minimal_report(next_best_action=_make_next_best_action())
        result = build_narrative_input(report)
        assert result["next_best_action"] is not None
        assert result["next_best_action"]["title"] == "Hành động tốt nhất"

    def test_next_best_action_none_when_missing(self):
        report = _make_minimal_report(next_best_action=None)
        result = build_narrative_input(report)
        assert result["next_best_action"] is None


class TestNoInternalFields:
    def test_no_patient_id(self):
        report = _make_minimal_report()
        result = build_narrative_input(report)
        assert "patient_id" not in result

    def test_no_generated_at(self):
        report = _make_minimal_report()
        result = build_narrative_input(report)
        assert "generated_at" not in result

    def test_no_ai_draft_contract(self):
        report = _make_minimal_report()
        result = build_narrative_input(report)
        assert "ai_draft_contract" not in result

    def test_no_disclaimer_vi(self):
        report = _make_minimal_report()
        result = build_narrative_input(report)
        assert "disclaimer_vi" not in result


class TestMaxLimits:
    def test_max_5_insights(self):
        insights = [_make_insight(i) for i in range(10)]
        report = _make_minimal_report(insights=insights)
        result = build_narrative_input(report)
        assert len(result["top_insights"]) == 5

    def test_max_3_patterns(self):
        patterns = [{"name_vi": f"Pattern {i}"} for i in range(8)]
        report = _make_minimal_report(patterns_v3=patterns)
        result = build_narrative_input(report)
        assert len(result["clinical_patterns"]) == 3

    def test_max_3_urgent_alerts(self):
        alerts = [_make_urgent_alert(i) for i in range(6)]
        report = _make_minimal_report(urgent_alerts=alerts)
        result = build_narrative_input(report)
        assert len(result["urgent_alerts"]) == 3

    def test_max_5_preventive_domains(self):
        domains = [
            {**_make_preventive_domain("needs_monitoring"), "domain_id": f"domain_{i}"}
            for i in range(8)
        ]
        report = _make_minimal_report(preventive_risk_domains=domains)
        result = build_narrative_input(report)
        assert len(result["preventive_domains"]) <= 5

    def test_max_3_priorities(self):
        priorities = [_make_priority(i) for i in range(6)]
        report = _make_minimal_report(priorities=priorities)
        result = build_narrative_input(report)
        assert len(result["top_priorities"]) == 3

    def test_max_5_missing_context(self):
        missing = [f"missing_{i}" for i in range(10)]
        report = _make_minimal_report(missing_context=missing)
        result = build_narrative_input(report)
        assert len(result["missing_context"]) == 5


class TestLowConcernDomainsExcluded:
    def test_low_concern_excluded(self):
        domains = [
            _make_preventive_domain("low_concern"),
            _make_preventive_domain("needs_monitoring"),
        ]
        domains[1]["domain_id"] = "domain_b"
        report = _make_minimal_report(preventive_risk_domains=domains)
        result = build_narrative_input(report)
        # Only needs_monitoring should be present
        assert len(result["preventive_domains"]) == 1
        assert result["preventive_domains"][0]["level"] == "needs_monitoring"

    def test_all_low_concern_means_empty_domains(self):
        domains = [_make_preventive_domain("low_concern") for _ in range(3)]
        report = _make_minimal_report(preventive_risk_domains=domains)
        result = build_narrative_input(report)
        assert result["preventive_domains"] == []


class TestHandlesEmptyReport:
    def test_empty_lists_no_crash(self):
        report = _make_minimal_report(
            insights=[],
            urgent_alerts=[],
            priorities=[],
            patterns_v3=[],
            preventive_risk_domains=[],
            positive_reinforcement=[],
            missing_context=[],
        )
        result = build_narrative_input(report)
        assert result["top_insights"] == []
        assert result["urgent_alerts"] == []
        assert result["top_priorities"] == []
        assert result["clinical_patterns"] == []
        assert result["preventive_domains"] == []
        assert result["positive_areas"] == []
        assert result["missing_context"] == []

    def test_none_lists_no_crash(self):
        report = _make_minimal_report(
            insights=None,
            urgent_alerts=None,
            priorities=None,
            patterns_v3=None,
            preventive_risk_domains=None,
            positive_reinforcement=None,
            missing_context=None,
            context_completeness=None,
            next_best_action=None,
        )
        result = build_narrative_input(report)
        assert result["top_insights"] == []
        assert result["context_completeness"] == 0.0

    def test_zero_context_completeness(self):
        report = _make_minimal_report(context_completeness=0.0)
        result = build_narrative_input(report)
        assert result["context_completeness"] == 0.0


class TestInsightFields:
    def test_insight_fields_extracted(self):
        insight = _make_insight(0)
        report = _make_minimal_report(insights=[insight])
        result = build_narrative_input(report)
        assert len(result["top_insights"]) == 1
        top = result["top_insights"][0]
        assert top["title"] == insight["title_vi"]
        assert top["importance"] == insight["importance"]
        assert top["severity"] == insight["severity_label"]
        assert top["trend"] == insight["trend"]
        assert top["rationale"] == insight["rationale_vi"]

    def test_urgent_alert_fields_extracted(self):
        alert = _make_urgent_alert(0)
        report = _make_minimal_report(urgent_alerts=[alert])
        result = build_narrative_input(report)
        assert result["urgent_alerts"][0]["title"] == alert["title_vi"]
        assert result["urgent_alerts"][0]["detail"] == alert["detail_vi"]
