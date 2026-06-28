#!/usr/bin/env python3
"""Print a single OCRCase as JSON for debugging.

Usage:
    python scripts/ocr_case_inspect.py <case_id>
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.ocr_case import OCRCase
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _engine():
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)
    return create_engine(url)


def inspect(case_id: str) -> None:
    engine = _engine()
    with Session(engine) as db:
        case = db.get(OCRCase, case_id)
    if case is None:
        print(f"No OCRCase found with id={case_id}", file=sys.stderr)
        sys.exit(1)

    out = {
        "id": case.id,
        "patient_id": case.patient_id,
        "lab_batch_id": case.lab_batch_id,
        "hospital_detected": case.hospital_detected,
        "hospital_confidence": case.hospital_confidence,
        "source_file_hash": case.source_file_hash,
        "parser_version": case.parser_version,
        "ocr_engine_version": case.ocr_engine_version,
        "export_status": case.export_status,
        "exported_dataset_path": case.exported_dataset_path,
        "accuracy_score": case.accuracy_score,
        "row_accuracy": case.row_accuracy,
        "value_accuracy": case.value_accuracy,
        "unit_accuracy": case.unit_accuracy,
        "biomarker_accuracy": case.biomarker_accuracy,
        "editing_rate": case.editing_rate,
        "rows_total": case.rows_total,
        "rows_correct": case.rows_correct,
        "rows_missing": case.rows_missing,
        "rows_deleted": case.rows_deleted,
        "rows_added": case.rows_added,
        "rows_value_corrected": case.rows_value_corrected,
        "rows_unit_corrected": case.rows_unit_corrected,
        "rows_biomarker_corrected": case.rows_biomarker_corrected,
        "user_review_time_seconds": case.user_review_time_seconds,
        "created_at": case.created_at.isoformat() if case.created_at else None,
        "updated_at": case.updated_at.isoformat() if case.updated_at else None,
        "extracted_rows": json.loads(case.extracted_rows_json or "[]"),
        "corrected_rows": json.loads(case.corrected_rows_json or "[]"),
        "gap_report": json.loads(case.gap_report_json or "{}"),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: ocr_case_inspect.py <case_id>", file=sys.stderr)
        sys.exit(1)
    inspect(sys.argv[1])


if __name__ == "__main__":
    main()
