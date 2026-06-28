"""Integration tests for OCRCase service lifecycle (create -> confirm -> export)."""

from __future__ import annotations

import json
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("MCP_ENV", "dev")
os.environ.setdefault("SECRET_KEY", "test-secret-key-32-characters-ok")

from app.core.database import Base
from app.models import OCRCase  # noqa: F401 — ensures OCRCase is registered with Base
from app.services import ocr_case as ocr_case_svc


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


def _extracted():
    return [
        {
            "test_name": "glucose",
            "original_test_name": "Glucose",
            "mapped_metric_type": "glucose",
            "display_name_vi": "Duong mau",
            "value": 5.2,
            "unit": "mmol/L",
        },
        {
            "test_name": "urea",
            "original_test_name": "Urea",
            "mapped_metric_type": "urea",
            "display_name_vi": "Ure",
            "value": 6.0,
            "unit": "mmol/L",
        },
    ]


def _corrected():
    return [
        {
            "test_name": "glucose",
            "original_test_name": "Glucose",
            "mapped_metric_type": "glucose",
            "display_name_vi": "Duong mau",
            "value": 5.5,
            "unit": "mmol/L",
        },
        {
            "test_name": "urea",
            "original_test_name": "Urea",
            "mapped_metric_type": "urea",
            "display_name_vi": "Ure",
            "value": 6.0,
            "unit": "mmol/L",
        },
    ]


def test_create_case_persists_extracted_rows(db):
    case = ocr_case_svc.create_case(
        db,
        patient_id="patient-1",
        extracted_rows=_extracted(),
        hospital_id="vinmec",
        hospital_confidence=0.9,
        source_file_hash="abc123",
        ocr_engine_version="tesseract",
    )
    db.commit()
    assert case.id is not None
    assert case.patient_id == "patient-1"
    assert case.rows_total == 2
    assert json.loads(case.extracted_rows_json)[0]["test_name"] == "glucose"


def test_confirm_case_computes_gap(db):
    case = ocr_case_svc.create_case(
        db,
        patient_id="patient-1",
        extracted_rows=_extracted(),
        hospital_id="vinmec",
        hospital_confidence=0.9,
        source_file_hash="abc123",
        ocr_engine_version="tesseract",
    )
    db.flush()
    confirmed = ocr_case_svc.confirm_case(
        db,
        case_id=case.id,
        patient_id="patient-1",
        lab_batch_id="batch-1",
        corrected_rows=_corrected(),
        test_date_iso="2026-06-01",
        user_review_time_seconds=45.0,
    )
    db.commit()
    assert confirmed is not None
    assert confirmed.lab_batch_id == "batch-1"
    assert confirmed.row_accuracy == 1.0
    assert confirmed.rows_value_corrected == 1


def test_confirm_case_rejects_wrong_patient(db):
    case = ocr_case_svc.create_case(
        db,
        patient_id="patient-1",
        extracted_rows=_extracted(),
        hospital_id=None,
        hospital_confidence=None,
        source_file_hash=None,
        ocr_engine_version=None,
    )
    db.flush()
    result = ocr_case_svc.confirm_case(
        db,
        case_id=case.id,
        patient_id="patient-WRONG",
        lab_batch_id="batch-1",
        corrected_rows=_corrected(),
        test_date_iso="2026-06-01",
    )
    assert result is None


def test_confirm_case_missing_case_returns_none(db):
    result = ocr_case_svc.confirm_case(
        db,
        case_id="nonexistent-id",
        patient_id="patient-1",
        lab_batch_id="batch-1",
        corrected_rows=[],
        test_date_iso="2026-06-01",
    )
    assert result is None


def test_get_case_returns_own(db):
    case = ocr_case_svc.create_case(
        db,
        patient_id="patient-1",
        extracted_rows=[],
        hospital_id=None,
        hospital_confidence=None,
        source_file_hash=None,
        ocr_engine_version=None,
    )
    db.commit()
    found = ocr_case_svc.get_case(db, case_id=case.id, patient_id="patient-1")
    assert found is not None and found.id == case.id


def test_get_case_blocks_other_patient(db):
    case = ocr_case_svc.create_case(
        db,
        patient_id="patient-1",
        extracted_rows=[],
        hospital_id=None,
        hospital_confidence=None,
        source_file_hash=None,
        ocr_engine_version=None,
    )
    db.commit()
    assert ocr_case_svc.get_case(db, case_id=case.id, patient_id="patient-2") is None


def test_create_case_export_status_pending(db):
    case = ocr_case_svc.create_case(
        db,
        patient_id="p",
        extracted_rows=[],
        hospital_id=None,
        hospital_confidence=None,
        source_file_hash=None,
        ocr_engine_version=None,
    )
    assert case.export_status == "pending"


def test_confirm_case_changes_export_status(db):
    case = ocr_case_svc.create_case(
        db,
        patient_id="p",
        extracted_rows=_extracted(),
        hospital_id="vinmec",
        hospital_confidence=0.9,
        source_file_hash=None,
        ocr_engine_version=None,
    )
    db.flush()
    confirmed = ocr_case_svc.confirm_case(
        db,
        case_id=case.id,
        patient_id="p",
        lab_batch_id="b",
        corrected_rows=_corrected(),
        test_date_iso="2026-06-01",
    )
    db.commit()
    assert confirmed.export_status in ("exported", "skipped", "failed")


def test_confirm_case_stores_corrected_rows(db):
    case = ocr_case_svc.create_case(
        db,
        patient_id="p",
        extracted_rows=_extracted(),
        hospital_id=None,
        hospital_confidence=None,
        source_file_hash=None,
        ocr_engine_version=None,
    )
    db.flush()
    ocr_case_svc.confirm_case(
        db,
        case_id=case.id,
        patient_id="p",
        lab_batch_id="b",
        corrected_rows=_corrected(),
        test_date_iso="2026-06-01",
    )
    db.commit()
    db.refresh(case)
    assert len(json.loads(case.corrected_rows_json)) == 2


def test_confirm_case_stores_review_time(db):
    case = ocr_case_svc.create_case(
        db,
        patient_id="p",
        extracted_rows=_extracted(),
        hospital_id=None,
        hospital_confidence=None,
        source_file_hash=None,
        ocr_engine_version=None,
    )
    db.flush()
    confirmed = ocr_case_svc.confirm_case(
        db,
        case_id=case.id,
        patient_id="p",
        lab_batch_id="b",
        corrected_rows=_corrected(),
        test_date_iso="2026-06-01",
        user_review_time_seconds=120.5,
    )
    assert confirmed.user_review_time_seconds == 120.5


def test_confirm_case_editing_rate_one_of_two(db):
    case = ocr_case_svc.create_case(
        db,
        patient_id="p",
        extracted_rows=_extracted(),
        hospital_id=None,
        hospital_confidence=None,
        source_file_hash=None,
        ocr_engine_version=None,
    )
    db.flush()
    confirmed = ocr_case_svc.confirm_case(
        db,
        case_id=case.id,
        patient_id="p",
        lab_batch_id="b",
        corrected_rows=_corrected(),
        test_date_iso="2026-06-01",
    )
    assert confirmed.editing_rate == pytest.approx(0.5, abs=0.01)


def test_confirm_case_gap_report_stored(db):
    case = ocr_case_svc.create_case(
        db,
        patient_id="p",
        extracted_rows=_extracted(),
        hospital_id=None,
        hospital_confidence=None,
        source_file_hash=None,
        ocr_engine_version=None,
    )
    db.flush()
    ocr_case_svc.confirm_case(
        db,
        case_id=case.id,
        patient_id="p",
        lab_batch_id="b",
        corrected_rows=_corrected(),
        test_date_iso="2026-06-01",
    )
    db.commit()
    db.refresh(case)
    gap = json.loads(case.gap_report_json)
    assert "overall_accuracy" in gap
    assert "row_diffs" in gap
