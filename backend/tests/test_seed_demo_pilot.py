"""Tests for seed_demo_pilot.py — transaction safety (Task A) and
production guard (Task B).

Uses the same SQLite-backed `db` fixture as the rest of the test suite.
The seed script is loaded via importlib so sys.path manipulation inside
the script runs at import time without polluting this module.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from app.models.clinical import HealthMetric, LabResult, Medication
from app.models.patient import PatientProfile
from app.models.user import User
from sqlalchemy import select

# ---------------------------------------------------------------------------
# Load the script module without executing __main__
# ---------------------------------------------------------------------------
_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "seed_demo_pilot.py"
_spec = importlib.util.spec_from_file_location("seed_demo_pilot", _SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

seed = _mod.seed
_check_not_production = _mod._check_not_production


# ---------------------------------------------------------------------------
# Task B — Production guard
# ---------------------------------------------------------------------------


class TestProductionGuard:
    def test_blocks_production_env(self):
        with patch.dict(os.environ, {"ENV": "production"}, clear=False):
            os.environ.pop("ALLOW_DEMO_SEED", None)
            with pytest.raises(RuntimeError, match="refused to run against production"):
                _check_not_production()

    def test_blocks_production_allow_false(self):
        with patch.dict(os.environ, {"ENV": "production", "ALLOW_DEMO_SEED": "false"}):
            with pytest.raises(RuntimeError, match="refused to run against production"):
                _check_not_production()

    def test_allows_production_with_override(self):
        with patch.dict(os.environ, {"ENV": "production", "ALLOW_DEMO_SEED": "true"}):
            _check_not_production()  # must not raise

    def test_allows_staging_env(self):
        with patch.dict(os.environ, {"ENV": "staging"}):
            _check_not_production()  # must not raise

    def test_allows_test_env(self):
        with patch.dict(os.environ, {"ENV": "test"}):
            _check_not_production()  # must not raise

    def test_allows_missing_env_var(self):
        env_without = {k: v for k, v in os.environ.items() if k not in ("ENV", "ALLOW_DEMO_SEED")}
        with patch.dict(os.environ, env_without, clear=True):
            _check_not_production()  # must not raise

    def test_error_message_includes_override_instruction(self):
        with patch.dict(os.environ, {"ENV": "production"}, clear=False):
            os.environ.pop("ALLOW_DEMO_SEED", None)
            with pytest.raises(RuntimeError, match="ALLOW_DEMO_SEED=true"):
                _check_not_production()

    def test_seed_calls_guard_before_db(self, db):
        """seed() must invoke the production guard before touching the DB."""
        with patch.dict(os.environ, {"ENV": "production"}, clear=False):
            os.environ.pop("ALLOW_DEMO_SEED", None)
            with pytest.raises(RuntimeError, match="refused to run"):
                seed(db)
        # No pilot patients should have been created
        pilot_phones = [row[0] for row in _mod.PILOT_PATIENTS]
        users = db.execute(
            select(User).where(User.phone.in_(pilot_phones))
        ).scalars().all()
        assert len(users) == 0


# ---------------------------------------------------------------------------
# Task A — Transaction safety & idempotency
# ---------------------------------------------------------------------------


class TestSeedIdempotency:
    """All tests in this class call seed() and observe the cumulative SQLite state.

    Because the db fixture does not rollback between tests, the seed is additive:
    the first call that actually inserts rows will return counts; later calls
    see existing rows and return 0 (idempotent). Tests are written to remain
    correct regardless of execution order.
    """

    def test_seed_creates_all_patients_and_data(self, db):
        """Single comprehensive first-run check: 10 patients, expected counts."""
        # Collect what the db already has before this test runs
        existing_phones = {
            u.phone for u in db.execute(select(User)).scalars()
        }
        pilot_phones = {row[0] for row in _mod.PILOT_PATIENTS}
        already_seeded = pilot_phones & existing_phones

        result = seed(db)

        expected_new = 10 - len(already_seeded)
        assert len(result["patients_created"]) == expected_new
        assert len(result["patients_skipped"]) == len(already_seeded)
        assert result["patients_failed"] == []

        # All 10 pilot users must exist in the DB regardless of whether
        # they were just created or already present
        users = db.execute(
            select(User).where(User.phone.in_(pilot_phones))
        ).scalars().all()
        assert len(users) == 10

        # Get profile IDs for pilot patients
        pilot_profile_ids = set()
        for ph in pilot_phones:
            profile = db.execute(
                select(PatientProfile).join(User, PatientProfile.user_id == User.id)
                .where(User.phone == ph)
            ).scalar_one_or_none()
            if profile:
                pilot_profile_ids.add(profile.id)

        metric_count = len(db.execute(
            select(HealthMetric).where(HealthMetric.patient_id.in_(pilot_profile_ids))
        ).scalars().all())
        lab_count = len(db.execute(
            select(LabResult).where(LabResult.patient_id.in_(pilot_profile_ids))
        ).scalars().all())
        med_count = len(db.execute(
            select(Medication).where(Medication.patient_id.in_(pilot_profile_ids))
        ).scalars().all())

        assert metric_count >= 960
        assert lab_count == 84
        assert med_count == 35

    def test_second_run_is_no_op(self, db):
        """Two consecutive seed() calls: second returns zero new records."""
        seed(db)      # ensure fully seeded
        result2 = seed(db)

        assert len(result2["patients_created"]) == 0
        assert len(result2["patients_skipped"]) == 10
        assert result2["patients_failed"] == []
        assert result2["metrics"] == 0
        assert result2["lab_results"] == 0
        assert result2["medications"] == 0
        assert result2["adherence_records"] == 0


class TestTransactionSafety:
    """Verify per-patient savepoint behavior using isolated test patients.

    These tests use phone numbers in the +84999999XXX range that are not
    in PILOT_PATIENTS, ensuring they are unaffected by idempotency tests
    that run earlier in the same SQLite session.
    """

    # Isolated patients used only by this class
    _PHONE_A = "+84999999001"
    _PHONE_B = "+84999999002"
    _PHONE_C = "+84999999003"

    def _mini_patients(self, phones: list[str]) -> list[tuple]:
        """Build minimal PILOT_PATIENTS-compatible rows for isolated phones."""
        names = [f"Test Patient {i+1}" for i, _ in enumerate(phones)]
        return [
            (
                phone, "TestPass1!", name,
                "1990-01-01", "male",
                170.0, 70.0, 80.0, "low",
                "Không có", "Không có", "Không có", "Không có",
            )
            for phone, name in zip(phones, names, strict=False)
        ]

    def _seed_mini(self, db, phones: list[str], patch_fn=None):
        """Seed a minimal patient set (no METRIC/LAB/MED specs) with optional lab mock."""
        original_pilot = _mod.PILOT_PATIENTS
        original_metric = _mod.METRIC_SPECS
        original_lab = _mod.LAB_SPECS
        original_med = _mod.MED_SPECS
        _mod.PILOT_PATIENTS = self._mini_patients(phones)
        _mod.METRIC_SPECS = {}
        _mod.LAB_SPECS = {}
        _mod.MED_SPECS = {}
        try:
            if patch_fn:
                with patch.object(_mod, "_seed_labs", side_effect=patch_fn):
                    result = seed(db)
            else:
                result = seed(db)
        finally:
            _mod.PILOT_PATIENTS = original_pilot
            _mod.METRIC_SPECS = original_metric
            _mod.LAB_SPECS = original_lab
            _mod.MED_SPECS = original_med
        return result

    def test_savepoint_rolls_back_failed_patient_data(self, db):
        """A lab-seeding failure must roll back that patient's savepoint.

        Strategy: inject a real LabResult inside _seed_labs for patient B,
        then raise. The savepoint should undo the insert — patient B has 0 labs.
        Patient A (succeeds) and patient C (succeeds) are unaffected.
        """
        phones = [self._PHONE_A, self._PHONE_B, self._PHONE_C]

        def inject_then_fail(inner_db, patient_id, phone, now):
            if phone == self._PHONE_B:
                # Insert a lab result then raise — savepoint must undo this
                inner_db.add(LabResult(
                    patient_id=patient_id,
                    test_name="Glucose",
                    canonical_name="fasting_glucose",
                    value=100.0,
                    unit="mg/dL",
                    reference_range="70-99",
                    status="normal",
                    test_date=now.date(),
                    ocr_confidence=1.0,
                    verified_by_user=True,
                    verified_by_doctor=False,
                ))
                raise ValueError("forced failure for B")
            return 0  # A and C: no labs

        result = self._seed_mini(db, phones, patch_fn=inject_then_fail)

        assert len(result["patients_failed"]) == 1
        assert result["patients_failed"][0]["name"] == "Test Patient 2"

        # Patient B's user still exists (auth.register is irreversible)
        user_b = db.execute(
            select(User).where(User.phone == self._PHONE_B)
        ).scalar_one()
        assert user_b is not None

        # Patient B has no lab results (savepoint rolled back the insert)
        profile_b = db.execute(
            select(PatientProfile).where(PatientProfile.user_id == user_b.id)
        ).scalar_one()
        labs_b = db.execute(
            select(LabResult).where(LabResult.patient_id == profile_b.id)
        ).scalars().all()
        assert len(labs_b) == 0

    def test_rerun_recovers_failed_patient(self, db):
        """After a partial-seed crash, re-running seeds the missing patient."""
        # Use distinct phones so previous tests don't interfere
        phones = ["+84999999011", "+84999999012"]
        original_pilot = _mod.PILOT_PATIENTS
        original_metric = _mod.METRIC_SPECS
        original_lab = _mod.LAB_SPECS
        original_med = _mod.MED_SPECS
        _mod.PILOT_PATIENTS = self._mini_patients(phones)
        _mod.METRIC_SPECS = {}
        _mod.MED_SPECS = {}

        # First run: patient 2 gets a lab failure
        # Give patient 2 one lab spec so _seed_labs is called
        _mod.LAB_SPECS = {
            phones[1]: [[("FBG", "fasting_glucose", 99.0, "mg/dL", "70-99", "normal")]]
        }
        call_count = {"n": 0}
        original_seed_labs = _mod._seed_labs

        def fail_second_call(inner_db, patient_id, phone, now):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("transient error")
            return original_seed_labs(inner_db, patient_id, phone, now)

        try:
            with patch.object(_mod, "_seed_labs", side_effect=fail_second_call):
                r1 = seed(db)

            assert len(r1["patients_failed"]) == 1

            # Second run without mock — patient 2's labs seeded
            r2 = seed(db)
            assert r2["patients_failed"] == []
            assert r2["lab_results"] > 0  # labs inserted for the previously-failed patient
        finally:
            _mod.PILOT_PATIENTS = original_pilot
            _mod.METRIC_SPECS = original_metric
            _mod.LAB_SPECS = original_lab
            _mod.MED_SPECS = original_med

    def test_patients_failed_entry_includes_name_and_error(self, db):
        """patients_failed list carries both name and error string."""
        phones = ["+84999999021"]
        # Save originals BEFORE mutating
        orig_pilot = _mod.PILOT_PATIENTS
        orig_metric = _mod.METRIC_SPECS
        orig_lab = _mod.LAB_SPECS
        orig_med = _mod.MED_SPECS
        _mod.PILOT_PATIENTS = self._mini_patients(phones)
        _mod.METRIC_SPECS = {}
        _mod.LAB_SPECS = {}
        _mod.MED_SPECS = {}

        def always_fail(inner_db, patient_id, phone, now):
            raise RuntimeError("quota exceeded")

        try:
            with patch.object(_mod, "_seed_labs", side_effect=always_fail):
                result = seed(db)
        finally:
            _mod.PILOT_PATIENTS = orig_pilot
            _mod.METRIC_SPECS = orig_metric
            _mod.LAB_SPECS = orig_lab
            _mod.MED_SPECS = orig_med

        assert any(e["name"] == "Test Patient 1" for e in result["patients_failed"])
        assert any("quota exceeded" in e["error"] for e in result["patients_failed"])
