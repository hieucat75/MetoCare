"""Tests for Engine 14 — PreventiveRiskEngine."""
from __future__ import annotations

from app.domain.patient_context import PatientContext
from app.domain.preventive_risk import (
    PreventiveRiskDomain,
    PreventiveRiskEngine,
)

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


def _engine() -> PreventiveRiskEngine:
    return PreventiveRiskEngine()


def _domain(domains: list[PreventiveRiskDomain], domain_id: str) -> PreventiveRiskDomain:
    for d in domains:
        if d.domain_id == domain_id:
            return d
    raise AssertionError(f"Domain {domain_id!r} not found in result")


# ---------------------------------------------------------------------------
# test_cardiometabolic_high_priority
# CVD history + high LDL → high_preventive_priority
# ---------------------------------------------------------------------------


class TestCardiometabolicHighPriority:
    def test_cvd_history_alone_is_high_priority(self):
        ctx = _ctx(has_cvd_history=True, cv_risk_category="very_high")
        findings = _findings(ldl="high")
        domains = _engine().assess(findings, {}, ctx)
        d = _domain(domains, "cardiometabolic")
        assert d.level == "high_preventive_priority"

    def test_three_signals_give_high_priority(self):
        ctx = _ctx(has_hypertension=True, is_smoker=True, cv_risk_category="high")
        findings = _findings(ldl="high")
        domains = _engine().assess(findings, {}, ctx)
        d = _domain(domains, "cardiometabolic")
        # has_hypertension + is_smoker + cv_risk_high + ldl_elevated = 4 signals
        assert d.level == "high_preventive_priority"

    def test_two_signals_is_discuss_with_doctor(self):
        ctx = _ctx(has_hypertension=True, is_smoker=True, cv_risk_category="low")
        domains = _engine().assess({}, {}, ctx)
        d = _domain(domains, "cardiometabolic")
        assert d.level == "discuss_with_doctor"

    def test_one_signal_is_needs_monitoring(self):
        ctx = _ctx(has_hypertension=True)
        domains = _engine().assess({}, {}, ctx)
        d = _domain(domains, "cardiometabolic")
        assert d.level == "needs_monitoring"


# ---------------------------------------------------------------------------
# test_cardiometabolic_low_concern
# No signals → low_concern
# ---------------------------------------------------------------------------


class TestCardiometabolicLowConcern:
    def test_no_signals_low_concern(self):
        ctx = _ctx()
        domains = _engine().assess({}, {}, ctx)
        d = _domain(domains, "cardiometabolic")
        assert d.level == "low_concern"

    def test_normal_ldl_no_history_low_concern(self):
        ctx = _ctx(cv_risk_category="low")
        findings = _findings(ldl="normal")
        domains = _engine().assess(findings, {}, ctx)
        d = _domain(domains, "cardiometabolic")
        assert d.level == "low_concern"

    def test_tc_hdl_ratio_high_single_signal(self):
        ctx = _ctx()
        derived = _derived(tc_hdl_ratio=5.5)
        domains = _engine().assess({}, derived, ctx)
        d = _domain(domains, "cardiometabolic")
        assert d.level == "needs_monitoring"


# ---------------------------------------------------------------------------
# test_diabetes_discuss_doctor
# glucose high + HbA1c high + overweight → discuss_with_doctor
# ---------------------------------------------------------------------------


class TestDiabetesDiscussDoctor:
    def test_three_signals_non_diabetic(self):
        ctx = _ctx(bmi=28.0)
        findings = _findings(fasting_glucose="high", hba1c="high")
        derived = _derived(tg_hdl_ratio=3.5)
        domains = _engine().assess(findings, derived, ctx)
        d = _domain(domains, "diabetes_progression")
        assert d.level == "discuss_with_doctor"

    def test_diabetic_with_high_glucose(self):
        ctx = _ctx(has_diabetes=True)
        findings = _findings(fasting_glucose="high")
        domains = _engine().assess(findings, {}, ctx)
        d = _domain(domains, "diabetes_progression")
        assert d.level == "discuss_with_doctor"

    def test_diabetic_with_high_hba1c(self):
        ctx = _ctx(has_diabetes=True)
        findings = _findings(hba1c="high")
        domains = _engine().assess(findings, {}, ctx)
        d = _domain(domains, "diabetes_progression")
        assert d.level == "discuss_with_doctor"

    def test_non_diabetic_multiple_signals_discuss(self):
        ctx = _ctx(bmi=27.0)
        findings = _findings(fasting_glucose="high")
        derived = _derived(tg_hdl_ratio=3.5, tyg_index=9.5)
        domains = _engine().assess(findings, derived, ctx)
        d = _domain(domains, "diabetes_progression")
        # glucose_high + tg_hdl + tyg + overweight = >=3 signals → discuss_with_doctor
        assert d.level == "discuss_with_doctor"


# ---------------------------------------------------------------------------
# test_diabetes_needs_monitoring
# Single borderline glucose signal → needs_monitoring
# ---------------------------------------------------------------------------


class TestDiabetesNeedsMonitoring:
    def test_single_borderline_glucose(self):
        ctx = _ctx()
        findings = _findings(fasting_glucose="borderline")
        domains = _engine().assess(findings, {}, ctx)
        d = _domain(domains, "diabetes_progression")
        assert d.level == "needs_monitoring"

    def test_overweight_only_is_needs_monitoring(self):
        ctx = _ctx(bmi=26.5)
        domains = _engine().assess({}, {}, ctx)
        d = _domain(domains, "diabetes_progression")
        assert d.level == "needs_monitoring"

    def test_two_signals_needs_monitoring(self):
        ctx = _ctx(bmi=26.0)
        findings = _findings(fasting_glucose="borderline")
        domains = _engine().assess(findings, {}, ctx)
        d = _domain(domains, "diabetes_progression")
        assert d.level == "needs_monitoring"


# ---------------------------------------------------------------------------
# test_ckd_high_priority
# Creatinine critical → high_preventive_priority
# ---------------------------------------------------------------------------


class TestCkdHighPriority:
    def test_creatinine_critical(self):
        ctx = _ctx()
        findings = _findings(creatinine="critical")
        domains = _engine().assess(findings, {}, ctx)
        d = _domain(domains, "ckd_monitoring")
        assert d.level == "high_preventive_priority"

    def test_egfr_below_45(self):
        ctx = _ctx()
        derived = _derived(egfr_ckd_epi=40.0)
        domains = _engine().assess({}, derived, ctx)
        d = _domain(domains, "ckd_monitoring")
        assert d.level == "high_preventive_priority"

    def test_creatinine_high_is_discuss(self):
        ctx = _ctx()
        findings = _findings(creatinine="high")
        domains = _engine().assess(findings, {}, ctx)
        d = _domain(domains, "ckd_monitoring")
        assert d.level == "discuss_with_doctor"

    def test_egfr_below_60_is_discuss(self):
        ctx = _ctx()
        derived = _derived(egfr_ckd_epi=55.0)
        domains = _engine().assess({}, derived, ctx)
        d = _domain(domains, "ckd_monitoring")
        assert d.level == "discuss_with_doctor"


# ---------------------------------------------------------------------------
# test_ckd_screening_signal
# has_diabetes context → needs_monitoring (screening)
# ---------------------------------------------------------------------------


class TestCkdScreeningSignal:
    def test_diabetes_context_triggers_screening(self):
        ctx = _ctx(has_diabetes=True)
        # No creatinine in findings
        domains = _engine().assess({}, {}, ctx)
        d = _domain(domains, "ckd_monitoring")
        assert d.level == "needs_monitoring"

    def test_hypertension_context_triggers_screening(self):
        ctx = _ctx(has_hypertension=True)
        domains = _engine().assess({}, {}, ctx)
        d = _domain(domains, "ckd_monitoring")
        assert d.level == "needs_monitoring"

    def test_ckd_flag_without_labs(self):
        ctx = _ctx(has_ckd=True)
        domains = _engine().assess({}, {}, ctx)
        d = _domain(domains, "ckd_monitoring")
        assert d.level == "needs_monitoring"


# ---------------------------------------------------------------------------
# test_fatty_liver_discuss
# ALT critical → discuss_with_doctor
# ---------------------------------------------------------------------------


class TestFattyLiverDiscuss:
    def test_alt_critical(self):
        ctx = _ctx()
        findings = _findings(alt="critical")
        domains = _engine().assess(findings, {}, ctx)
        d = _domain(domains, "fatty_liver_metabolic")
        assert d.level == "discuss_with_doctor"

    def test_alt_high_ast_high_tg_high(self):
        ctx = _ctx()
        findings = _findings(alt="high", ast="high", triglyceride="high")
        domains = _engine().assess(findings, {}, ctx)
        d = _domain(domains, "fatty_liver_metabolic")
        assert d.level == "discuss_with_doctor"

    def test_alt_high_plus_overweight(self):
        ctx = _ctx(bmi=27.0)
        findings = _findings(alt="high")
        domains = _engine().assess(findings, {}, ctx)
        d = _domain(domains, "fatty_liver_metabolic")
        assert d.level == "needs_monitoring"

    def test_alt_high_plus_fatty_liver_flag(self):
        ctx = _ctx(has_fatty_liver=True)
        findings = _findings(alt="high")
        domains = _engine().assess(findings, {}, ctx)
        d = _domain(domains, "fatty_liver_metabolic")
        assert d.level == "needs_monitoring"

    def test_fatty_liver_flag_only(self):
        ctx = _ctx(has_fatty_liver=True)
        domains = _engine().assess({}, {}, ctx)
        d = _domain(domains, "fatty_liver_metabolic")
        assert d.level == "needs_monitoring"


# ---------------------------------------------------------------------------
# test_cv_prevention_opportunity_positive
# Intermediate risk → needs_monitoring with positive framing
# ---------------------------------------------------------------------------


class TestCvPreventionOpportunityPositive:
    def test_intermediate_risk_needs_monitoring(self):
        ctx = _ctx(cv_risk_category="intermediate")
        domains = _engine().assess({}, {}, ctx)
        d = _domain(domains, "cv_prevention_opportunity")
        assert d.level == "needs_monitoring"
        # Positive framing — description should contain "cơ hội phòng ngừa"
        assert "cơ hội phòng ngừa" in d.description_vi.lower() or "phòng ngừa" in d.description_vi.lower()

    def test_very_high_risk_high_priority(self):
        ctx = _ctx(cv_risk_category="very_high", has_cvd_history=True)
        domains = _engine().assess({}, {}, ctx)
        d = _domain(domains, "cv_prevention_opportunity")
        assert d.level == "high_preventive_priority"

    def test_high_risk_discuss_with_doctor(self):
        ctx = _ctx(cv_risk_category="high")
        domains = _engine().assess({}, {}, ctx)
        d = _domain(domains, "cv_prevention_opportunity")
        assert d.level == "discuss_with_doctor"

    def test_low_risk_low_concern(self):
        ctx = _ctx(cv_risk_category="low")
        domains = _engine().assess({}, {}, ctx)
        d = _domain(domains, "cv_prevention_opportunity")
        assert d.level == "low_concern"


# ---------------------------------------------------------------------------
# test_all_low_concern
# Healthy profile → all domains low_concern
# ---------------------------------------------------------------------------


class TestAllLowConcern:
    def test_healthy_profile_all_low_concern(self):
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
        )
        findings = _findings(
            ldl="normal",
            hdl="normal",
            fasting_glucose="normal",
            creatinine="normal",
            alt="normal",
        )
        domains = _engine().assess(findings, {}, ctx)
        for d in domains:
            if d.domain_id in ("cardiometabolic", "diabetes_progression", "ckd_monitoring", "fatty_liver_metabolic"):
                assert d.level == "low_concern", f"Expected low_concern for {d.domain_id}, got {d.level}"

    def test_all_domains_returned(self):
        """Engine always returns all 5 domains."""
        ctx = _ctx()
        domains = _engine().assess({}, {}, ctx)
        domain_ids = {d.domain_id for d in domains}
        assert "cardiometabolic" in domain_ids
        assert "diabetes_progression" in domain_ids
        assert "ckd_monitoring" in domain_ids
        assert "fatty_liver_metabolic" in domain_ids
        assert "cv_prevention_opportunity" in domain_ids


# ---------------------------------------------------------------------------
# test_safety_note_always_present
# safety_note_vi present on all domains
# ---------------------------------------------------------------------------


class TestSafetyNoteAlwaysPresent:
    def test_safety_note_on_all_domains(self):
        ctx = _ctx(has_cvd_history=True, has_diabetes=True, bmi=30.0)
        findings = _findings(
            ldl="high", creatinine="critical", alt="critical",
            fasting_glucose="high", hba1c="high",
        )
        domains = _engine().assess(findings, {}, ctx)
        for d in domains:
            assert d.safety_note_vi, f"Domain {d.domain_id} missing safety_note_vi"
            assert "đánh giá hỗ trợ" in d.safety_note_vi or "chẩn đoán" in d.safety_note_vi

    def test_safety_note_contains_no_diagnosis_language(self):
        ctx = _ctx()
        domains = _engine().assess({}, {}, ctx)
        for d in domains:
            note_lower = d.safety_note_vi.lower()
            # safety note should contain educational disclaimer, not diagnosis
            assert "chẩn đoán y khoa" in note_lower or "bác sĩ" in note_lower

    def test_description_never_says_ban_co_nguy_co(self):
        """Description must never say 'bạn có nguy cơ cao bị X'."""
        ctx = _ctx(has_cvd_history=True, has_diabetes=True, bmi=35.0)
        findings = _findings(ldl="critical", hba1c="high", creatinine="critical")
        domains = _engine().assess(findings, {}, ctx)
        for d in domains:
            assert "bạn có nguy cơ cao bị" not in d.description_vi.lower()

    def test_all_levels_valid(self):
        valid_levels = {"low_concern", "needs_monitoring", "discuss_with_doctor", "high_preventive_priority"}
        ctx = _ctx(has_cvd_history=True)
        domains = _engine().assess({}, {}, ctx)
        for d in domains:
            assert d.level in valid_levels

    def test_sorting_high_first(self):
        """High priority domains should come first after sorting."""
        ctx = _ctx(has_cvd_history=True)
        findings = _findings(creatinine="critical")
        domains = _engine().assess(findings, {}, ctx)
        # First domain should be one of the highest priority ones
        assert domains[0].level in ("high_preventive_priority", "discuss_with_doctor")
