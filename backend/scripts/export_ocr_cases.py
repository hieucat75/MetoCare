#!/usr/bin/env python3
"""Re-export confirmed OCRCase records to ocr_dataset/benchmark/<hospital>/.

Useful after adding new hospitals or correcting export logic.

Usage:
    python scripts/export_ocr_cases.py [--hospital HOSPITAL] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.domain.ocr_dataset_export import export_case
from app.models.ocr_case import OCRCase
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


def _engine():
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)
    return create_engine(url)


def _make_sample_id(case: OCRCase) -> str:
    date_str = case.created_at.strftime("%Y%m%d") if case.created_at else "00000000"
    hospital = (case.hospital_detected or "other").replace("-", "")
    return f"{date_str}_{hospital}_{case.id[:8]}"


def run(*, hospital_filter: str | None, dry_run: bool) -> None:
    engine = _engine()
    with Session(engine) as db:
        stmt = (
            select(OCRCase)
            .where(OCRCase.corrected_rows_json.is_not(None))
            .where(OCRCase.accuracy_score.is_not(None))
        )
        if hospital_filter:
            stmt = stmt.where(OCRCase.hospital_detected == hospital_filter)
        cases = db.execute(stmt).scalars().all()

    print(f"Found {len(cases)} confirmed cases to export.")
    exported = skipped = failed = 0

    for case in cases:
        sample_id = _make_sample_id(case)
        corrected_rows = json.loads(case.corrected_rows_json or "[]")
        gap_report = json.loads(case.gap_report_json or "{}")

        if dry_run:
            print(f"  [dry-run] {sample_id} hospital={case.hospital_detected}")
            continue

        try:
            result = export_case(
                sample_id=sample_id,
                hospital_id=case.hospital_detected,
                corrected_rows=corrected_rows,
                test_date=None,
                gap_report=gap_report,
                hospital_confidence=case.hospital_confidence,
                parser_version=case.parser_version,
                user_consent_granted=False,
            )
            if result.exported:
                print(f"  [ok] {sample_id} -> {result.dataset_path}")
                exported += 1
            else:
                print(f"  [skip] {sample_id} reason={result.reason}")
                skipped += 1
        except Exception as exc:
            print(f"  [fail] {sample_id} err={exc}", file=sys.stderr)
            failed += 1

    if not dry_run:
        print(f"\nexported={exported} skipped={skipped} failed={failed}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-export confirmed OCRCase records")
    parser.add_argument("--hospital", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(hospital_filter=args.hospital, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
