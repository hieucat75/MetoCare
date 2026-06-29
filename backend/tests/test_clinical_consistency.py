"""test_clinical_consistency.py — P0 clinical value pipeline consistency tests.

Verifies the single-source-of-truth canonical pipeline:
  OCR → normalize → store → display (original) → AI (original formatted)

Tests cover:
  - _build_clinical_input: display-value path (Bug 1)
  - float artifact elimination (Bug 2)
  - _clean_reference_range: unit-suffix stripping (Bug 3)
  - statusLabel vocabulary parity (Bug 4)
  - format_lab_value formatting rules
  - validate_explanation / build_prompt compatibility
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Helpers — import target functions directly (unit tests, no HTTP)
# ---------------------------------------------------------------------------
from app.api.v1.routes.lab import _build_clinical_input, _clean_reference_range
from app.services.clinical_explanation import (
    build_prompt,
    get_deterministic_fallback,
    validate_explanation,
)
from app.utils.number_format import format_lab_value

# ---------------------------------------------------------------------------
# Minimal LabResult stub — avoids DB session
# ---------------------------------------------------------------------------

class _LabRow:
    """Minimal stand-in for app.models.clinical.LabResult for unit tests."""

    def __init__(
        self,
        *,
        test_name: str = "Glucose",
        canonical_name: str | None = "glucose",
        value: float | None = None,
        unit: str | None = None,
        original_value: float | None = None,
        original_unit: str | None = None,
        normalized_value_si: float | None = None,
        normalized_unit_si: str | None = None,
        reference_range: str | None = None,
        status: str | None = "normal",
    ):
        self.test_name = test_name
        self.canonical_name = canonical_name
        self.value = value
        self.unit = unit
        self.original_value = original_value
        self.original_unit = original_unit
        self.normalized_value_si = normalized_value_si
        self.normalized_unit_si = normalized_unit_si
        self.reference_range = reference_range
        self.status = status


# ===========================================================================
# Bug 1 — Display value is original_value / original_unit, not SI float
# ===========================================================================

class TestBuildClinicalInputDisplayValue:
    """normalized_value in the returned dict must reflect original_value/unit."""

    def test_mmol_original_returns_display_string_not_si_float(self):
        """When original is 6.0 mmol/L, normalized_value should be '6.0', not '231.63...'"""
        row = _LabRow(
            original_value=6.0,
            original_unit="mmol/L",
            normalized_value_si=231.63330000000002,
            normalized_unit_si="mg/dL",
        )
        ci = _build_clinical_input(row)
        assert ci["normalized_value"] == "6.0", (
            f"Expected '6.0' but got {ci['normalized_value']!r}"
        )
        assert ci["normalized_unit"] == "mmol/L"

    def test_display_value_not_si_value(self):
        """normalized_value must be the formatted original, not the SI float."""
        row = _LabRow(
            original_value=5.5,
            original_unit="mmol/L",
            normalized_value_si=99.0,
            normalized_unit_si="mg/dL",
        )
        ci = _build_clinical_input(row)
        # Must not contain SI unit or SI value
        assert "99" not in ci["normalized_value"]
        assert ci["normalized_unit"] == "mmol/L"

    def test_canonical_si_fields_preserved(self):
        """canonical_value_si and canonical_unit_si must carry the SI data."""
        row = _LabRow(
            original_value=6.0,
            original_unit="mmol/L",
            normalized_value_si=231.63330000000002,
            normalized_unit_si="mg/dL",
        )
        ci = _build_clinical_input(row)
        assert ci["canonical_value_si"] == round(231.63330000000002, 4)
        assert ci["canonical_unit_si"] == "mg/dL"

    def test_mg_dl_original_returns_integer_string(self):
        """original_value in mg/dL should format as integer."""
        row = _LabRow(
            original_value=174.0,
            original_unit="mg/dL",
            normalized_value_si=174.0,
            normalized_unit_si="mg/dL",
        )
        ci = _build_clinical_input(row)
        assert ci["normalized_value"] == "174"
        assert ci["normalized_unit"] == "mg/dL"


# ===========================================================================
# Bug 2 — Float artifact elimination
# ===========================================================================

class TestFloatArtifactElimination:
    """normalized_value in clinical_input must never contain raw float artifacts."""

    def test_no_float_artifact_in_normalized_value(self):
        """231.63330000000002 must never appear in normalized_value."""
        row = _LabRow(
            original_value=None,  # no original — fallback to SI
            normalized_value_si=231.63330000000002,
            normalized_unit_si="mg/dL",
        )
        ci = _build_clinical_input(row)
        assert "231.6333" not in ci["normalized_value"], (
            f"Float artifact leaked: {ci['normalized_value']!r}"
        )

    def test_si_fallback_formats_to_integer_for_mg_dl(self):
        """When original_value is absent, SI value should be formatted (no artifact)."""
        row = _LabRow(
            original_value=None,
            normalized_value_si=231.63330000000002,
            normalized_unit_si="mg/dL",
        )
        ci = _build_clinical_input(row)
        # mg/dL → integer formatting rule
        assert ci["normalized_value"] == "232"

    def test_canonical_value_si_rounded_to_4dp(self):
        """canonical_value_si must be rounded to 4 decimal places."""
        row = _LabRow(
            original_value=6.0,
            original_unit="mmol/L",
            normalized_value_si=231.63330000000002,
            normalized_unit_si="mg/dL",
        )
        ci = _build_clinical_input(row)
        assert isinstance(ci["canonical_value_si"], float)
        # Check no more than 4 decimal places
        str_val = str(ci["canonical_value_si"])
        parts = str_val.split(".")
        assert len(parts) < 2 or len(parts[1]) <= 4, (
            f"canonical_value_si has too many decimals: {ci['canonical_value_si']}"
        )

    def test_build_clinical_input_no_original_and_no_si(self):
        """When both original and SI are absent, normalized_value must be the missing sentinel."""
        row = _LabRow(
            original_value=None,
            normalized_value_si=None,
        )
        ci = _build_clinical_input(row)
        assert ci["normalized_value"] == "—"


# ===========================================================================
# Bug 3 — _clean_reference_range
# ===========================================================================

class TestCleanReferenceRange:
    """Reference range cleaning must strip embedded unit suffixes."""

    def test_matching_unit_stripped(self):
        assert _clean_reference_range("0.6–1.3 mg/dL", "mg/dL") == "0.6–1.3"

    def test_double_unit_stripped(self):
        assert _clean_reference_range("2.76–8.07 mg/dL mg/dL", "mg/dL") == "2.76–8.07"

    def test_mismatched_unit_suffix_stripped(self):
        """Even a different unit suffix after the range should be stripped."""
        assert _clean_reference_range("0.6–1.3 mg/dL pmol/L", "mg/dL") == "0.6–1.3"

    def test_no_unit_range_unchanged(self):
        assert _clean_reference_range("< 200", "mg/dL") == "< 200"

    def test_none_returns_empty_string(self):
        assert _clean_reference_range(None, "mg/dL") == ""

    def test_empty_string_returns_empty_string(self):
        assert _clean_reference_range("", "mg/dL") == ""

    def test_numeric_only_range_unchanged(self):
        assert _clean_reference_range("70–99", "mg/dL") == "70–99"

    def test_lt_symbol_no_unit_unchanged(self):
        assert _clean_reference_range("< 5.7", "%") == "< 5.7"

    def test_reference_range_stored_in_clinical_input_is_clean(self):
        """_build_clinical_input must propagate cleaned reference_range."""
        row = _LabRow(
            original_value=5.0,
            original_unit="mmol/L",
            normalized_value_si=90.0,
            normalized_unit_si="mg/dL",
            reference_range="3.9–5.6 mmol/L mmol/L",
        )
        ci = _build_clinical_input(row)
        assert ci["reference_range"] == "3.9–5.6"


# ===========================================================================
# Bug 4 — Status vocabulary parity
# ===========================================================================

class TestStatusVocabularyParity:
    """All backend status values must produce meaningful canonical_status in _build_clinical_input."""

    BACKEND_STATUS_VALUES = ["normal", "borderline", "high", "low", "critical"]

    def test_borderline_maps_to_borderline_high(self):
        row = _LabRow(status="borderline")
        ci = _build_clinical_input(row)
        assert ci["canonical_status"] == "borderline_high", (
            f"Expected 'borderline_high' but got {ci['canonical_status']!r}"
        )

    def test_critical_sets_doctor_review_required(self):
        row = _LabRow(status="critical")
        ci = _build_clinical_input(row)
        assert ci["doctor_review_required"] is True

    def test_normal_does_not_require_doctor(self):
        row = _LabRow(status="normal")
        ci = _build_clinical_input(row)
        assert ci["doctor_review_required"] is False

    def test_all_status_values_produce_known_canonical_status(self):
        known = {"normal", "borderline_high", "high", "low", "critical", "unknown"}
        for status in self.BACKEND_STATUS_VALUES:
            row = _LabRow(status=status)
            ci = _build_clinical_input(row)
            assert ci["canonical_status"] in known, (
                f"Status '{status}' produced unknown canonical_status '{ci['canonical_status']}'"
            )

    def test_all_backend_statuses_not_chura_ro(self):
        """None of the defined backend status values should fall through to 'Chưa rõ'.

        This is a parity check for the frontend statusLabel() function.
        All expected values are mapped — verified here at the canonical_status level.
        """
        # The frontend 'Chưa rõ' default is only for truly unknown statuses.
        # Mapping: normal→normal, borderline→borderline_high, high→high, low→low, critical→critical
        expected_canonical = {
            "normal": "normal",
            "borderline": "borderline_high",
            "high": "high",
            "low": "low",
            "critical": "critical",
        }
        for backend_status, expected in expected_canonical.items():
            row = _LabRow(status=backend_status)
            ci = _build_clinical_input(row)
            assert ci["canonical_status"] == expected, (
                f"Backend status '{backend_status}' → canonical '{ci['canonical_status']}', "
                f"expected '{expected}'"
            )


# ===========================================================================
# format_lab_value unit tests
# ===========================================================================

class TestFormatLabValue:
    """Verify number_format.format_lab_value rules that feed clinical_input."""

    def test_mg_dl_integer(self):
        assert format_lab_value(231.63330000000002, "mg/dL") == "232"

    def test_mg_dl_clean_int(self):
        assert format_lab_value(174.0, "mg/dL") == "174"

    def test_mmol_l_one_decimal(self):
        assert format_lab_value(6.0, "mmol/L") == "6.0"

    def test_mmol_l_rounds_one_decimal(self):
        assert format_lab_value(5.7321, "mmol/L") == "5.7"

    def test_none_returns_sentinel(self):
        assert format_lab_value(None, "mg/dL") == "—"

    def test_non_numeric_string_passthrough(self):
        assert format_lab_value("<5", "µmol/L") == "<5"


# ===========================================================================
# Two LabResults with different original_units get independent display units
# ===========================================================================

class TestMultiResultDisplayUnit:
    """Each result's display_unit is derived from its own original_unit."""

    def test_different_original_units_independent(self):
        row_a = _LabRow(
            canonical_name="glucose",
            original_value=6.0,
            original_unit="mmol/L",
            normalized_value_si=108.0,
            normalized_unit_si="mg/dL",
        )
        row_b = _LabRow(
            canonical_name="glucose",
            original_value=108.0,
            original_unit="mg/dL",
            normalized_value_si=108.0,
            normalized_unit_si="mg/dL",
        )
        ci_a = _build_clinical_input(row_a)
        ci_b = _build_clinical_input(row_b)
        assert ci_a["normalized_unit"] == "mmol/L"
        assert ci_b["normalized_unit"] == "mg/dL"
        assert ci_a["normalized_value"] == "6.0"
        assert ci_b["normalized_value"] == "108"


# ===========================================================================
# validate_explanation compatibility — normalized_value is now a string
# ===========================================================================

class TestValidateExplanationCompatibility:
    """validate_explanation must still work when normalized_value is a formatted string."""

    def test_validate_passes_with_string_normalized_value(self):
        clinical_input = {
            "canonical_status": "normal",
            "canonical_severity": "none",
            "doctor_review_required": False,
            "normalized_value": "6.0",
            "normalized_unit": "mmol/L",
            "biomarker_name": "glucose",
            "biomarker_display_name": "Đường huyết",
        }
        output = {
            "explanation": "Chỉ số đường huyết của bạn đang ở mức bình thường.",
            "why_it_matters": "Đây là chỉ số quan trọng.",
            "what_to_monitor": "Tiếp tục duy trì lối sống lành mạnh.",
            "next_step": "Xét nghiệm lại sau 6 tháng.",
        }
        result = validate_explanation(output, clinical_input)
        assert result["passed"] is True

    def test_deterministic_fallback_with_string_normalized_value(self):
        """get_deterministic_fallback must work with string normalized_value."""
        clinical_input = {
            "canonical_status": "high",
            "canonical_severity": "moderate",
            "doctor_review_required": False,
            "normalized_value": "232",
            "normalized_unit": "mg/dL",
            "biomarker_name": "glucose",
            "biomarker_display_name": "Đường huyết",
        }
        result = get_deterministic_fallback(clinical_input)
        assert "232" in result["explanation"]
        assert "mg/dL" in result["explanation"]
        assert result["source"] == "deterministic_fallback"

    def test_build_prompt_no_float_artifact(self):
        """build_prompt must not include raw float artifacts in the JSON string."""
        clinical_input = {
            "canonical_status": "borderline_high",
            "canonical_severity": "moderate",
            "doctor_review_required": False,
            "normalized_value": "232",   # formatted string — no artifact
            "normalized_unit": "mg/dL",
            "canonical_value_si": 231.6333,
            "canonical_unit_si": "mg/dL",
            "biomarker_name": "glucose",
            "biomarker_display_name": "Đường huyết",
            "reference_range": "70–99",
            "safety_flags": [],
        }
        prompt = build_prompt(clinical_input)
        # The ugly artifact must not appear in what Claude sees
        assert "231.6333000000" not in prompt
        # The formatted value should be present
        assert "232" in prompt


# ---------------------------------------------------------------------------
# Regression guard: _clean_reference_range must preserve qualitative strings
# (regression guard for b4f27b6 partial fix)
# ---------------------------------------------------------------------------

def test_clean_reference_range_preserves_qualitative():
    """Qualitative reference values must not be stripped by _clean_reference_range.

    Regression guard: prior regex (r'\\s+[A-Za-zµμ%/·]+.*$') was too greedy and
    would strip text from values like 'Âm tính', 'Bình thường', 'Negative'.
    """
    from app.api.v1.routes.lab import _clean_reference_range

    # Vietnamese qualitative — must be fully preserved
    assert _clean_reference_range("Âm tính", "U/L") == "Âm tính"
    assert _clean_reference_range("Bình thường", "U/L") == "Bình thường"
    # English qualitative — must be fully preserved
    assert _clean_reference_range("Negative", "mg/dL") == "Negative"
    # Numeric with unit — unit suffix must be stripped
    assert _clean_reference_range("0.6–1.3 mg/dL", "mg/dL") == "0.6–1.3"
    # Pure numeric — must be preserved
    assert _clean_reference_range("< 200", "mg/dL") == "< 200"
    assert _clean_reference_range("70–99", "mg/dL") == "70–99"
