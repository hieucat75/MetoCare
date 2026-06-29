"""Tests for P0 Health Record Edit & Delete.

Covers:
  - PATCH /patients/{patient_id}/metrics/{metric_id}   (update_metric)
  - DELETE /patients/{patient_id}/metrics/{metric_id}  (delete_metric)
  - DELETE /patients/{patient_id}/lab-results/{result_id} (delete_lab_result)
  - PATCH /patients/{patient_id}/lab-results/{result_id}  (edit_lab_result)
  - narrative_cache.invalidate_patient()
  - Consent gate enforcement
"""

from __future__ import annotations

import json
import os

import pytest
from app.core.security import create_access_token
from app.main import app
from app.models.clinical import HealthMetric, LabResult, LabUploadBatch
from app.models.patient import PatientProfile
from app.models.user import User, UserRole
from app.services import narrative_cache
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mint(user_id: str, role: str = "patient") -> dict[str, str]:
    token = create_access_token(subject=user_id, role=role)
    return {"Authorization": f"Bearer {token}"}


def _seed_patient(db):
    """Create a fresh patient+user, return ids dict."""
    user = User(
        email=f"edit-delete-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Test Patient",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="Test Patient", waist_cm=90)
    db.add(profile)
    db.commit()
    return {"user_id": user.id, "patient_id": profile.id}


def _seed_metric(db, patient_id: str) -> HealthMetric:
    m = HealthMetric(
        patient_id=patient_id,
        metric_type="fasting_glucose",
        value=100.0,
        unit="mg/dL",
        measured_at=__import__("datetime").datetime(2024, 1, 15, 8, 0),
        source="manual",
        normal_range_min=70.0,
        normal_range_max=99.0,
        status="high",
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def _seed_lab_result(db, patient_id: str) -> tuple[LabUploadBatch, LabResult]:
    import datetime as dt

    batch = LabUploadBatch(patient_id=patient_id, lab_name="TestLab", test_date=dt.date(2024, 1, 10))
    db.add(batch)
    db.flush()

    result = LabResult(
        patient_id=patient_id,
        batch_id=batch.id,
        test_name="Glucose",
        canonical_name="fasting_glucose",
        value=110.0,
        unit="mg/dL",
        reference_range="70-100 mg/dL",
        status="high",
        verified_by_user=True,
        test_date=dt.date(2024, 1, 10),
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    return batch, result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def pat(db):
    return _seed_patient(db)


@pytest.fixture
def pat2(db):
    """Second patient — used to test ownership violations."""
    return _seed_patient(db)


# ---------------------------------------------------------------------------
# 1. PATCH metric — success
# ---------------------------------------------------------------------------

def test_patch_metric_success(client, db, pat):
    m = _seed_metric(db, pat["patient_id"])
    headers = _mint(pat["user_id"])
    resp = client.patch(
        f"/api/v1/patients/{pat['patient_id']}/metrics/{m.id}",
        json={"value": 85.0, "unit": "mg/dL"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["value"] == 85.0
    assert data["status"] == "normal"
    assert data["id"] == m.id  # id preserved


def test_patch_metric_partial_fields(client, db, pat):
    m = _seed_metric(db, pat["patient_id"])
    headers = _mint(pat["user_id"])
    # Only update measured_at
    resp = client.patch(
        f"/api/v1/patients/{pat['patient_id']}/metrics/{m.id}",
        json={"measured_at": "2024-03-01T08:00:00"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["value"] == 100.0  # unchanged


def test_patch_metric_updates_status(client, db, pat):
    """Status should be re-derived after value update."""
    m = _seed_metric(db, pat["patient_id"])
    headers = _mint(pat["user_id"])
    # Set value well above normal_range_max → should be 'high'
    resp = client.patch(
        f"/api/v1/patients/{pat['patient_id']}/metrics/{m.id}",
        json={"value": 200.0},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "high"


def test_patch_metric_not_found(client, db, pat):
    headers = _mint(pat["user_id"])
    resp = client.patch(
        f"/api/v1/patients/{pat['patient_id']}/metrics/nonexistent-id",
        json={"value": 90.0},
        headers=headers,
    )
    assert resp.status_code == 404


def test_patch_metric_ownership_violation(client, db, pat, pat2):
    """PATIENT may not edit another patient's metric."""
    m = _seed_metric(db, pat["patient_id"])
    headers = _mint(pat2["user_id"])  # different patient
    resp = client.patch(
        f"/api/v1/patients/{pat['patient_id']}/metrics/{m.id}",
        json={"value": 90.0},
        headers=headers,
    )
    assert resp.status_code == 403


def test_patch_metric_field_validation(client, db, pat):
    """Sending a non-updatable field should be silently ignored (not error)."""
    m = _seed_metric(db, pat["patient_id"])
    headers = _mint(pat["user_id"])
    # 'id' is not in _ALLOWED — should be ignored
    resp = client.patch(
        f"/api/v1/patients/{pat['patient_id']}/metrics/{m.id}",
        json={"value": 90.0, "id": "hacked"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == m.id  # original id preserved


# ---------------------------------------------------------------------------
# 2. DELETE metric — success
# ---------------------------------------------------------------------------

def test_delete_metric_success(client, db, pat):
    m = _seed_metric(db, pat["patient_id"])
    headers = _mint(pat["user_id"])
    resp = client.delete(
        f"/api/v1/patients/{pat['patient_id']}/metrics/{m.id}",
        headers=headers,
    )
    assert resp.status_code == 204
    # Verify soft-delete
    db.expire(m)
    db.refresh(m)
    assert m.deleted_at is not None
    assert m.deleted_by == pat["user_id"]


def test_delete_metric_not_found(client, db, pat):
    headers = _mint(pat["user_id"])
    resp = client.delete(
        f"/api/v1/patients/{pat['patient_id']}/metrics/no-such-metric",
        headers=headers,
    )
    assert resp.status_code == 404


def test_delete_metric_ownership_violation(client, db, pat, pat2):
    m = _seed_metric(db, pat["patient_id"])
    headers = _mint(pat2["user_id"])  # wrong patient
    resp = client.delete(
        f"/api/v1/patients/{pat['patient_id']}/metrics/{m.id}",
        headers=headers,
    )
    assert resp.status_code == 403


def test_delete_metric_already_deleted(client, db, pat):
    """Deleting an already-soft-deleted metric should return 404."""
    m = _seed_metric(db, pat["patient_id"])
    headers = _mint(pat["user_id"])
    # First delete
    r1 = client.delete(f"/api/v1/patients/{pat['patient_id']}/metrics/{m.id}", headers=headers)
    assert r1.status_code == 204
    # Second delete
    r2 = client.delete(f"/api/v1/patients/{pat['patient_id']}/metrics/{m.id}", headers=headers)
    assert r2.status_code == 404


def test_delete_metric_not_in_list_afterwards(client, db, pat):
    """Deleted metric must not appear in list_metrics."""
    m = _seed_metric(db, pat["patient_id"])
    headers = _mint(pat["user_id"])
    client.delete(f"/api/v1/patients/{pat['patient_id']}/metrics/{m.id}", headers=headers)
    resp = client.get(f"/api/v1/patients/{pat['patient_id']}/metrics", headers=headers)
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()]
    assert m.id not in ids


# ---------------------------------------------------------------------------
# 3. DELETE lab result
# ---------------------------------------------------------------------------

def test_delete_lab_result_success(client, db, pat):
    _, result = _seed_lab_result(db, pat["patient_id"])
    headers = _mint(pat["user_id"])
    resp = client.delete(
        f"/api/v1/patients/{pat['patient_id']}/lab-results/{result.id}",
        headers=headers,
    )
    assert resp.status_code == 204
    db.expire(result)
    db.refresh(result)
    assert result.deleted_at is not None
    assert result.deleted_by == pat["user_id"]


def test_delete_lab_result_not_found(client, db, pat):
    headers = _mint(pat["user_id"])
    resp = client.delete(
        f"/api/v1/patients/{pat['patient_id']}/lab-results/no-such-id",
        headers=headers,
    )
    assert resp.status_code == 404


def test_delete_lab_result_ownership_violation(client, db, pat, pat2):
    _, result = _seed_lab_result(db, pat["patient_id"])
    headers = _mint(pat2["user_id"])
    resp = client.delete(
        f"/api/v1/patients/{pat['patient_id']}/lab-results/{result.id}",
        headers=headers,
    )
    assert resp.status_code == 403


def test_delete_lab_result_already_deleted(client, db, pat):
    _, result = _seed_lab_result(db, pat["patient_id"])
    headers = _mint(pat["user_id"])
    r1 = client.delete(
        f"/api/v1/patients/{pat['patient_id']}/lab-results/{result.id}", headers=headers
    )
    assert r1.status_code == 204
    r2 = client.delete(
        f"/api/v1/patients/{pat['patient_id']}/lab-results/{result.id}", headers=headers
    )
    assert r2.status_code == 404


# ---------------------------------------------------------------------------
# 4. PATCH lab result (extended edit)
# ---------------------------------------------------------------------------

def test_edit_lab_result_metadata(client, db, pat):
    _, result = _seed_lab_result(db, pat["patient_id"])
    headers = _mint(pat["user_id"])
    resp = client.patch(
        f"/api/v1/patients/{pat['patient_id']}/lab-results/{result.id}",
        json={"test_name": "Fasting Blood Glucose", "reference_range": "70-99 mg/dL"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["test_name"] == "Fasting Blood Glucose"
    assert data["reference_range"] == "70-99 mg/dL"


def test_edit_lab_result_value_triggers_reclassify(client, db, pat):
    _, result = _seed_lab_result(db, pat["patient_id"])
    headers = _mint(pat["user_id"])
    resp = client.patch(
        f"/api/v1/patients/{pat['patient_id']}/lab-results/{result.id}",
        json={"value": 80.0, "unit": "mg/dL"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    # 80 mg/dL is within normal fasting glucose range → normal
    data = resp.json()
    assert data["status"] == "normal"


def test_edit_lab_result_not_found(client, db, pat):
    headers = _mint(pat["user_id"])
    resp = client.patch(
        f"/api/v1/patients/{pat['patient_id']}/lab-results/nonexistent",
        json={"test_name": "X"},
        headers=headers,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 5. Narrative cache invalidation
# ---------------------------------------------------------------------------

def test_invalidate_patient_deletes_matching_files(tmp_path, monkeypatch):
    """invalidate_patient removes all cache files whose patient_id matches."""
    monkeypatch.setattr(narrative_cache, "NARRATIVE_CACHE_DIR", str(tmp_path))

    pid = "patient-abc"
    # Write two matching files and one non-matching
    for i in range(2):
        fpath = tmp_path / f"file{i}.json"
        fpath.write_text(json.dumps({"patient_id": pid, "narrative": "x"}))
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"patient_id": "other-patient"}))

    count = narrative_cache.invalidate_patient(pid)
    assert count == 2
    assert not (tmp_path / "file0.json").exists()
    assert not (tmp_path / "file1.json").exists()
    assert (tmp_path / "other.json").exists()


def test_invalidate_patient_no_files_is_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(narrative_cache, "NARRATIVE_CACHE_DIR", str(tmp_path))
    count = narrative_cache.invalidate_patient("no-such-patient")
    assert count == 0


def test_invalidate_patient_missing_dir_is_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(
        narrative_cache, "NARRATIVE_CACHE_DIR", str(tmp_path / "nonexistent")
    )
    count = narrative_cache.invalidate_patient("any-patient")
    assert count == 0


def test_invalidate_patient_corrupted_json_skipped(tmp_path, monkeypatch):
    """A corrupt json file should be skipped without raising."""
    monkeypatch.setattr(narrative_cache, "NARRATIVE_CACHE_DIR", str(tmp_path))
    corrupt = tmp_path / "bad.json"
    corrupt.write_text("not-valid-json")
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"patient_id": "p1"}))

    count = narrative_cache.invalidate_patient("p1")
    assert count == 1
    assert not good.exists()


# ---------------------------------------------------------------------------
# 6. Consent gate — unauthenticated requests
# ---------------------------------------------------------------------------

def test_patch_metric_requires_auth(client, db, pat):
    m = _seed_metric(db, pat["patient_id"])
    resp = client.patch(
        f"/api/v1/patients/{pat['patient_id']}/metrics/{m.id}",
        json={"value": 90.0},
    )
    assert resp.status_code == 401


def test_delete_metric_requires_auth(client, db, pat):
    m = _seed_metric(db, pat["patient_id"])
    resp = client.delete(f"/api/v1/patients/{pat['patient_id']}/metrics/{m.id}")
    assert resp.status_code == 401


def test_delete_lab_result_requires_auth(client, db, pat):
    _, result = _seed_lab_result(db, pat["patient_id"])
    resp = client.delete(f"/api/v1/patients/{pat['patient_id']}/lab-results/{result.id}")
    assert resp.status_code == 401
