"""Tests for Engine 2 — CrossMarkerCorrelationEngine v3."""

from __future__ import annotations

from app.domain.clinical_patterns_v3 import (
    ClinicalPattern,
    detect_patterns_v3,
)
from app.domain.patient_context import PatientContext

# ── Helpers ───────────────────────────────────────────────────────────────────

def _ctx(**kwargs) -> PatientContext:
    """Build a PatientContext with given overrides."""
    ctx = PatientContext()
    for k, v in kwargs.items():
        setattr(ctx, k, v)
    return ctx


def _findings(**statuses) -> dict:
    """Build findings dict: {canonical: {"status": status}}."""
    return {canonical: {"status": status} for canonical, status in statuses.items()}


def _derived(**values) -> dict:
    """Build derived dict: {canonical: float}."""
    return dict(values)


def _pattern_ids(patterns: list[ClinicalPattern]) -> list[str]:
    return [p.pattern_id for p in patterns]


# ── Engine 2: CrossMarkerCorrelationEngine Tests ───────────────────────────────

class TestInsulinResistanceDetected:
    """test_insulin_resistance_detected: tyg > 9, glucose high, tg high, hdl low → insulin_resistance."""

    def test_full_signal_set(self):
        findings = _findings(fasting_glucose="high", triglyceride="high", hdl="low")
        derived = _derived(tyg_index=9.5, tg_hdl_ratio=3.5)
        ctx = _ctx()
        patterns = detect_patterns_v3(findings, derived, ctx)
        assert "insulin_resistance" in _pattern_ids(patterns)

    def test_tyg_and_glucose_sufficient(self):
        findings = _findings(fasting_glucose="borderline")
        derived = _derived(tyg_index=9.2)
        ctx = _ctx()
        # tyg > 9 + glucose borderline = 2 signals → detected
        patterns = detect_patterns_v3(findings, derived, ctx)
        assert "insulin_resistance" in _pattern_ids(patterns)

    def test_tg_hdl_ratio_and_glucose(self):
        findings = _findings(fasting_glucose="high", triglyceride="borderline")
        derived = _derived(tg_hdl_ratio=3.5)
        ctx = _ctx()
        patterns = detect_patterns_v3(findings, derived, ctx)
        assert "insulin_resistance" in _pattern_ids(patterns)

    def test_only_hdl_low_insufficient(self):
        """Single signal: only HDL low → should NOT detect insulin resistance."""
        findings = _findings(hdl="low")
        derived = {}
        ctx = _ctx()
        patterns = detect_patterns_v3(findings, derived, ctx)
        assert "insulin_resistance" not in _pattern_ids(patterns)


class TestAtherogenicCholesterolDetected:
    """test_atherogenic_cholesterol_detected: ldl high + non_hdl high → atherogenic_cholesterol."""

    def test_ldl_and_non_hdl_detected(self):
        findings = _findings(ldl="high", total_cholesterol="high")
        derived = _derived(ldl_friedewald=145.0, non_hdl_cholesterol=4.5)
        ctx = _ctx()
        patterns = detect_patterns_v3(findings, derived, ctx)
        assert "atherogenic_cholesterol" in _pattern_ids(patterns)

    def test_friedewald_and_tc_ratio(self):
        findings = _findings(total_cholesterol="high")
        derived = _derived(ldl_friedewald=140.0, tc_hdl_ratio=5.5)
        ctx = _ctx()
        patterns = detect_patterns_v3(findings, derived, ctx)
        assert "atherogenic_cholesterol" in _pattern_ids(patterns)

    def test_ldl_finding_and_non_hdl_derived(self):
        findings = _findings(ldl="critical")
        derived = _derived(non_hdl_cholesterol=4.2)
        ctx = _ctx()
        patterns = detect_patterns_v3(findings, derived, ctx)
        assert "atherogenic_cholesterol" in _pattern_ids(patterns)

    def test_only_ldl_high_insufficient(self):
        """Only 1 signal → no pattern."""
        findings = _findings(ldl="high")
        derived = {}
        ctx = _ctx()
        patterns = detect_patterns_v3(findings, derived, ctx)
        assert "atherogenic_cholesterol" not in _pattern_ids(patterns)


class TestNoPatternSingleMarker:
    """test_no_pattern_single_marker: only one signal → no pattern."""

    def test_single_glucose_no_pattern(self):
        findings = _findings(fasting_glucose="high")
        derived = {}
        ctx = _ctx()
        patterns = detect_patterns_v3(findings, derived, ctx)
        # No multi-marker patterns should fire with single glucose
        assert "insulin_resistance" not in _pattern_ids(patterns)
        assert "metabolic_syndrome" not in _pattern_ids(patterns)

    def test_single_alt_no_hepatic(self):
        findings = _findings(alt="high")
        derived = {}
        ctx = _ctx()
        patterns = detect_patterns_v3(findings, derived, ctx)
        assert "hepatic_metabolic" not in _pattern_ids(patterns)

    def test_empty_findings_no_patterns(self):
        patterns = detect_patterns_v3({}, {}, _ctx())
        assert patterns == []


class TestContextBoostsSeverity:
    """test_context_boosts_severity: IR pattern + ctx.has_diabetes → severity = "urgent"."""

    def test_ir_severity_urgent_with_diabetes(self):
        findings = _findings(fasting_glucose="high", triglyceride="high", hdl="low")
        derived = _derived(tyg_index=9.5)
        ctx = _ctx(has_diabetes=True, bmi=27.0)
        patterns = detect_patterns_v3(findings, derived, ctx)
        ir = next((p for p in patterns if p.pattern_id == "insulin_resistance"), None)
        assert ir is not None
        assert ir.severity == "urgent"

    def test_ir_severity_warning_without_diabetes(self):
        findings = _findings(fasting_glucose="high", triglyceride="high")
        derived = _derived(tyg_index=9.5)
        ctx = _ctx(has_diabetes=False, bmi=22.0)
        patterns = detect_patterns_v3(findings, derived, ctx)
        ir = next((p for p in patterns if p.pattern_id == "insulin_resistance"), None)
        assert ir is not None
        assert ir.severity == "warning"

    def test_atherogenic_severity_urgent_with_cvd(self):
        findings = _findings(ldl="high", total_cholesterol="critical")
        derived = _derived(ldl_friedewald=145.0, non_hdl_cholesterol=4.5)
        ctx = _ctx(has_cvd_history=True)
        patterns = detect_patterns_v3(findings, derived, ctx)
        ath = next((p for p in patterns if p.pattern_id == "atherogenic_cholesterol"), None)
        assert ath is not None
        assert ath.severity == "urgent"

    def test_kidney_severity_warning_with_diabetes(self):
        findings = _findings(creatinine="high")
        derived = _derived(egfr_ckd_epi=50.0)
        ctx = _ctx(has_diabetes=True)
        patterns = detect_patterns_v3(findings, derived, ctx)
        kidney = next((p for p in patterns if p.pattern_id == "kidney_risk"), None)
        assert kidney is not None
        assert kidney.severity == "warning"

    def test_context_modifiers_populated(self):
        findings = _findings(fasting_glucose="high", triglyceride="high")
        derived = _derived(tyg_index=9.5)
        ctx = _ctx(has_diabetes=True)
        patterns = detect_patterns_v3(findings, derived, ctx)
        ir = next((p for p in patterns if p.pattern_id == "insulin_resistance"), None)
        assert ir is not None
        assert len(ir.context_modifiers) > 0


class TestMAFLDPattern:
    """test_mafld_pattern: alt high + ast high + tg high → hepatic_metabolic."""

    def test_alt_ast_tg_detected(self):
        findings = _findings(alt="high", ast="high", triglyceride="borderline")
        derived = {}
        ctx = _ctx()
        patterns = detect_patterns_v3(findings, derived, ctx)
        assert "hepatic_metabolic" in _pattern_ids(patterns)

    def test_alt_tg_detected(self):
        findings = _findings(alt="high", triglyceride="high")
        derived = {}
        ctx = _ctx()
        patterns = detect_patterns_v3(findings, derived, ctx)
        assert "hepatic_metabolic" in _pattern_ids(patterns)

    def test_bmi_proxy_boosts_confidence(self):
        """Overweight BMI + ALT high → bmi_proxy signal added."""
        findings = _findings(alt="high")
        derived = {}
        ctx = _ctx(bmi=27.0)  # overweight
        # bmi_proxy + alt = 2 signals → detects
        patterns = detect_patterns_v3(findings, derived, ctx)
        assert "hepatic_metabolic" in _pattern_ids(patterns)

    def test_alcohol_adds_context_modifier(self):
        findings = _findings(alt="high", ast="high", triglyceride="high")
        derived = {}
        ctx = _ctx(drinks_alcohol=True)
        patterns = detect_patterns_v3(findings, derived, ctx)
        hepatic = next((p for p in patterns if p.pattern_id == "hepatic_metabolic"), None)
        assert hepatic is not None
        assert any("rượu" in mod.lower() or "alcohol" in mod.lower() for mod in hepatic.context_modifiers)

    def test_bmi_proxy_excluded_from_supporting_findings(self):
        """bmi_proxy should NOT appear in supporting_findings (not a lab result)."""
        findings = _findings(alt="high")
        derived = {}
        ctx = _ctx(bmi=27.0)
        patterns = detect_patterns_v3(findings, derived, ctx)
        hepatic = next((p for p in patterns if p.pattern_id == "hepatic_metabolic"), None)
        if hepatic:
            assert "bmi_proxy" not in hepatic.supporting_findings


class TestMetabolicSyndromePattern:
    """test_metabolic_syndrome_pattern: tg+hdl+glucose all abnormal → metabolic_syndrome."""

    def test_three_criteria_detected(self):
        findings = _findings(
            triglyceride="high",
            hdl="low",
            fasting_glucose="high",
        )
        derived = {}
        ctx = _ctx()
        patterns = detect_patterns_v3(findings, derived, ctx)
        assert "metabolic_syndrome" in _pattern_ids(patterns)

    def test_with_hypertension_context(self):
        findings = _findings(triglyceride="high", hdl="low")
        derived = {}
        ctx = _ctx(has_hypertension=True, waist_cm=95.0, sex="male")
        patterns = detect_patterns_v3(findings, derived, ctx)
        assert "metabolic_syndrome" in _pattern_ids(patterns)

    def test_metabolic_syndrome_from_derived(self):
        """Should detect if derived metabolic_syndrome has meets_criteria status."""
        findings = {}
        derived = {"metabolic_syndrome": {"status": "meets_criteria", "criteria_count": 4}}
        ctx = _ctx()
        patterns = detect_patterns_v3(findings, derived, ctx)
        assert "metabolic_syndrome" in _pattern_ids(patterns)

    def test_two_criteria_insufficient(self):
        """Only 2 criteria → should NOT detect metabolic syndrome."""
        findings = _findings(triglyceride="high", hdl="low")
        derived = {}
        ctx = _ctx()  # no hypertension, no waist, no glucose
        patterns = detect_patterns_v3(findings, derived, ctx)
        assert "metabolic_syndrome" not in _pattern_ids(patterns)

    def test_diabetes_adds_context_modifier(self):
        findings = _findings(triglyceride="high", hdl="low", fasting_glucose="high")
        derived = {}
        ctx = _ctx(has_diabetes=True)
        patterns = detect_patterns_v3(findings, derived, ctx)
        ms = next((p for p in patterns if p.pattern_id == "metabolic_syndrome"), None)
        assert ms is not None
        assert len(ms.context_modifiers) > 0


class TestKidneyRiskPattern:
    """Test kidney risk pattern detection."""

    def test_creatinine_only_detected(self):
        findings = _findings(creatinine="high")
        derived = {}
        ctx = _ctx()
        patterns = detect_patterns_v3(findings, derived, ctx)
        assert "kidney_risk" in _pattern_ids(patterns)

    def test_egfr_low_detected(self):
        findings = {}
        derived = _derived(egfr_ckd_epi=45.0)
        ctx = _ctx()
        patterns = detect_patterns_v3(findings, derived, ctx)
        assert "kidney_risk" in _pattern_ids(patterns)

    def test_normal_egfr_not_detected(self):
        findings = {}
        derived = _derived(egfr_ckd_epi=85.0)
        ctx = _ctx()
        patterns = detect_patterns_v3(findings, derived, ctx)
        assert "kidney_risk" not in _pattern_ids(patterns)


class TestThyroidPattern:
    """Test thyroid dysfunction pattern detection."""

    def test_tsh_abnormal_detected(self):
        findings = _findings(tsh="high")
        derived = {}
        ctx = _ctx()
        patterns = detect_patterns_v3(findings, derived, ctx)
        assert "thyroid_dysfunction" in _pattern_ids(patterns)

    def test_tsh_normal_not_detected(self):
        """TSH normal → no thyroid pattern."""
        findings = _findings(tsh="normal")
        derived = {}
        ctx = _ctx()
        patterns = detect_patterns_v3(findings, derived, ctx)
        assert "thyroid_dysfunction" not in _pattern_ids(patterns)

    def test_levothyroxine_adds_context_modifier(self):
        findings = _findings(tsh="low")
        derived = {}
        ctx = _ctx(medications=["levothyroxine"])
        patterns = detect_patterns_v3(findings, derived, ctx)
        thyroid = next((p for p in patterns if p.pattern_id == "thyroid_dysfunction"), None)
        assert thyroid is not None
        assert len(thyroid.context_modifiers) > 0


class TestPatternStructure:
    """Test that returned ClinicalPattern objects have required fields."""

    def test_clinical_pattern_has_required_fields(self):
        findings = _findings(fasting_glucose="high", triglyceride="high")
        derived = _derived(tyg_index=9.5)
        ctx = _ctx()
        patterns = detect_patterns_v3(findings, derived, ctx)
        for p in patterns:
            assert p.pattern_id
            assert p.display_name_vi
            assert p.description_vi
            assert p.severity in ("info", "watch", "warning", "urgent")
            assert isinstance(p.supporting_findings, list)
            assert p.confidence in ("high", "medium", "low")
            assert isinstance(p.evidence_based, bool)
            assert p.evidence_source in ("established", "moderate", "emerging")
            assert p.reasoning_vi
            assert p.clinical_significance_vi

    def test_pattern_deduplication(self):
        """Same pattern should not appear twice."""
        findings = _findings(triglyceride="high", hdl="low", fasting_glucose="high")
        derived = _derived(tyg_index=9.5, tg_hdl_ratio=3.5)
        ctx = _ctx()
        patterns = detect_patterns_v3(findings, derived, ctx)
        ids = [p.pattern_id for p in patterns]
        assert len(ids) == len(set(ids))
