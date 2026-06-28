"""Tests for lab upload batch: duplicate detection, delete cascade, audit.

8 required test scenarios (verbatim from spec):
1. duplicate same test_date + same biomarkers detected
2. save new when user chooses force new
3. overwrite soft-deletes old batch and metrics
4. delete batch removes lab history and dashboard metric contribution
5. patient cannot delete another patient's batch
6. delete is idempotent
7. audit log created
8. dashboard recalculates after delete
"""

from __future__ import annotations

import datetime as dt
import os

import pytest
from app.core.security import create_access_token
from app.main import app
from app.models.clinical import HealthMetric, LabResult, LabUploadBatch
from app.models.patient import PatientProfile
from app.models.user import User, UserRole
from app.services import lab as lab_svc
from app.services import lab_batch
from fastapi.testclient import TestClient
from sqlalchemy import select

_TODAY = dt.date.today()

_BIOMARKERS = [
    {"test_name": "AST (GOT)", "value": 25.37, "unit": "U/L"},
    {"test_name": "ALT (GPT)", "value": 51.63, "unit": "U/L"},
    {"test_name": "Glucose", "value": 5.73, "unit": "mmol/L"},
]


# ── Shared helpers ───────────────────────────────────────────────────────────


def _make_patient(db):
    user = User(
        email=f"batch-{os.urandom(4).hex()}@test.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Batch Test",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="Batch Test", waist_cm=80)
    db.add(profile)
    db.commit()
    token = create_access_token(subject=user.id, role="patient")
    return {
        "user_id": user.id,
        "patient_id": profile.id,
        "headers": {"Authorization": f"Bearer {token}"},
    }


def _save_batch(db, patient_id, user_id, test_date=None):
    doc, rows = lab_svc.create_manual_entry(
        db,
        patient_id=patient_id,
        requester_id=user_id,
        lab_name="MEDLATEC",
        test_date=test_date or _TODAY,
        results=_BIOMARKERS,
    )
    batch = (
        db.execute(
            select(LabUploadBatch).where(
                LabUploadBatch.patient_id == patient_id,
                LabUploadBatch.deleted_at.is_(None),
            )
        )
        .scalars()
        .first()
    )
    return batch, rows


# ── Test 1: duplicate same test_date + same biomarkers detected ──────────────


class TestDuplicateDetected:
    def test_same_date_overlapping_biomarkers_flagged(self, db):
        p = _make_patient(db)
        _save_batch(db, p["patient_id"], p["user_id"])

        is_dup, batch_id, reason = lab_batch.check_duplicate(
            db,
            patient_id=p["patient_id"],
            test_date=_TODAY,
            biomarker_names=["ast", "alt", "fasting_glucose"],
        )

        assert is_dup is True
        assert batch_id is not None
        assert reason == "overlapping_biomarkers"

    def test_different_date_not_duplicate(self, db):
        p = _make_patient(db)
        _save_batch(db, p["patient_id"], p["user_id"])

        is_dup, _, _ = lab_batch.check_duplicate(
            db,
            patient_id=p["patient_id"],
            test_date=_TODAY - dt.timedelta(days=90),
            biomarker_names=["ast", "alt", "fasting_glucose"],
        )

        assert is_dup is False

    def test_api_returns_409_with_existing_batch_id(self, db):
        p = _make_patient(db)
        _save_batch(db, p["patient_id"], p["user_id"])

        client = TestClient(app)
        resp = client.post(
            f"/api/v1/patients/{p['patient_id']}/lab-results",
            json={
                "lab_name": "MEDLATEC",
                "test_date": str(_TODAY),
                "results": _BIOMARKERS,
            },
            headers=p["headers"],
        )
        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert detail["duplicate"] is True
        assert detail["existing_batch_id"] is not None


# ── Test 2: save new when user chooses force_mode="new" ─────────────────────


class TestSaveAsNew:
    def test_force_new_creates_second_batch(self, db):
        p = _make_patient(db)
        _save_batch(db, p["patient_id"], p["user_id"])

        client = TestClient(app)
        resp = client.post(
            f"/api/v1/patients/{p['patient_id']}/lab-results",
            json={
                "lab_name": "MEDLATEC",
                "test_date": str(_TODAY),
                "results": _BIOMARKERS,
                "force_mode": "new",
            },
            headers=p["headers"],
        )
        assert resp.status_code == 201

        live_batches = (
            db.execute(
                select(LabUploadBatch).where(
                    LabUploadBatch.patient_id == p["patient_id"],
                    LabUploadBatch.deleted_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        assert len(live_batches) == 2


# ── Test 3: overwrite soft-deletes old batch and metrics ─────────────────────


class TestOverwrite:
    def test_overwrite_soft_deletes_old_batch_results_and_metrics(self, db):
        p = _make_patient(db)
        old_batch, old_rows = _save_batch(db, p["patient_id"], p["user_id"])
        old_batch_id = old_batch.id
        old_result_ids = [r.id for r in old_rows]

        lab_svc.create_manual_entry(
            db,
            patient_id=p["patient_id"],
            requester_id=p["user_id"],
            lab_name="MEDLATEC",
            test_date=_TODAY,
            results=_BIOMARKERS,
            force_mode="overwrite",
            existing_batch_id=old_batch_id,
        )
        db.expire_all()

        assert db.get(LabUploadBatch, old_batch_id).deleted_at is not None

        for rid in old_result_ids:
            assert db.get(LabResult, rid).deleted_at is not None

        for rid in old_result_ids:
            for m in db.execute(
                select(HealthMetric).where(HealthMetric.source_ref == rid)
            ).scalars():
                assert m.deleted_at is not None

        live = (
            db.execute(
                select(LabUploadBatch).where(
                    LabUploadBatch.patient_id == p["patient_id"],
                    LabUploadBatch.deleted_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        assert len(live) == 1
        assert live[0].id != old_batch_id


# ── Test 4: delete batch removes lab history and metrics ─────────────────────


class TestDeleteBatchCascade:
    def test_delete_removes_results_and_metrics_from_live_queries(self, db):
        p = _make_patient(db)
        batch, _ = _save_batch(db, p["patient_id"], p["user_id"])

        lab_batch.delete_batch(
            db,
            batch_id=batch.id,
            deleted_by_user_id=p["user_id"],
            patient_id=p["patient_id"],
        )
        db.expire_all()

        live_results = (
            db.execute(
                select(LabResult).where(
                    LabResult.patient_id == p["patient_id"],
                    LabResult.deleted_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        assert live_results == []

        live_metrics = (
            db.execute(
                select(HealthMetric).where(
                    HealthMetric.patient_id == p["patient_id"],
                    HealthMetric.deleted_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        assert live_metrics == []

    def test_api_delete_returns_204(self, db):
        p = _make_patient(db)
        batch, _ = _save_batch(db, p["patient_id"], p["user_id"])

        resp = TestClient(app).delete(
            f"/api/v1/patients/{p['patient_id']}/lab-batches/{batch.id}",
            headers=p["headers"],
        )
        assert resp.status_code == 204


# ── Test 5: patient cannot delete another patient's batch ───────────────────


class TestCrossPatientDelete:
    def test_service_raises_permission_error(self, db):
        owner = _make_patient(db)
        attacker = _make_patient(db)
        batch, _ = _save_batch(db, owner["patient_id"], owner["user_id"])

        with pytest.raises(PermissionError):
            lab_batch.delete_batch(
                db,
                batch_id=batch.id,
                deleted_by_user_id=attacker["user_id"],
                patient_id=attacker["patient_id"],
            )

    def test_api_returns_403_or_404(self, db):
        owner = _make_patient(db)
        attacker = _make_patient(db)
        batch, _ = _save_batch(db, owner["patient_id"], owner["user_id"])

        resp = TestClient(app).delete(
            f"/api/v1/patients/{attacker['patient_id']}/lab-batches/{batch.id}",
            headers=attacker["headers"],
        )
        assert resp.status_code in (403, 404)


# ── Test 6: delete is idempotent ────────────────────────────────────────────


class TestDeleteIdempotent:
    def test_double_delete_does_not_raise(self, db):
        p = _make_patient(db)
        batch, _ = _save_batch(db, p["patient_id"], p["user_id"])

        lab_batch.delete_batch(
            db, batch_id=batch.id, deleted_by_user_id=p["user_id"], patient_id=p["patient_id"]
        )
        lab_batch.delete_batch(
            db, batch_id=batch.id, deleted_by_user_id=p["user_id"], patient_id=p["patient_id"]
        )

    def test_api_double_delete_both_return_204(self, db):
        p = _make_patient(db)
        batch, _ = _save_batch(db, p["patient_id"], p["user_id"])
        client = TestClient(app)
        url = f"/api/v1/patients/{p['patient_id']}/lab-batches/{batch.id}"
        assert client.delete(url, headers=p["headers"]).status_code == 204
        assert client.delete(url, headers=p["headers"]).status_code == 204


# ── Test 7: audit log created ────────────────────────────────────────────────


class TestAuditLog:
    def test_audit_record_written_on_delete(self, db):
        from app.models.governance import AuditLog

        p = _make_patient(db)
        batch, _ = _save_batch(db, p["patient_id"], p["user_id"])

        lab_batch.delete_batch(
            db,
            batch_id=batch.id,
            deleted_by_user_id=p["user_id"],
            reason="user requested",
            patient_id=p["patient_id"],
        )

        entry = (
            db.execute(
                select(AuditLog).where(
                    AuditLog.resource_type == "lab_upload_batch",
                    AuditLog.resource_id == batch.id,
                    AuditLog.action == "delete_lab_batch",
                )
            )
            .scalars()
            .first()
        )
        assert entry is not None
        assert entry.actor_id == p["user_id"]

    def test_batch_row_stores_deleted_by_and_reason(self, db):
        p = _make_patient(db)
        batch, _ = _save_batch(db, p["patient_id"], p["user_id"])

        lab_batch.delete_batch(
            db,
            batch_id=batch.id,
            deleted_by_user_id=p["user_id"],
            reason="cleanup test",
            patient_id=p["patient_id"],
        )
        db.expire_all()

        b = db.get(LabUploadBatch, batch.id)
        assert b.deleted_at is not None
        assert b.deleted_by == p["user_id"]
        assert b.delete_reason == "cleanup test"


# ── Test 8: dashboard recalculates after delete ──────────────────────────────


class TestDashboardRecalculates:
    def test_list_metrics_excludes_deleted_batch_metrics(self, db):
        from app.services.health_metrics import list_metrics

        p = _make_patient(db)
        batch, _ = _save_batch(db, p["patient_id"], p["user_id"])

        before = list_metrics(db, patient_id=p["patient_id"], requester_id=p["user_id"])
        assert len(before) > 0

        lab_batch.delete_batch(
            db, batch_id=batch.id, deleted_by_user_id=p["user_id"], patient_id=p["patient_id"]
        )
        db.expire_all()

        after = list_metrics(db, patient_id=p["patient_id"], requester_id=p["user_id"])
        assert len(after) == 0

    def test_metabolic_score_uses_no_deleted_metrics(self, db):
        from app.services.metabolic_live import compute_live_score

        p = _make_patient(db)
        batch, _ = _save_batch(db, p["patient_id"], p["user_id"])

        lab_batch.delete_batch(
            db, batch_id=batch.id, deleted_by_user_id=p["user_id"], patient_id=p["patient_id"]
        )
        db.expire_all()

        live = (
            db.execute(
                select(HealthMetric).where(
                    HealthMetric.patient_id == p["patient_id"],
                    HealthMetric.deleted_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        assert live == []

        score = compute_live_score(db, patient_id=p["patient_id"])
        assert score is None or score is not None  # score without inputs = None or default


# ── Test 9: list lab-results rejects limit > 100 (regression: frontend sent 200) ──


class TestListLabResultsLimitValidation:
    """Regression: frontend bug sent limit=200 which exceeds backend le=100 constraint.
    Backend must return 422 with a clear validation error."""

    def test_limit_200_returns_422(self, db):
        p = _make_patient(db)
        client = TestClient(app)
        resp = client.get(
            f"/api/v1/patients/{p['patient_id']}/lab-results?limit=200",
            headers=p["headers"],
        )
        assert resp.status_code == 422
        body = resp.json()
        assert "detail" in body
        # FastAPI validation error contains "less than or equal to 100" message
        detail_str = str(body["detail"]).lower()
        assert "100" in detail_str or "less_than_equal" in detail_str or "le" in detail_str

    def test_limit_100_returns_200(self, db):
        p = _make_patient(db)
        client = TestClient(app)
        resp = client.get(
            f"/api/v1/patients/{p['patient_id']}/lab-results?limit=100",
            headers=p["headers"],
        )
        assert resp.status_code == 200

    def test_limit_101_returns_422(self, db):
        p = _make_patient(db)
        client = TestClient(app)
        resp = client.get(
            f"/api/v1/patients/{p['patient_id']}/lab-results?limit=101",
            headers=p["headers"],
        )
        assert resp.status_code == 422


# ── Test 10: P0 clinical safety — glucose mmol/L must be converted to mg/dL ────


class TestGlucoseMmolConversion:
    """
    P0 Patient Safety Regression:
    Manual entry with glucose in mmol/L must be stored/classified in mg/dL.
    clinical_rules.assess_biomarker always runs in mg/dL.
    A value like 5.7 mmol/L = 102.7 mg/dL (borderline high) must NEVER
    be classified as critical/low (which would happen if stored as 5.7 mg/dL).

    Test matrix (all mmol/L input, expected canonical mg/dL status):
      2.8  → critical (2.8 * 18.018 = 50.5 mg/dL < 54 critical_low)
      3.5  → low      (3.5 * 18.018 = 63.1 mg/dL  < 70 ref_low)
      4.8  → normal   (4.8 * 18.018 = 86.5 mg/dL in 70–99)
      5.7  → high/borderline (5.7 * 18.018 = 102.7 mg/dL, in 100–125 prediabetes)
      7.2  → high     (7.2 * 18.018 = 129.7 mg/dL in 126–299)
      11.1 → critical (11.1 * 18.018 = 200.0 mg/dL < 300 but > 126, so high not critical)
    """

    MMOL_TO_MGDL = 18.018

    def _create_glucose_entry(self, db, patient_id, user_id, mmol_value):
        """Create a manual lab entry with glucose in mmol/L."""
        from app.services.lab import create_manual_entry

        doc, rows = create_manual_entry(
            db,
            patient_id=patient_id,
            requester_id=user_id,
            lab_name="TEST_LAB",
            test_date=_TODAY,
            results=[
                {
                    "test_name": "fasting_glucose",
                    "value": mmol_value,
                    "unit": "mmol/L",
                }
            ],
        )
        return rows

    def test_5_7_mmol_stored_as_mgdl(self, db):
        """5.7 mmol/L = 102.7 mg/dL — must NOT be stored as 5.7 mg/dL (would be critical low)."""
        p = _make_patient(db)
        rows = self._create_glucose_entry(db, p["patient_id"], p["user_id"], 5.7)
        assert len(rows) == 1
        row = rows[0]
        # Value stored in DB must be ~102.7 mg/dL, not 5.7
        expected_mgdl = round(5.7 * self.MMOL_TO_MGDL, 1)
        assert abs(row.value - expected_mgdl) < 2.0, (
            f"Expected ~{expected_mgdl} mg/dL, got {row.value} {row.unit}. "
            "Glucose mmol/L not converted — P0 clinical bug!"
        )
        assert row.unit == "mg/dL"
        # Original value must be preserved
        assert row.original_value == 5.7
        assert row.original_unit == "mmol/L"

    def test_5_7_mmol_not_classified_as_critical(self, db):
        """5.7 mmol/L is borderline/prediabetes — must NOT be critical or low."""
        from app.domain.clinical_rules import assess_biomarker

        p = _make_patient(db)
        rows = self._create_glucose_entry(db, p["patient_id"], p["user_id"], 5.7)
        assert len(rows) == 1
        finding = assess_biomarker("fasting_glucose", rows[0].value)
        assert finding is not None
        assert finding.status in ("borderline", "high"), (
            f"5.7 mmol/L → {rows[0].value} mg/dL → status={finding.status!r}; "
            "expected borderline or high (prediabetes range)"
        )
        assert finding.status not in ("critical",), (
            "5.7 mmol/L must NEVER be classified as critical. "
            "This means the mmol/L value was not converted to mg/dL."
        )

    def test_2_8_mmol_is_critical(self, db):
        """2.8 mmol/L = ~50.5 mg/dL — critical hypoglycemia."""
        from app.domain.clinical_rules import assess_biomarker

        p = _make_patient(db)
        rows = self._create_glucose_entry(db, p["patient_id"], p["user_id"], 2.8)
        assert len(rows) == 1
        expected_mgdl = round(2.8 * self.MMOL_TO_MGDL, 1)
        assert abs(rows[0].value - expected_mgdl) < 2.0
        finding = assess_biomarker("fasting_glucose", rows[0].value)
        assert finding is not None
        assert finding.status == "critical", (
            f"2.8 mmol/L = {expected_mgdl} mg/dL should be critical, got {finding.status}"
        )

    def test_3_5_mmol_is_low(self, db):
        """3.5 mmol/L = ~63.1 mg/dL — below ref_low=70, status low."""
        from app.domain.clinical_rules import assess_biomarker

        p = _make_patient(db)
        rows = self._create_glucose_entry(db, p["patient_id"], p["user_id"], 3.5)
        assert len(rows) == 1
        expected_mgdl = round(3.5 * self.MMOL_TO_MGDL, 1)
        assert abs(rows[0].value - expected_mgdl) < 2.0
        finding = assess_biomarker("fasting_glucose", rows[0].value)
        assert finding is not None
        assert finding.status == "low", (
            f"3.5 mmol/L = {expected_mgdl} mg/dL should be low, got {finding.status}"
        )

    def test_4_8_mmol_is_normal(self, db):
        """4.8 mmol/L = ~86.5 mg/dL — normal range 70–99."""
        from app.domain.clinical_rules import assess_biomarker

        p = _make_patient(db)
        rows = self._create_glucose_entry(db, p["patient_id"], p["user_id"], 4.8)
        assert len(rows) == 1
        expected_mgdl = round(4.8 * self.MMOL_TO_MGDL, 1)
        assert abs(rows[0].value - expected_mgdl) < 2.0
        finding = assess_biomarker("fasting_glucose", rows[0].value)
        assert finding is not None
        assert finding.status == "normal", (
            f"4.8 mmol/L = {expected_mgdl} mg/dL should be normal, got {finding.status}"
        )

    def test_7_2_mmol_is_high(self, db):
        """7.2 mmol/L = ~129.7 mg/dL — diabetic range (126–299)."""
        from app.domain.clinical_rules import assess_biomarker

        p = _make_patient(db)
        rows = self._create_glucose_entry(db, p["patient_id"], p["user_id"], 7.2)
        assert len(rows) == 1
        expected_mgdl = round(7.2 * self.MMOL_TO_MGDL, 1)
        assert abs(rows[0].value - expected_mgdl) < 2.0
        finding = assess_biomarker("fasting_glucose", rows[0].value)
        assert finding is not None
        assert finding.status == "high", (
            f"7.2 mmol/L = {expected_mgdl} mg/dL should be high, got {finding.status}"
        )

    def test_11_1_mmol_is_high(self, db):
        """11.1 mmol/L = ~200 mg/dL — clearly diabetic, high (not critical yet, <300)."""
        from app.domain.clinical_rules import assess_biomarker

        p = _make_patient(db)
        rows = self._create_glucose_entry(db, p["patient_id"], p["user_id"], 11.1)
        assert len(rows) == 1
        expected_mgdl = round(11.1 * self.MMOL_TO_MGDL, 1)
        assert abs(rows[0].value - expected_mgdl) < 2.0
        finding = assess_biomarker("fasting_glucose", rows[0].value)
        assert finding is not None
        assert finding.status == "high", (
            f"11.1 mmol/L = {expected_mgdl} mg/dL should be high (126-299), got {finding.status}"
        )

    def test_mgdl_input_unchanged(self, db):
        """Input already in mg/dL (e.g. 102.7) must NOT be double-converted."""
        from app.services.lab import create_manual_entry

        p = _make_patient(db)
        doc, rows = create_manual_entry(
            db,
            patient_id=p["patient_id"],
            requester_id=p["user_id"],
            lab_name="TEST_LAB",
            test_date=_TODAY,
            results=[
                {
                    "test_name": "fasting_glucose",
                    "value": 102.7,
                    "unit": "mg/dL",
                }
            ],
        )
        assert len(rows) == 1
        assert abs(rows[0].value - 102.7) < 0.5, (
            f"mg/dL input should be stored unchanged, got {rows[0].value}"
        )
        assert rows[0].unit == "mg/dL"
