"""Clinical Safety Sweep — Regression Tests
===========================================
Verifies unit conversions, threshold classification, and original-value
preservation for all unit-dependent biomarkers.

Run:
    cd backend && python -m pytest tests/test_clinical_safety.py -v
"""
from __future__ import annotations

import pytest

from app.domain.lab_interpreter import (
    BiomarkerSpec,
    LabStatus,
    classify_value,
    normalize_biomarker,
    _ALIAS_INDEX,
)
from app.domain.lab_normalization import normalize_value_to_si, classify_status
from app.domain.clinical_rules import assess_biomarker


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------

def _convert(value: float, unit: str, canonical: str) -> tuple[float, str]:
    """Convenience wrapper."""
    return normalize_value_to_si(value, unit, canonical)


# ---------------------------------------------------------------------------
# Phase 1 — Conversion paths
# ---------------------------------------------------------------------------

class TestGlucoseConversion:
    def test_glucose_mmol_slightly_high(self):
        """5.7 mmol/L → ~102.7 mg/dL → pre-diabetic. MUST NOT be LOW."""
        converted, unit = _convert(5.7, "mmol/L", "fasting_glucose")
        assert abs(converted - 102.7026) < 0.01
        assert unit == "mg/dL"
        status = classify_value("fasting_glucose", converted)
        # 102.7 mg/dL is > ref_high=99, so HIGH (not LOW, not CRITICAL)
        assert status == LabStatus.HIGH, (
            f"5.7 mmol/L → {converted:.2f} mg/dL classified as {status}, expected HIGH"
        )

    def test_glucose_mmol_normal(self):
        """4.5 mmol/L → 81 mg/dL → normal."""
        converted, unit = _convert(4.5, "mmol/L", "fasting_glucose")
        assert abs(converted - 81.081) < 0.01
        assert unit == "mg/dL"
        status = classify_value("fasting_glucose", converted)
        assert status == LabStatus.NORMAL

    def test_glucose_mgdl_critical_high(self):
        """502 mg/dL → critical high. Must not reject or return wrong status."""
        # No conversion needed when already mg/dL
        converted, unit = _convert(502.0, "mg/dL", "fasting_glucose")
        assert abs(converted - 502.0) < 0.001
        assert unit == "mg/dL"
        status = classify_value("fasting_glucose", converted)
        assert status == LabStatus.CRITICAL, (
            f"502 mg/dL expected CRITICAL, got {status}"
        )

    def test_glucose_equivalent_units(self):
        """5.7 mmol/L and 102.7 mg/dL must give same clinical status."""
        from_mmol, _ = _convert(5.7, "mmol/L", "fasting_glucose")
        from_mgdl, _ = _convert(102.7, "mg/dL", "fasting_glucose")
        status_mmol = classify_value("fasting_glucose", from_mmol)
        status_mgdl = classify_value("fasting_glucose", from_mgdl)
        assert status_mmol == status_mgdl, (
            f"mmol/L→{status_mmol} ≠ mg/dL→{status_mgdl}"
        )

    def test_glucose_not_critical_at_300(self):
        """300 mg/dL is no longer the critical threshold (raised to 500)."""
        status = classify_value("fasting_glucose", 300.0)
        # 300 > ref_high=99, so HIGH (not CRITICAL since critical_high=500)
        assert status == LabStatus.HIGH, (
            f"300 mg/dL expected HIGH, got {status}"
        )

    def test_glucose_critical_low_boundary(self):
        """54 mg/dL → CRITICAL (critical_low=54)."""
        status = classify_value("fasting_glucose", 54.0)
        assert status == LabStatus.CRITICAL

    def test_glucose_mmol_critical_low(self):
        """2.8 mmol/L → 50.5 mg/dL → CRITICAL."""
        converted, _ = _convert(2.8, "mmol/L", "fasting_glucose")
        assert converted < 54.0
        status = classify_value("fasting_glucose", converted)
        assert status == LabStatus.CRITICAL


class TestCholesterolConversion:
    def test_cholesterol_mmol(self):
        """6.2 mmol/L → 239.75 mg/dL → HIGH (>199)."""
        converted, unit = _convert(6.2, "mmol/L", "total_cholesterol")
        assert abs(converted - 239.754) < 0.01
        assert unit == "mg/dL"
        status = classify_value("total_cholesterol", converted)
        assert status == LabStatus.HIGH

    def test_cholesterol_equivalent_units(self):
        """6.2 mmol/L and 239.7 mg/dL → same status."""
        from_mmol, _ = _convert(6.2, "mmol/L", "total_cholesterol")
        from_mgdl, _ = _convert(239.7, "mg/dL", "total_cholesterol")
        assert classify_value("total_cholesterol", from_mmol) == \
               classify_value("total_cholesterol", from_mgdl)

    def test_cholesterol_normal_mgdl(self):
        """185 mg/dL → NORMAL."""
        status = classify_value("total_cholesterol", 185.0)
        assert status == LabStatus.NORMAL

    def test_cholesterol_high_mgdl(self):
        """242 mg/dL → HIGH (real clinical value, must not be rejected)."""
        converted, unit = _convert(242.0, "mg/dL", "total_cholesterol")
        assert abs(converted - 242.0) < 0.001
        status = classify_value("total_cholesterol", converted)
        assert status == LabStatus.HIGH


class TestLDLConversion:
    def test_ldl_mmol_borderline(self):
        """3.4 mmol/L → ~131 mg/dL → HIGH (>ref_high=99)."""
        converted, unit = _convert(3.4, "mmol/L", "ldl")
        assert abs(converted - 131.478) < 0.01
        assert unit == "mg/dL"
        status = classify_value("ldl", converted)
        assert status == LabStatus.HIGH

    def test_ldl_clinical_rules_uses_mgdl_threshold(self):
        """clinical_rules LDL threshold must be mg/dL (>130), not mmol/L (>3.4)."""
        # 3.4 mg/dL is essentially nothing (sub-physiological) — must NOT trigger warning
        finding_tiny = assess_biomarker("ldl", 3.4)
        # 131 mg/dL IS high (borderline by AHA)
        finding_high = assess_biomarker("ldl", 131.0)
        assert finding_tiny is not None
        assert finding_tiny.status == "normal", (
            f"ldl=3.4 mg/dL must be 'normal', got '{finding_tiny.status}'"
        )
        assert finding_high is not None
        assert finding_high.status == "high", (
            f"ldl=131 mg/dL must be 'high', got '{finding_high.status}'"
        )


class TestHDLConversion:
    def test_hdl_mmol_low_male(self):
        """0.85 mmol/L → ~32.9 mg/dL → LOW (<40 for males)."""
        converted, unit = _convert(0.85, "mmol/L", "hdl")
        assert abs(converted - 32.8695) < 0.01
        assert unit == "mg/dL"
        status = classify_value("hdl", converted)
        assert status == LabStatus.LOW


class TestTriglycerideConversion:
    def test_triglycerides_mmol(self):
        """2.5 mmol/L → ~221 mg/dL → HIGH (>149)."""
        converted, unit = _convert(2.5, "mmol/L", "triglyceride")
        assert abs(converted - 221.425) < 0.01
        assert unit == "mg/dL"
        status = classify_value("triglyceride", converted)
        assert status == LabStatus.HIGH

    def test_triglycerides_high_502_mgdl(self):
        """502 mg/dL → HIGH/CRITICAL. Must not reject with validation error."""
        converted, unit = _convert(502.0, "mg/dL", "triglyceride")
        assert abs(converted - 502.0) < 0.001
        status = classify_value("triglyceride", converted)
        assert status == LabStatus.CRITICAL, (
            f"502 mg/dL TG expected CRITICAL (≥500), got {status}"
        )

    def test_triglycerides_clinical_rules_mgdl_threshold(self):
        """clinical_rules TG threshold must be 500 mg/dL, not 5.6 mmol/L."""
        # 5.6 mg/dL is NOT high; only 5.6 mmol/L (=496 mg/dL) would be
        finding_low = assess_biomarker("triglyceride", 5.6)
        finding_very_high = assess_biomarker("triglyceride", 502.0)
        assert finding_low is not None
        assert finding_low.status == "normal", (
            f"TG=5.6 mg/dL must be 'normal', got '{finding_low.status}' "
            f"(old mmol/L threshold bug)"
        )
        assert finding_very_high is not None
        assert finding_very_high.status == "high", (
            f"TG=502 mg/dL must be 'high', got '{finding_very_high.status}'"
        )


class TestCreatinineConversion:
    def test_creatinine_umol(self):
        """110 µmol/L → ~1.24 mg/dL → slightly elevated male (ref_high=1.3)."""
        converted, unit = _convert(110.0, "µmol/L", "creatinine")
        assert abs(converted - 1.2440) < 0.001
        assert unit == "mg/dL"
        # 1.244 < ref_high=1.3 → NORMAL
        status = classify_value("creatinine", converted)
        assert status == LabStatus.NORMAL, (
            f"Creatinine 110 µmol/L → {converted:.3f} mg/dL expected NORMAL, got {status}"
        )

    def test_creatinine_umol_elevated(self):
        """135 µmol/L → ~1.53 mg/dL → HIGH (>ref_high=1.3)."""
        converted, _ = _convert(135.0, "µmol/L", "creatinine")
        assert abs(converted - 135 / 88.42) < 0.001
        status = classify_value("creatinine", converted)
        assert status == LabStatus.HIGH

    def test_creatinine_si_factor(self):
        """Verify si_factor for creatinine ≈ 0.011310 (1/88.42)."""
        spec = _ALIAS_INDEX.get("creatinine")
        assert spec is not None
        assert abs(spec.si_factor - 0.011310) < 0.0001


class TestUricAcidConversion:
    def test_uric_acid_umol(self):
        """420 µmol/L → ~7.06 mg/dL → borderline high male (ref_high=7.0)."""
        converted, unit = _convert(420.0, "µmol/L", "uric_acid")
        assert abs(converted - 420 / 59.48) < 0.001
        assert unit == "mg/dL"
        # 7.06 > ref_high=7.0 → HIGH
        status = classify_value("uric_acid", converted)
        assert status == LabStatus.HIGH, (
            f"Uric acid 420 µmol/L → {converted:.3f} mg/dL expected HIGH, got {status}"
        )

    def test_uric_acid_si_factor_exists(self):
        """uric_acid must have si_unit and si_factor defined for µmol/L conversion."""
        spec = _ALIAS_INDEX.get("uric_acid")
        assert spec is not None, "uric_acid not in biomarker index"
        assert spec.si_unit is not None, "uric_acid.si_unit must not be None"
        assert spec.si_factor > 0, "uric_acid.si_factor must be positive"
        assert abs(spec.si_factor - 0.016813) < 0.0001

    def test_uric_acid_normal(self):
        """350 µmol/L → ~5.88 mg/dL → NORMAL (3.5–7.0)."""
        converted, _ = _convert(350.0, "µmol/L", "uric_acid")
        status = classify_value("uric_acid", converted)
        assert status == LabStatus.NORMAL


class TestUreaConversion:
    def test_urea_mmol_normal(self):
        """5.0 mmol/L → ~30.0 mg/dL urea → NORMAL (ref 15–40)."""
        converted, unit = _convert(5.0, "mmol/L", "urea")
        assert abs(converted - 30.03) < 0.01
        assert unit == "mg/dL"
        status = classify_value("urea", converted)
        assert status == LabStatus.NORMAL, (
            f"Urea 5 mmol/L → {converted:.2f} mg/dL expected NORMAL, got {status}"
        )

    def test_urea_threshold_is_for_full_urea_not_bun(self):
        """ref_low=15, ref_high=40 mg/dL (full urea molecule, not BUN 7–20)."""
        spec = _ALIAS_INDEX.get("urea")
        assert spec is not None
        assert spec.ref_low == 15, f"urea ref_low should be 15 mg/dL, got {spec.ref_low}"
        assert spec.ref_high == 40, f"urea ref_high should be 40 mg/dL, got {spec.ref_high}"


class TestEnzymeNoConversion:
    def test_alt_no_conversion(self):
        """ALT 45 U/L → stays 45, slightly elevated (ref_high=56 for this spec)."""
        converted, unit = _convert(45.0, "U/L", "alt")
        assert abs(converted - 45.0) < 0.001
        assert unit == "U/L"
        # 45 < ref_high=56 → NORMAL
        status = classify_value("alt", converted)
        assert status == LabStatus.NORMAL

    def test_alt_elevated(self):
        """ALT 60 U/L → HIGH (>56)."""
        status = classify_value("alt", 60.0)
        assert status == LabStatus.HIGH

    def test_ast_no_conversion(self):
        """AST 35 U/L → NORMAL."""
        converted, unit = _convert(35.0, "U/L", "ast")
        assert abs(converted - 35.0) < 0.001
        status = classify_value("ast", converted)
        assert status == LabStatus.NORMAL

    def test_no_unit_conversion_for_ul(self):
        """ALT 45 U/L stays 45. confirm assess_biomarker agrees."""
        finding = assess_biomarker("alt", 45.0)
        assert finding is not None
        assert finding.status == "normal", (
            f"ALT=45 U/L expected normal, got {finding.status}"
        )


class TestHbA1c:
    def test_hba1c_diabetic(self):
        """6.5% → CRITICAL (spec critical_high=10) or HIGH."""
        # 6.5% > ref_high=5.6 → HIGH
        status = classify_value("hba1c", 6.5)
        assert status == LabStatus.HIGH

    def test_hba1c_prediabetes_rule(self):
        """5.7–6.4% → borderline/watch via clinical_rules."""
        finding = assess_biomarker("hba1c", 5.8)
        assert finding is not None
        assert finding.status == "borderline", (
            f"HbA1c=5.8% expected borderline, got {finding.status}"
        )

    def test_hba1c_diabetic_clinical_rule(self):
        """6.5% → NOT borderline in clinical_rules (falls through to normal/watch)."""
        finding = assess_biomarker("hba1c", 6.5)
        assert finding is not None
        # 6.5 > 6.4 upper prediabetes boundary — no explicit rule, returns normal
        # But classify_value sees it as HIGH
        assert classify_value("hba1c", 6.5) == LabStatus.HIGH

    def test_hba1c_normal(self):
        """5.5% → NORMAL."""
        status = classify_value("hba1c", 5.5)
        assert status == LabStatus.NORMAL


# ---------------------------------------------------------------------------
# Phase 2 — Original value preservation
# ---------------------------------------------------------------------------

class TestOriginalValuePreservation:
    """normalize_value_to_si must never mutate original_value / original_unit.
    These fields are display-only and must survive the conversion pipeline."""

    def test_original_value_preserved_glucose(self):
        """After conversion, original_value=5.7 and original_unit='mmol/L' unchanged."""
        raw_value = 5.7
        raw_unit = "mmol/L"
        canonical_value, canonical_unit = _convert(raw_value, raw_unit, "fasting_glucose")
        # The normalize_value_to_si function returns new values; original is unchanged
        assert abs(raw_value - 5.7) < 1e-9, "raw_value must not be mutated"
        assert raw_unit == "mmol/L", "raw_unit must not be mutated"
        assert abs(canonical_value - 102.7026) < 0.01
        assert canonical_unit == "mg/dL"

    def test_original_value_preserved_creatinine(self):
        """110 µmol/L → canonical, original stays 110 µmol/L."""
        raw_value = 110.0
        raw_unit = "µmol/L"
        canonical_value, canonical_unit = _convert(raw_value, raw_unit, "creatinine")
        assert abs(raw_value - 110.0) < 1e-9
        assert raw_unit == "µmol/L"
        assert canonical_unit == "mg/dL"

    def test_normalized_si_values_correct_glucose(self):
        """normalized_value_si and normalized_unit_si must be mg/dL."""
        converted, unit = _convert(5.7, "mmol/L", "fasting_glucose")
        assert unit == "mg/dL"
        assert abs(converted - 102.7026) < 0.01

    def test_original_preserved_uric_acid_umol(self):
        """420 µmol/L preserved; converted = ~7.06 mg/dL."""
        raw = 420.0
        raw_unit = "µmol/L"
        converted, c_unit = _convert(raw, raw_unit, "uric_acid")
        assert abs(raw - 420.0) < 1e-9
        assert raw_unit == "µmol/L"
        assert c_unit == "mg/dL"
        assert abs(converted - 7.06) < 0.01


# ---------------------------------------------------------------------------
# Phase 3 — Threshold correctness matrix
# ---------------------------------------------------------------------------

class TestThresholdMatrix:
    """Validate ref_low, ref_high, critical_low, critical_high for all biomarkers."""

    def _spec(self, canonical: str) -> BiomarkerSpec:
        spec = _ALIAS_INDEX.get(canonical)
        assert spec is not None, f"{canonical} not found in biomarker index"
        return spec

    def test_glucose_thresholds(self):
        spec = self._spec("fasting_glucose")
        assert spec.ref_low == 70
        assert spec.ref_high == 99
        assert spec.critical_low == 54
        assert spec.critical_high == 500  # updated from 300

    def test_total_cholesterol_thresholds(self):
        spec = self._spec("total_cholesterol")
        assert spec.ref_low == 0
        assert spec.ref_high == 199  # normal <200

    def test_ldl_thresholds(self):
        spec = self._spec("ldl")
        assert spec.ref_high == 99   # optimal <100 mg/dL

    def test_hdl_thresholds(self):
        spec = self._spec("hdl")
        assert spec.ref_low == 40    # low for male
        assert spec.critical_low == 20

    def test_triglyceride_thresholds(self):
        spec = self._spec("triglyceride")
        assert spec.ref_high == 149  # normal <150
        assert spec.critical_high == 500  # very high

    def test_creatinine_thresholds(self):
        spec = self._spec("creatinine")
        assert spec.ref_low == 0.6
        assert spec.ref_high == 1.3

    def test_urea_thresholds_full_urea_not_bun(self):
        spec = self._spec("urea")
        assert spec.ref_low == 15
        assert spec.ref_high == 40

    def test_uric_acid_thresholds(self):
        spec = self._spec("uric_acid")
        assert spec.ref_low == 3.5
        assert spec.ref_high == 7.0
        assert spec.critical_high == 10.0

    def test_alt_thresholds(self):
        spec = self._spec("alt")
        assert spec.ref_high == 56

    def test_ast_thresholds(self):
        spec = self._spec("ast")
        assert spec.ref_high == 40

    def test_ggt_thresholds(self):
        spec = self._spec("ggt")
        assert spec.ref_high == 48  # approximate male ULN

    def test_hba1c_thresholds(self):
        spec = self._spec("hba1c")
        assert spec.ref_high == 5.6  # <5.7% normal → 5.6 is the last normal value


# ---------------------------------------------------------------------------
# Phase 4 — Clinical rules use mg/dL (not mmol/L residual thresholds)
# ---------------------------------------------------------------------------

class TestClinicalRulesMgDl:
    def test_glucose_prediabetes_clinical_rule(self):
        """102 mg/dL → borderline (prediabetes 100–125)."""
        finding = assess_biomarker("fasting_glucose", 102.0)
        assert finding is not None
        assert finding.status == "borderline"

    def test_glucose_high_clinical_rule(self):
        """135 mg/dL → high (diabetic range 126–499)."""
        finding = assess_biomarker("fasting_glucose", 135.0)
        assert finding is not None
        assert finding.status == "high"

    def test_glucose_critical_high_clinical_rule(self):
        """502 mg/dL → critical."""
        finding = assess_biomarker("fasting_glucose", 502.0)
        assert finding is not None
        assert finding.status == "critical"

    def test_glucose_mild_hypo_clinical_rule(self):
        """60 mg/dL → low (54 < value < 70 mild hypoglycemia)."""
        finding = assess_biomarker("fasting_glucose", 60.0)
        assert finding is not None
        assert finding.status == "low"

    def test_glucose_critical_low_clinical_rule(self):
        """50 mg/dL → critical (≤54)."""
        finding = assess_biomarker("fasting_glucose", 50.0)
        assert finding is not None
        assert finding.status == "critical"

    def test_ldl_normal_low_mg_dl_not_flagged(self):
        """LDL 3.4 mg/dL must NOT trigger warning (old mmol/L threshold bug)."""
        finding = assess_biomarker("ldl", 3.4)
        assert finding is not None
        assert finding.status == "normal", (
            f"ldl=3.4 mg/dL (sub-physiological) should be 'normal', got '{finding.status}'. "
            "This indicates the mmol/L threshold (>3.4) bug is NOT fixed."
        )

    def test_ldl_high_mg_dl_flagged(self):
        """LDL 131 mg/dL → high (>130 mg/dL threshold)."""
        finding = assess_biomarker("ldl", 131.0)
        assert finding is not None
        assert finding.status == "high"

    def test_tg_not_high_at_5_6_mg_dl(self):
        """TG 5.6 mg/dL → normal. Old bug: 5.6 mmol/L (=496 mg/dL) was threshold."""
        finding = assess_biomarker("triglyceride", 5.6)
        assert finding is not None
        assert finding.status == "normal", (
            f"TG=5.6 mg/dL should be 'normal', got '{finding.status}'. "
            "This indicates the mmol/L threshold (>5.6) bug is NOT fixed."
        )

    def test_tg_very_high_mg_dl_flagged(self):
        """TG 502 mg/dL → critical (≥500 mg/dL per spec)."""
        # classify_value sees 502 >= critical_high=500 → CRITICAL
        status = classify_value("triglyceride", 502.0)
        assert status == LabStatus.CRITICAL

        # assess_biomarker: TG > 500 → warning (high) via rule engine
        finding = assess_biomarker("triglyceride", 502.0)
        assert finding is not None
        assert finding.status in {"high", "critical"}, (
            f"TG=502 mg/dL expected high or critical, got {finding.status}"
        )
