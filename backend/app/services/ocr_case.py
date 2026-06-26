"""OCR case service — create/update OCRCase records, orchestrate gap + export.

Lifecycle:
  create_case()  — called from POST /lab-uploads after draft is produced.
  confirm_case() — called from lab.create_manual_entry() after save, with
                   corrected rows from the user.

Never raises into the caller's save transaction — export/gap errors are logged.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.ocr_dataset_export import export_case as _export_case
from app.domain.ocr_gap_analysis import compute_gap
from app.models.ocr_case import OCRCase

_logger = logging.getLogger("mcp.ocr_case")

_PARSER_VERSION = "hospital_profiles_v1"


def create_case(
    db: Session,
    *,
    patient_id: str,
    extracted_rows: list[dict],
    hospital_id: str | None,
    hospital_confidence: float | None,
    source_file_hash: str | None,
    ocr_engine_version: str | None,
) -> OCRCase:
    """Create OCRCase for a completed OCR draft. Caller must commit."""
    case = OCRCase(
        patient_id=patient_id,
        hospital_detected=hospital_id,
        hospital_confidence=hospital_confidence,
        source_file_hash=source_file_hash,
        parser_version=_PARSER_VERSION,
        ocr_engine_version=ocr_engine_version,
        extracted_rows_json=json.dumps(extracted_rows, ensure_ascii=False),
        rows_total=len(extracted_rows),
        export_status="pending",
    )
    db.add(case)
    db.flush()
    _logger.info(
        "ocr_case_created id=%s patient=%s hospital=%s rows=%d",
        case.id, patient_id, hospital_id, len(extracted_rows),
    )
    return case


def confirm_case(
    db: Session,
    *,
    case_id: str,
    patient_id: str,
    lab_batch_id: str,
    corrected_rows: list[dict],
    test_date_iso: str | None,
    user_review_time_seconds: float | None = None,
) -> OCRCase | None:
    """Update OCRCase with corrected rows, compute gap, trigger export.

    Returns updated case or None if not found / wrong patient.
    Export failures are caught and logged; never propagate to the save transaction.
    """
    case = db.execute(
        select(OCRCase).where(OCRCase.id == case_id)
    ).scalars().first()

    if case is None:
        _logger.warning("ocr_case_not_found id=%s", case_id)
        return None

    if case.patient_id != patient_id:
        _logger.error(
            "ocr_case_ownership_violation id=%s expected=%s got=%s",
            case_id, case.patient_id, patient_id,
        )
        return None

    extracted: list[dict] = []
    if case.extracted_rows_json:
        try:
            extracted = json.loads(case.extracted_rows_json)
        except (json.JSONDecodeError, ValueError):
            _logger.warning("ocr_case_bad_json id=%s", case_id)

    gap = compute_gap(extracted, corrected_rows)
    gap_dict = asdict(gap)

    case.lab_batch_id = lab_batch_id
    case.corrected_rows_json = json.dumps(corrected_rows, ensure_ascii=False)
    case.gap_report_json = json.dumps(gap_dict, ensure_ascii=False)
    case.user_review_time_seconds = user_review_time_seconds

    case.row_accuracy = gap.row_accuracy
    case.value_accuracy = gap.value_accuracy
    case.unit_accuracy = gap.unit_accuracy
    case.biomarker_accuracy = gap.biomarker_accuracy
    case.accuracy_score = gap.overall_accuracy
    case.editing_rate = gap.editing_rate
    case.rows_total = gap.total_extracted_rows
    case.rows_correct = gap.matched_rows
    case.rows_missing = gap.missing_rows        # corrected rows not found in extracted
    case.rows_added = gap.corrected_rows_count  # rows that had any correction applied
    case.rows_deleted = gap.false_positive_rows
    case.rows_value_corrected = gap.value_mismatches
    case.rows_unit_corrected = gap.unit_mismatches
    case.rows_biomarker_corrected = gap.biomarker_mismatches

    _logger.info(
        "ocr_case_gap id=%s row_acc=%.3f val_acc=%.3f edit_rate=%.3f",
        case_id, gap.row_accuracy, gap.value_accuracy, gap.editing_rate,
    )

    try:
        result = _export_case(
            sample_id=_make_sample_id(case),
            hospital_id=case.hospital_detected,
            corrected_rows=corrected_rows,
            test_date=test_date_iso,
            gap_report=gap_dict,
            hospital_confidence=case.hospital_confidence,
            parser_version=case.parser_version,
        )
        case.export_status = "exported" if result.exported else "skipped"
        case.exported_dataset_path = result.dataset_path
    except Exception as exc:  # noqa: BLE001
        _logger.error("ocr_export_exception id=%s err=%s", case_id, exc)
        case.export_status = "failed"

    db.flush()
    return case


def get_case(db: Session, *, case_id: str, patient_id: str) -> OCRCase | None:
    case = db.get(OCRCase, case_id)
    if case is None or case.patient_id != patient_id:
        return None
    return case


def _make_sample_id(case: OCRCase) -> str:
    date_str = case.created_at.strftime("%Y%m%d") if case.created_at else "00000000"
    hospital = (case.hospital_detected or "other").replace("-", "")
    return f"{date_str}_{hospital}_{case.id[:8]}"
