"""
Data Integrity Guardrails — test suite.

Tests:
- biomarker_specs.check_plausibility() unit-checks
- validate_before_save() write-time guardrail (via service layer)
- cleanup script: never deletes, only flags
- original_value is never overwritten by cleanup
"""

from __future__ import annotations

import os
import pytest

# ─── Plausibility checks (pure, no DB) ──────────────────────────────────────

from app.services.biomarker_specs import check_plausibility


class TestCheckPlausibility:
    def test_creatinine_877_umol_is_plausible(self):
        """87.7 µmol/L is valid creatinine in SI unit."""
        result = check_plausibility("creatinine", 87.7, "µmol/L")
        assert result["plausible"] is True
        assert result["suspicious"] is False

    def test_creatinine_099_mgdl_is_plausible(self):
        """0.99 mg/dL is a normal creatinine value (canonical unit)."""
        result = check_plausibility("creatinine", 0.99, "mg/dL")
        assert result["plausible"] is True

    def test_creatinine_877_mgdl_is_suspicious(self):
        """87.7 mg/dL creatinine is physiologically impossible (max ~30) but plausible for µmol/L."""
        result = check_plausibility("creatinine", 87.7, "mg/dL")
        assert result["plausible"] is False
        assert result["suspicious"] is True
        assert "unit mismatch" in result["reason"].lower()

    def test_creatinine_502_mgdl_is_suspicious(self):
        """502 mg/dL creatinine — implausible for mg/dL, plausible for µmol/L."""
        result = check_plausibility("creatinine", 502.0, "mg/dL")
        assert result["plausible"] is False
        assert result["suspicious"] is True

    def test_glucose_502_mgdl_is_plausible(self):
        """502 mg/dL glucose is critically high but physiologically real."""
        result = check_plausibility("fasting_glucose", 502.0, "mg/dL")
        assert result["plausible"] is True
        assert result["suspicious"] is False

    def test_glucose_55_mmol_plausible(self):
        """5.5 mmol/L is normal fasting glucose in SI."""
        result = check_plausibility("fasting_glucose", 5.5, "mmol/L")
        assert result["plausible"] is True

    def test_alt_5000_ul_plausible(self):
        """5000 U/L ALT is extreme but within physiological max."""
        result = check_plausibility("alt", 5000.0, "U/L")
        assert result["plausible"] is True

    def test_alt_20000_ul_implausible(self):
        """20000 U/L ALT is beyond physiological max (15000)."""
        result = check_plausibility("alt", 20000.0, "U/L")
        assert result["plausible"] is False

    def test_unknown_biomarker_is_allowed(self):
        """Unknown biomarker should not be flagged (pass-through)."""
        result = check_plausibility("unknown_marker_xyz", 999.0, "some_unit")
        assert result["plausible"] is True
        assert result["suspicious"] is False
        assert "not validated" in result["reason"]

    def test_cholesterol_800_mgdl_plausible(self):
        """800 mg/dL total cholesterol — within very high but recorded max."""
        result = check_plausibility("total_cholesterol", 800.0, "mg/dL")
        assert result["plausible"] is True

    def test_hdl_300_mgdl_implausible(self):
        """300 mg/dL HDL — beyond physiological max (200 mg/dL)."""
        result = check_plausibility("hdl", 300.0, "mg/dL")
        # 300 mg/dL > alt_max(5.2 mmol/L) AND > si_max(200 mg/dL)?
        # si_unit for HDL is mg/dL, max=200. So 300 > 200 = implausible.
        assert result["plausible"] is False

    def test_creatinine_critical_high_mgdl_plausible(self):
        """28 mg/dL creatinine — at the physiological max boundary."""
        result = check_plausibility("creatinine", 28.0, "mg/dL")
        assert result["plausible"] is True  # exactly at boundary

    def test_creatinine_31_mgdl_suspicious(self):
        """31 mg/dL creatinine — above si_max_plausible (30), plausible as µmol/L."""
        result = check_plausibility("creatinine", 31.0, "mg/dL")
        assert result["plausible"] is False
        assert result["suspicious"] is True


# ─── validate_before_save (unit-level, no DB) ───────────────────────────────

from app.services.lab import validate_before_save


class TestValidateBeforeSave:
    def test_creatinine_877_umol_ok(self):
        """87.7 µmol/L original + correctly normalized 0.99 mg/dL → no flag."""
        result = validate_before_save(
            biomarker_name="creatinine",
            original_value=87.7,
            original_unit="µmol/L",
            normalized_value_si=0.991,
            normalized_unit_si="mg/dL",
        )
        assert result["valid"] is True
        assert result["suspicious"] is False
        assert result["action"] == "save"

    def test_creatinine_877_claiming_mgdl_flagged(self):
        """87.7 claiming to be mg/dL → suspicious flag."""
        result = validate_before_save(
            biomarker_name="creatinine",
            original_value=87.7,
            original_unit="mg/dL",
            normalized_value_si=87.7,
            normalized_unit_si="mg/dL",
        )
        assert result["valid"] is True   # save regardless
        assert result["suspicious"] is True
        assert result["action"] == "flag"

    def test_glucose_502_mgdl_not_flagged(self):
        """Glucose 502 mg/dL is clinically valid — no flag."""
        result = validate_before_save(
            biomarker_name="fasting_glucose",
            original_value=502.0,
            original_unit="mg/dL",
            normalized_value_si=502.0,
            normalized_unit_si="mg/dL",
        )
        assert result["valid"] is True
        assert result["suspicious"] is False

    def test_unknown_biomarker_always_saves(self):
        """Unknown biomarker should always pass through — no flag."""
        result = validate_before_save(
            biomarker_name="mystery_biomarker",
            original_value=999.0,
            original_unit="U/L",
            normalized_value_si=999.0,
            normalized_unit_si="U/L",
        )
        assert result["valid"] is True
        assert result["suspicious"] is False

    def test_always_valid_never_reject(self):
        """validate_before_save must NEVER return valid=False — only flag."""
        # Worst case: completely implausible value
        result = validate_before_save(
            biomarker_name="creatinine",
            original_value=999999.0,
            original_unit="mg/dL",
            normalized_value_si=999999.0,
            normalized_unit_si="mg/dL",
        )
        # Must still be valid (save, don't reject)
        assert result["valid"] is True

    def test_normal_normalized_with_suspicious_original_flagged(self):
        """Even if normalized value looks OK, suspicious original triggers flag."""
        result = validate_before_save(
            biomarker_name="creatinine",
            original_value=87.7,
            original_unit="mg/dL",  # suspicious: 87.7 mg/dL is implausible
            normalized_value_si=0.99,  # normalized might look OK
            normalized_unit_si="mg/dL",
        )
        assert result["suspicious"] is True
        assert result["action"] == "flag"


# ─── Cleanup script safety constraints ──────────────────────────────────────

class TestCleanupScript:
    def test_no_deletion_on_clean_db(self, db):
        """Cleanup on a clean DB should find 0 suspicious records and delete nothing."""
        from scripts.data_integrity_cleanup import run_cleanup
        summary = run_cleanup(dry_run=True)
        assert summary["total_suspicious"] == 0
        assert len(summary["errors"]) == 0

    def test_original_value_never_overwritten(self, db):
        """After apply mode: original_value must remain unchanged."""
        from app.models.clinical import LabDocument, LabResult

        # Create a test LabResult with a 'bad' normalized value
        doc = LabDocument(
            patient_id="00000000-0000-0000-0000-000000000001",
            storage_key="test:integrity",
            file_type="manual",
            ocr_status="done",
            status="manual",
        )
        db.add(doc)
        db.flush()

        row = LabResult(
            patient_id="00000000-0000-0000-0000-000000000001",
            document_id=doc.id,
            test_name="creatinine",
            canonical_name="creatinine",
            value=87.7,
            unit="mg/dL",
            original_value=87.7,    # <-- must never change
            original_unit="mg/dL",  # <-- must never change
            normalized_value_si=87.7,  # bad: should be ~0.99
            normalized_unit_si="mg/dL",
        )
        db.add(row)
        db.commit()

        original_val_before = row.original_value
        original_unit_before = row.original_unit

        from scripts.data_integrity_cleanup import run_cleanup
        run_cleanup(dry_run=False)
        db.refresh(row)

        # CRITICAL: original_value and original_unit must NEVER change
        assert row.original_value == original_val_before
        assert row.original_unit == original_unit_before

        # The corrected normalized value should be re-normalized
        if row.normalized_value_si is not None:
            assert row.normalized_value_si < 5.0, (
                "After correction, creatinine should be < 5 mg/dL (re-normalized from µmol/L)"
            )

        # data_quality_flag should be set
        assert row.data_quality_flag == "flag"

        # Cleanup
        db.delete(row)
        db.delete(doc)
        db.commit()

    def test_no_silent_deletion(self, db):
        """Cleanup script must never delete records."""
        from sqlalchemy import select
        from app.models.clinical import LabResult

        before_count = db.execute(
            select(LabResult).where(LabResult.deleted_at.is_(None))
        ).scalars().all()
        count_before = len(before_count)

        from scripts.data_integrity_cleanup import run_cleanup
        run_cleanup(dry_run=False)

        after_rows = db.execute(
            select(LabResult).where(LabResult.deleted_at.is_(None))
        ).scalars().all()
        count_after = len(after_rows)

        # Must not delete any records
        assert count_after >= count_before, (
            f"Cleanup deleted {count_before - count_after} records! NEVER DELETE."
        )
