"""Lab interpreter tests — classification, normalization, safe explanations."""

from __future__ import annotations

import pytest
from app.domain import lab_interpreter, policies
from app.domain.lab_interpreter import LabStatus, RawLabValue
from app.services import lab_parser


def test_normalize_aliases():
    assert lab_interpreter.normalize_biomarker("Glucose") == "fasting_glucose"
    assert lab_interpreter.normalize_biomarker("đường huyết đói") == "fasting_glucose"
    assert lab_interpreter.normalize_biomarker("HbA1c") == "hba1c"
    assert lab_interpreter.normalize_biomarker("mỡ máu") == "triglyceride"
    assert lab_interpreter.normalize_biomarker("không biết chỉ số này") is None


def test_classify_boundaries():
    assert lab_interpreter.classify_value("fasting_glucose", 90) == LabStatus.NORMAL
    assert lab_interpreter.classify_value("fasting_glucose", 120) == LabStatus.HIGH
    # 60 is below ref_low (70) but above critical_low (54) -> LOW
    assert lab_interpreter.classify_value("fasting_glucose", 60) == LabStatus.LOW
    # 50 is at/below critical_low (54) -> CRITICAL
    assert lab_interpreter.classify_value("fasting_glucose", 50) == LabStatus.CRITICAL
    # 320 mg/dL: below updated critical_high=500 -> HIGH (not CRITICAL)
    # clinical_safety_sweep 2026-06-27: critical_high raised 300→500 (ADA 2024)
    assert lab_interpreter.classify_value("fasting_glucose", 320) == LabStatus.HIGH
    # 502 mg/dL: above critical_high=500 -> CRITICAL
    assert lab_interpreter.classify_value("fasting_glucose", 502) == LabStatus.CRITICAL


def test_unknown_biomarker_needs_verification():
    b = lab_interpreter.interpret_value(RawLabValue("mystery_marker", 1.0))
    assert b.status == LabStatus.UNKNOWN
    assert b.needs_verification is True


def test_low_ocr_confidence_flags_verification():
    b = lab_interpreter.interpret_value(RawLabValue("HDL", 38.0, ocr_confidence=0.5))
    assert b.needs_verification is True
    assert "xác nhận" in b.patient_note


def test_panel_explanation_is_safe():
    panel = [
        RawLabValue("Glucose", 502.0, "mg/dL"),  # critical (>=500)
        RawLabValue("Triglyceride", 220.0, "mg/dL"),  # high
        RawLabValue("HDL", 60.0, "mg/dL"),  # normal
    ]
    result = lab_interpreter.interpret_panel(panel)
    assert "fasting_glucose" in result.critical
    assert "triglyceride" in result.abnormal
    # mandatory disclaimer present, no diagnosis assertion language
    assert policies.DISCLAIMER_VI in result.patient_explanation
    assert "bạn bị" not in result.patient_explanation.lower()
    # doctor summary is data-only
    assert "no AI conclusion" in result.doctor_summary


def test_mock_ocr_extract_is_deterministic():
    a = lab_interpreter.mock_ocr_extract("doc-1")
    b = lab_interpreter.mock_ocr_extract("doc-1")
    assert [(x.test_name, x.value) for x in a] == [(x.test_name, x.value) for x in b]


# ---------------------------------------------------------------------------
# P0 Confidence Engine — golden regression tests
# ---------------------------------------------------------------------------


def _parse_single(text: str, canonical: str):
    results = lab_parser.parse_lab_text(text)
    return next((r for r in results if r.test_name == canonical), None)


class TestCreatinineUmolL:
    """82.2 µmol/L must convert to mg/dL with confidence=1.0 (not store as 82.2 mg/dL)."""

    def test_converts_to_mg_dl(self):
        v = _parse_single("Creatinine  82.2 µmol/L", "creatinine")
        assert v is not None
        assert abs(v.value - 82.2 * 0.011312) < 0.001
        assert v.unit == "mg/dL"

    def test_confidence_is_high(self):
        v = _parse_single("Creatinine  82.2 µmol/L", "creatinine")
        assert v is not None
        assert v.ocr_confidence == 1.0

    def test_unicode_variant_mu_u03bc(self):
        """μ (U+03BC Greek) must normalize identically to µ (U+00B5 micro sign)."""
        v = _parse_single("Creatinine  82.2 μmol/L", "creatinine")
        assert v is not None
        assert v.ocr_confidence == 1.0

    def test_unicode_variant_umol(self):
        """umol/L (ASCII u) must be recognized as µmol/L."""
        v = _parse_single("Creatinine  82.2 umol/L", "creatinine")
        assert v is not None
        assert v.ocr_confidence == 1.0

    @pytest.mark.parametrize("unit_str", ["µmol/L", "μmol/L", "umol/L", "µMol/L"])
    def test_all_micro_variants(self, unit_str: str):
        text = f"Creatinine  82.2 {unit_str}"
        v = _parse_single(text, "creatinine")
        assert v is not None, f"Not parsed with unit {unit_str!r}"
        assert abs(v.value - 82.2 * 0.011312) < 0.001
        assert v.ocr_confidence == 1.0

    def test_value_not_stored_as_raw_umol(self):
        """Sanity: converted value must be <<1 mg/dL, not 82.2 mg/dL."""
        v = _parse_single("Creatinine  82.2 µmol/L", "creatinine")
        assert v is not None
        assert v.value < 2.0, f"Expected ~0.93 mg/dL, got {v.value}"


class TestUreaMmolL:
    """4.47 mmol/L must convert to mg/dL with high confidence."""

    def test_converts_to_mg_dl(self):
        v = _parse_single("Urea  4.47 mmol/L", "urea")
        assert v is not None
        assert abs(v.value - 4.47 * 6.006) < 0.01
        assert v.unit == "mg/dL"

    def test_confidence_is_high(self):
        v = _parse_single("Urea  4.47 mmol/L", "urea")
        assert v is not None
        assert v.ocr_confidence == 1.0


class TestTSHOcrVariants:
    """TSH: pIU/mL (Azure OCR misread of µ) must be corrected and converted."""

    def test_piu_ml_corrected_and_confidence_high(self):
        v = _parse_single("TSH  1.26 pIU/mL", "tsh")
        assert v is not None
        assert abs(v.value - 1.26) < 0.01
        assert v.ocr_confidence == 1.0

    def test_uiu_ml_high_confidence(self):
        v = _parse_single("TSH  1.26 uIU/mL", "tsh")
        assert v is not None
        assert v.ocr_confidence == 1.0

    def test_mcium_ml_high_confidence(self):
        """mcIU/mL (mc=micro OCR variant) must normalize to µIU/mL."""
        v = _parse_single("TSH  1.26 mcIU/mL", "tsh")
        assert v is not None
        assert v.ocr_confidence == 1.0

    @pytest.mark.parametrize("unit_str", ["µIU/mL", "μIU/mL", "uIU/mL", "pIU/mL", "mcIU/mL"])
    def test_all_tsh_unit_variants(self, unit_str: str):
        text = f"TSH  1.26 {unit_str}"
        v = _parse_single(text, "tsh")
        assert v is not None, f"Not parsed with unit {unit_str!r}"
        assert v.ocr_confidence == 1.0
        assert abs(v.value - 1.26) < 0.01


class TestConfidenceDetail:
    """ConfidenceDetail is populated and reasons are human-readable."""

    def test_detail_present_for_parsed_row(self):
        v = _parse_single("Creatinine  82.2 µmol/L", "creatinine")
        assert v is not None
        assert v.confidence_detail is not None

    def test_high_confidence_has_check_marks(self):
        v = _parse_single("Creatinine  82.2 µmol/L", "creatinine")
        assert v is not None
        assert v.confidence_detail is not None
        reasons = v.confidence_detail.reasons
        assert any("✓" in r for r in reasons)
        assert not any("⚠" in r for r in reasons)

    def test_missing_unit_lowers_ocr_and_conversion_dim(self):
        v = _parse_single("Creatinine  0.9", "creatinine")
        assert v is not None
        assert v.confidence_detail is not None
        assert v.confidence_detail.ocr < 1.0
        assert v.confidence_detail.conversion < 1.0

    def test_incompatible_unit_gives_zero_overall(self):
        v = _parse_single("Glucose  5.4 mIU/mL", "fasting_glucose")
        assert v is not None
        assert v.ocr_confidence == 0.0


class TestNormUnit:
    """_norm_unit correctly handles all micro-sign variants."""

    def test_micro_sign_u00b5(self):
        assert lab_parser._norm_unit("µmol/L") == "umol/l"

    def test_greek_mu_u03bc(self):
        assert lab_parser._norm_unit("μmol/L") == "umol/l"

    def test_mc_prefix(self):
        assert lab_parser._norm_unit("mcIU/mL") == "uiu/ml"

    def test_mol_not_changed_to_umol(self):
        """mol must NOT auto-become µmol — only explicit µ/μ/mc prefixes are replaced."""
        result = lab_parser._norm_unit("mol/L")
        assert result == "mol/l"
        assert "u" not in result


class TestParenStripping:
    """normalize_biomarker() strips parenthetical suffixes before alias lookup (Phase B W1)."""

    def test_alt_gpt_suffix(self):
        assert lab_interpreter.normalize_biomarker("ALT (GPT)") == "alt"

    def test_ast_got_suffix(self):
        assert lab_interpreter.normalize_biomarker("AST (GOT)") == "ast"

    def test_sgot_ast_suffix(self):
        assert lab_interpreter.normalize_biomarker("SGOT (AST)") == "ast"

    def test_sgpt_alt_suffix(self):
        assert lab_interpreter.normalize_biomarker("SGPT (ALT)") == "alt"

    def test_ldl_tinh_suffix(self):
        assert lab_interpreter.normalize_biomarker("LDL-Cholesterol (tính)") == "ldl"

    def test_ldl_calculated_suffix(self):
        assert lab_interpreter.normalize_biomarker("LDL-Cholesterol (calculated)") == "ldl"

    def test_glucose_cobas_suffix(self):
        assert lab_interpreter.normalize_biomarker("Glucose (Cobas C502)") == "fasting_glucose"

    def test_fullwidth_paren(self):
        """Full-width Unicode parens（）from certain PDF printers (Phase B W4 fix)."""
        assert lab_interpreter.normalize_biomarker("ALT（GPT）") == "alt"

    def test_no_suffix_unchanged(self):
        assert lab_interpreter.normalize_biomarker("Glucose") == "fasting_glucose"

    def test_nested_suffix_stripped_iteratively(self):
        """Multiple trailing groups removed iteratively."""
        assert (
            lab_interpreter.normalize_biomarker("Glucose (mau) (Cobas C502)") == "fasting_glucose"
        )
