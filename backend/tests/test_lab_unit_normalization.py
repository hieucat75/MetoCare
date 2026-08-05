"""Analyte-aware unit normalization — the registry itself.

Two failures motivated it, and they were opposite failures of the same missing
abstraction:

  - the MDI document path called ``is_unit_convertible``, which accepts only the
    canonical or SI unit, so it REFUSED every CBC line printed the way Vietnamese
    labs print them — platelet ``20 G/L``, WBC ``0.8 G/L``, haemoglobin
    ``70 g/L``. A patient could not confirm a critical thrombocytopenia.
  - ``/lab-uploads`` and manual entry had no guard at all.
    ``normalize_value_to_si`` returns the value UNCHANGED under its ORIGINAL unit
    when it knows no conversion, and ``classify_value`` ignores the unit — so a
    perfectly normal haemoglobin of ``140 g/L`` was stored as ``140`` and
    classified against the ``12.0–17.5 g/dL`` range as **critical**.

So one printed report produced a refusal on one path and a fabricated critical on
another, and the refusal's own message ("vui lòng sửa đơn vị") invited the patient
to retype ``g/L`` as ``g/dL`` without touching the number — landing on the same
wrong value.

The most dangerous detail is a single character's case: ``G/L`` (giga per litre)
is a CELL COUNT; ``g/L`` (grams per litre) is a MASS CONCENTRATION. Every other
normalizer in this codebase lower-cases the unit before comparing, which silently
merges them.

Cross-path parity is asserted separately, in test_lab_unit_parity.py.
"""

from __future__ import annotations

import pytest
from app.domain.unit_registry import (
    CONVERSION_RULE_VERSION,
    accepted_units,
    convert_to_canonical,
    normalize_unit_token,
)
from app.services.lab import normalize_and_classify

# ── 1. Notation: every variant OCR actually emits ───────────────────────────


@pytest.mark.parametrize(
    "printed,expected",
    [
        ("G/L", "10^9/l"), ("G/l", "10^9/l"), (" G/L ", "10^9/l"),
        ("10^9/L", "10^9/l"), ("10⁹/L", "10^9/l"), ("10^9/l", "10^9/l"),
        ("x10^9/L", "10^9/l"), ("×10^9/L", "10^9/l"), ("10*9/L", "10^9/l"),
        ("T/L", "10^12/l"), ("10^12/L", "10^12/l"), ("10¹²/L", "10^12/l"),
        ("g/L", "g/l"), ("g/dL", "g/dl"), ("g / L", "g/l"), ("G / L", "10^9/l"),
    ],
)
def test_notation_variants_normalize(printed, expected):
    assert normalize_unit_token(printed) == expected


def test_case_distinguishes_a_cell_count_from_a_mass_concentration():
    """The single most dangerous detail here. `G/L` and `g/L` differ by one
    character's case and are not interconvertible; lower-casing merges them."""
    assert normalize_unit_token("G/L") != normalize_unit_token("g/L")
    assert normalize_unit_token("G/L") == normalize_unit_token("10^9/L")


@pytest.mark.parametrize("empty", [None, "", "   "])
def test_an_empty_unit_has_no_token(empty):
    assert normalize_unit_token(empty) == ""


# ── 2. The minimum CBC conversions, by value ────────────────────────────────


@pytest.mark.parametrize(
    "analyte,value,unit,expected,expected_unit",
    [
        # Haemoglobin: 1 g/dL = 10 g/L.
        ("hemoglobin", 70.0, "g/L", 7.0, "g/dL"),
        ("hemoglobin", 140.0, "g/L", 14.0, "g/dL"),
        ("hemoglobin", 14.0, "g/dL", 14.0, "g/dL"),
        # Cell counts: G/L IS 10^9/L, T/L IS 10^12/L — notation, not scaling.
        ("wbc", 0.8, "G/L", 0.8, "10^9/L"),
        ("wbc", 7.2, "10^9/L", 7.2, "10^9/L"),
        ("wbc", 7.2, "x10^9/L", 7.2, "10^9/L"),
        ("platelet", 20.0, "G/L", 20.0, "10^9/L"),
        ("platelet", 230.0, "10⁹/L", 230.0, "10^9/L"),
        ("rbc", 4.5, "T/L", 4.5, "10^12/L"),
        ("rbc", 4.5, "10^12/L", 4.5, "10^12/L"),
    ],
)
def test_cbc_conversions(analyte, value, unit, expected, expected_unit):
    r = convert_to_canonical(analyte, value, unit)
    assert r.ok, r.reason
    assert r.normalized_value == pytest.approx(expected)
    assert r.canonical_unit == expected_unit
    assert r.rule_version == CONVERSION_RULE_VERSION


def test_conversion_is_exactly_the_liter_deciliter_relation():
    """Not an approximation: a dL is one tenth of a litre, so the factor is 0.1."""
    r = convert_to_canonical("hemoglobin", 100.0, "g/L")
    assert r.factor == pytest.approx(0.1)
    assert r.normalized_value == pytest.approx(10.0)


# ── 3. Incompatible analyte/unit pairs are REFUSED ──────────────────────────


def test_a_count_unit_is_refused_for_hemoglobin():
    """"Do not apply count-unit conversions to hemoglobin." G/L for Hb is a
    plausible-looking OCR outcome and a wrong-dimension value."""
    r = convert_to_canonical("hemoglobin", 140.0, "G/L")
    assert not r.ok
    assert r.reason == "dimension_mismatch"
    assert r.normalized_value is None


@pytest.mark.parametrize("analyte", ["wbc", "platelet", "rbc"])
def test_a_mass_unit_is_refused_for_a_cell_count(analyte):
    """"Do not apply mass-concentration conversions to cell counts.\""""
    r = convert_to_canonical(analyte, 7.2, "g/L")
    assert not r.ok
    assert r.reason == "dimension_mismatch"
    assert r.normalized_value is None


def test_a_right_dimension_wrong_magnitude_unit_is_refused():
    """RBC printed in G/L is 1000x low. Neither converted nor accepted."""
    r = convert_to_canonical("rbc", 4.5, "G/L")
    assert not r.ok
    assert r.normalized_value is None


@pytest.mark.parametrize("unit", ["", "   ", "banana", "%%%", "mmHg"])
def test_unknown_or_missing_units_are_refused(unit):
    r = convert_to_canonical("hemoglobin", 14.0, unit)
    assert not r.ok
    assert r.normalized_value is None


def test_an_impossible_converted_value_is_refused():
    """Creatinine 88 mg/dL is beyond any survivable concentration — almost
    certainly a mislabelled 88 µmol/L. Bounds are checked in the CANONICAL
    domain, the only domain they are expressed in."""
    r = convert_to_canonical("creatinine", 88.0, "mg/dL")
    assert not r.ok
    assert r.reason == "impossible_converted_value"


def test_a_non_blood_specimen_is_refused():
    r = convert_to_canonical("creatinine", 120.0, "mg/dL", label="Creatinin niệu")
    assert not r.ok
    assert r.reason == "specimen_mismatch"


def test_ambiguous_analyte_is_refused():
    assert not convert_to_canonical(None, 5.0, "mg/dL").ok


@pytest.mark.parametrize("bad", [float("inf"), float("nan")])
def test_non_finite_values_are_refused(bad):
    assert not convert_to_canonical("hemoglobin", bad, "g/dL").ok


def test_a_refusal_names_the_accepted_units():
    """A message that only says "fix the unit" is how g/L gets retyped as g/dL
    with the number untouched."""
    r = convert_to_canonical("hemoglobin", 14.0, "banana")
    assert set(r.detail.get("accepted", [])) >= {"g/dl", "g/l"}
    assert "g/dl" in accepted_units("hemoglobin")


# ── 4. Classification happens ONLY after a successful conversion ────────────


def test_a_normal_hemoglobin_in_g_per_litre_is_not_called_critical():
    """The regression. 140 g/L is a NORMAL haemoglobin; it was classified against
    the g/dL range and came back critical — a fabricated critical on a healthy
    patient."""
    r = normalize_and_classify("hemoglobin", 140.0, "g/L")
    assert r["normalized_value_si"] == pytest.approx(14.0)
    assert r["normalized_unit_si"] == "g/dL"
    assert r["status"] == "normal"


def test_a_low_hemoglobin_stays_low_after_conversion():
    """The opposite direction must hold too: normalization must not rescue a
    genuinely dangerous value into looking fine."""
    r = normalize_and_classify("hemoglobin", 70.0, "g/L")
    assert r["normalized_value_si"] == pytest.approx(7.0)
    assert r["status"] in ("low", "critical")


def test_thrombocytopenia_stays_low_after_g_per_litre_normalization():
    r = normalize_and_classify("platelet", 20.0, "G/L")
    assert r["normalized_value_si"] == pytest.approx(20.0)
    assert r["status"] in ("low", "critical")


def test_severe_neutropenia_remains_abnormal():
    r = normalize_and_classify("wbc", 0.8, "G/L")
    assert r["normalized_value_si"] == pytest.approx(0.8)
    assert r["status"] in ("low", "critical")


def test_a_failed_conversion_yields_no_status_and_no_value():
    """"No fallback to generic range when conversion failed." A refusal must not
    leave anything a downstream reader could interpret."""
    r = normalize_and_classify("hemoglobin", 140.0, "G/L")
    assert r["conversion_ok"] is False
    assert r["status"] is None
    assert r["normalized_value_si"] is None
    assert r["clinical_message"] is None


def test_no_result_becomes_normal_merely_because_the_unit_was_relabelled():
    """Relabelling without converting is the dangerous edit the old refusal
    message invited. Whatever happens, it must not read as normal."""
    r = normalize_and_classify("hemoglobin", 70.0, "g/dL")  # 70 "g/dL" — impossible
    assert r.get("status") != "normal"


# ── 5. Provenance ───────────────────────────────────────────────────────────


def test_a_successful_conversion_records_how_it_was_derived():
    p = convert_to_canonical("hemoglobin", 140.0, "g/L").provenance()
    assert p["original_value"] == 140.0
    assert p["original_unit"] == "g/L"
    assert p["normalized_value"] == pytest.approx(14.0)
    assert p["canonical_unit"] == "g/dL"
    assert p["factor"] == pytest.approx(0.1)
    assert p["rule_version"] == CONVERSION_RULE_VERSION


def test_original_value_and_unit_are_preserved_verbatim():
    r = convert_to_canonical("platelet", 20.0, "G/L")
    assert (r.original_value, r.original_unit) == (20.0, "G/L")
    assert r.normalized_value == 20.0
    assert r.canonical_unit == "10^9/L"


def test_an_assumed_unit_is_recorded_as_assumed():
    """Manual entry may omit the unit because the form is labelled with it. That
    is a stated contract, not a guess — but it must never be indistinguishable
    from a unit that was actually read."""
    read = convert_to_canonical("fasting_glucose", 95, "mg/dL")
    assumed = convert_to_canonical(
        "fasting_glucose", 95, "", assume_canonical_when_missing=True
    )
    assert read.ok and assumed.ok
    assert assumed.detail.get("unit_assumed_canonical") is True
    assert read.detail.get("unit_assumed_canonical") is None


def test_a_document_path_never_assumes_a_missing_unit():
    """On a document path a missing unit means the printed unit was not READ, so
    the value could be in any domain."""
    assert not convert_to_canonical("fasting_glucose", 95, "").ok
