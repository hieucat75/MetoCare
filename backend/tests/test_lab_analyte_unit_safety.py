"""P0: an analyte and a unit from different dimensions must never yield a severity.

Production showed one stored CBC row as `rbc 0.50 L/L` = "Nguy hiểm" on the labs
screen and "Rất thấp" on the health-metrics screen. Both were confident, they
contradicted each other, and both were wrong: the row was a hematocrit fraction
filed as a red cell count.

Three defects compounded, and each is pinned here:
  1. every VN hematocrit phrase CONTAINS the RBC alias "hồng cầu", and only
     "dung tích hồng cầu" was registered as hematocrit;
  2. unit compatibility was a DENYLIST (`spec.incompatible_units`), empty for
     both analytes, so `rbc + L/L` was accepted;
  3. `rbc.physiological_min` is 0.5, so the fraction 0.50 passed the magnitude
     check and then classified CRITICAL against `critical_low = 2.5`.
"""

from __future__ import annotations

import datetime as _dt

import pytest
from app.domain.analyte_units import (
    NEEDS_REVIEW_MESSAGE,
    UnitCompatibility,
    is_unsafe_pair,
    resolve_erythrocyte_analyte,
    to_canonical_unit,
    unit_compatibility,
)
from app.schemas.health import MetricOut
from app.schemas.lab import LabResultOut
from app.services.lab_parser import parse_lab_text

_NOW = _dt.datetime(2026, 6, 15, tzinfo=_dt.UTC)

# --------------------------------------------------------------------------- #
# Unit compatibility — fail closed
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("unit", ["10^12/L", "10¹²/L", "T/L", "x10^12/L", "10^6/uL"])
def test_rbc_accepts_only_count_per_volume_units(unit):
    assert unit_compatibility("rbc", unit) in (
        UnitCompatibility.CANONICAL,
        UnitCompatibility.CONVERTIBLE,
    )
    assert not is_unsafe_pair("rbc", unit)


@pytest.mark.parametrize("unit", ["L/L", "%", "ratio"])
def test_rbc_rejects_volume_fraction_units(unit):
    """The exact pair that produced a false "Nguy hiểm" in production."""
    assert unit_compatibility("rbc", unit) is UnitCompatibility.INCOMPATIBLE
    assert is_unsafe_pair("rbc", unit)


@pytest.mark.parametrize("unit", ["%", "L/L"])
def test_hematocrit_accepts_percent_and_fraction(unit):
    assert not is_unsafe_pair("hematocrit", unit)


@pytest.mark.parametrize("unit", ["10^12/L", "T/L"])
def test_hematocrit_rejects_count_units(unit):
    assert unit_compatibility("hematocrit", unit) is UnitCompatibility.INCOMPATIBLE
    assert is_unsafe_pair("hematocrit", unit)


@pytest.mark.parametrize("unit", ["mg/dL", "mmol/L", "banana", "", None])
def test_unknown_unit_is_refused_not_assumed_compatible(unit):
    """A denylist accepts anything unlisted. An allowlist must not."""
    assert unit_compatibility("rbc", unit) is UnitCompatibility.UNKNOWN
    assert is_unsafe_pair("rbc", unit)


def test_unguarded_analytes_are_untouched():
    """Scoped hotfix: analytes without an allowlist keep existing behaviour."""
    assert unit_compatibility("glucose", "mg/dL") is UnitCompatibility.NOT_GUARDED
    assert not is_unsafe_pair("glucose", "anything")


# --------------------------------------------------------------------------- #
# Conversion — relabelling without converting is the original bug
# --------------------------------------------------------------------------- #


def test_hematocrit_fraction_converts_to_percent():
    assert to_canonical_unit("hematocrit", 0.50, "L/L") == (50.0, "%")
    assert to_canonical_unit("hematocrit", 0.42, "L/L") == (42.0, "%")
    assert to_canonical_unit("hematocrit", 0.47, "L/L") == (47.0, "%")


def test_percent_is_already_canonical():
    assert to_canonical_unit("hematocrit", 50.0, "%") == (50.0, "%")


def test_conversion_refused_for_foreign_unit():
    assert to_canonical_unit("rbc", 0.50, "L/L") is None


def test_analyte_is_resolved_by_dimension_not_magnitude():
    assert resolve_erythrocyte_analyte("L/L") == "hematocrit"
    assert resolve_erythrocyte_analyte("%") == "hematocrit"
    assert resolve_erythrocyte_analyte("10^12/L") == "rbc"
    assert resolve_erythrocyte_analyte("T/L") == "rbc"
    assert resolve_erythrocyte_analyte("mg/dL") is None


# --------------------------------------------------------------------------- #
# Parser: Vietnamese label matrix
# --------------------------------------------------------------------------- #


def _parse_one(line: str):
    rows = parse_lab_text(line)
    return rows[0] if rows else None


@pytest.mark.parametrize(
    "label",
    [
        "Dung tích hồng cầu",
        "Thể tích khối hồng cầu",
        "Tỷ lệ thể tích hồng cầu",
        "Hematocrit",
        "HCT",
    ],
)
def test_vietnamese_hematocrit_labels_resolve_to_hematocrit(label):
    """Every one of these contains "hồng cầu"; none may become an RBC count."""
    row = _parse_one(f"{label}: 0.50 L/L")
    assert row is not None, label
    assert row.test_name == "hematocrit", f"{label} -> {row.test_name}"
    assert row.value == 50.0, f"{label} kept the fraction instead of converting"
    assert row.unit == "%"


def test_ambiguous_hong_cau_with_fraction_unit_becomes_hematocrit():
    row = _parse_one("Hồng cầu: 0.50 L/L")
    assert row is not None
    assert row.test_name == "hematocrit"
    assert row.value == 50.0
    assert row.unit == "%"


def test_ambiguous_hong_cau_with_count_unit_stays_rbc():
    for unit in ("10^12/L", "T/L"):
        row = _parse_one(f"Hồng cầu: 5.0 {unit}")
        assert row is not None, unit
        assert row.test_name == "rbc", unit
        assert row.value == 5.0


@pytest.mark.parametrize("unit", ["10^12/L", "T/L"])
def test_explicit_rbc_with_count_unit_is_accepted(unit):
    row = _parse_one(f"RBC: 5.0 {unit}")
    assert row is not None
    assert row.test_name == "rbc"
    assert row.value == 5.0


def test_explicit_rbc_with_fraction_unit_is_not_emitted():
    """Never relabel an explicit analyte — that guesses which half is wrong."""
    assert _parse_one("RBC: 0.50 L/L") is None


def test_explicit_hct_with_count_unit_is_not_emitted():
    assert _parse_one("HCT: 5.0 10^12/L") is None


def test_hct_percent_is_parsed_directly():
    row = _parse_one("HCT: 50 %")
    assert row is not None
    assert row.test_name == "hematocrit"
    assert row.value == 50.0


# --------------------------------------------------------------------------- #
# Read path: rows ALREADY in production, before any remediation
# --------------------------------------------------------------------------- #


def _lab_row(**kw) -> LabResultOut:
    base = dict(
        id="r1",
        patient_id="p1",
        document_id=None,
        test_name="Hồng cầu (RBC)",
        canonical_name="rbc",
        value=0.50,
        unit="L/L",
        reference_range="0.42-0.47 L/L",
        status="critical",
        test_date=None,
        verified_by_user=False,
        created_at=_NOW,
    )
    base.update(kw)
    return LabResultOut(**base)


def test_labs_screen_refuses_to_classify_the_stored_bad_row():
    """The row that displayed "Nguy hiểm". It must make no clinical claim."""
    out = _lab_row()
    assert out.status == "unknown"
    assert out.clinical_message == NEEDS_REVIEW_MESSAGE


def test_metrics_screen_refuses_to_classify_the_same_row():
    """The screen that displayed "Rất thấp" for that same record."""
    out = MetricOut(
        id="m1",
        patient_id="p1",
        metric_type="rbc",
        value=0.50,
        unit="L/L",
        status="low",
        measured_at=_NOW,
    )
    assert out.status == "unknown"
    assert out.is_critical is False
    assert out.clinical_message == NEEDS_REVIEW_MESSAGE


def test_both_screens_agree_on_the_same_stored_row():
    """The defining symptom was disagreement. Pin agreement, not just safety."""
    lab = _lab_row()
    metric = MetricOut(
        id="m1",
        patient_id="p1",
        metric_type="rbc",
        value=0.50,
        unit="L/L",
        status="critical",
        measured_at=_NOW,
    )
    assert lab.status == metric.status == "unknown"
    assert lab.clinical_message == metric.clinical_message == NEEDS_REVIEW_MESSAGE


def test_an_upstream_supplied_severity_is_still_overridden():
    """A severity handed in by a caller is exactly as unsupportable."""
    out = MetricOut(
        id="m1",
        patient_id="p1",
        metric_type="rbc",
        value=0.50,
        unit="L/L",
        status="critical",
        is_critical=True,
        clinical_message="Nguy hiểm",
        measured_at=_NOW,
    )
    assert out.is_critical is False
    assert out.clinical_message == NEEDS_REVIEW_MESSAGE


def test_a_healthy_rbc_row_is_unaffected():
    """The guard must not blunt real classification."""
    out = _lab_row(value=5.0, unit="10^12/L", reference_range="4.2-5.9", status="normal")
    assert out.status != "unknown"
    assert out.clinical_message != NEEDS_REVIEW_MESSAGE


def test_a_correct_hematocrit_row_is_unaffected():
    out = _lab_row(
        canonical_name="hematocrit",
        test_name="Hematocrit (HCT)",
        value=50.0,
        unit="%",
        reference_range="36-50",
        status="normal",
    )
    assert out.status != "unknown"
