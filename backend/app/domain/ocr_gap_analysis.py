"""Pure gap analysis between OCR-extracted draft rows and user-corrected rows.

No DB, no I/O. Input/output are plain Python dicts so callers can JSON-serialize.

Matching strategy (priority order):
  1. ``mapped_metric_type`` equality (canonical biomarker key)
  2. ``original_test_name`` / ``test_name`` 4-char prefix match (case-insensitive)
  3. ``display_name_vi`` exact match

Value match: within VALUE_TOLERANCE_ABS (0.005) or VALUE_TOLERANCE_REL (0.5%).
Unit match: normalized lower-case after collapsing µ/u variants.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

VALUE_TOLERANCE_REL = 0.005
VALUE_TOLERANCE_ABS = 0.005

_MU_RE = re.compile(r"µ|μ")


def _norm_unit(u: str | None) -> str:
    if not u:
        return ""
    return _MU_RE.sub("u", u.strip().lower())


def _values_match(a: float | None, b: float | None) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    diff = abs(a - b)
    if diff <= VALUE_TOLERANCE_ABS:
        return True
    denom = max(abs(a), abs(b))
    return (diff / denom) <= VALUE_TOLERANCE_REL if denom > 0 else diff == 0


def _name_score(extracted: dict, corrected: dict) -> float:
    """Return match score: 1.0 = canonical match, 0.5 = name prefix, 0.0 = no match."""
    e_metric = (extracted.get("mapped_metric_type") or "").strip().lower()
    c_metric = (corrected.get("mapped_metric_type") or "").strip().lower()
    if e_metric and c_metric and e_metric == c_metric:
        return 1.0

    e_name = (extracted.get("original_test_name") or "").strip().lower()
    c_name = (
        (corrected.get("original_test_name") or corrected.get("test_name") or "").strip().lower()
    )
    if e_name and c_name and len(e_name) >= 4 and len(c_name) >= 4:
        if e_name[:4] == c_name[:4]:
            return 0.5

    e_vi = (extracted.get("display_name_vi") or "").strip().lower()
    c_vi = (corrected.get("display_name_vi") or "").strip().lower()
    if e_vi and c_vi and e_vi == c_vi:
        return 0.5

    return 0.0


def _best_match(extracted: dict, pool: list[dict]) -> dict | None:
    best_score, best = 0.0, None
    for c in pool:
        s = _name_score(extracted, c)
        if s > best_score:
            best_score, best = s, c
    return best if best_score > 0 else None


@dataclass(frozen=True)
class RowDiff:
    extracted_index: int
    corrected_index: int | None
    matched: bool
    value_corrected: bool = False
    unit_corrected: bool = False
    biomarker_corrected: bool = False
    edit_type: str = "none"


@dataclass(frozen=True)
class GapReport:
    total_extracted_rows: int
    total_corrected_rows: int
    matched_rows: int
    missing_rows: int
    false_positive_rows: int
    biomarker_mismatches: int
    value_mismatches: int
    unit_mismatches: int
    corrected_rows_count: int
    editing_rate: float
    row_accuracy: float
    value_accuracy: float
    unit_accuracy: float
    biomarker_accuracy: float
    overall_accuracy: float
    row_diffs: list[dict] = field(default_factory=list)


def compute_gap(
    extracted_rows: list[dict],
    corrected_rows: list[dict],
) -> GapReport:
    """Compare OCR draft rows against user-corrected rows. Pure — no side effects."""
    if not extracted_rows and not corrected_rows:
        return GapReport(
            total_extracted_rows=0,
            total_corrected_rows=0,
            matched_rows=0,
            missing_rows=0,
            false_positive_rows=0,
            biomarker_mismatches=0,
            value_mismatches=0,
            unit_mismatches=0,
            corrected_rows_count=0,
            editing_rate=0.0,
            row_accuracy=0.0,
            value_accuracy=0.0,
            unit_accuracy=0.0,
            biomarker_accuracy=0.0,
            overall_accuracy=0.0,
        )

    unmatched_corrected: list[tuple[int, dict]] = list(enumerate(corrected_rows))
    row_diffs: list[RowDiff] = []
    biomarker_mismatches = value_mismatches = unit_mismatches = corrected_count = matched = 0

    for e_idx, e_row in enumerate(extracted_rows):
        pool = [c for _, c in unmatched_corrected]
        best = _best_match(e_row, pool)

        if best is None:
            row_diffs.append(RowDiff(e_idx, None, False, edit_type="deleted"))
            continue

        c_global_idx = next(gi for gi, c in unmatched_corrected if c is best)
        unmatched_corrected = [(gi, c) for gi, c in unmatched_corrected if c is not best]

        bm_changed = bool(
            (e_row.get("mapped_metric_type") or "").lower()
            != (best.get("mapped_metric_type") or "").lower()
            and e_row.get("mapped_metric_type")
            and best.get("mapped_metric_type")
        )
        val_changed = not _values_match(e_row.get("value"), best.get("value"))
        unit_changed = _norm_unit(e_row.get("unit")) != _norm_unit(best.get("unit"))

        if bm_changed:
            biomarker_mismatches += 1
        if val_changed:
            value_mismatches += 1
        if unit_changed:
            unit_mismatches += 1
        if bm_changed or val_changed or unit_changed:
            corrected_count += 1

        edits = (
            (["biomarker"] if bm_changed else [])
            + (["value"] if val_changed else [])
            + (["unit"] if unit_changed else [])
        )
        edit_type = "multi" if len(edits) > 1 else (edits[0] if edits else "none")

        matched += 1
        row_diffs.append(
            RowDiff(e_idx, c_global_idx, True, bm_changed, val_changed, unit_changed, edit_type)
        )

    missing_rows = len(unmatched_corrected)
    for gi, _ in unmatched_corrected:
        row_diffs.append(RowDiff(-1, gi, False, edit_type="added"))

    total_e, total_c = len(extracted_rows), len(corrected_rows)
    false_positives = sum(1 for d in row_diffs if d.edit_type == "deleted")
    denom_rows = max(total_e, total_c) or 1
    denom_m = matched or 1

    row_acc = matched / denom_rows
    val_acc = (matched - value_mismatches) / denom_m
    unit_acc = (matched - unit_mismatches) / denom_m
    bm_acc = (matched - biomarker_mismatches) / denom_m
    editing_rate = corrected_count / total_e if total_e else 0.0
    overall = (row_acc + val_acc + unit_acc) / 3

    return GapReport(
        total_extracted_rows=total_e,
        total_corrected_rows=total_c,
        matched_rows=matched,
        missing_rows=missing_rows,
        false_positive_rows=false_positives,
        biomarker_mismatches=biomarker_mismatches,
        value_mismatches=value_mismatches,
        unit_mismatches=unit_mismatches,
        corrected_rows_count=corrected_count,
        editing_rate=round(editing_rate, 4),
        row_accuracy=round(row_acc, 4),
        value_accuracy=round(val_acc, 4),
        unit_accuracy=round(unit_acc, 4),
        biomarker_accuracy=round(bm_acc, 4),
        overall_accuracy=round(overall, 4),
        row_diffs=[asdict(d) for d in row_diffs],
    )
