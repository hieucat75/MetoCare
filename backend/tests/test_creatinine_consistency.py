"""Tests for creatinine unit consistency — P0 clinical safety.

Validates:
- Correct normalization of µmol/L → mg/dL (si_factor=0.011312, i.e. 1/88.42)
- pmol/L and other incompatible units are blocked (overall=0.0, needs_verification)
- Plausibility detection catches creatinine in mg/dL that looks like µmol/L value
- _clean_reference_range preserves qualitative strings (regression guard)
- LabResultOut schema exposes data_quality_flag
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Helpers / imports
# ---------------------------------------------------------------------------
from app.api.v1.routes.lab import _clean_reference_range
from app.domain.lab_interpreter import _ALIAS_INDEX, classify_value
from app.domain.lab_normalization import normalize_value_to_si
from app.services.biomarker_specs import check_plausibility

# ---------------------------------------------------------------------------
# Test 1: creatinine 88 µmol/L normalises to ≈0.995 mg/dL → normal
# ---------------------------------------------------------------------------

def test_creatinine_88_umol_is_normal():
    """88 µmol/L × 0.011312 = 0.9954 mg/dL — within [0.6, 1.3] → normal."""
    value, unit = normalize_value_to_si(88.0, "µmol/L", "creatinine")
    assert unit == "mg/dL", f"Expected mg/dL, got {unit}"
    assert abs(value - (88.0 * 0.011312)) < 0.001, f"Unexpected value {value}"
    status = classify_value("creatinine", value)
    assert status is not None
    assert status.value == "normal", f"Expected normal, got {status.value}"


# ---------------------------------------------------------------------------
# Test 2: creatinine 0.99 mg/dL → normal
# ---------------------------------------------------------------------------

def test_creatinine_099_mgdl_is_normal():
    """0.99 mg/dL is within [0.6, 1.3] → normal."""
    status = classify_value("creatinine", 0.99)
    assert status is not None
    assert status.value == "normal", f"Expected normal, got {status.value}"


# ---------------------------------------------------------------------------
# Test 3: creatinine 88 mg/dL → critical (impossibly high in mg/dL units)
# ---------------------------------------------------------------------------

def test_creatinine_88_mgdl_is_critical():
    """88 mg/dL far exceeds critical_high=4.0 → critical."""
    status = classify_value("creatinine", 88.0)
    assert status is not None
    assert status.value == "critical", f"Expected critical, got {status.value}"


# ---------------------------------------------------------------------------
# Test 4: creatinine + pmol/L → incompatible, overall=0.0, suspicious=True
# ---------------------------------------------------------------------------

def test_creatinine_pmol_l_flagged_as_incompatible():
    """pmol/L is clinically impossible for creatinine — must be flagged overall=0.0."""
    result = check_plausibility("creatinine", 88.0, "pmol/L")
    assert result["plausible"] is False, "pmol/L must NOT be plausible for creatinine"
    assert result["suspicious"] is True, "pmol/L must be flagged as suspicious"
    assert result.get("overall", 1.0) == 0.0, f"overall must be 0.0, got {result.get('overall')}"


# ---------------------------------------------------------------------------
# Test 5: creatinine + µmol/L → plausible=True
# ---------------------------------------------------------------------------

def test_creatinine_umol_l_accepted():
    """µmol/L is the canonical SI unit for creatinine — must be accepted."""
    result = check_plausibility("creatinine", 88.0, "µmol/L")
    assert result["plausible"] is True, f"µmol/L should be plausible: {result}"


# ---------------------------------------------------------------------------
# Test 6: encoding variants of µmol/L all convert correctly
# ---------------------------------------------------------------------------

def test_creatinine_umol_encoding_variants():
    """umol/L and μmol/L (unicode variants) must convert to mg/dL correctly."""
    for variant in ("umol/L", "μmol/L"):
        value, unit = normalize_value_to_si(88.0, variant, "creatinine")
        assert unit == "mg/dL", f"Variant {variant!r} did not convert: got {unit}"
        assert abs(value - (88.0 * 0.011312)) < 0.001, (
            f"Variant {variant!r} gave wrong value {value}"
        )


# ---------------------------------------------------------------------------
# Test 7: plausibility of 88 mg/dL → suspicious (value fits µmol/L better)
# ---------------------------------------------------------------------------

def test_creatinine_plausibility_88_mgdl():
    """88 mg/dL exceeds physiological_max for mg/dL but fits µmol/L → suspicious."""
    result = check_plausibility("creatinine", 88.0, "mg/dL")
    # value 88 is above si_max_plausible=30 for mg/dL
    # and within alt_max_plausible=2650 for µmol/L → suspicious
    assert result["plausible"] is False, f"88 mg/dL should not be plausible: {result}"
    assert result["suspicious"] is True, f"88 mg/dL should be suspicious: {result}"


# ---------------------------------------------------------------------------
# Test 8: BiomarkerSpec.incompatible_units includes "pmol/L"
# ---------------------------------------------------------------------------

def test_creatinine_incompatible_units_list():
    """BiomarkerSpec for creatinine must list pmol/L as incompatible."""
    spec = _ALIAS_INDEX.get("creatinine")
    assert spec is not None, "creatinine spec not found in _ALIAS_INDEX"
    assert "pmol/L" in spec.incompatible_units, (
        f"pmol/L not in incompatible_units: {spec.incompatible_units}"
    )


# ---------------------------------------------------------------------------
# Test 9: _clean_reference_range preserves "Âm tính"
# ---------------------------------------------------------------------------

def test_clean_ref_range_preserves_am_tinh():
    """Qualitative result 'Âm tính' must not be stripped."""
    result = _clean_reference_range("Âm tính", "mg/dL")
    assert result == "Âm tính", f"Expected 'Âm tính', got {result!r}"


# ---------------------------------------------------------------------------
# Test 10: _clean_reference_range preserves "Bình thường"
# ---------------------------------------------------------------------------

def test_clean_ref_range_preserves_binh_thuong():
    """Qualitative result 'Bình thường' must not be stripped."""
    result = _clean_reference_range("Bình thường", "mg/dL")
    assert result == "Bình thường", f"Expected 'Bình thường', got {result!r}"


# ---------------------------------------------------------------------------
# Test 11: _clean_reference_range preserves "Negative"
# ---------------------------------------------------------------------------

def test_clean_ref_range_preserves_negative():
    """Qualitative result 'Negative' must not be stripped."""
    result = _clean_reference_range("Negative", "mg/dL")
    assert result == "Negative", f"Expected 'Negative', got {result!r}"


# ---------------------------------------------------------------------------
# Test 12: _clean_reference_range strips unit suffix from numeric range
# ---------------------------------------------------------------------------

def test_clean_ref_range_strips_unit():
    """'0.6–1.3 mg/dL' → '0.6–1.3'."""
    result = _clean_reference_range("0.6–1.3 mg/dL", "mg/dL")
    assert result == "0.6–1.3", f"Expected '0.6–1.3', got {result!r}"


# ---------------------------------------------------------------------------
# Test 13: _clean_reference_range strips double unit suffix
# ---------------------------------------------------------------------------

def test_clean_ref_range_strips_double_unit():
    """'53–115 µmol/L µmol/L' → '53–115'."""
    result = _clean_reference_range("53–115 µmol/L µmol/L", "µmol/L")
    assert result == "53–115", f"Expected '53–115', got {result!r}"


# ---------------------------------------------------------------------------
# Test 14: _clean_reference_range preserves "< 200"
# ---------------------------------------------------------------------------

def test_clean_ref_range_preserves_lt_200():
    """'< 200' has no unit slash token — must be preserved."""
    result = _clean_reference_range("< 200", "mg/dL")
    assert result == "< 200", f"Expected '< 200', got {result!r}"


# ---------------------------------------------------------------------------
# Test 15: LabResultOut schema exposes data_quality_flag field
# ---------------------------------------------------------------------------

def test_data_quality_flag_in_schema():
    """LabResultOut must expose data_quality_flag as an optional field."""
    from app.schemas.lab import LabResultOut
    fields = LabResultOut.model_fields
    assert "data_quality_flag" in fields, (
        f"data_quality_flag missing from LabResultOut fields: {list(fields.keys())}"
    )
    field = fields["data_quality_flag"]
    # Should be Optional[str] — default None
    assert field.default is None or field.is_required() is False, (
        "data_quality_flag should be optional (default None)"
    )
