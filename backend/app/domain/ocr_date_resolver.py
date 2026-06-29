"""OCR Date Resolver — deterministic date classification from OCR-extracted dates.

Classifies raw OCR date candidates into: DOB, COLLECTION_DATE, RESULT_DATE,
EXAM_DATE, or UNKNOWN.  Pure domain logic — no DB imports, no I/O.

Design invariant: NEVER use a DOB-classified date as a lab/exam date.
If the only available date is a DOB, return None from best_exam_date and
signal needs_user_confirmation=True so the caller can prompt the user.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

# --------------------------------------------------------------------------- #
# Public types
# --------------------------------------------------------------------------- #

class DateClassification(StrEnum):
    DOB = "DOB"
    COLLECTION_DATE = "COLLECTION_DATE"
    RESULT_DATE = "RESULT_DATE"
    EXAM_DATE = "EXAM_DATE"
    UNKNOWN = "UNKNOWN"


@dataclass
class ResolvedDate:
    date: str                          # ISO YYYY-MM-DD
    classification: DateClassification
    confidence: float                  # 0.0–1.0
    source_label: str                  # raw OCR label that drove the classification


# --------------------------------------------------------------------------- #
# Classification keyword tables (Vietnamese + English)
# --------------------------------------------------------------------------- #

# Each entry is a compiled regex pattern matched case-insensitively against the
# normalised label string.
_DOB_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ng[àa]y\s*sinh", re.IGNORECASE),
    re.compile(r"\bdob\b", re.IGNORECASE),
    re.compile(r"\bbirth(day|date)?\b", re.IGNORECASE),
    re.compile(r"\bborn\b", re.IGNORECASE),
    re.compile(r"n[aă]m\s*sinh", re.IGNORECASE),
    re.compile(r"\btu[oổ]i\b", re.IGNORECASE),
    re.compile(r"\bdate\s*of\s*birth\b", re.IGNORECASE),
    re.compile(r"\bsn\b", re.IGNORECASE),          # abbreviated "sinh năm" on some forms
]

_COLLECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"l[aấ]y\s*m[aẫ]u", re.IGNORECASE),
    re.compile(r"thu\s*m[aẫ]u", re.IGNORECASE),
    re.compile(r"\bcollection\b", re.IGNORECASE),
    re.compile(r"\bsample\s*(date|time)?\b", re.IGNORECASE),
    re.compile(r"\bspecimen\b", re.IGNORECASE),
]

_RESULT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"k[eế]t\s*qu[aả]", re.IGNORECASE),
    re.compile(r"\bresult\b", re.IGNORECASE),
    re.compile(r"\bissued\b", re.IGNORECASE),
    re.compile(r"ph[aá]t\s*h[aà]nh", re.IGNORECASE),
    re.compile(r"\breport\s*date\b", re.IGNORECASE),
]

_EXAM_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"x[eé]t\s*nghi[eệ]m", re.IGNORECASE),
    re.compile(r"ng[àa]y\s*x[eé]t\s*nghi[eệ]m", re.IGNORECASE),
    re.compile(r"\bexam\b", re.IGNORECASE),
    re.compile(r"\btest\s*date\b", re.IGNORECASE),
    re.compile(r"ng[àa]y\s*kh[aá]m", re.IGNORECASE),
    re.compile(r"\bvisit\s*date\b", re.IGNORECASE),
    re.compile(r"ng[àa]y\s*th[uự]c\s*hi[eệ]n", re.IGNORECASE),
]

# Priority order for classification — first match wins.
_ORDERED_RULES: list[tuple[DateClassification, list[re.Pattern[str]]]] = [
    (DateClassification.DOB, _DOB_PATTERNS),
    (DateClassification.COLLECTION_DATE, _COLLECTION_PATTERNS),
    (DateClassification.RESULT_DATE, _RESULT_PATTERNS),
    (DateClassification.EXAM_DATE, _EXAM_PATTERNS),
]

# Priority for best_exam_date selection (lowest index = highest priority).
_EXAM_PRIORITY: list[DateClassification] = [
    DateClassification.EXAM_DATE,
    DateClassification.RESULT_DATE,
    DateClassification.COLLECTION_DATE,
    DateClassification.UNKNOWN,
]


# --------------------------------------------------------------------------- #
# Helper utilities
# --------------------------------------------------------------------------- #

def _current_year() -> int:
    return datetime.now().year


def _parse_iso_year(iso_str: str) -> int | None:
    """Extract the year from an ISO YYYY-MM-DD string; return None on failure."""
    try:
        return date.fromisoformat(iso_str).year
    except (ValueError, TypeError):
        return None


def _classify_by_label(label: str) -> DateClassification:
    """Match label against keyword tables in priority order."""
    for classification, patterns in _ORDERED_RULES:
        for pat in patterns:
            if pat.search(label):
                return classification
    return DateClassification.UNKNOWN


def _heuristic_dob_check(iso_str: str, confidence: float) -> bool:
    """Return True when heuristics suggest the date is more likely a DOB than
    an exam date.  Conservative — only flags when two independent signals agree.
    """
    year = _parse_iso_year(iso_str)
    if year is None:
        return False
    current = _current_year()
    age_like_year = current - year
    # Year is implausibly old for a lab test (>80 years ago = almost certainly DOB or error).
    if age_like_year > 80:
        return True
    # Year suggests someone 18–80 years old AND OCR confidence is low — possible DOB.
    if 18 <= age_like_year <= 80 and confidence < 0.7:
        return True
    return False


# --------------------------------------------------------------------------- #
# OcrDateResolver
# --------------------------------------------------------------------------- #

class OcrDateResolver:
    """Classify OCR-extracted date candidates and surface the best exam date.

    Usage::

        resolver = OcrDateResolver()
        resolved = resolver.resolve(raw_dates)
        best = resolver.best_exam_date(resolved)
        if resolver.needs_user_confirmation(resolved):
            # prompt user to confirm / enter date manually
            ...
    """

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def resolve(self, raw_dates: list[dict]) -> list[ResolvedDate]:
        """Classify a list of raw OCR date dicts.

        Parameters
        ----------
        raw_dates:
            Each dict must contain:
            - ``value``      — ISO date string (YYYY-MM-DD)
            - ``label``      — raw OCR label string (e.g. "Ngày xét nghiệm")
            - ``confidence`` — float 0..1 from OCR engine

        Returns
        -------
        list[ResolvedDate]
            One entry per input, in the same order.
        """
        results: list[ResolvedDate] = []
        for raw in raw_dates:
            value: str = str(raw.get("value", "")).strip()
            label: str = str(raw.get("label", "")).strip()
            confidence: float = float(raw.get("confidence", 0.0))

            classification = _classify_by_label(label)

            # Apply heuristic upgrade: if label didn't match DOB keywords but
            # the date pattern looks like a birth year, reclassify as DOB.
            if classification is DateClassification.UNKNOWN:
                if _heuristic_dob_check(value, confidence):
                    classification = DateClassification.DOB

            results.append(
                ResolvedDate(
                    date=value,
                    classification=classification,
                    confidence=confidence,
                    source_label=label,
                )
            )
        return results

    def best_exam_date(self, resolved: list[ResolvedDate]) -> ResolvedDate | None:
        """Return the highest-priority non-DOB date candidate.

        Priority (descending): EXAM_DATE > RESULT_DATE > COLLECTION_DATE > UNKNOWN.
        DOB candidates are never returned.

        Returns None when the only candidates are classified as DOB.
        """
        non_dob = [r for r in resolved if r.classification is not DateClassification.DOB]
        if not non_dob:
            return None

        # Sort by (priority_index ASC, confidence DESC) so the best candidate
        # ends up first after sorting.
        def _sort_key(r: ResolvedDate) -> tuple[int, float]:
            try:
                pri = _EXAM_PRIORITY.index(r.classification)
            except ValueError:
                pri = len(_EXAM_PRIORITY)
            return (pri, -r.confidence)  # negate confidence so higher → smaller

        return sorted(non_dob, key=_sort_key)[0]

    def needs_user_confirmation(self, resolved: list[ResolvedDate]) -> bool:
        """Return True when the resolved date set is uncertain and the user
        should be asked to confirm or enter the exam date manually.

        Triggers when:
        - No non-DOB date found at all, OR
        - The best non-DOB candidate has confidence < 0.6
        """
        best = self.best_exam_date(resolved)
        if best is None:
            return True
        return best.confidence < 0.6
