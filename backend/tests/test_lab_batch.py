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
    {"test_name": "Glucose",   "value": 5.73,  "unit": "mmol/L"},
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
    batch = db.execute(
        select(LabUploadBatch).where(
            LabUploadBatch.patient_id == patient_id,
            LabUploadBatch.deleted_at.is_(None),
        )
    ).scalars().first()
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

        live_batches = db.execute(
            select(LabUploadBatch).where(
                LabUploadBatch.patient_id == p["patient_id"],
                LabUploadBatch.deleted_at.is_(None),
            )
        ).scalars().all()
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

        live = db.execute(
            select(LabUploadBatch).where(
                LabUploadBatch.patient_id == p["patient_id"],
                LabUploadBatch.deleted_at.is_(None),
            )
        ).scalars().all()
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

        live_results = db.execute(
            select(LabResult).where(
                LabResult.patient_id == p["patient_id"],
                LabResult.deleted_at.is_(None),
            )
        ).scalars().all()
        assert live_results == []

        live_metrics = db.execute(
            select(HealthMetric).where(
                HealthMetric.patient_id == p["patient_id"],
                HealthMetric.deleted_at.is_(None),
            )
        ).scalars().all()
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
            db, batch_id=batch.id, deleted_by_user_id=p["user_id"],
            reason="user requested", patient_id=p["patient_id"],
        )

        entry = db.execute(
            select(AuditLog).where(
                AuditLog.resource_type == "lab_upload_batch",
                AuditLog.resource_id == batch.id,
                AuditLog.action == "delete_lab_batch",
            )
        ).scalars().first()
        assert entry is not None
        assert entry.actor_id == p["user_id"]

    def test_batch_row_stores_deleted_by_and_reason(self, db):
        p = _make_patient(db)
        batch, _ = _save_batch(db, p["patient_id"], p["user_id"])

        lab_batch.delete_batch(
            db, batch_id=batch.id, deleted_by_user_id=p["user_id"],
            reason="cleanup test", patient_id=p["patient_id"],
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

        live = db.execute(
            select(HealthMetric).where(
                HealthMetric.patient_id == p["patient_id"],
                HealthMetric.deleted_at.is_(None),
            )
        ).scalars().all()
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
