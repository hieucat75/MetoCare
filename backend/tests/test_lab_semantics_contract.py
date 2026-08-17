"""Unified LabResult contract — regression tests for the shared resolver.

Locks the specific defect class #153/#154 were filed over: one stored value,
two screens (LabResultOut for the labs screen, MetricOut for the metrics
screen), two independently-computed severities. Both schemas now delegate to
`app.domain.lab_semantics.resolve_lab_semantics` — these tests assert the two
outputs AGREE on canonical analyte, display name, normalized value/unit,
reference range + its source, status, severity, and interpretation state for
the same underlying record.
"""

from __future__ import annotations

import datetime as _dt

import pytest
from app.domain.lab_semantics import ReferenceSource, resolve_lab_semantics
from app.schemas.health import MetricOut
from app.schemas.lab import LabResultOut

_NOW = _dt.datetime(2026, 1, 1, tzinfo=_dt.UTC)


def _lab_result_out(**overrides) -> LabResultOut:
    base = dict(
        id="lr1",
        patient_id="p1",
        document_id=None,
        test_name=overrides.pop("test_name", "Hematocrit"),
        canonical_name="hematocrit",
        value=50.0,
        unit="%",
        reference_range=None,
        status=None,
        test_date=None,
        verified_by_user=True,
        created_at=_NOW,
    )
    base.update(overrides)
    return LabResultOut(**base)


def _metric_out(**overrides) -> MetricOut:
    base = dict(
        id="m1",
        metric_type="hematocrit",
        value=50.0,
        unit="%",
        measured_at=_NOW,
        status=None,
    )
    base.update(overrides)
    return MetricOut(**base)


# --------------------------------------------------------------------------- #
# Source-reference-range propagation across schemas (B2 follow-up) — the same
# confirmed result must resolve identical reference_display/reference_source
# whether read via LabResultOut (original_reference_range) or MetricOut
# (source_reference_text, the field HealthMetric carries the printed range in
# after promotion). See test_lab_metric_promotion.py for the end-to-end
# promotion-path regression; these test the schemas' resolver wiring directly.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "canonical,value,unit,printed_range",
    [
        ("hematocrit", 50.0, "%", "42–47"),
        ("hemoglobin", 14.0, "g/dL", "13–17"),
    ],
)
def test_lab_result_and_metric_agree_on_source_report_range(
    canonical, value, unit, printed_range
):
    lab = _lab_result_out(
        canonical_name=canonical,
        value=value,
        unit=unit,
        original_reference_range=printed_range,
        original_unit=unit,
    )
    metric = _metric_out(
        metric_type=canonical,
        value=value,
        unit=unit,
        source_reference_text=printed_range,
        original_unit=unit,
    )

    assert lab.reference_source == metric.reference_source == "source_report"
    assert lab.reference_display == metric.reference_display == printed_range


@pytest.mark.parametrize(
    "canonical,value,unit",
    [("rbc", 4.5, "10^12/L"), ("hemoglobin", 14.0, "g/dL")],
)
def test_lab_result_and_metric_agree_on_canonical_fallback_without_source_range(
    canonical, value, unit
):
    """No printed range on either side — both must land on CANONICAL_FALLBACK,
    not just avoid disagreeing (catches a bug where both silently claim
    SOURCE_REPORT with no actual source text)."""
    lab = _lab_result_out(canonical_name=canonical, value=value, unit=unit)
    metric = _metric_out(metric_type=canonical, value=value, unit=unit)

    assert lab.reference_source == metric.reference_source == "canonical_fallback"


def test_lab_result_and_metric_agree_on_needs_review_even_with_a_source_range():
    """A source range being present must never force SOURCE_REPORT/a confident
    status for an unsafe analyte/unit pair — the resolver's guard runs first
    on both schemas identically."""
    lab = _lab_result_out(
        canonical_name="rbc",
        value=0.50,
        unit="L/L",
        original_reference_range="3.5–5.5",
    )
    metric = _metric_out(
        metric_type="rbc",
        value=0.50,
        unit="L/L",
        source_reference_text="3.5–5.5",
    )

    assert lab.status == metric.status == "unknown"
    assert lab.interpretation_state == metric.interpretation_state == "needs_review"
    assert lab.needs_review is metric.needs_review is True


# --------------------------------------------------------------------------- #
# Both-screen consistency — section 9 of the brief's matrix
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "canonical,value,unit",
    [
        ("hematocrit", 50.0, "%"),
        ("rbc", 4.5, "10^12/L"),
        ("hemoglobin", 14.0, "g/dL"),
    ],
)
def test_lab_result_and_metric_agree_for_confirmed_values(canonical, value, unit):
    lab = _lab_result_out(canonical_name=canonical, value=value, unit=unit)
    metric = _metric_out(metric_type=canonical, value=value, unit=unit)

    assert lab.status == metric.status, (lab.status, metric.status)
    assert lab.severity == metric.severity
    assert lab.display_name == metric.display_name
    assert lab.reference_low == metric.reference_low
    assert lab.reference_high == metric.reference_high
    assert lab.reference_source == metric.reference_source
    assert lab.interpretation_state == metric.interpretation_state == "confirmed"
    assert lab.needs_review is metric.needs_review is False


def test_lab_result_and_metric_agree_on_needs_review_for_incompatible_pair():
    """The exact #153/#154 incident value: rbc stored with a hematocrit unit."""
    lab = _lab_result_out(canonical_name="rbc", value=0.50, unit="L/L")
    metric = _metric_out(metric_type="rbc", value=0.50, unit="L/L")

    assert lab.status == metric.status == "unknown"
    assert lab.severity == metric.severity == "unknown"
    assert lab.interpretation_state == metric.interpretation_state == "needs_review"
    assert lab.needs_review is metric.needs_review is True
    # Neither screen may render a confident severity for this pair.
    assert lab.status not in ("critical", "high", "low")
    assert metric.is_critical is False


def test_needs_review_renders_the_same_everywhere_for_an_unrecognised_unit():
    lab = _lab_result_out(canonical_name="hemoglobin", value=140.0, unit="mmol/L")
    metric = _metric_out(metric_type="hemoglobin", value=140.0, unit="mmol/L")

    assert lab.status == metric.status == "unknown"
    assert lab.interpretation_state == metric.interpretation_state == "needs_review"


# --------------------------------------------------------------------------- #
# Reference-range precedence — section 10 of the brief
# --------------------------------------------------------------------------- #


def test_source_report_range_takes_precedence_over_canonical_fallback():
    """HCT: a valid source-printed range (42-47%) must be used verbatim, and
    reference_source must say so — never silently substituted by the
    registry's own [5, 75] fallback."""
    semantics = resolve_lab_semantics(
        "hematocrit", 50.0, "%", printed_reference_text="42–47"
    )
    assert semantics is not None
    assert semantics.reference_display == "42–47"
    assert semantics.reference_source == ReferenceSource.SOURCE_REPORT.value
    # Status is still computed from the canonical registry, never the printed
    # range — 50% is within hematocrit's own bounds regardless of what the
    # printed range says.
    assert semantics.status == "normal"


def test_no_source_range_falls_back_to_canonical_registry():
    semantics = resolve_lab_semantics("hematocrit", 50.0, "%")
    assert semantics is not None
    assert semantics.reference_source == ReferenceSource.CANONICAL_FALLBACK.value
    assert semantics.reference_low is not None and semantics.reference_high is not None


def test_display_range_choice_never_changes_classification():
    """The patient may choose which range to display (source vs canonical) —
    per product decision, that choice must never change status/severity."""
    with_source = resolve_lab_semantics(
        "hematocrit", 20.0, "%", printed_reference_text="42–47"
    )
    without_source = resolve_lab_semantics("hematocrit", 20.0, "%")
    assert with_source is not None and without_source is not None
    assert with_source.status == without_source.status
    assert with_source.severity == without_source.severity
    # Only the DISPLAY fields differ.
    assert with_source.reference_display != without_source.reference_display


# --------------------------------------------------------------------------- #
# Clinical state matrix — section 11 of the brief
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "value,expected_status",
    [
        (14.0, "normal"),
        (10.0, "low"),
        (19.0, "high"),
        (5.0, "critical"),
    ],
)
def test_hemoglobin_state_matrix_is_consistent_across_schemas(value, expected_status):
    lab = _lab_result_out(canonical_name="hemoglobin", value=value, unit="g/dL")
    metric = _metric_out(metric_type="hemoglobin", value=value, unit="g/dL")
    assert lab.status == metric.status == expected_status
    assert lab.severity == metric.severity == expected_status


def test_unknown_state_never_carries_a_confident_severity():
    lab = _lab_result_out(canonical_name="rbc", value=0.50, unit="L/L")
    metric = _metric_out(metric_type="rbc", value=0.50, unit="L/L")
    for out in (lab, metric):
        assert out.status == "unknown"
        assert out.severity == "unknown"


def test_display_name_is_centralized_not_reinvented_per_schema():
    lab = _lab_result_out(canonical_name="hemoglobin", value=14.0, unit="g/dL")
    metric = _metric_out(metric_type="hemoglobin", value=14.0, unit="g/dL")
    assert lab.display_name == metric.display_name
    assert lab.display_name  # non-empty


# --------------------------------------------------------------------------- #
# General (non-CBC-guarded) analyte path — a value with an unrecognised or
# missing unit must fail closed exactly like the guarded path does; it must
# never be silently classified against the wrong-dimension thresholds.
# --------------------------------------------------------------------------- #


def test_general_path_fails_closed_on_an_unrecognised_unit():
    """total_cholesterol with no unit at all must not be silently classified
    against mg/dL thresholds — is_unit_convertible must gate this."""
    semantics = resolve_lab_semantics("total_cholesterol", 5.2, None)
    assert semantics is not None
    assert semantics.status == "unknown"
    assert semantics.interpretation_state == "needs_review"
    assert semantics.needs_review is True


def test_general_path_classifies_normally_with_a_recognised_unit():
    semantics = resolve_lab_semantics("total_cholesterol", 180.0, "mg/dL")
    assert semantics is not None
    assert semantics.status != "unknown"
    assert semantics.interpretation_state == "confirmed"


def test_general_path_ignores_a_mismatched_si_pair():
    """normalized_value_si/normalized_unit_si must be used only when BOTH are
    present together — a value written by one path paired with a unit left
    over from a different one must not be trusted."""
    # value=90 mg/dL glucose (normal, unambiguous); a stray/legacy
    # normalized_value_si of 200 (would read "high") with NO matching
    # normalized_unit_si must be ignored in favour of the raw (value, unit)
    # pair, not paired with a unit it was never actually converted to.
    semantics = resolve_lab_semantics(
        "fasting_glucose",
        90.0,
        "mg/dL",
        normalized_value_si=200.0,
        normalized_unit_si=None,
    )
    assert semantics is not None
    assert semantics.status == "normal", semantics.status


def test_general_path_uses_the_si_pair_only_when_both_fields_present():
    semantics = resolve_lab_semantics(
        "fasting_glucose",
        None,
        None,
        normalized_value_si=90.0,
        normalized_unit_si="mg/dL",
    )
    assert semantics is not None
    assert semantics.status == "normal"


def test_guarded_reference_range_converts_when_printed_in_a_different_unit():
    """HCT printed range 0.42-0.47 L/L must convert to 42-47% for display —
    never sit unconverted next to the canonical-unit value, mirroring #155's
    fix at the extraction layer."""
    semantics = resolve_lab_semantics(
        "hematocrit",
        50.0,
        "%",
        printed_reference_text="0.42–0.47",
        printed_reference_unit="L/L",
    )
    assert semantics is not None
    assert semantics.reference_display == "42–47"


def test_lab_result_out_fails_closed_when_resolution_raises(monkeypatch):
    """An exception inside resolution must never leave a stale upstream
    status/severity in place — that is the #153/#154 hazard verbatim."""
    import app.domain.lab_semantics as lab_semantics_module

    def _boom(*a, **k):
        raise RuntimeError("simulated resolver failure")

    monkeypatch.setattr(lab_semantics_module, "resolve_lab_semantics", _boom)
    lab = _lab_result_out(
        canonical_name="rbc", value=0.50, unit="L/L", status="critical"
    )
    assert lab.status == "unknown"
    assert lab.needs_review is True
    assert lab.reference_range is None


def test_metric_out_fails_closed_when_resolution_raises(monkeypatch):
    import app.domain.lab_semantics as lab_semantics_module

    def _boom(*a, **k):
        raise RuntimeError("simulated resolver failure")

    monkeypatch.setattr(lab_semantics_module, "resolve_lab_semantics", _boom)
    metric = _metric_out(
        metric_type="rbc", value=0.50, unit="L/L", status="critical", is_critical=True
    )
    assert metric.status == "unknown"
    assert metric.is_critical is False
    assert metric.needs_review is True
