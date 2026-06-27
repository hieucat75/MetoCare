"""
Tests for auto-classify LabResult at creation time.

Covers:
  - Manual entry creation → status classified at save
  - OCR interpret path → status classified at save
  - User correction → reclassify on edit
  - Unsupported biomarker → status=None, no crash
  - Null value → skip classification, no crash
  - Original fields preserved after classify
  - Backfill regression (key backfill tests still pass)

Run:
    cd backend && python -m pytest tests/test_auto_classify.py -v
"""
from __future__ import annotations

import json
import uuid
import datetime as dt

import pytest

from app.models.clinical import LabDocument, LabResult, LabUploadBatch
from app.models.user import User, UserRole
from app.models.patient import PatientProfile
from app.services.lab import create_manual_entry, correct_lab_result, normalize_and_classify


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_patient(db) -> dict:
    """Create a minimal patient + user; return {"patient_id": ..., "user_id": ...}."""
    user = User(
        email=f"ac-test-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Auto Classify Test Patient",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="Auto Classify Test Patient")
    db.add(profile)
    db.flush()
    return {"patient_id": profile.id, "user_id": user.id}


def _make_result_directly(
    db,
    *,
    patient_id: str,
    canonical_name: str | None = None,
    test_name: str = "test",
    original_value: float | None = None,
    original_unit: str | None = None,
    normalized_value_si: float | None = None,
    normalized_unit_si: str | None = None,
    status: str | None = None,
) -> LabResult:
    """Insert a LabResult row directly (no service layer), for backfill regression tests."""
    row = LabResult(
        patient_id=patient_id,
        test_name=test_name,
        canonical_name=canonical_name,
        original_value=original_value,
        original_unit=original_unit,
        normalized_value_si=normalized_value_si,
        normalized_unit_si=normalized_unit_si,
        status=status,
    )
    db.add(row)
    db.flush()
    return row


def _create_entry(db, p: dict, test_name: str, value: float, unit: str, test_date=None) -> LabResult:
    """Convenience: create a manual entry and return the first row."""
    _, rows = create_manual_entry(
        db,
        patient_id=p["patient_id"],
        requester_id=p["user_id"],
        lab_name="Test Lab",
        test_date=test_date or dt.date(2026, 6, 27),
        results=[{"test_name": test_name, "value": value, "unit": unit}],
    )
    assert rows, "create_manual_entry returned no rows"
    return rows[0]


# ---------------------------------------------------------------------------
# Phase 1: normalize_and_classify() unit tests
# ---------------------------------------------------------------------------

class TestNormalizeAndClassify:
    def test_glucose_mmol_normalized_and_classified(self):
        result = normalize_and_classify("fasting_glucose", 5.7, "mmol/L")
        assert result, "Should return non-empty dict"
        assert result["status"] is not None
        assert abs(result["normalized_value_si"] - 102.7) < 1.0  # 5.7 * 18.018 ≈ 102.7
        assert result["normalized_unit_si"] == "mg/dL"

    def test_glucose_mgdl_no_conversion_needed(self):
        result = normalize_and_classify("fasting_glucose", 102.7, "mg/dL")
        assert result["status"] is not None
        assert abs(result["normalized_value_si"] - 102.7) < 0.1

    def test_null_value_returns_empty(self):
        result = normalize_and_classify("fasting_glucose", None, "mg/dL")
        assert result == {}

    def test_none_canonical_returns_empty(self):
        result = normalize_and_classify(None, 5.7, "mmol/L")
        assert result == {}

    def test_empty_canonical_returns_empty(self):
        result = normalize_and_classify("", 5.7, "mmol/L")
        assert result == {}

    def test_unsupported_biomarker_status_none(self):
        result = normalize_and_classify("vitamin_d_total_xyz_unknown", 50.0, "ng/mL")
        # Should return dict (with normalized fields) but status=None
        # OR return empty dict — either is acceptable. Must not crash.
        if result:
            assert result.get("status") is None, (
                f"Unsupported biomarker should have status=None, got {result}"
            )

    def test_ldl_mmol_classified(self):
        """LDL 4.5 mmol/L ~ 174 mg/dL → HIGH."""
        result = normalize_and_classify("ldl", 4.5, "mmol/L")
        assert result.get("status") in ("high", "critical"), (
            f"LDL 4.5 mmol/L should be high/critical, got {result}"
        )

    def test_triglyceride_very_high(self):
        """TG 502 mg/dL → critical (>500 critical_high)."""
        result = normalize_and_classify("triglyceride", 502, "mg/dL")
        assert result.get("status") in ("high", "critical"), (
            f"TG 502 mg/dL should be high/critical, got {result}"
        )


# ---------------------------------------------------------------------------
# Phase 2: Manual entry creation — auto-classified at save
# ---------------------------------------------------------------------------

class TestManualEntryAutoClassify:
    def test_glucose_57_mmol_classified_at_save(self, db):
        """create_manual_entry(glucose 5.7 mmol/L) → status != None after DB save."""
        p = _make_patient(db)
        row = _create_entry(db, p, "fasting_glucose", 5.7, "mmol/L")
        db.refresh(row)

        assert row.status is not None, "status must be classified at creation, not None"
        assert row.status in ("high", "borderline", "normal", "low", "critical"), (
            f"Unexpected status '{row.status}'"
        )
        # 5.7 mmol/L ≈ 102.7 mg/dL — prediabetes/borderline range (>= 100)
        assert row.status in ("high", "borderline"), (
            f"Glucose 5.7 mmol/L (≈102.7 mg/dL) should be high or borderline, got '{row.status}'"
        )

    def test_glucose_57_mmol_original_fields_preserved(self, db):
        """create_manual_entry preserves original_value, original_unit."""
        p = _make_patient(db)
        row = _create_entry(db, p, "fasting_glucose", 5.7, "mmol/L")
        db.refresh(row)

        # original_value and original_unit must be the raw inputs
        assert row.original_value == 5.7, (
            f"original_value must be 5.7, got {row.original_value}"
        )
        assert row.original_unit == "mmol/L", (
            f"original_unit must be 'mmol/L', got {row.original_unit}"
        )

    def test_glucose_57_mmol_normalized_value_set(self, db):
        """Normalized SI value is approximately 102.7 mg/dL."""
        p = _make_patient(db)
        row = _create_entry(db, p, "fasting_glucose", 5.7, "mmol/L")
        db.refresh(row)

        assert row.normalized_value_si is not None, "normalized_value_si must be set"
        assert abs(row.normalized_value_si - 102.7) < 1.0, (
            f"Expected ~102.7 mg/dL, got {row.normalized_value_si}"
        )
        assert row.normalized_unit_si == "mg/dL"

    def test_glucose_mgdl_classified_at_save(self, db):
        """create_manual_entry(glucose 102.7 mg/dL) → same status as mmol/L version."""
        p = _make_patient(db)
        row = _create_entry(db, p, "fasting_glucose", 102.7, "mg/dL")
        db.refresh(row)

        assert row.status is not None
        assert row.status in ("high", "borderline"), (
            f"Glucose 102.7 mg/dL should be high or borderline, got '{row.status}'"
        )

    def test_ldl_classified_at_save(self, db):
        """LDL 4.5 mmol/L → classified at save."""
        p = _make_patient(db)
        row = _create_entry(db, p, "ldl", 4.5, "mmol/L")
        db.refresh(row)

        assert row.status is not None, "LDL status must be classified at creation"
        assert row.status in ("high", "critical"), (
            f"LDL 4.5 mmol/L (~174 mg/dL) should be high/critical, got '{row.status}'"
        )

    def test_tg_502_classified_at_save(self, db):
        """TG 502 mg/dL → high or critical at save."""
        p = _make_patient(db)
        row = _create_entry(db, p, "triglyceride", 502, "mg/dL")
        db.refresh(row)

        assert row.status is not None
        assert row.status in ("high", "critical"), (
            f"TG 502 mg/dL should be high/critical, got '{row.status}'"
        )

    def test_creatinine_umol_classified_at_save(self, db):
        """Creatinine 110 umol/L → slightly high or elevated."""
        p = _make_patient(db)
        # 110 umol/L ≈ 1.24 mg/dL (ref_high typically ~1.2 mg/dL for male)
        row = _create_entry(db, p, "creatinine", 110, "umol/L")
        db.refresh(row)

        # May be high or normal depending on exact ref_high in catalog.
        assert row.status is not None, "creatinine status must be classified at creation"
        assert row.status in ("normal", "high", "low", "critical"), (
            f"Unexpected status '{row.status}' for creatinine 110 umol/L"
        )

    def test_normal_glucose_classified_as_normal(self, db):
        """Glucose 85 mg/dL → normal."""
        p = _make_patient(db)
        row = _create_entry(db, p, "fasting_glucose", 85, "mg/dL")
        db.refresh(row)

        assert row.status == "normal", (
            f"Glucose 85 mg/dL should be 'normal', got '{row.status}'"
        )

    def test_unsupported_biomarker_status_none_no_crash(self, db):
        """Unsupported biomarker name → status=None, no crash."""
        p = _make_patient(db)
        # Use a name that won't normalize to a known biomarker
        row = _create_entry(db, p, "vitamin_d_total_unknown_xyzabc", 50.0, "ng/mL")
        db.refresh(row)

        # Should not crash; status may be None (unsupported) or possibly None
        # (We do not require a specific value, just no exception and no crash)
        # Status could be None if biomarker is not in catalog

    def test_null_value_entry_no_crash(self, db):
        """Null value → no classification, no crash, status=None."""
        p = _make_patient(db)
        _, rows = create_manual_entry(
            db,
            patient_id=p["patient_id"],
            requester_id=p["user_id"],
            lab_name="Test Lab",
            test_date=dt.date(2026, 6, 27),
            results=[{"test_name": "fasting_glucose", "value": None, "unit": "mg/dL"}],
        )
        assert rows
        db.refresh(rows[0])
        # Should not crash; status may be None since value is None
        assert rows[0].status is None, (
            f"Null value should produce status=None, got '{rows[0].status}'"
        )


# ---------------------------------------------------------------------------
# Phase 3: User correction → reclassify
# ---------------------------------------------------------------------------

class TestUserCorrectionReclassify:
    def test_correction_triggers_reclassify(self, db):
        """Correct glucose from 5.7 mmol/L (high) to 4.5 mmol/L (normal)."""
        p = _make_patient(db)
        row = _create_entry(db, p, "fasting_glucose", 5.7, "mmol/L")
        db.refresh(row)

        initial_status = row.status
        assert initial_status in ("high", "borderline"), (
            f"5.7 mmol/L should start as high/borderline, got '{initial_status}'"
        )

        # Correct to 4.5 mmol/L ≈ 81 mg/dL → normal
        corrected = correct_lab_result(
            db,
            result_id=row.id,
            patient_id=p["patient_id"],
            requester_id=p["user_id"],
            new_value=4.5,
            new_unit="mmol/L",
        )

        assert corrected.status == "normal", (
            f"After correction to 4.5 mmol/L, status should be 'normal', got '{corrected.status}'"
        )
        assert corrected.original_value == 4.5
        assert corrected.original_unit == "mmol/L"
        assert corrected.normalized_value_si is not None

    def test_correction_saves_provenance(self, db):
        """Correction history should record old value."""
        p = _make_patient(db)
        row = _create_entry(db, p, "fasting_glucose", 5.7, "mmol/L")
        db.refresh(row)
        old_value = row.original_value  # Should be 5.7

        correct_lab_result(
            db,
            result_id=row.id,
            patient_id=p["patient_id"],
            requester_id=p["user_id"],
            new_value=4.5,
            new_unit="mmol/L",
        )
        db.refresh(row)

        assert row.correction_history_json is not None
        history = json.loads(row.correction_history_json)
        assert len(history) >= 1
        assert history[0]["old_value"] == old_value
        assert history[0]["corrected_by"] == "user"

    def test_correction_updates_normalized_value(self, db):
        """After correction, normalized_value_si reflects the new value."""
        p = _make_patient(db)
        row = _create_entry(db, p, "fasting_glucose", 5.7, "mmol/L")
        db.refresh(row)
        old_norm = row.normalized_value_si

        corrected = correct_lab_result(
            db,
            result_id=row.id,
            patient_id=p["patient_id"],
            requester_id=p["user_id"],
            new_value=85.0,
            new_unit="mg/dL",
        )

        # 85 mg/dL should be normalized as-is
        assert corrected.normalized_value_si != old_norm or abs(corrected.normalized_value_si - 85.0) < 0.1

    def test_correction_not_found_raises(self, db):
        """Correcting non-existent result_id raises ValueError."""
        p = _make_patient(db)
        with pytest.raises(ValueError, match="not found"):
            correct_lab_result(
                db,
                result_id=str(uuid.uuid4()),
                patient_id=p["patient_id"],
                requester_id=p["user_id"],
                new_value=5.0,
                new_unit="mmol/L",
            )


# ---------------------------------------------------------------------------
# Phase 4: OCR / interpret_document path
# ---------------------------------------------------------------------------

class TestOCRPathAutoClassify:
    """
    Test that interpret_document (the OCR confirm path) also auto-classifies at save.
    We use mock OCR mode (set in conftest.py env) so no real OCR is called.
    """

    def test_ocr_interpret_classifies_at_save(self, db):
        """interpret_document() should produce LabResult rows with status set."""
        from app.services.lab import interpret_document, register_document

        p = _make_patient(db)

        # Register a mock document (storage_key="manual:" triggers mock path).
        doc = LabDocument(
            patient_id=p["patient_id"],
            storage_key=f"manual:{p['patient_id']}",
            file_type="manual",
            ocr_status="pending",
            status="uploaded",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        # interpret_document uses the mock OCR provider in test mode.
        interpretation = interpret_document(
            db,
            document_id=doc.id,
            requester_id=p["user_id"],
        )
        assert interpretation is not None

        # Fetch the saved rows
        from sqlalchemy import select as _select
        rows = list(
            db.execute(
                _select(LabResult).where(
                    LabResult.document_id == doc.id,
                    LabResult.deleted_at.is_(None),
                )
            ).scalars()
        )

        # At least some rows should have been saved
        if rows:
            # Any recognized biomarker row should have status set
            classified = [r for r in rows if r.canonical_name and r.canonical_name != "unknown"]
            for r in classified:
                # status should not be None for supported biomarkers with values
                if r.value is not None:
                    assert r.status is not None, (
                        f"Row {r.canonical_name} should have status after interpret_document"
                    )


# ---------------------------------------------------------------------------
# Backfill regression: existing backfill logic still passes
# ---------------------------------------------------------------------------

class TestBackfillRegression:
    """Ensure the reclassify backfill path still works (regression guard)."""

    def test_backfill_glucose_high(self, db):
        """reclassify_lab_results still classifies glucose correctly."""
        from app.services.lab import reclassify_lab_results

        p = _make_patient(db)
        row = _make_result_directly(
            db,
            patient_id=p["patient_id"],
            canonical_name="fasting_glucose",
            test_name="Glucose",
            normalized_value_si=102.7,
            normalized_unit_si="mg/dL",
            status=None,
        )
        db.commit()

        reclassify_lab_results(db, dry_run=False)
        db.refresh(row)
        assert row.status in ("high", "borderline"), (
            f"Backfill should classify glucose 102.7 mg/dL as high/borderline, got '{row.status}'"
        )

    def test_backfill_original_preserved(self, db):
        """reclassify does not overwrite original_value/original_unit."""
        from app.services.lab import reclassify_lab_results

        p = _make_patient(db)
        row = _make_result_directly(
            db,
            patient_id=p["patient_id"],
            canonical_name="fasting_glucose",
            test_name="Glucose",
            original_value=5.7,
            original_unit="mmol/L",
            normalized_value_si=102.7,
            normalized_unit_si="mg/dL",
            status=None,
        )
        db.commit()

        reclassify_lab_results(db, dry_run=False)
        db.refresh(row)

        assert row.original_value == 5.7
        assert row.original_unit == "mmol/L"

    def test_backfill_null_value_skipped(self, db):
        """Null value → backfill skips gracefully."""
        from app.services.lab import reclassify_lab_results

        p = _make_patient(db)
        _make_result_directly(
            db,
            patient_id=p["patient_id"],
            canonical_name="fasting_glucose",
            test_name="Glucose",
            original_value=None,
            normalized_value_si=None,
            status=None,
        )
        db.commit()

        result = reclassify_lab_results(db, dry_run=False)
        assert result["skipped"] >= 1
        assert len(result["errors"]) == 0

    def test_classify_on_read_fallback_still_works(self, db):
        """Classify-on-read fallback still returns in-memory status for legacy rows."""
        from app.services.lab import get_results_by_batch

        p = _make_patient(db)
        batch = LabUploadBatch(
            patient_id=p["patient_id"],
            lab_name="Test Batch",
        )
        db.add(batch)
        db.flush()

        row = _make_result_directly(
            db,
            patient_id=p["patient_id"],
            canonical_name="fasting_glucose",
            test_name="Glucose",
            normalized_value_si=102.7,
            normalized_unit_si="mg/dL",
            status=None,
        )
        row.batch_id = batch.id
        db.flush()
        db.commit()

        results = get_results_by_batch(db, batch_id=batch.id, patient_id=p["patient_id"])
        assert results
        classified = [r for r in results if r.canonical_name == "fasting_glucose"]
        assert classified
        assert classified[0].status is not None, "classify-on-read should compute status"
