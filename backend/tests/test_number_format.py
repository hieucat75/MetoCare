"""Tests for app.utils.number_format — shared lab/metric formatter.

Covers:
  - Each unit type from the spec table
  - Edge cases: None, NaN, inf, 0, very large, very small, unknown unit
  - String input: numeric strings parsed, non-numeric pass-through
  - Case-insensitive unit matching
  - format_lab_display with / without unit
"""

from __future__ import annotations

from app.utils.number_format import format_lab_display, format_lab_value

# ── Missing / invalid values ─────────────────────────────────────────────────


def test_none_returns_dash() -> None:
    assert format_lab_value(None) == "—"


def test_none_with_unit_returns_dash() -> None:
    assert format_lab_value(None, "mg/dL") == "—"


def test_nan_returns_dash() -> None:
    assert format_lab_value(float("nan")) == "—"


def test_pos_infinity_returns_dash() -> None:
    assert format_lab_value(float("inf")) == "—"


def test_neg_infinity_returns_dash() -> None:
    assert format_lab_value(float("-inf")) == "—"


# ── mg/dL → integer ──────────────────────────────────────────────────────────


def test_mgdl_rounds_float_artefact() -> None:
    assert format_lab_value(174.48289999999997, "mg/dL") == "174"


def test_mgdl_case_insensitive_lower() -> None:
    assert format_lab_value(100.7, "mg/dl") == "101"


def test_mgdl_case_insensitive_upper() -> None:
    assert format_lab_value(100.7, "MG/DL") == "101"


def test_mgdl_integer_stays_integer() -> None:
    assert format_lab_value(92, "mg/dL") == "92"


def test_mgdl_zero() -> None:
    assert format_lab_value(0, "mg/dL") == "0"


# ── mmol/L → 1 decimal ───────────────────────────────────────────────────────


def test_mmoll_one_decimal() -> None:
    assert format_lab_value(5.7321, "mmol/L") == "5.7"


def test_mmoll_trailing_zero() -> None:
    assert format_lab_value(1.009, "mmol/L") == "1.0"


def test_mmoll_case_insensitive() -> None:
    assert format_lab_value(5.7321, "MMOL/L") == "5.7"


# ── % → 1 decimal ────────────────────────────────────────────────────────────


def test_percent_one_decimal() -> None:
    assert format_lab_value(6.234, "%") == "6.2"


# ── BMI kg/m² → 1 decimal ────────────────────────────────────────────────────


def test_bmi_kg_m2_unicode() -> None:
    assert format_lab_value(22.456, "kg/m²") == "22.5"


def test_bmi_kg_m2_ascii() -> None:
    assert format_lab_value(22.456, "kg/m2") == "22.5"


# ── mmHg → integer ───────────────────────────────────────────────────────────


def test_mmhg_integer() -> None:
    assert format_lab_value(120.9, "mmHg") == "121"


def test_mmhg_case_insensitive() -> None:
    assert format_lab_value(80.3, "MMHG") == "80"


# ── eGFR mL/min → integer ────────────────────────────────────────────────────


def test_egfr_ml_min() -> None:
    assert format_lab_value(67.89, "mL/min/1.73m²") == "68"


def test_egfr_bare_ml_min() -> None:
    assert format_lab_value(89.2, "mL/min") == "89"


# ── µmol/L → integer ─────────────────────────────────────────────────────────


def test_umol_unicode_mu() -> None:
    assert format_lab_value(88.5678, "µmol/L") == "89"


def test_umol_ascii_u() -> None:
    assert format_lab_value(88.3, "umol/L") == "88"


def test_umol_alternate_mu() -> None:
    assert format_lab_value(44.7, "μmol/L") == "45"


# ── g/dL → 2 decimals ────────────────────────────────────────────────────────


def test_gdl_two_decimals() -> None:
    assert format_lab_value(14.5, "g/dL") == "14.50"


def test_gdl_trailing_zeros() -> None:
    assert format_lab_value(14.00001, "g/dL") == "14.00"


def test_gdl_case_insensitive() -> None:
    assert format_lab_value(14.5, "G/DL") == "14.50"


# ── IU/L → integer ───────────────────────────────────────────────────────────


def test_ul_enzyme_units() -> None:
    assert format_lab_value(45.7, "U/L") == "46"


def test_iul_variant() -> None:
    assert format_lab_value(32.4, "IU/L") == "32"


# ── mIU/L → 1 decimal ────────────────────────────────────────────────────────


def test_miu_l_tsh() -> None:
    assert format_lab_value(2.543, "mIU/L") == "2.5"


def test_miu_l_case_insensitive() -> None:
    assert format_lab_value(2.543, "miu/l") == "2.5"


# ── Default / unknown unit ────────────────────────────────────────────────────


def test_unknown_unit_small_float_two_decimals() -> None:
    assert format_lab_value(1.234, "foobar") == "1.23"


def test_unknown_unit_large_float_one_decimal() -> None:
    assert format_lab_value(12.34, "xyz") == "12.3"


def test_unknown_unit_integer_zero_decimals() -> None:
    assert format_lab_value(42, "xyz") == "42"


def test_no_unit_integer() -> None:
    assert format_lab_value(120) == "120"


def test_no_unit_float() -> None:
    assert format_lab_value(5.678) == "5.7"


# ── String input ─────────────────────────────────────────────────────────────


def test_numeric_string_parsed() -> None:
    assert format_lab_value("174.9", "mg/dL") == "175"


def test_non_numeric_string_passes_through() -> None:
    assert format_lab_value("<5", "µmol/L") == "<5"


def test_non_numeric_word_passes_through() -> None:
    assert format_lab_value("negative", "mg/dL") == "negative"


# ── format_lab_display ────────────────────────────────────────────────────────


def test_display_appends_unit() -> None:
    assert format_lab_display(174.48289999999997, "mg/dL") == "174 mg/dL"


def test_display_mmoll() -> None:
    assert format_lab_display(5.7321, "mmol/L") == "5.7 mmol/L"


def test_display_none_no_unit_suffix() -> None:
    assert format_lab_display(None, "mg/dL") == "—"


def test_display_empty_unit_no_suffix() -> None:
    assert format_lab_display(120, "") == "120"


def test_display_none_unit_no_suffix() -> None:
    assert format_lab_display(120, None) == "120"


def test_display_whitespace_unit_trimmed() -> None:
    assert format_lab_display(120, "  mmHg  ") == "120 mmHg"


def test_display_gdl_with_unit() -> None:
    assert format_lab_display(14.5, "g/dL") == "14.50 g/dL"
