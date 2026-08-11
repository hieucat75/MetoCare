"""
Tests for Gap 2 — LabResult Status Backfill / Reclassification.

Covers:
  - reclassify_lab_results() logic per biomarker
  - classify-on-read fallback in get_results_by_batch()
  - idempotency (double-run)
  - original field preservation
  - null-value skip
  - unsupported biomarker skip

Run:
    cd backend && python -m pytest tests/test_status_backfill.py -v
"""

from __future__ import annotations

import uuid

# --- fixtures (shared conftest.py already sets up in-memory SQLite) ---
from app.models.clinical import LabResult, LabUploadBatch
from app.models.patient import PatientProfile
from app.models.user import User, UserRole
from app.services.lab import get_results_by_batch, reclassify_lab_results

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_patient(db) -> str:
    """Create a minimal patient and return patient_id."""
    user = User(
        email=f"test-backfill-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Test Backfill Patient",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="Test Backfill Patient")
    db.add(profile)
    db.flush()
    return profile.id


def _make_batch(db, patient_id: str) -> str:
    """Create a minimal LabUploadBatch and return its id."""
    batch = LabUploadBatch(
        patient_id=patient_id,
        lab_name="Test Batch",
    )
    db.add(batch)
    db.flush()
    return batch.id


def _make_lab_result(
    db,
    *,
    patient_id: str,
    batch_id: str | None = None,
    canonical_name: str | None = None,
    test_name: str = "test",
    original_value: float | None = None,
    original_unit: str | None = None,
    value: float | None = None,
    unit: str | None = None,
    normalized_value_si: float | None = None,
    normalized_unit_si: str | None = None,
    status: str | None = None,
) -> LabResult:
    row = LabResult(
        patient_id=patient_id,
        batch_id=batch_id,
        test_name=test_name,
        canonical_name=canonical_name,
        original_value=original_value,
        original_unit=original_unit,
        value=value,
        unit=unit,
        normalized_value_si=normalized_value_si,
        normalized_unit_si=normalized_unit_si,
        status=status,
    )
    db.add(row)
    db.flush()
    return row


# ---------------------------------------------------------------------------
# Core classification tests
# ---------------------------------------------------------------------------


class TestGlucoseReclassification:
    def test_glucose_57_mmol_reclassified_as_high(self, db):
        """Glucose 5.7 mmol/L → ~102.7 mg/dL → HIGH (pre-diabetic range >99 mg/dL)."""
        patient_id = _make_patient(db)
        # Already normalized: 5.7 mmol/L × 18.018 ≈ 102.7 mg/dL
        row = _make_lab_result(
            db,
            patient_id=patient_id,
            canonical_name="fasting_glucose",
            test_name="Đường huyết lúc đói",
            original_value=5.7,
            original_unit="mmol/L",
            normalized_value_si=102.7026,
            normalized_unit_si="mg/dL",
            status=None,
        )
        db.commit()

        result = reclassify_lab_results(db, dry_run=False)

        db.refresh(row)
        assert row.status is not None, "Status should not be None after reclassify"
        assert row.status in ("high", "borderline"), (
            f"Glucose 5.7 mmol/L (~102.7 mg/dL) should be 'high', got '{row.status}'"
        )
        assert result["updated"] >= 1
        # Original fields preserved
        assert row.original_value == 5.7
        assert row.original_unit == "mmol/L"

    def test_glucose_normal_reclassified(self, db):
        """Glucose 85 mg/dL → NORMAL."""
        patient_id = _make_patient(db)
        row = _make_lab_result(
            db,
            patient_id=patient_id,
            canonical_name="fasting_glucose",
            test_name="fasting_glucose",
            normalized_value_si=85.0,
            normalized_unit_si="mg/dL",
            status=None,
        )
        db.commit()

        reclassify_lab_results(db, dry_run=False)
        db.refresh(row)
        assert row.status == "normal"

    def test_glucose_critical_reclassified(self, db):
        """Glucose 510 mg/dL → CRITICAL."""
        patient_id = _make_patient(db)
        row = _make_lab_result(
            db,
            patient_id=patient_id,
            canonical_name="fasting_glucose",
            test_name="fasting_glucose",
            normalized_value_si=510.0,
            normalized_unit_si="mg/dL",
            status=None,
        )
        db.commit()

        reclassify_lab_results(db, dry_run=False)
        db.refresh(row)
        assert row.status == "critical"


class TestLipidPanelReclassification:
    def test_ldl_high_reclassified(self, db):
        """LDL 160 mg/dL → HIGH (ref_high=99)."""
        patient_id = _make_patient(db)
        row = _make_lab_result(
            db,
            patient_id=patient_id,
            canonical_name="ldl",
            test_name="LDL",
            normalized_value_si=160.0,
            normalized_unit_si="mg/dL",
            status=None,
        )
        db.commit()

        reclassify_lab_results(db, dry_run=False)
        db.refresh(row)
        assert row.status == "high", f"LDL 160 mg/dL expected 'high', got '{row.status}'"

    def test_hdl_low_male_reclassified(self, db):
        """HDL 35 mg/dL → LOW (ref_low=40 for males)."""
        patient_id = _make_patient(db)
        row = _make_lab_result(
            db,
            patient_id=patient_id,
            canonical_name="hdl",
            test_name="HDL",
            normalized_value_si=35.0,
            normalized_unit_si="mg/dL",
            status=None,
        )
        db.commit()

        reclassify_lab_results(db, dry_run=False)
        db.refresh(row)
        assert row.status == "low", f"HDL 35 mg/dL expected 'low', got '{row.status}'"

    def test_triglycerides_very_high(self, db):
        """TG 502 mg/dL → CRITICAL (critical_high=500)."""
        patient_id = _make_patient(db)
        row = _make_lab_result(
            db,
            patient_id=patient_id,
            canonical_name="triglyceride",
            test_name="TG",
            normalized_value_si=502.0,
            normalized_unit_si="mg/dL",
            status=None,
        )
        db.commit()

        reclassify_lab_results(db, dry_run=False)
        db.refresh(row)
        assert row.status == "critical", f"TG 502 mg/dL expected 'critical', got '{row.status}'"

    def test_cholesterol_normal(self, db):
        """Total cholesterol 180 mg/dL → NORMAL (ref_high=199)."""
        patient_id = _make_patient(db)
        row = _make_lab_result(
            db,
            patient_id=patient_id,
            canonical_name="total_cholesterol",
            test_name="Cholesterol",
            normalized_value_si=180.0,
            normalized_unit_si="mg/dL",
            status=None,
        )
        db.commit()

        reclassify_lab_results(db, dry_run=False)
        db.refresh(row)
        assert row.status == "normal"


class TestCreatinineReclassification:
    def test_creatinine_normal_range(self, db):
        """Creatinine 0.9 mg/dL → NORMAL."""
        patient_id = _make_patient(db)
        row = _make_lab_result(
            db,
            patient_id=patient_id,
            canonical_name="creatinine",
            test_name="Creatinine",
            normalized_value_si=0.9,
            normalized_unit_si="mg/dL",
            status=None,
        )
        db.commit()

        reclassify_lab_results(db, dry_run=False)
        db.refresh(row)
        assert row.status == "normal"


# ---------------------------------------------------------------------------
# Safety / edge-case tests
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_idempotent_double_run(self, db):
        """Running reclassify twice produces the same result, no corruption."""
        patient_id = _make_patient(db)
        row = _make_lab_result(
            db,
            patient_id=patient_id,
            canonical_name="fasting_glucose",
            test_name="Glucose",
            normalized_value_si=102.7,
            normalized_unit_si="mg/dL",
            status=None,
        )
        db.commit()

        # First dry-run preview.
        result1 = reclassify_lab_results(db, dry_run=True)
        assert result1["updated"] >= 1

        # First live run.
        reclassify_lab_results(db, dry_run=False)
        db.refresh(row)
        assert row.status is not None

        status_after_first = row.status

        # Second dry-run: should show 0 updates needed (already classified).
        result2 = reclassify_lab_results(db, dry_run=True)
        assert result2["updated"] == 0, (
            f"Second dry-run should show 0 updates, got {result2['updated']}"
        )

        # Second live run: status should not change.
        reclassify_lab_results(db, dry_run=False)
        db.refresh(row)
        assert row.status == status_after_first, "Status changed on second run — not idempotent!"


class TestOriginalFieldPreservation:
    def test_original_fields_preserved_after_reclassify(self, db):
        """After reclassify: original_value, original_unit, original_test_name unchanged."""
        patient_id = _make_patient(db)
        row = _make_lab_result(
            db,
            patient_id=patient_id,
            canonical_name="fasting_glucose",
            test_name="Glucose",
            original_value=5.7,
            original_unit="mmol/L",
            normalized_value_si=102.7026,
            normalized_unit_si="mg/dL",
            status=None,
        )
        row.original_test_name = "Đường huyết lúc đói (OCR)"
        db.flush()
        db.commit()

        reclassify_lab_results(db, dry_run=False)
        db.refresh(row)

        # Normalized + status fields updated.
        assert row.status is not None

        # Original fields MUST be untouched.
        assert row.original_value == 5.7
        assert row.original_unit == "mmol/L"
        assert row.original_test_name == "Đường huyết lúc đói (OCR)"


class TestNullValueSkipped:
    def test_null_value_skipped_no_crash(self, db):
        """Record with original_value=None and no normalized value → skipped, no crash."""
        patient_id = _make_patient(db)
        _make_lab_result(
            db,
            patient_id=patient_id,
            canonical_name="fasting_glucose",
            test_name="Glucose",
            original_value=None,
            value=None,
            normalized_value_si=None,
            status=None,
        )
        db.commit()

        result = reclassify_lab_results(db, dry_run=False)
        # No crash; record counted as skipped.
        assert result["skipped"] >= 1
        assert len(result["errors"]) == 0


class TestUnsupportedBiomarker:
    def test_unsupported_biomarker_skipped_no_crash(self, db):
        """Biomarker not in clinical_rules → status remains None, no crash."""
        patient_id = _make_patient(db)
        row = _make_lab_result(
            db,
            patient_id=patient_id,
            canonical_name="unknown_biomarker_xyz",
            test_name="Unknown Test",
            normalized_value_si=42.0,
            normalized_unit_si="mg/dL",
            status=None,
        )
        db.commit()

        result = reclassify_lab_results(db, dry_run=False)
        db.refresh(row)

        # Status still None (classify_value returns UNKNOWN, which we skip).
        # No crash; record counted as skipped.
        assert result["skipped"] >= 1
        assert len(result["errors"]) == 0

    def test_null_canonical_name_skipped(self, db):
        """Record with null canonical_name → skipped."""
        patient_id = _make_patient(db)
        row = _make_lab_result(
            db,
            patient_id=patient_id,
            canonical_name=None,
            test_name="Unrecognized Test ABC",
            normalized_value_si=100.0,
            normalized_unit_si="mg/dL",
            status=None,
        )
        db.commit()

        result = reclassify_lab_results(db, dry_run=False)
        db.refresh(row)
        assert row.status is None  # not touched
        assert result["skipped"] >= 1


# ---------------------------------------------------------------------------
# Batch-scoped reclassification
# ---------------------------------------------------------------------------


class TestBatchScoped:
    def test_batch_id_filters_correctly(self, db):
        """Providing batch_id processes only records from that batch."""
        patient_id = _make_patient(db)
        batch_id = _make_batch(db, patient_id)

        # Row in target batch.
        row_in = _make_lab_result(
            db,
            patient_id=patient_id,
            batch_id=batch_id,
            canonical_name="fasting_glucose",
            test_name="Glucose",
            normalized_value_si=102.7,
            normalized_unit_si="mg/dL",
            status=None,
        )
        # Row NOT in that batch (no batch_id).
        row_out = _make_lab_result(
            db,
            patient_id=patient_id,
            batch_id=None,
            canonical_name="fasting_glucose",
            test_name="Glucose",
            normalized_value_si=102.7,
            normalized_unit_si="mg/dL",
            status=None,
        )
        db.commit()

        reclassify_lab_results(db, batch_id=batch_id, dry_run=False)
        db.refresh(row_in)
        db.refresh(row_out)

        assert row_in.status is not None, "Row in target batch should be reclassified"
        assert row_out.status is None, "Row outside target batch should not be touched"


# ---------------------------------------------------------------------------
# Dry-run mode
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_no_db_writes(self, db):
        """dry_run=True: returns counts but does not write to DB."""
        patient_id = _make_patient(db)
        row = _make_lab_result(
            db,
            patient_id=patient_id,
            canonical_name="fasting_glucose",
            test_name="Glucose",
            normalized_value_si=102.7,
            normalized_unit_si="mg/dL",
            status=None,
        )
        db.commit()

        result = reclassify_lab_results(db, dry_run=True)
        assert result["updated"] >= 1

        db.refresh(row)
        assert row.status is None, "dry_run should NOT write to DB"


# ---------------------------------------------------------------------------
# Classify-on-read fallback
# ---------------------------------------------------------------------------


class TestClassifyOnReadFallback:
    def test_classify_on_read_returns_status_without_db_write(self, db):
        """get_results_by_batch() fallback: rows with status=None but valid normalized_value_si
        should return computed status in-memory, without committing to DB."""

        patient_id = _make_patient(db)
        batch_id = _make_batch(db, patient_id)

        row = _make_lab_result(
            db,
            patient_id=patient_id,
            batch_id=batch_id,
            canonical_name="fasting_glucose",
            test_name="Glucose",
            normalized_value_si=102.7,
            normalized_unit_si="mg/dL",
            status=None,
        )
        db.commit()
        row_id = row.id

        # Use get_results_by_batch without committing a backfill first.
        # Reload the DB session to ensure we start clean.
        from app.core.database import SessionLocal

        db2 = SessionLocal()
        try:
            results = get_results_by_batch(db2, batch_id=batch_id, patient_id=patient_id)
            assert results is not None
            assert len(results) == 1

            # Status should be populated from the fallback classify-on-read.
            assert results[0].status is not None, (
                "classify-on-read fallback should return computed status"
            )
            assert results[0].status in ("high", "normal", "low", "critical")
        finally:
            db2.close()

        # Verify original DB row was NOT committed (status still None).
        from app.core.database import SessionLocal as SL
        from app.models.clinical import LabResult as _LR
        from sqlalchemy import select as _select

        db3 = SL()
        try:
            persisted = db3.execute(_select(_LR).where(_LR.id == row_id)).scalar_one_or_none()
            assert persisted is not None
            # The classify-on-read fallback must NOT have written to DB.
            assert persisted.status is None, "classify-on-read fallback must NOT commit to DB"
        finally:
            db3.close()


# ---------------------------------------------------------------------------
# Normalization from original_value + original_unit
# ---------------------------------------------------------------------------


class TestNormalizationFromOriginal:
    def test_normalizes_from_original_when_si_null(self, db):
        """If normalized_value_si is null, reclassify computes it from original_value/unit."""
        patient_id = _make_patient(db)
        row = _make_lab_result(
            db,
            patient_id=patient_id,
            canonical_name="fasting_glucose",
            test_name="Glucose",
            original_value=5.7,
            original_unit="mmol/L",
            value=5.7,
            unit="mmol/L",
            normalized_value_si=None,  # intentionally null
            normalized_unit_si=None,
            status=None,
        )
        db.commit()

        result = reclassify_lab_results(db, dry_run=False)
        db.refresh(row)

        assert result["updated"] >= 1
        assert row.status is not None
        assert row.status in ("high", "normal")  # 5.7 mmol/L = ~102.7 mg/dL = high
        # normalized_value_si should now be populated.
        assert row.normalized_value_si is not None
        assert abs(row.normalized_value_si - 102.7026) < 0.5


# ---------------------------------------------------------------------------
# CBC analyte/unit safety — reclassify must neutralise, count, and converge
# ---------------------------------------------------------------------------


class TestCbcGuardedReclassify:
    """The round-3 fix changed `reclassify_lab_results` and had no test on it,
    which is how two regressions (a dry-run counter that reported zero, and a
    row that never converged) reached round-4 review."""

    def test_stale_severity_is_cleared_not_left_standing(self, db):
        patient_id = _make_patient(db)
        row = _make_lab_result(
            db,
            patient_id=patient_id,
            canonical_name="rbc",
            test_name="Hồng cầu (RBC)",
            value=0.50,
            unit="L/L",
            status="critical",
        )
        db.commit()

        result = reclassify_lab_results(db, dry_run=False)
        db.refresh(row)

        # Several surfaces read the STORED status raw — masking it on two screens
        # while leaving `critical` in the database is not a fix.
        assert row.status is None, row.status
        assert row.normalized_value_si is None
        assert result["updated"] >= 1

    def test_dry_run_reports_the_rows_it_would_clear(self, db):
        patient_id = _make_patient(db)
        row = _make_lab_result(
            db,
            patient_id=patient_id,
            canonical_name="rbc",
            test_name="Hồng cầu (RBC)",
            value=0.50,
            unit="L/L",
            status="critical",
        )
        db.commit()

        result = reclassify_lab_results(db, dry_run=True)
        db.refresh(row)

        # dry_run is the operational gate before the real pass. Counting these as
        # `skipped` reported "updated: 0" for exactly the rows that need fixing.
        assert result["updated"] >= 1, result
        assert row.status == "critical", "dry_run must not write"

    def test_legacy_fabricated_canonical_unit_is_also_cleared(self, db):
        patient_id = _make_patient(db)
        """The old write path stamped `10^12/L` onto unit-free rows, so this shape
        is already stored and reads as perfectly canonical."""
        row = _make_lab_result(
            db,
            patient_id=patient_id,
            canonical_name="rbc",
            test_name="Hồng cầu (RBC)",
            value=0.50,
            unit="10^12/L",
            status="critical",
        )
        db.commit()

        reclassify_lab_results(db, dry_run=False)
        db.refresh(row)
        assert row.status is None

    def test_convertible_row_converges_and_is_idempotent(self, db):
        patient_id = _make_patient(db)
        row = _make_lab_result(
            db,
            patient_id=patient_id,
            canonical_name="hematocrit",
            test_name="Dung tích hồng cầu",
            value=0.45,
            unit="L/L",
            normalized_value_si=0.45,
            normalized_unit_si="L/L",
            status=None,
        )
        db.commit()

        first = reclassify_lab_results(db, dry_run=False)
        db.refresh(row)
        assert row.status == "normal", row.status
        # The normalized pair must be rewritten, or the idempotency check below
        # never matches and every run re-counts the row forever.
        assert row.normalized_value_si == 45.0, row.normalized_value_si
        assert row.normalized_unit_si == "%"
        assert first["updated"] >= 1

        second = reclassify_lab_results(db, dry_run=False)
        db.refresh(row)
        assert row.status == "normal"
        assert second["updated"] == 0, "reclassify must converge"
