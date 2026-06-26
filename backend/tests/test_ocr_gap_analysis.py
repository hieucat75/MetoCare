"""Unit tests for ocr_gap_analysis.compute_gap()."""
from __future__ import annotations

import pytest

from app.domain.ocr_gap_analysis import compute_gap


def _row(name: str, value: float | None = 5.0, unit: str = "g/dL", metric: str | None = None) -> dict:
    return {
        "test_name": name,
        "original_test_name": name,
        "mapped_metric_type": metric or name,
        "display_name_vi": name,
        "value": value,
        "unit": unit,
    }


class TestEmptyInputs:
    def test_both_empty_returns_zero_report(self):
        gap = compute_gap([], [])
        assert gap.overall_accuracy == 0.0
        assert gap.total_extracted_rows == 0

    def test_empty_extracted_all_added(self):
        gap = compute_gap([], [_row("glucose")])
        assert gap.missing_rows == 1
        assert gap.matched_rows == 0

    def test_empty_corrected_all_deleted(self):
        gap = compute_gap([_row("glucose")], [])
        assert gap.false_positive_rows == 1
        assert gap.matched_rows == 0


class TestPerfectMatch:
    def test_identical_rows_full_accuracy(self):
        rows = [_row("glucose", 5.0), _row("urea", 3.2)]
        gap = compute_gap(rows, rows)
        assert gap.row_accuracy == 1.0
        assert gap.value_accuracy == 1.0
        assert gap.unit_accuracy == 1.0
        assert gap.editing_rate == 0.0
        assert gap.value_mismatches == 0

    def test_value_within_tolerance_not_flagged(self):
        extracted = [_row("glucose", 5.000)]
        corrected = [_row("glucose", 5.003)]
        gap = compute_gap(extracted, corrected)
        assert gap.value_mismatches == 0

    def test_value_just_outside_tolerance_flagged(self):
        extracted = [_row("glucose", 5.000)]
        corrected = [_row("glucose", 5.100)]  # 2% relative — exceeds both tolerances
        gap = compute_gap(extracted, corrected)
        assert gap.value_mismatches == 1


class TestValueCorrections:
    def test_single_value_correction_detected(self):
        extracted = [_row("glucose", 4.5)]
        corrected = [_row("glucose", 6.0)]
        gap = compute_gap(extracted, corrected)
        assert gap.value_mismatches == 1
        assert gap.editing_rate == 1.0

    def test_partial_value_correction(self):
        extracted = [_row("a", 1.0), _row("b", 2.0), _row("c", 3.0)]
        corrected = [_row("a", 1.0), _row("b", 9.9), _row("c", 3.0)]
        gap = compute_gap(extracted, corrected)
        assert gap.corrected_rows_count == 1
        assert gap.value_mismatches == 1
        assert gap.editing_rate == pytest.approx(1 / 3, abs=1e-3)


class TestUnitCorrections:
    def test_unit_mismatch_detected(self):
        extracted = [_row("glucose", unit="mg/dL")]
        corrected = [_row("glucose", unit="mmol/L")]
        gap = compute_gap(extracted, corrected)
        assert gap.unit_mismatches == 1

    def test_mu_normalization_no_false_mismatch(self):
        extracted = [_row("urea", unit="µmol/L")]
        corrected = [_row("urea", unit="umol/L")]
        gap = compute_gap(extracted, corrected)
        assert gap.unit_mismatches == 0

    def test_case_normalization_no_false_mismatch(self):
        extracted = [_row("hb", unit="G/DL")]
        corrected = [_row("hb", unit="g/dl")]
        gap = compute_gap(extracted, corrected)
        assert gap.unit_mismatches == 0


class TestAddedDeletedRows:
    def test_added_row_counted_as_missing(self):
        extracted = [_row("glucose")]
        corrected = [_row("glucose"), _row("urea")]
        gap = compute_gap(extracted, corrected)
        assert gap.missing_rows == 1

    def test_deleted_row_counted_as_false_positive(self):
        extracted = [_row("glucose"), _row("urea")]
        corrected = [_row("glucose")]
        gap = compute_gap(extracted, corrected)
        assert gap.false_positive_rows == 1

    def test_row_diffs_contain_edit_types(self):
        extracted = [_row("a"), _row("b")]
        corrected = [_row("a"), _row("c")]
        gap = compute_gap(extracted, corrected)
        edit_types = {d["edit_type"] for d in gap.row_diffs}
        assert edit_types & {"deleted", "added"}


class TestAccuracyMetrics:
    def test_row_accuracy_formula(self):
        extracted = [_row("a"), _row("b"), _row("c")]
        corrected = [_row("a"), _row("b")]
        gap = compute_gap(extracted, corrected)
        assert gap.row_accuracy == pytest.approx(2 / 3, abs=1e-3)

    def test_overall_accuracy_is_average_of_three(self):
        extracted = [_row("a", 1.0, "g"), _row("b", 2.0, "g")]
        corrected = [_row("a", 1.0, "g"), _row("b", 9.9, "mg")]
        gap = compute_gap(extracted, corrected)
        expected = (gap.row_accuracy + gap.value_accuracy + gap.unit_accuracy) / 3
        assert gap.overall_accuracy == pytest.approx(expected, abs=1e-4)

    def test_all_accuracy_fields_non_negative(self):
        gap = compute_gap([_row("x", 1.0)], [_row("x", 2.0)])
        for field in ("row_accuracy", "value_accuracy", "unit_accuracy", "biomarker_accuracy", "overall_accuracy", "editing_rate"):
            assert getattr(gap, field) >= 0.0

    def test_canonical_match_takes_priority(self):
        e = [{"test_name": "a", "original_test_name": "aaa", "mapped_metric_type": "glucose", "display_name_vi": "", "value": 1.0, "unit": "g"}]
        c = [{"test_name": "a", "original_test_name": "aab", "mapped_metric_type": "glucose", "display_name_vi": "", "value": 1.0, "unit": "g"}]
        gap = compute_gap(e, c)
        assert gap.matched_rows == 1
