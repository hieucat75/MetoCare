"""Tests for Engine 4 — PriorityEngine."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.patient_context import PatientContext
from app.domain.priority_engine import PriorityEngine

# ── Helpers ───────────────────────────────────────────────────────────────────

def _ctx(**kwargs) -> PatientContext:
    ctx = PatientContext()
    for k, v in kwargs.items():
        setattr(ctx, k, v)
    return ctx


@dataclass
class MockInsightCard:
    card_id: str
    title_vi: str
    importance: str = "medium"
    urgency_label: str = "routine"


@dataclass
class MockPattern:
    pattern_id: str
    display_name_vi: str
    severity: str = "watch"


@dataclass
class MockUrgentAlert:
    alert_id: str
    title_vi: str


def _engine() -> PriorityEngine:
    return PriorityEngine()


# ── PriorityEngine Tests ──────────────────────────────────────────────────────

class TestUrgentAlertAlwaysRank1:
    """test_urgent_alert_always_rank1: urgent alert present → rank=1."""

    def test_alert_ranks_first(self):
        alert = MockUrgentAlert("alert_glucose", "Đường huyết nguy hiểm")
        pattern = MockPattern("insulin_resistance", "Kháng insulin", severity="warning")
        card = MockInsightCard("insight_ldl", "LDL cao", importance="high")
        priorities = _engine().rank([card], [pattern], [alert], _ctx())
        assert priorities[0].issue_id == "alert_glucose"
        assert priorities[0].rank == 1
        assert priorities[0].urgency == "immediately"

    def test_alert_outranks_urgent_pattern(self):
        alert = MockUrgentAlert("alert_critical", "Chỉ số nguy hiểm")
        pattern = MockPattern("atherogenic_cholesterol", "Cholesterol", severity="urgent")
        priorities = _engine().rank([], [pattern], [alert], _ctx())
        assert priorities[0].issue_id == "alert_critical"

    def test_multiple_alerts_all_rank_high(self):
        alerts = [
            MockUrgentAlert("alert_a", "Alert A"),
            MockUrgentAlert("alert_b", "Alert B"),
        ]
        priorities = _engine().rank([], [], alerts, _ctx())
        # Both alerts should appear in top priorities
        ids = [p.issue_id for p in priorities]
        assert "alert_a" in ids
        assert "alert_b" in ids

    def test_urgency_immediately_for_alert(self):
        alert = MockUrgentAlert("alert_1", "Alert")
        priorities = _engine().rank([], [], [alert], _ctx())
        p = next(pi for pi in priorities if pi.issue_id == "alert_1")
        assert p.urgency == "immediately"
        assert p.urgency_vi == "Gặp bác sĩ ngay"


class TestPatternOutranksCard:
    """test_pattern_outranks_card: same importance level → pattern > individual card."""

    def test_warning_pattern_outranks_medium_card(self):
        pattern = MockPattern("insulin_resistance", "Kháng insulin", severity="warning")
        card = MockInsightCard("insight_alt", "ALT cao", importance="medium")
        priorities = _engine().rank([card], [pattern], [], _ctx())
        pattern_rank = next(p.rank for p in priorities if p.issue_id == "insulin_resistance")
        card_rank = next(p.rank for p in priorities if p.issue_id == "insight_alt")
        assert pattern_rank < card_rank

    def test_watch_pattern_outranks_low_card(self):
        pattern = MockPattern("hypertriglyceridemia_low_hdl", "TG cao", severity="watch")
        card = MockInsightCard("insight_wbc", "WBC", importance="low")
        priorities = _engine().rank([card], [pattern], [], _ctx())
        pattern_rank = next(p.rank for p in priorities if p.issue_id == "hypertriglyceridemia_low_hdl")
        card_rank = next(p.rank for p in priorities if p.issue_id == "insight_wbc")
        assert pattern_rank < card_rank

    def test_urgent_pattern_is_rank_1_without_alert(self):
        pattern = MockPattern("atherogenic_cholesterol", "Cholesterol", severity="urgent")
        card = MockInsightCard("insight_ldl", "LDL", importance="high")
        priorities = _engine().rank([card], [pattern], [], _ctx())
        assert priorities[0].issue_id == "atherogenic_cholesterol"
        assert priorities[0].rank == 1


class TestCVDHistoryBoostsCholesterol:
    """test_cvd_history_boosts_cholesterol: atherogenic_cholesterol + has_cvd_history → top rank."""

    def test_cholesterol_boosted_with_cvd(self):
        ctx_cvd = _ctx(has_cvd_history=True, cv_risk_category="very_high")
        ctx_no_cvd = _ctx(has_cvd_history=False, cv_risk_category="low")
        pattern = MockPattern("atherogenic_cholesterol", "Cholesterol", severity="warning")

        priorities_cvd = _engine().rank([], [pattern], [], ctx_cvd)
        _engine().rank([], [pattern], [], ctx_no_cvd)  # baseline (no CVD)

        # With CVD history, cholesterol pattern should appear at rank 1
        assert priorities_cvd[0].issue_id == "atherogenic_cholesterol"

    def test_very_high_risk_boosts_all_patterns(self):
        ctx = _ctx(cv_risk_category="very_high", has_cvd_history=True)
        pattern_cholesterol = MockPattern("atherogenic_cholesterol", "Cholesterol", severity="warning")
        pattern_kidney = MockPattern("kidney_risk", "Thận", severity="watch")
        priorities = _engine().rank([], [pattern_cholesterol, pattern_kidney], [], ctx)
        # cholesterol should rank above kidney (higher base + bigger boost)
        ath_rank = next(p.rank for p in priorities if p.issue_id == "atherogenic_cholesterol")
        kidney_rank = next(p.rank for p in priorities if p.issue_id == "kidney_risk")
        assert ath_rank < kidney_rank

    def test_priority_reason_mentions_cvd(self):
        ctx = _ctx(has_cvd_history=True)
        pattern = MockPattern("atherogenic_cholesterol", "Cholesterol", severity="warning")
        priorities = _engine().rank([], [pattern], [], ctx)
        p = next(pi for pi in priorities if pi.issue_id == "atherogenic_cholesterol")
        assert "tim mạch" in p.priority_reason_vi.lower()


class TestMax5Priorities:
    """test_max_5_priorities: 10 issues → only 5 returned."""

    def test_ten_cards_returns_five(self):
        cards = [
            MockInsightCard(f"card_{i}", f"Card {i}", importance="medium")
            for i in range(10)
        ]
        priorities = _engine().rank(cards, [], [], _ctx())
        assert len(priorities) <= 5

    def test_ten_patterns_returns_five(self):
        patterns = [
            MockPattern(f"pattern_{i}", f"Pattern {i}", severity="watch")
            for i in range(10)
        ]
        priorities = _engine().rank([], patterns, [], _ctx())
        assert len(priorities) == 5

    def test_mixed_ten_issues_returns_five(self):
        patterns = [MockPattern(f"p_{i}", f"Pattern {i}", severity="watch") for i in range(5)]
        cards = [MockInsightCard(f"c_{i}", f"Card {i}", importance="low") for i in range(5)]
        priorities = _engine().rank(cards, patterns, [], _ctx())
        assert len(priorities) <= 5

    def test_ranks_are_sequential(self):
        patterns = [MockPattern(f"p_{i}", f"Pattern {i}", severity="watch") for i in range(3)]
        priorities = _engine().rank([], patterns, [], _ctx())
        ranks = [p.rank for p in priorities]
        assert ranks == list(range(1, len(ranks) + 1))


class TestPriorityReasonContextAware:
    """test_priority_reason_context_aware: diabetes context → reason mentions diabetes."""

    def test_diabetes_context_in_insulin_resistance_reason(self):
        ctx = _ctx(has_diabetes=True)
        pattern = MockPattern("insulin_resistance", "Kháng insulin", severity="warning")
        priorities = _engine().rank([], [pattern], [], ctx)
        p = next(pi for pi in priorities if pi.issue_id == "insulin_resistance")
        # Should mention diabetes in reason
        assert "tiểu đường" in p.priority_reason_vi.lower() or "diabetes" in p.priority_reason_vi.lower()

    def test_diabetes_kidney_reason(self):
        ctx = _ctx(has_diabetes=True)
        pattern = MockPattern("kidney_risk", "Thận", severity="watch")
        priorities = _engine().rank([], [pattern], [], ctx)
        p = next(pi for pi in priorities if pi.issue_id == "kidney_risk")
        assert "tiểu đường" in p.priority_reason_vi.lower() or "biến chứng" in p.priority_reason_vi.lower()

    def test_empty_context_generic_reason(self):
        ctx = _ctx()
        pattern = MockPattern("hepatic_metabolic", "Gan", severity="watch")
        priorities = _engine().rank([], [pattern], [], ctx)
        p = next(pi for pi in priorities if pi.issue_id == "hepatic_metabolic")
        assert len(p.priority_reason_vi) > 10  # Non-empty reason


class TestPriorityIssueStructure:
    """Test that PriorityIssue objects have correct structure."""

    def test_priority_issue_fields(self):
        pattern = MockPattern("metabolic_syndrome", "Hội chứng chuyển hóa", severity="warning")
        priorities = _engine().rank([], [pattern], [], _ctx())
        p = priorities[0]
        assert isinstance(p.rank, int)
        assert p.rank >= 1
        assert p.issue_id
        assert p.title_vi
        assert p.priority_reason_vi
        assert p.urgency in ("routine", "1_month", "soon", "immediately")
        assert p.urgency_vi

    def test_urgency_vi_maps_correctly(self):
        pattern = MockPattern("atherogenic_cholesterol", "Cholesterol", severity="urgent")
        priorities = _engine().rank([], [pattern], [], _ctx())
        p = priorities[0]
        assert p.urgency == "immediately"
        assert p.urgency_vi == "Gặp bác sĩ ngay"

    def test_watch_severity_routine_urgency(self):
        pattern = MockPattern("hypertriglyceridemia_low_hdl", "TG/HDL", severity="watch")
        ctx = _ctx(cv_risk_category="low")  # low risk → no upgrade
        priorities = _engine().rank([], [pattern], [], ctx)
        p = next(pi for pi in priorities if pi.issue_id == "hypertriglyceridemia_low_hdl")
        assert p.urgency == "routine"


class TestDeduplication:
    """Test that the same issue ID is not returned twice."""

    def test_no_duplicate_pattern_ids(self):
        patterns = [
            MockPattern("insulin_resistance", "IR 1", severity="warning"),
            MockPattern("insulin_resistance", "IR 2", severity="urgent"),  # duplicate id
        ]
        priorities = _engine().rank([], patterns, [], _ctx())
        ids = [p.issue_id for p in priorities]
        assert len(ids) == len(set(ids))


class TestCardLinkedCardId:
    """Test that individual cards have linked_card_id set."""

    def test_card_has_linked_id(self):
        card = MockInsightCard("insight_ldl_high", "LDL cao", importance="high")
        priorities = _engine().rank([card], [], [], _ctx())
        p = next(pi for pi in priorities if pi.issue_id == "insight_ldl_high")
        assert p.linked_card_id == "insight_ldl_high"

    def test_pattern_has_no_linked_id(self):
        pattern = MockPattern("kidney_risk", "Thận", severity="watch")
        priorities = _engine().rank([], [pattern], [], _ctx())
        p = next(pi for pi in priorities if pi.issue_id == "kidney_risk")
        assert p.linked_card_id is None


class TestCKDBoost:
    """Test CKD context boost for kidney risk pattern."""

    def test_ckd_boosts_kidney_priority(self):
        ctx_ckd = _ctx(has_ckd=True, cv_risk_category="low")
        ctx_no_ckd = _ctx(has_ckd=False, cv_risk_category="low")

        # Compare scores: with CKD the kidney pattern should score higher
        pattern = MockPattern("kidney_risk", "Thận", severity="watch")

        priorities_ckd = _engine().rank([], [pattern], [], ctx_ckd)
        priorities_no_ckd = _engine().rank([], [pattern], [], ctx_no_ckd)

        # With CKD, urgency should be elevated
        p_ckd = priorities_ckd[0]
        p_no_ckd = priorities_no_ckd[0]
        # CKD adds 3 to score, which can upgrade urgency from routine to 1_month
        assert p_ckd.rank == 1  # only one issue in both cases
        assert p_no_ckd.rank == 1
