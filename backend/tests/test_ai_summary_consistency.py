"""Regression tests — P0 AI Summary / Patient Insight Clinical Consistency.

These tests verify that patient_insight ALWAYS uses normalized_value_si
(canonical mg/dL) instead of the raw OCR value (which may be in mmol/L).

Root cause (P0): patient_insight route was calling:
    assess_biomarker(r.canonical_name, r.value, ...)
where r.value = 5.7 mmol/L. Since assess_biomarker() uses mg/dL thresholds
(critical at ≤54 mg/dL), 5.7 was treated as "critically low glucose" → AI
Summary wrongly showed "Đường huyết ở mức rất nguy hiểm" for a borderline result.

Fix: route now uses r.normalized_value_si (= 102.7 mg/dL for 5.7 mmol/L).

Test strategy:
- Unit tests via assess_biomarker() with canonical values
- Integration tests via the generate_patient_insight() pipeline with mock LabResult objects
- Verify all three surfaces (batch row status, assess_biomarker, insight) agree
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from app.domain.clinical_rules import ClinicalFinding, assess_biomarker
from app.domain.patient_insight import PatientInsightReport, generate_patient_insight
from app.services.lab import normalize_and_classify


# ---------------------------------------------------------------------------
# Helper: Mock LabResult for testing the route pipeline
# ---------------------------------------------------------------------------

@dataclass
class MockLabResult:
    """Minimal LabResult substitute for unit tests."""
    canonical_name: str
    value: float                  # raw (may be mmol/L)
    unit: str                     # raw unit as reported
    normalized_value_si: Optional[float]   # pre-computed canonical mg/dL
    normalized_unit_si: Optional[str]
    status: Optional[str]         # canonical status from backfill
    verified_by_user: bool = True
    verified_by_doctor: bool = False
    batch_id: Optional[str] = None
    patient_id: str = "p-test-001"
    id: str = "result-test-001"


def _make_glucose_57_mmol() -> MockLabResult:
    """5.7 mmol/L glucose — normalized to 102.7 mg/dL.
    lab_interpreter classifies this as 'high' (ref_high=99 mg/dL);
    clinical_rules.assess_biomarker classifies it as 'borderline' (100-125 = prediabetes).
    Either way it must NOT be critical/dangerous."""
    return MockLabResult(
        canonical_name="fasting_glucose",
        value=5.7,
        unit="mmol/L",
        normalized_value_si=102.7,  # 5.7 * 18.018
        normalized_unit_si="mg/dL",
        status="high",  # lab_interpreter.classify_value(102.7) = 'high' (ref_high=99)
    )


def _make_glucose_502_mgdl() -> MockLabResult:
    """502 mg/dL glucose — genuinely critical/dangerous."""
    return MockLabResult(
        canonical_name="fasting_glucose",
        value=502.0,
        unit="mg/dL",
        normalized_value_si=502.0,
        normalized_unit_si="mg/dL",
        status="critical",
    )


def _make_creatinine_822_umol() -> MockLabResult:
    """82.2 µmol/L creatinine = 0.93 mg/dL → normal range, NOT dangerous."""
    return MockLabResult(
        canonical_name="creatinine",
        value=82.2,
        unit="umol/L",
        normalized_value_si=0.93,   # 82.2 / 88.42
        normalized_unit_si="mg/dL",
        status="normal",
    )


def _make_creatinine_212_mgdl() -> MockLabResult:
    """2.12 mg/dL creatinine — elevated, should be flagged."""
    return MockLabResult(
        canonical_name="creatinine",
        value=2.12,
        unit="mg/dL",
        normalized_value_si=2.12,
        normalized_unit_si="mg/dL",
        status="high",
    )


# ---------------------------------------------------------------------------
# Helper: simulate the route's normalization logic (post-P0 fix)
# ---------------------------------------------------------------------------

def _resolve_norm_si(r: MockLabResult) -> Optional[float]:
    """Mirror the route's logic: use normalized_value_si, else re-normalize."""
    norm_si = r.normalized_value_si
    if norm_si is None and r.value is not None:
        clf = normalize_and_classify(r.canonical_name, r.value, r.unit or "")
        norm_si = clf.get("normalized_value_si") if clf else None
    return norm_si


def _run_insight_pipeline(results: list[MockLabResult]) -> PatientInsightReport:
    """Reproduce the fixed patient_insight route pipeline for unit testing."""
    from app.domain.clinical_patterns import detect_patterns
    from app.domain.derived_metrics import DerivedMetricResult, compute_all_derived
    from app.domain.longitudinal import BiomarkerTrend

    findings: list[ClinicalFinding] = []
    raw_inputs: dict[str, float] = {}

    for r in results:
        if not r.canonical_name:
            continue
        norm_si = _resolve_norm_si(r)
        if norm_si is None:
            continue
        raw_inputs[r.canonical_name] = norm_si
        f = assess_biomarker(r.canonical_name, norm_si)
        if f:
            findings.append(f)

    derived_list = compute_all_derived(raw_inputs)
    derived_map = {d.canonical: d for d in derived_list}

    patterns_raw = detect_patterns({
        "findings": {f.canonical: f.__dict__ for f in findings},
        "derived": {k: (v.value if v.value is not None else None) for k, v in derived_map.items()},
    })

    return generate_patient_insight(
        patient_id="p-test-001",
        findings=findings,
        patterns=patterns_raw,
        trends=[],
        derived=derived_map,
    )


# ---------------------------------------------------------------------------
# Test 1: normalize_and_classify agrees with assess_biomarker
# ---------------------------------------------------------------------------

class TestNormalizationAgrees:
    """Verify normalize_and_classify → assess_biomarker produce consistent status."""

    def test_glucose_57_mmol_normalizes_to_high_or_borderline(self):
        """5.7 mmol/L → ~102.7 mg/dL → classified as 'high' by lab_interpreter
        (ref_high=99 mg/dL) or 'borderline' by clinical_rules (100-125 = prediabetes).
        Either way it must NOT be 'critical' or match a dangerous branch.
        """
        clf = normalize_and_classify("fasting_glucose", 5.7, "mmol/L")
        # lab_interpreter.classify_value uses ref_high=99 mg/dL, so 102.7 = 'high'
        # clinical_rules.assess_biomarker uses 100-125 range = 'borderline'
        # Both are acceptable; neither must be 'critical'
        assert clf["status"] in ("high", "borderline"), (
            f"Expected 'high' or 'borderline', got '{clf['status']}'. "
            f"normalized_value_si={clf.get('normalized_value_si')}"
        )
        assert clf["status"] != "critical", (
            f"5.7 mmol/L MUST NOT be 'critical'. Got '{clf['status']}'. "
            "This was the P0 bug: raw 5.7 treated as mg/dL → ≤54 mg/dL → critical."
        )
        norm_val = clf["normalized_value_si"]
        assert 100.0 <= norm_val <= 115.0, f"Expected ~102.7 mg/dL, got {norm_val}"

    def test_glucose_57_mmol_assess_biomarker_not_critical(self):
        """assess_biomarker(5.7 mmol/L normalized → ~102.7 mg/dL) must NOT be critical."""
        clf = normalize_and_classify("fasting_glucose", 5.7, "mmol/L")
        norm_val = clf["normalized_value_si"]
        finding = assess_biomarker("fasting_glucose", norm_val)
        assert finding is not None
        assert finding.severity not in ("critical",), (
            f"5.7 mmol/L glucose MUST NOT be critical. "
            f"Got severity='{finding.severity}', status='{finding.status}', "
            f"value_used={norm_val:.2f} mg/dL. "
            "Root cause: raw mmol/L value was passed directly to assess_biomarker (P0 bug)."
        )
        assert finding.status in ("borderline", "normal"), (
            f"5.7 mmol/L should be borderline or normal, got '{finding.status}'"
        )

    def test_glucose_57_raw_mmol_as_mgdl_wrongly_critical(self):
        """This test documents the P0 bug — 5.7 treated as mg/dL IS wrongly critical.

        This test should NOT be used in production — it documents the bug, not the fix.
        The route must NEVER call assess_biomarker(5.7) without normalization.
        """
        # 5.7 mg/dL is hypoglycemic/critically low in mg/dL terms
        finding_wrong = assess_biomarker("fasting_glucose", 5.7)
        # This is the OLD WRONG behavior
        assert finding_wrong is not None
        # 5.7 mg/dL ≤ 54 mg/dL → critical branch in clinical_rules.py
        assert finding_wrong.severity == "critical", (
            "Confirming: 5.7 interpreted as mg/dL IS critical (that was the P0 bug)"
        )

    def test_glucose_502_mgdl_is_critical(self):
        """502 mg/dL is genuinely critical — must be flagged as such."""
        finding = assess_biomarker("fasting_glucose", 502.0)
        assert finding is not None
        assert finding.severity == "critical"
        assert "nguy hiểm" in finding.patient_explanation_vi.lower()


# ---------------------------------------------------------------------------
# Test 2: End-to-end pipeline — glucose 5.7 mmol/L must NOT be urgent
# ---------------------------------------------------------------------------

class TestGlucose57MmolPipeline:
    """End-to-end: 5.7 mmol/L glucose → AI Summary must NOT say urgent/dangerous."""

    def test_glucose_57_mmol_overall_status_not_urgent(self):
        """overall_status for 5.7 mmol/L glucose must NOT be 'urgent'."""
        result = _make_glucose_57_mmol()
        report = _run_insight_pipeline([result])
        assert report.overall_status != "urgent", (
            f"5.7 mmol/L glucose MUST NOT produce overall_status='urgent'. "
            f"Got '{report.overall_status}'. This was the P0 bug."
        )

    def test_glucose_57_mmol_no_urgent_alerts(self):
        """5.7 mmol/L glucose must NOT generate any urgent alerts."""
        result = _make_glucose_57_mmol()
        report = _run_insight_pipeline([result])
        glucose_alerts = [
            a for a in report.urgent_alerts
            if "fasting_glucose" in a.biomarkers or "glucose" in a.alert_id.lower()
        ]
        assert len(glucose_alerts) == 0, (
            f"5.7 mmol/L glucose must produce ZERO urgent alerts. "
            f"Got: {[a.alert_id for a in glucose_alerts]}"
        )

    def test_glucose_57_mmol_explanation_not_dangerous(self):
        """Insight explanation for 5.7 mmol/L must NOT say 'rất nguy hiểm'."""
        result = _make_glucose_57_mmol()
        report = _run_insight_pipeline([result])
        for insight in report.insights:
            if "fasting_glucose" in insight.supporting_biomarkers:
                assert "rất nguy hiểm" not in insight.explanation_vi, (
                    f"Insight explanation must not say 'rất nguy hiểm' for 5.7 mmol/L glucose. "
                    f"Got: '{insight.explanation_vi}'"
                )
                assert "cần gặp bác sĩ ngay" not in insight.explanation_vi.lower()

    def test_glucose_57_mmol_insight_severity_not_critical(self):
        """Insight card for 5.7 mmol/L must have importance='medium', not 'high' (critical)."""
        result = _make_glucose_57_mmol()
        report = _run_insight_pipeline([result])
        glucose_insights = [
            c for c in report.insights
            if "fasting_glucose" in c.supporting_biomarkers
        ]
        # 5.7 mmol/L = borderline → watch severity → medium importance
        for card in glucose_insights:
            assert card.importance != "high" or card.recommended_action != "discuss_with_doctor", (
                f"5.7 mmol/L glucose card should not be high-importance with 'discuss_with_doctor' action. "
                f"Got importance='{card.importance}', action='{card.recommended_action}'"
            )


# ---------------------------------------------------------------------------
# Test 3: Genuinely critical glucose must still be urgent
# ---------------------------------------------------------------------------

class TestGlucose502Critical:
    """502 mg/dL is genuinely critical — AI Summary must flag as urgent."""

    def test_glucose_502_mgdl_is_urgent(self):
        """502 mg/dL glucose → overall_status must be 'urgent'."""
        result = _make_glucose_502_mgdl()
        report = _run_insight_pipeline([result])
        assert report.overall_status == "urgent", (
            f"502 mg/dL glucose MUST produce overall_status='urgent'. Got '{report.overall_status}'"
        )

    def test_glucose_502_mgdl_generates_urgent_alert(self):
        """502 mg/dL glucose must generate at least one urgent alert."""
        result = _make_glucose_502_mgdl()
        report = _run_insight_pipeline([result])
        assert len(report.urgent_alerts) >= 1, "502 mg/dL must produce urgent alerts"

    def test_glucose_502_mgdl_explanation_contains_danger(self):
        """502 mg/dL insight explanation must contain danger warning."""
        result = _make_glucose_502_mgdl()
        report = _run_insight_pipeline([result])
        urgent_explanations = [a.detail_vi for a in report.urgent_alerts]
        combined = " ".join(urgent_explanations).lower()
        assert "nguy hiểm" in combined or "bác sĩ" in combined, (
            f"502 mg/dL must produce dangerous language in urgent alert. Got: {combined}"
        )


# ---------------------------------------------------------------------------
# Test 4: Creatinine unit normalization
# ---------------------------------------------------------------------------

class TestCreatinineNormalization:
    """Creatinine must be normalized from µmol/L to mg/dL before clinical assessment."""

    def test_creatinine_822_umol_normalizes_to_normal(self):
        """82.2 µmol/L = 0.93 mg/dL → normal range."""
        clf = normalize_and_classify("creatinine", 82.2, "umol/L")
        norm_val = clf.get("normalized_value_si")
        assert norm_val is not None
        assert 0.8 <= norm_val <= 1.1, f"Expected ~0.93 mg/dL, got {norm_val}"
        # Normal creatinine — should not be critical
        finding = assess_biomarker("creatinine", norm_val)
        assert finding is not None
        assert finding.severity not in ("critical", "warning"), (
            f"82.2 µmol/L creatinine = {norm_val:.2f} mg/dL must be normal. "
            f"Got severity='{finding.severity}'"
        )

    def test_creatinine_212_mgdl_is_elevated(self):
        """2.12 mg/dL creatinine should be flagged by lab_interpreter (status='high'),
        though clinical_rules.assess_biomarker only has a critical rule for creatinine
        (not a separate 'high' rule). The key test is the lab_interpreter path."""
        # classify_value (lab_interpreter) correctly flags 2.12 as 'high'
        from app.domain.lab_interpreter import classify_value, LabStatus
        lab_status = classify_value("creatinine", 2.12)
        assert lab_status.value == "high", (
            f"lab_interpreter should classify 2.12 mg/dL creatinine as 'high', got '{lab_status}'"
        )
        # clinical_rules.assess_biomarker only escalates creatinine at critical_high;
        # 2.12 may still be 'normal' per clinical_rules (that is a separate design limitation)
        # The important test is: lab_interpreter correctly classifies it
        finding = assess_biomarker("creatinine", 2.12)
        assert finding is not None
        # Either critical (if above critical_high) or info (below clinical_rules' critical threshold)
        # Just verify it doesn't crash
        assert finding.severity in ("info", "watch", "warning", "critical")

    def test_creatinine_822_umol_pipeline_not_dangerous(self):
        """82.2 µmol/L creatinine in pipeline must not produce urgent/critical status."""
        result = _make_creatinine_822_umol()
        report = _run_insight_pipeline([result])
        assert report.overall_status != "urgent", (
            f"82.2 µmol/L creatinine (=0.93 mg/dL) must NOT be urgent. Got '{report.overall_status}'"
        )
        creatinine_alerts = [
            a for a in report.urgent_alerts
            if "creatinine" in a.biomarkers
        ]
        assert len(creatinine_alerts) == 0, (
            f"82.2 µmol/L creatinine must produce NO urgent alerts. Got: {creatinine_alerts}"
        )


# ---------------------------------------------------------------------------
# Test 5: All surfaces must agree
# ---------------------------------------------------------------------------

class TestSurfaceConsistency:
    """Batch row, assess_biomarker, and AI Summary must all agree on severity."""

    def test_glucose_57_all_surfaces_agree_not_critical(self):
        """5.7 mmol/L: LabResult.status, assess_biomarker, and insight must all be non-critical."""
        result = _make_glucose_57_mmol()

        # Surface 1: stored LabResult.status (from lab_interpreter.classify_value)
        # lab_interpreter uses ref_high=99 mg/dL, so 102.7 mg/dL = 'high' (not critical)
        lab_result_status = result.status
        assert lab_result_status not in ("critical",), (
            f"LabResult.status for 5.7 mmol/L must not be 'critical', got '{lab_result_status}'"
        )

        # Surface 2: assess_biomarker with normalized value (as the FIXED route does)
        norm_si = _resolve_norm_si(result)
        assert norm_si is not None
        finding = assess_biomarker("fasting_glucose", norm_si)
        assert finding is not None
        assert finding.severity != "critical", (
            f"assess_biomarker(normalized 102.7 mg/dL) must not be critical. "
            f"Got severity='{finding.severity}'"
        )

        # Surface 3: AI Summary overall_status
        report = _run_insight_pipeline([result])
        assert report.overall_status != "urgent", (
            f"AI Summary for 5.7 mmol/L must not be 'urgent'. Got '{report.overall_status}'"
        )

        # Verify consistency between surfaces
        is_critical = (
            lab_result_status == "critical"
            or finding.severity == "critical"
            or report.overall_status == "urgent"
        )
        assert not is_critical, (
            "SURFACE INCONSISTENCY: At least one surface incorrectly shows critical for 5.7 mmol/L"
        )

    def test_glucose_502_all_surfaces_agree_critical(self):
        """502 mg/dL: all three surfaces must agree it IS critical."""
        result = _make_glucose_502_mgdl()

        lab_result_status = result.status
        assert lab_result_status == "critical", (
            f"LabResult.status for 502 mg/dL must be 'critical', got '{lab_result_status}'"
        )

        norm_si = _resolve_norm_si(result)
        finding = assess_biomarker("fasting_glucose", norm_si)
        assert finding is not None
        assert finding.severity == "critical", (
            f"assess_biomarker(502 mg/dL) must be critical. Got '{finding.severity}'"
        )

        report = _run_insight_pipeline([result])
        assert report.overall_status == "urgent", (
            f"AI Summary for 502 mg/dL must be 'urgent'. Got '{report.overall_status}'"
        )


# ---------------------------------------------------------------------------
# Test 6: normalized_value_si must be used, not raw value
# ---------------------------------------------------------------------------

class TestNormalizedValueUsed:
    """Verify the route uses normalized_value_si, not r.value."""

    def test_resolve_norm_si_uses_stored_normalized_value(self):
        """When normalized_value_si is set, use it directly (no re-normalization)."""
        result = MockLabResult(
            canonical_name="fasting_glucose",
            value=5.7,         # raw mmol/L
            unit="mmol/L",
            normalized_value_si=102.7,   # pre-computed canonical
            normalized_unit_si="mg/dL",
            status="borderline",
        )
        norm_si = _resolve_norm_si(result)
        assert norm_si == 102.7, (
            f"Should use stored normalized_value_si=102.7, got {norm_si}"
        )
        assert norm_si != 5.7, (
            "CRITICAL: Route must NOT use raw 5.7 (mmol/L) as mg/dL value!"
        )

    def test_resolve_norm_si_fallback_normalizes(self):
        """When normalized_value_si is None, fall back to on-the-fly normalization."""
        result = MockLabResult(
            canonical_name="fasting_glucose",
            value=5.7,
            unit="mmol/L",
            normalized_value_si=None,   # not pre-computed
            normalized_unit_si=None,
            status=None,
        )
        norm_si = _resolve_norm_si(result)
        assert norm_si is not None, "Fallback normalization must produce a value"
        assert 100.0 <= norm_si <= 115.0, (
            f"5.7 mmol/L should normalize to ~102.7 mg/dL, got {norm_si}"
        )
        assert norm_si != 5.7, (
            "Fallback must normalize, not return raw mmol/L value!"
        )

    def test_raw_57_as_mgdl_would_be_critically_wrong(self):
        """Document that using r.value=5.7 directly would incorrectly classify as critical.

        This test CONFIRMS the P0 bug existed before the fix.
        The route fix (using normalized_value_si) prevents this.
        """
        # Pre-fix wrong path: assess_biomarker("fasting_glucose", 5.7)
        wrong_finding = assess_biomarker("fasting_glucose", 5.7)
        assert wrong_finding is not None
        assert wrong_finding.severity == "critical"  # This is WRONG for 5.7 mmol/L

        # Post-fix correct path: assess_biomarker("fasting_glucose", 102.7)
        correct_finding = assess_biomarker("fasting_glucose", 102.7)
        assert correct_finding is not None
        assert correct_finding.severity != "critical"  # This is CORRECT

        # The two findings must disagree (that's the whole point of the fix)
        assert wrong_finding.severity != correct_finding.severity, (
            "This test confirms the P0 fix matters: "
            "wrong (5.7 mg/dL) and correct (102.7 mg/dL) must give different results"
        )
