#!/usr/bin/env python3
"""Print per-hospital OCR accuracy from OCRCase records in the database.

Usage:
    python scripts/ocr_accuracy_report.py [--days N] [--hospital HOSPITAL_ID]

Reads DB URL from DATABASE_URL env var (or .env). Prints a table of:
    hospital | cases | row_acc | val_acc | unit_acc | edit_rate | avg_review_s
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.ocr_case import OCRCase


def _engine():
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)
    return create_engine(url)


def report(*, days: int | None, hospital_filter: str | None) -> None:
    from sqlalchemy import select
    engine = _engine()
    with Session(engine) as db:
        stmt = select(OCRCase).where(OCRCase.accuracy_score.is_not(None))
        if days:
            cutoff = datetime.utcnow() - timedelta(days=days)
            stmt = stmt.where(OCRCase.created_at >= cutoff)
        if hospital_filter:
            stmt = stmt.where(OCRCase.hospital_detected == hospital_filter)
        rows = db.execute(stmt).scalars().all()

    if not rows:
        print("No confirmed OCRCase records found.")
        return

    by_hospital: dict[str, list[OCRCase]] = {}
    for case in rows:
        key = case.hospital_detected or "unknown"
        by_hospital.setdefault(key, []).append(case)

    header = (
        f"{'Hospital':<14} {'Cases':>5} {'RowAcc':>7} {'ValAcc':>7} "
        f"{'UnitAcc':>8} {'EditRate':>9} {'AvgReview(s)':>13}"
    )
    print(header)
    print("-" * len(header))

    for hospital in sorted(by_hospital):
        cases = by_hospital[hospital]
        n = len(cases)
        row_acc = sum(c.row_accuracy or 0 for c in cases) / n
        val_acc = sum(c.value_accuracy or 0 for c in cases) / n
        unit_acc = sum(c.unit_accuracy or 0 for c in cases) / n
        edit_rate = sum(c.editing_rate or 0 for c in cases) / n
        review_times = [c.user_review_time_seconds for c in cases if c.user_review_time_seconds]
        avg_review = sum(review_times) / len(review_times) if review_times else 0.0
        print(
            f"{hospital:<14} {n:>5} {row_acc:>7.1%} {val_acc:>7.1%} "
            f"{unit_acc:>8.1%} {edit_rate:>9.1%} {avg_review:>13.1f}"
        )

    print(f"\nTotal cases: {len(rows)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="OCR accuracy report from DB")
    parser.add_argument("--days", type=int, default=None, help="Only include last N days")
    parser.add_argument("--hospital", default=None, help="Filter to one hospital_id")
    args = parser.parse_args()
    report(days=args.days, hospital_filter=args.hospital)


if __name__ == "__main__":
    main()
