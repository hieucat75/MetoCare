"""Tests for OCR Date Resolver — deterministic date classification.

Covers:
 - DOB classification (label-based)
 - EXAM_DATE classification (label-based)
 - COLLECTION_DATE classification (label-based)
 - RESULT_DATE classification (label-based)
 - UNKNOWN classification (no matching label)
 - Heuristic fallback: year > 80 years ago → DOB
 - Heuristic fallback: year 18–80 years ago + low confidence → DOB
 - Heuristic fallback: year 18–80 years ago + high confidence → UNKNOWN (not DOB)
 - best_exam_date priority ordering
 - best_exam_date returns None when only DOBs
 - needs_user_confirmation logic
 - end-to-end: DOB discards exam date when only DOB present
 - English label variants
 - Empty input list
 - Mixed bag with a clear winner
"""

from __future__ import annotations

from datetime import datetime

import pytest
from app.domain.ocr_date_resolver import (
    DateClassification,
    OcrDateResolver,
    ResolvedDate,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def resolver() -> OcrDateResolver:
    return OcrDateResolver()


def _make(value: str, label: str, confidence: float = 0.9) -> dict:
    """Build a raw_date dict for resolver.resolve()."""
    return {"value": value, "label": label, "confidence": confidence}


def _current_year() -> int:
    return datetime.now().year


# ---------------------------------------------------------------------------
# 1. DOB classification — label-based (Vietnamese)
# ---------------------------------------------------------------------------

class TestDobLabelClassification:
    def test_ngay_sinh_label(self, resolver: OcrDateResolver) -> None:
        raw = [_make("1975-10-22", "Ngày sinh", 0.95)]
        result = resolver.resolve(raw)
        assert result[0].classification is DateClassification.DOB

    def test_nam_sinh_label(self, resolver: OcrDateResolver) -> None:
        raw = [_make("1980-03-15", "Năm sinh", 0.90)]
        result = resolver.resolve(raw)
        assert result[0].classification is DateClassification.DOB

    def test_tuoi_label(self, resolver: OcrDateResolver) -> None:
        raw = [_make("1965-07-01", "Tuổi: 58", 0.85)]
        result = resolver.resolve(raw)
        assert result[0].classification is DateClassification.DOB

    def test_dob_english_label(self, resolver: OcrDateResolver) -> None:
        raw = [_make("1990-05-11", "DOB", 0.92)]
        result = resolver.resolve(raw)
        assert result[0].classification is DateClassification.DOB

    def test_date_of_birth_label(self, resolver: OcrDateResolver) -> None:
        raw = [_make("1985-12-25", "Date of Birth", 0.88)]
        result = resolver.resolve(raw)
        assert result[0].classification is DateClassification.DOB


# ---------------------------------------------------------------------------
# 2. EXAM_DATE classification — label-based
# ---------------------------------------------------------------------------

class TestExamDateLabelClassification:
    def test_xet_nghiem_label_vi(self, resolver: OcrDateResolver) -> None:
        raw = [_make("2024-11-05", "Ngày xét nghiệm", 0.95)]
        result = resolver.resolve(raw)
        assert result[0].classification is DateClassification.EXAM_DATE

    def test_ngay_kham_label_vi(self, resolver: OcrDateResolver) -> None:
        raw = [_make("2024-11-10", "Ngày khám", 0.90)]
        result = resolver.resolve(raw)
        assert result[0].classification is DateClassification.EXAM_DATE

    def test_test_date_english_label(self, resolver: OcrDateResolver) -> None:
        raw = [_make("2024-06-01", "Test Date", 0.88)]
        result = resolver.resolve(raw)
        assert result[0].classification is DateClassification.EXAM_DATE

    def test_exam_english_label(self, resolver: OcrDateResolver) -> None:
        raw = [_make("2024-03-20", "Exam date: 20/03/2024", 0.91)]
        result = resolver.resolve(raw)
        assert result[0].classification is DateClassification.EXAM_DATE


# ---------------------------------------------------------------------------
# 3. COLLECTION_DATE classification
# ---------------------------------------------------------------------------

class TestCollectionDateClassification:
    def test_lay_mau_label_vi(self, resolver: OcrDateResolver) -> None:
        raw = [_make("2024-11-04", "Ngày lấy mẫu", 0.93)]
        result = resolver.resolve(raw)
        assert result[0].classification is DateClassification.COLLECTION_DATE

    def test_collection_english_label(self, resolver: OcrDateResolver) -> None:
        raw = [_make("2024-09-12", "Collection Date", 0.87)]
        result = resolver.resolve(raw)
        assert result[0].classification is DateClassification.COLLECTION_DATE

    def test_specimen_label(self, resolver: OcrDateResolver) -> None:
        raw = [_make("2024-07-07", "Specimen Date", 0.82)]
        result = resolver.resolve(raw)
        assert result[0].classification is DateClassification.COLLECTION_DATE


# ---------------------------------------------------------------------------
# 4. RESULT_DATE classification
# ---------------------------------------------------------------------------

class TestResultDateClassification:
    def test_ket_qua_label_vi(self, resolver: OcrDateResolver) -> None:
        raw = [_make("2024-11-06", "Ngày kết quả", 0.90)]
        result = resolver.resolve(raw)
        assert result[0].classification is DateClassification.RESULT_DATE

    def test_result_english_label(self, resolver: OcrDateResolver) -> None:
        raw = [_make("2024-10-30", "Result Date", 0.85)]
        result = resolver.resolve(raw)
        assert result[0].classification is DateClassification.RESULT_DATE

    def test_issued_label(self, resolver: OcrDateResolver) -> None:
        raw = [_make("2024-10-29", "Issued: 29/10/2024", 0.88)]
        result = resolver.resolve(raw)
        assert result[0].classification is DateClassification.RESULT_DATE


# ---------------------------------------------------------------------------
# 5. UNKNOWN classification
# ---------------------------------------------------------------------------

class TestUnknownClassification:
    def test_empty_label(self, resolver: OcrDateResolver) -> None:
        raw = [_make("2024-06-15", "", 0.75)]
        result = resolver.resolve(raw)
        # Year 2024 is not DOB-like with high confidence → UNKNOWN
        assert result[0].classification is DateClassification.UNKNOWN

    def test_irrelevant_label(self, resolver: OcrDateResolver) -> None:
        raw = [_make("2023-01-01", "Số phiếu", 0.80)]
        result = resolver.resolve(raw)
        assert result[0].classification is DateClassification.UNKNOWN


# ---------------------------------------------------------------------------
# 6. Heuristic fallback — birth-year patterns
# ---------------------------------------------------------------------------

class TestHeuristicFallback:
    def test_year_over_80_years_ago_is_dob(self, resolver: OcrDateResolver) -> None:
        old_year = _current_year() - 85
        raw = [_make(f"{old_year}-05-20", "Ngày", 0.95)]  # no DOB keyword
        result = resolver.resolve(raw)
        assert result[0].classification is DateClassification.DOB

    def test_year_under_18_not_flagged_as_dob_heuristic(self, resolver: OcrDateResolver) -> None:
        """A very recent year (last year) should NOT be classified DOB by heuristic."""
        recent_year = _current_year() - 1
        raw = [_make(f"{recent_year}-03-01", "Ngày", 0.50)]
        result = resolver.resolve(raw)
        # age < 18 → heuristic doesn't fire
        assert result[0].classification is DateClassification.UNKNOWN

    def test_middle_age_year_low_confidence_is_dob(self, resolver: OcrDateResolver) -> None:
        """Year consistent with 30-year-old + low OCR confidence → DOB heuristic fires."""
        age30_year = _current_year() - 30
        raw = [_make(f"{age30_year}-08-14", "Ngày", 0.50)]  # confidence < 0.7
        result = resolver.resolve(raw)
        assert result[0].classification is DateClassification.DOB

    def test_middle_age_year_high_confidence_not_dob(self, resolver: OcrDateResolver) -> None:
        """Same year but high OCR confidence → heuristic does NOT fire → UNKNOWN."""
        age30_year = _current_year() - 30
        raw = [_make(f"{age30_year}-08-14", "Ngày", 0.85)]
        result = resolver.resolve(raw)
        assert result[0].classification is DateClassification.UNKNOWN


# ---------------------------------------------------------------------------
# 7. best_exam_date priority
# ---------------------------------------------------------------------------

class TestBestExamDate:
    def test_exam_date_wins_over_result_and_collection(self, resolver: OcrDateResolver) -> None:
        resolved = [
            ResolvedDate("2024-11-01", DateClassification.COLLECTION_DATE, 0.90, "lấy mẫu"),
            ResolvedDate("2024-11-02", DateClassification.RESULT_DATE, 0.92, "kết quả"),
            ResolvedDate("2024-11-03", DateClassification.EXAM_DATE, 0.88, "xét nghiệm"),
        ]
        best = resolver.best_exam_date(resolved)
        assert best is not None
        assert best.date == "2024-11-03"
        assert best.classification is DateClassification.EXAM_DATE

    def test_result_date_beats_collection_when_no_exam(self, resolver: OcrDateResolver) -> None:
        resolved = [
            ResolvedDate("2024-11-01", DateClassification.COLLECTION_DATE, 0.90, "lấy mẫu"),
            ResolvedDate("2024-11-02", DateClassification.RESULT_DATE, 0.80, "kết quả"),
        ]
        best = resolver.best_exam_date(resolved)
        assert best is not None
        assert best.classification is DateClassification.RESULT_DATE

    def test_collection_beats_unknown(self, resolver: OcrDateResolver) -> None:
        resolved = [
            ResolvedDate("2024-10-10", DateClassification.UNKNOWN, 0.70, ""),
            ResolvedDate("2024-10-11", DateClassification.COLLECTION_DATE, 0.75, "sample"),
        ]
        best = resolver.best_exam_date(resolved)
        assert best is not None
        assert best.classification is DateClassification.COLLECTION_DATE

    def test_returns_none_when_only_dob(self, resolver: OcrDateResolver) -> None:
        resolved = [
            ResolvedDate("1975-10-22", DateClassification.DOB, 0.95, "ngày sinh"),
        ]
        assert resolver.best_exam_date(resolved) is None

    def test_returns_none_on_empty_list(self, resolver: OcrDateResolver) -> None:
        assert resolver.best_exam_date([]) is None

    def test_skips_dob_and_returns_exam(self, resolver: OcrDateResolver) -> None:
        resolved = [
            ResolvedDate("1975-10-22", DateClassification.DOB, 0.97, "ngày sinh"),
            ResolvedDate("2024-11-05", DateClassification.EXAM_DATE, 0.85, "xét nghiệm"),
        ]
        best = resolver.best_exam_date(resolved)
        assert best is not None
        assert best.date == "2024-11-05"

    def test_higher_confidence_wins_within_same_class(self, resolver: OcrDateResolver) -> None:
        resolved = [
            ResolvedDate("2024-10-01", DateClassification.EXAM_DATE, 0.60, "xét nghiệm"),
            ResolvedDate("2024-11-01", DateClassification.EXAM_DATE, 0.95, "ngày xét nghiệm"),
        ]
        best = resolver.best_exam_date(resolved)
        assert best is not None
        assert best.date == "2024-11-01"
        assert best.confidence == 0.95


# ---------------------------------------------------------------------------
# 8. needs_user_confirmation
# ---------------------------------------------------------------------------

class TestNeedsUserConfirmation:
    def test_true_when_no_non_dob_date(self, resolver: OcrDateResolver) -> None:
        resolved = [ResolvedDate("1975-01-01", DateClassification.DOB, 0.95, "ngày sinh")]
        assert resolver.needs_user_confirmation(resolved) is True

    def test_true_when_best_confidence_below_threshold(self, resolver: OcrDateResolver) -> None:
        resolved = [
            ResolvedDate("2024-11-05", DateClassification.EXAM_DATE, 0.55, "xét nghiệm")
        ]
        assert resolver.needs_user_confirmation(resolved) is True

    def test_false_when_high_confidence_exam_date(self, resolver: OcrDateResolver) -> None:
        resolved = [
            ResolvedDate("2024-11-05", DateClassification.EXAM_DATE, 0.92, "xét nghiệm")
        ]
        assert resolver.needs_user_confirmation(resolved) is False

    def test_false_when_collection_date_above_threshold(self, resolver: OcrDateResolver) -> None:
        resolved = [
            ResolvedDate("2024-10-10", DateClassification.COLLECTION_DATE, 0.75, "lấy mẫu")
        ]
        assert resolver.needs_user_confirmation(resolved) is False

    def test_true_on_empty_list(self, resolver: OcrDateResolver) -> None:
        assert resolver.needs_user_confirmation([]) is True

    def test_exactly_at_threshold_not_flagged(self, resolver: OcrDateResolver) -> None:
        """Confidence exactly 0.6 should NOT trigger confirmation (strict <)."""
        resolved = [
            ResolvedDate("2024-11-01", DateClassification.EXAM_DATE, 0.6, "xét nghiệm")
        ]
        assert resolver.needs_user_confirmation(resolved) is False


# ---------------------------------------------------------------------------
# 9. End-to-end: resolve() + best_exam_date() + needs_user_confirmation()
# ---------------------------------------------------------------------------

class TestEndToEnd:
    def test_typical_lab_report_with_exam_date(self, resolver: OcrDateResolver) -> None:
        raw = [
            _make("1985-06-20", "Ngày sinh", 0.95),
            _make("2024-11-05", "Ngày xét nghiệm", 0.91),
        ]
        resolved = resolver.resolve(raw)
        assert resolved[0].classification is DateClassification.DOB
        assert resolved[1].classification is DateClassification.EXAM_DATE
        best = resolver.best_exam_date(resolved)
        assert best is not None and best.date == "2024-11-05"
        assert resolver.needs_user_confirmation(resolved) is False

    def test_only_dob_found_returns_none_and_confirmation(self, resolver: OcrDateResolver) -> None:
        raw = [_make("1970-03-15", "Ngày sinh", 0.97)]
        resolved = resolver.resolve(raw)
        assert resolver.best_exam_date(resolved) is None
        assert resolver.needs_user_confirmation(resolved) is True

    def test_empty_raw_input(self, resolver: OcrDateResolver) -> None:
        resolved = resolver.resolve([])
        assert resolved == []
        assert resolver.best_exam_date(resolved) is None
        assert resolver.needs_user_confirmation(resolved) is True
