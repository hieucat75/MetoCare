#!/usr/bin/env python3
"""Developer accuracy report — pulls all confirmed OCRCases and produces:

  • Per-hospital accuracy table (row/value/unit/edit-rate)
  • Recurring error breakdown (grouped by edit_type × biomarker)
  • Concrete examples per error category
  • Overall baseline + data-sufficiency verdict

Usage:
    DATABASE_URL=postgres://... python scripts/ocr_gap_report.py [--days N] [--min-cases N]

Can also read DATABASE_URL from .env in the backend directory.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _engine():
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
    except ImportError:
        pass
    url = os.environ.get("DATABASE_URL") or os.environ.get("MCP_DATABASE_URL", "")
    if not url:
        print("ERROR: DATABASE_URL or MCP_DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)
    from sqlalchemy import create_engine
    return create_engine(url)


def _load_cases(engine, *, days: int | None) -> list:
    from app.models.ocr_case import OCRCase
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    with Session(engine) as db:
        stmt = select(OCRCase).where(OCRCase.gap_report_json.is_not(None))
        if days:
            cutoff = datetime.utcnow() - timedelta(days=days)
            stmt = stmt.where(OCRCase.created_at >= cutoff)
        return db.execute(stmt).scalars().all()


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def _parse_json(s: str | None) -> list | dict | None:
    if not s:
        return None
    try:
        return json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Core report logic
# ---------------------------------------------------------------------------

def run_report(cases: list) -> None:
    if not cases:
        print("No confirmed OCRCases with gap data found.")
        return

    by_hospital: dict[str, list] = defaultdict(list)
    error_counter: Counter = Counter()
    error_examples: dict[tuple, list] = defaultdict(list)

    total_stats: dict[str, float] = dict(
        row_acc=0.0, val_acc=0.0, unit_acc=0.0, bm_acc=0.0,
        edit_rate=0.0, review_s=0.0,
    )
    review_n = 0

    for case in cases:
        hospital = case.hospital_detected or "unknown"
        by_hospital[hospital].append(case)

        gap = _parse_json(case.gap_report_json) or {}
        extracted = _parse_json(case.extracted_rows_json) or []
        corrected = _parse_json(case.corrected_rows_json) or []

        total_stats["row_acc"] += case.row_accuracy or 0
        total_stats["val_acc"] += case.value_accuracy or 0
        total_stats["unit_acc"] += case.unit_accuracy or 0
        total_stats["bm_acc"] += case.biomarker_accuracy or 0
        total_stats["edit_rate"] += case.editing_rate or 0
        if case.user_review_time_seconds:
            total_stats["review_s"] += case.user_review_time_seconds
            review_n += 1

        for diff in gap.get("row_diffs", []):
            edit_type = diff.get("edit_type", "none")
            if edit_type == "none":
                continue

            e_idx = diff.get("extracted_index", -1)
            c_idx = diff.get("corrected_index")
            e_row = extracted[e_idx] if 0 <= e_idx < len(extracted) else {}
            c_row = corrected[c_idx] if c_idx is not None and 0 <= c_idx < len(corrected) else {}

            canonical = (
                e_row.get("mapped_metric_type")
                or c_row.get("mapped_metric_type")
                or e_row.get("test_name")
                or "unknown"
            )
            key = (edit_type, canonical)
            error_counter[key] += 1

            if len(error_examples[key]) < 3:
                error_examples[key].append({
                    "case_id": case.id[:8],
                    "hospital": hospital,
                    "e_name": e_row.get("original_test_name") or e_row.get("test_name"),
                    "e_value": e_row.get("value"),
                    "e_unit": e_row.get("unit"),
                    "c_name": c_row.get("original_test_name") or c_row.get("test_name"),
                    "c_value": c_row.get("value"),
                    "c_unit": c_row.get("unit"),
                })

    n = len(cases)

    print("=" * 72)
    print(f"  OCR Accuracy Baseline Report  ({n} case{'s' if n != 1 else ''})")
    print(f"  Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 72)

    print("\n## Overall Baseline\n")

    def avg(k: str) -> float:
        return total_stats[k] / n
    print(f"  Cases analysed : {n}")
    print(f"  Row accuracy   : {avg('row_acc'):.1%}")
    print(f"  Value accuracy : {avg('val_acc'):.1%}")
    print(f"  Unit accuracy  : {avg('unit_acc'):.1%}")
    print(f"  Biomarker acc  : {avg('bm_acc'):.1%}")
    print(f"  Edit rate      : {avg('edit_rate'):.1%}")
    if review_n:
        print(f"  Avg review time: {total_stats['review_s'] / review_n:.0f}s  ({review_n} timed)")

    print("\n## Per-Hospital Accuracy\n")
    hdr = f"  {'Hospital':<14} {'N':>3} {'Conf%':>6} {'RowAcc':>7} {'ValAcc':>7} {'UnitAcc':>8} {'EditRate':>9}"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for hosp in sorted(by_hospital):
        hcases = by_hospital[hosp]
        hn = len(hcases)
        confs = [c.hospital_confidence for c in hcases if c.hospital_confidence is not None]
        conf_str = f"{sum(confs)/len(confs):.0%}" if confs else "  n/a"
        ra = sum(c.row_accuracy or 0 for c in hcases) / hn
        va = sum(c.value_accuracy or 0 for c in hcases) / hn
        ua = sum(c.unit_accuracy or 0 for c in hcases) / hn
        er = sum(c.editing_rate or 0 for c in hcases) / hn
        print(
            f"  {hosp:<14} {hn:>3} {conf_str:>6} "
            f"{ra:>7.1%} {va:>7.1%} {ua:>8.1%} {er:>9.1%}"
        )

    total_errors = sum(error_counter.values())
    print(f"\n## Error Breakdown  ({total_errors} total edits)\n")

    by_type: dict[str, list] = defaultdict(list)
    for (edit_type, canonical), count in error_counter.most_common():
        by_type[edit_type].append((canonical, count))

    type_totals = {t: sum(c for _, c in items) for t, items in by_type.items()}
    for edit_type in sorted(type_totals, key=lambda t: -type_totals[t]):
        type_count = type_totals[edit_type]
        pct = type_count / total_errors if total_errors else 0
        print(f"  [{edit_type.upper()}]  {type_count} edits  ({pct:.0%} of total)\n")
        for canonical, cnt in sorted(by_type[edit_type], key=lambda x: -x[1])[:8]:
            print(f"    {canonical:<32} {cnt:>4}×")
        print()

    print("## Top Error Examples\n")
    for key in [k for k, _ in error_counter.most_common(6)]:
        edit_type, canonical = key
        count = error_counter[key]
        print(f"  [{edit_type.upper()}] {canonical}  ({count}×)")
        for ex in error_examples[key]:
            e_str = f"{ex['e_value']} {ex['e_unit']}" if ex['e_value'] is not None else "(no value)"
            c_str = f"{ex['c_value']} {ex['c_unit']}" if ex['c_value'] is not None else "(no value)"
            name_str = ex["e_name"] or "?"
            if ex.get("c_name") and ex["c_name"] != ex["e_name"]:
                name_str += f" → {ex['c_name']}"
            print(f"    case={ex['case_id']} hosp={ex['hospital']:<10}  {name_str}")
            if edit_type in ("value", "unit", "multi"):
                print(f"      OCR: {e_str}   →   user: {c_str}")
        print()

    print("## Data Sufficiency\n")
    THRESHOLD = 20
    if n >= THRESHOLD:
        print(f"  SUFFICIENT — {n} cases (≥{THRESHOLD}). Patterns are statistically meaningful.")
    else:
        print(f"  INSUFFICIENT — {n} case{'s' if n != 1 else ''} (need ≥{THRESHOLD}).")
        print("  Fix proposals are directional hypotheses only.")
        print(f"  Need {THRESHOLD - n} more real-patient uploads for reliable conclusions.")
    print("\n" + "=" * 72)


def main() -> None:
    parser = argparse.ArgumentParser(description="OCR gap analysis report")
    parser.add_argument("--days", type=int, default=None, help="Only last N days")
    args = parser.parse_args()
    engine = _engine()
    cases = _load_cases(engine, days=args.days)
    run_report(cases)


if __name__ == "__main__":
    main()
