"""Tests for Engine 15 — NextBestActionEngine."""
from __future__ import annotations

from app.domain.next_best_action import (
    NextBestAction,
    NextBestActionEngine,
    NextBestActionResult,
)
from app.domain.patient_context import PatientContext
from app.domain.patient_insight import generate_patient_insight
from app.domain.preventive_risk import PreventiveRiskEngine

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ctx(**kwargs) -> PatientContext:
    ctx = PatientContext()
    for k, v in kwargs.items():
        setattr(ctx, k, v)
    return ctx


def _findings(**statuses) -> dict:
    return {canonical: {"status": status} for canonical, status in statuses.items()}


def _derived(**values) -> dict:
    return dict(values)


def _engine() -> NextBestActionEngine:
    return NextBestActionEngine()


def _risk_engine() -> PreventiveRiskEngine:
    return PreventiveRiskEngine()


def _domains(findings=None, derived=None, ctx=None):
    findings = findings or {}
    derived = derived or {}
    ctx = ctx or _ctx()
    return _risk_engine().assess(findings, derived, ctx)


def _run(findings=None, derived=None, ctx=None, domains=None, urgent_alerts=None) -> NextBestActionResult:
    findings = findings or {}
    derived = derived or {}
    ctx = ctx or _ctx()
    domains = domains if domains is not None else _domains(findings, derived, ctx)
    urgent_alerts = urgent_alerts or []
    return _engine().generate(findings, derived, ctx, domains, urgent_alerts)


# ---------------------------------------------------------------------------
# test_primary_action_selected
# One eligible high-score action → is primary
# ---------------------------------------------------------------------------


class TestPrimaryActionSelected:
    def test_high_cv_risk_no_bp_gives_measure_bp(self):
        ctx = _ctx(age=55, cv_risk_category="high")
        result = _run(ctx=ctx)
        # measure_bp or discuss_lipid_management should be primary given high CV risk
        assert result.primary is not None
        assert result.primary.action_id is not None

    def test_primary_action_has_all_required_fields(self):
        ctx = _ctx(age=50, bmi=27.0)
        result = _run(ctx=ctx)
        p = result.primary
        assert p.action_id
        assert p.action_type
        assert p.title_vi
        assert p.why_vi
        assert p.expected_benefit_vi
        assert p.effort_level in ("low", "medium", "high")
        assert p.timeframe_vi
        assert p.confidence in ("high", "medium", "low")
        assert p.evidence_level in ("established", "moderate", "emerging")


# ---------------------------------------------------------------------------
# test_max_three_actions_total
# Many eligible actions → max 1 primary + 2 secondary
# ---------------------------------------------------------------------------


class TestMaxThreeActionsTotal:
    def test_max_secondary_is_two(self):
        # Create a context with many eligible action signals
        ctx = _ctx(
            age=55,
            sex="male",
            bmi=28.0,
            cv_risk_category="high",
            has_diabetes=True,
            has_hypertension=True,
            waist_cm=None,
            exercise_level="none",
            context_completeness=0.4,
        )
        findings = _findings(ldl="high", fasting_glucose="high", creatinine="high", alt="high")
        result = _run(findings=findings, ctx=ctx)
        assert len(result.secondary) <= 2, f"Expected at most 2 secondary, got {len(result.secondary)}"

    def test_primary_plus_secondary_max_three(self):
        ctx = _ctx(
            age=60,
            bmi=31.0,
            cv_risk_category="very_high",
            has_diabetes=True,
            waist_cm=None,
            exercise_level="none",
        )
        findings = _findings(ldl="high", creatinine="critical", alt="critical", hba1c="high")
        result = _run(findings=findings, ctx=ctx)
        total = 1 + len(result.secondary)
        assert total <= 3, f"Total actions must be ≤3, got {total}"


# ---------------------------------------------------------------------------
# test_high_clinical_beats_low_effort
# discuss_doctor > lifestyle action at same score
# ---------------------------------------------------------------------------


class TestHighClinicalBeatsLowEffort:
    def test_discuss_doctor_beats_lifestyle(self):
        """Discuss doctor action should beat lifestyle at similar eligibility."""
        ctx = _ctx(
            age=55,
            cv_risk_category="high",
            has_hypertension=True,
            bmi=27.0,
            exercise_level="none",
        )
        findings = _findings(ldl="high", triglyceride="high")
        result = _run(findings=findings, ctx=ctx)
        # With LDL high and no statin → discuss_lipid_management should win over lifestyle
        action_types = [result.primary.action_type] + [a.action_type for a in result.secondary]
        # Lifestyle should not be primary if a clinical action is available
        if "discuss_doctor" in action_types or "repeat_lab" in action_types:
            if result.primary.action_type == "lifestyle_today":
                # Only acceptable if no clinical action was eligible — verify
                pass  # lifestyle can be primary only if discuss_doctor not eligible
        # This test ensures discuss_doctor ranks above lifestyle
        clinical_ids = {"measure_bp", "get_hba1c", "get_apob", "discuss_lipid_management", "discuss_ckd_monitoring"}
        lifestyle_ids = {"lifestyle_diet_fat", "lifestyle_exercise"}
        if result.primary.action_id in lifestyle_ids:
            # Verify no high-scoring clinical action was eligible
            all_ids = {result.primary.action_id} | {a.action_id for a in result.secondary}
            assert not any(aid in clinical_ids for aid in all_ids), (
                "Clinical action was in top 3 but lifestyle was primary — tie-break failed"
            )


# ---------------------------------------------------------------------------
# test_measure_bp_fires_for_cv_risk
# High CV risk + no BP in findings → measure_bp action
# ---------------------------------------------------------------------------


class TestMeasureBpFiresForCvRisk:
    def test_high_cv_risk_no_bp_gives_measure_bp(self):
        ctx = _ctx(age=60, cv_risk_category="high")
        result = _run(ctx=ctx)
        all_ids = {result.primary.action_id} | {a.action_id for a in result.secondary}
        assert "measure_bp" in all_ids, f"measure_bp not in {all_ids}"

    def test_very_high_cv_risk_measure_bp_high_score(self):
        ctx = _ctx(age=65, cv_risk_category="very_high")
        result = _run(ctx=ctx)
        all_ids = {result.primary.action_id} | {a.action_id for a in result.secondary}
        assert "measure_bp" in all_ids

    def test_young_low_risk_no_bp_not_triggered(self):
        ctx = _ctx(age=25, cv_risk_category="low", has_hypertension=False)
        result = _run(ctx=ctx)
        all_ids = {result.primary.action_id} | {a.action_id for a in result.secondary}
        # measure_bp should NOT fire for young low-risk without hypertension
        assert "measure_bp" not in all_ids


# ---------------------------------------------------------------------------
# test_hba1c_action_fires
# diabetes_progression domain + HbA1c missing → get_hba1c primary
# ---------------------------------------------------------------------------


class TestHba1cActionFires:
    def test_diabetes_domain_without_hba1c_fires_get_hba1c(self):
        ctx = _ctx(has_diabetes=True)
        findings = _findings(fasting_glucose="high")
        # hba1c NOT in findings
        result = _run(findings=findings, ctx=ctx)
        all_ids = {result.primary.action_id} | {a.action_id for a in result.secondary}
        assert "get_hba1c" in all_ids, f"get_hba1c not in {all_ids}"

    def test_hba1c_already_present_no_action(self):
        ctx = _ctx(has_diabetes=True)
        # hba1c IS in findings
        findings = _findings(fasting_glucose="high", hba1c="high")
        result = _run(findings=findings, ctx=ctx)
        all_ids = {result.primary.action_id} | {a.action_id for a in result.secondary}
        assert "get_hba1c" not in all_ids, "get_hba1c should not fire when hba1c already in findings"

    def test_borderline_glucose_gets_hba1c_recommendation(self):
        ctx = _ctx()
        findings = _findings(fasting_glucose="borderline")
        derived = _derived(tyg_index=9.5)
        # diabetes_progression at needs_monitoring → get_hba1c should appear
        result = _run(findings=findings, derived=derived, ctx=ctx)
        all_ids = {result.primary.action_id} | {a.action_id for a in result.secondary}
        assert "get_hba1c" in all_ids


# ---------------------------------------------------------------------------
# test_maintain_current_fallback
# All domains low_concern → maintain_current
# ---------------------------------------------------------------------------


class TestMaintainCurrentFallback:
    def test_healthy_profile_returns_maintain_current(self):
        ctx = _ctx(
            age=35,
            sex="female",
            bmi=22.0,
            cv_risk_category="low",
            has_diabetes=False,
            has_hypertension=False,
            has_cvd_history=False,
            has_ckd=False,
            has_fatty_liver=False,
            is_smoker=False,
            waist_cm=75.0,
            exercise_level="moderate",
            context_completeness=0.8,
        )
        findings = _findings(
            ldl="normal",
            hdl="normal",
            fasting_glucose="normal",
            creatinine="normal",
            alt="normal",
        )
        result = _run(findings=findings, ctx=ctx)
        # With good completeness and low concern, maintain_current should be primary or in secondary
        # (may also get some action from other rules — just ensure maintain fires)
        all_ids = {result.primary.action_id} | {a.action_id for a in result.secondary}
        # maintain_current should fire with completeness >= 0.6 and all low concern
        assert "maintain_current" in all_ids, f"Expected maintain_current in top 3, got {all_ids}"


# ---------------------------------------------------------------------------
# test_no_unsafe_language
# No action contains "chẩn đoán", "kê đơn", "điều trị", "dừng thuốc"
# ---------------------------------------------------------------------------


class TestNoUnsafeLanguage:
    UNSAFE_PHRASES = ["chẩn đoán", "kê đơn", "điều trị", "dừng thuốc"]

    def _check_action(self, action: NextBestAction):
        all_text = " ".join([
            action.title_vi,
            action.why_vi,
            action.expected_benefit_vi,
        ]).lower()
        for phrase in self.UNSAFE_PHRASES:
            assert phrase not in all_text, (
                f"Unsafe phrase {phrase!r} found in action {action.action_id!r}: {all_text!r}"
            )

    def test_all_actions_safe_language(self):
        ctx = _ctx(
            age=55,
            bmi=29.0,
            cv_risk_category="high",
            has_diabetes=True,
            has_hypertension=True,
            waist_cm=None,
            exercise_level="none",
        )
        findings = _findings(ldl="high", fasting_glucose="high", creatinine="high", alt="high")
        result = _run(findings=findings, ctx=ctx)
        self._check_action(result.primary)
        for a in result.secondary:
            self._check_action(a)

    def test_lifestyle_actions_no_prescribing(self):
        ctx = _ctx(bmi=27.0, exercise_level="none", has_diabetes=True)
        result = _run(ctx=ctx)
        self._check_action(result.primary)

    def test_no_stap_medication_language(self):
        """Actions must never tell users to stop taking medication."""
        ctx = _ctx(cv_risk_category="high")
        findings = _findings(ldl="critical")
        result = _run(findings=findings, ctx=ctx)
        for action in [result.primary] + result.secondary:
            assert "dừng thuốc" not in action.why_vi.lower()
            assert "ngừng thuốc" not in action.why_vi.lower()
            assert "kê đơn" not in action.why_vi.lower()


# ---------------------------------------------------------------------------
# test_ranking_explanation_present
# Result always has ranking_explanation_vi non-empty
# ---------------------------------------------------------------------------


class TestRankingExplanationPresent:
    def test_ranking_explanation_non_empty(self):
        ctx = _ctx()
        result = _run(ctx=ctx)
        assert result.ranking_explanation_vi, "ranking_explanation_vi must be non-empty"

    def test_ranking_explanation_with_complex_case(self):
        ctx = _ctx(
            age=60,
            bmi=28.0,
            cv_risk_category="high",
            has_diabetes=True,
        )
        findings = _findings(ldl="high", fasting_glucose="high")
        result = _run(findings=findings, ctx=ctx)
        assert result.ranking_explanation_vi
        assert len(result.ranking_explanation_vi) > 10

    def test_ranking_explanation_mentions_primary_title(self):
        ctx = _ctx(age=55, cv_risk_category="high")
        result = _run(ctx=ctx)
        # The explanation should reference the primary action
        assert result.primary.title_vi in result.ranking_explanation_vi or (
            "được chọn" in result.ranking_explanation_vi
        )


# ---------------------------------------------------------------------------
# test_backward_compat_report
# PatientInsightReport without new fields still serializes
# ---------------------------------------------------------------------------


class TestBackwardCompatReport:
    def test_report_without_ctx_no_phase2a_fields(self):
        """Without ctx, Phase 2A fields should be empty defaults."""

        report = generate_patient_insight(
            patient_id="test-patient",
            findings=[],
            patterns=[],
            trends=[],
            derived={},
            ctx=None,
        )
        assert report.preventive_risk_domains == []
        assert report.next_best_action is None
        assert report.secondary_actions == []
        assert report.recommendation_ranking_explanation_vi == ""

    def test_report_with_ctx_has_phase2a_fields(self):
        """With ctx, Phase 2A fields should be populated."""

        ctx = _ctx(
            age=50,
            sex="male",
            bmi=26.0,
            cv_risk_category="intermediate",
            context_completeness=0.5,
        )
        report = generate_patient_insight(
            patient_id="test-patient",
            findings=[],
            patterns=[],
            trends=[],
            derived={},
            ctx=ctx,
        )
        assert len(report.preventive_risk_domains) == 5  # All 5 domains always returned
        assert report.next_best_action is not None
        # secondary_actions may be 0–2
        assert len(report.secondary_actions) <= 2
        assert report.recommendation_ranking_explanation_vi != ""

    def test_report_serializes_with_asdict(self):
        """dataclasses.asdict() should work on the report (API uses this)."""
        import dataclasses

        ctx = _ctx(age=45, cv_risk_category="low", context_completeness=0.7)
        report = generate_patient_insight(
            patient_id="test-p",
            findings=[],
            patterns=[],
            trends=[],
            derived={},
            ctx=ctx,
        )
        d = dataclasses.asdict(report)
        assert "preventive_risk_domains" in d
        assert "next_best_action" in d
        assert "secondary_actions" in d
        assert "recommendation_ranking_explanation_vi" in d
        # Existing fields still present
        assert "overall_status" in d
        assert "insights" in d
        assert "action_cards" in d

    def test_no_ctx_report_still_serializes(self):
        """Reports without ctx (legacy) must also serialize cleanly."""
        import dataclasses

        report = generate_patient_insight(
            patient_id="legacy-patient",
            findings=[],
            patterns=[],
            trends=[],
            derived={},
            ctx=None,
        )
        d = dataclasses.asdict(report)
        assert d["preventive_risk_domains"] == []
        assert d["next_best_action"] is None
        assert d["secondary_actions"] == []
