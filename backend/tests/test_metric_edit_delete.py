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

import datetime as dt
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

# ---------------------------------------------------------------------------
# 7. PATCH metric calls cache invalidation (Fix 2)
# ---------------------------------------------------------------------------

def test_patch_metric_calls_cache_invalidation(client, db, pat, monkeypatch):
    """PATCH /metrics/{id} must invalidate the narrative cache for the patient."""
    calls: list[str] = []

    def _fake_invalidate(patient_id: str) -> int:
        calls.append(patient_id)
        return 0

    from app.api.v1.routes import health as health_routes
    monkeypatch.setattr(health_routes.nc, "invalidate_patient", _fake_invalidate)

    m = _seed_metric(db, pat["patient_id"])
    headers = _mint(pat["user_id"])
    resp = client.patch(
        f"/api/v1/patients/{pat['patient_id']}/metrics/{m.id}",
        json={"value": 85.0},
        headers=headers,
    )
    assert resp.status_code == 200
    assert pat["patient_id"] in calls, "invalidate_patient must be called with correct patient_id"


# ---------------------------------------------------------------------------
# 8. DELETE lab result cascades to HealthMetric (Fix 3)
# ---------------------------------------------------------------------------

def test_delete_lab_result_cascades_to_health_metric(client, db, pat):
    """Soft-deleting a LabResult must also soft-delete promoted HealthMetric rows."""
    _, lab_result = _seed_lab_result(db, pat["patient_id"])

    # Create a HealthMetric that was promoted from this LabResult
    promoted = HealthMetric(
        patient_id=pat["patient_id"],
        metric_type="fasting_glucose",
        value=110.0,
        unit="mg/dL",
        measured_at=dt.datetime(2024, 1, 10, 8, 0),
        source="lab_result",
        source_ref=lab_result.id,
        status="high",
    )
    db.add(promoted)
    db.commit()
    db.refresh(promoted)

    headers = _mint(pat["user_id"])

    # Verify metric is visible before delete
    r_before = client.get(f"/api/v1/patients/{pat['patient_id']}/metrics", headers=headers)
    assert r_before.status_code == 200
    ids_before = [item["id"] for item in r_before.json()]
    assert promoted.id in ids_before

    # Delete the lab result
    resp = client.delete(
        f"/api/v1/patients/{pat['patient_id']}/lab-results/{lab_result.id}",
        headers=headers,
    )
    assert resp.status_code == 204

    # The promoted HealthMetric must be soft-deleted too
    db.expire(promoted)
    db.refresh(promoted)
    assert promoted.deleted_at is not None, "HealthMetric cascade soft-delete must set deleted_at"

    # Must not appear in GET /metrics
    r_after = client.get(f"/api/v1/patients/{pat['patient_id']}/metrics", headers=headers)
    assert r_after.status_code == 200
    ids_after = [item["id"] for item in r_after.json()]
    assert promoted.id not in ids_after, "Cascaded metric must not appear in list after delete"


# ---------------------------------------------------------------------------
# 9. save_narrative stores patient_id so invalidate_patient can find the file (Fix 2)
# ---------------------------------------------------------------------------

def test_narrative_cache_invalidation_stores_patient_id(tmp_path, monkeypatch):
    """save_narrative with patient_id kwarg must store patient_id in the JSON so
    invalidate_patient can locate and delete the file."""
    monkeypatch.setattr(narrative_cache, "NARRATIVE_CACHE_DIR", str(tmp_path))

    patient_id = "patient-xyz-test"
    cache_key = "test-key-123"
    payload = {
        "narrative": {"summary": "test"},
        "prompt_version": "1",
    }

    # save_narrative with patient_id kwarg
    narrative_cache.save_narrative(cache_key, payload, patient_id=patient_id)

    # File should exist and contain patient_id
    cache_files = list(tmp_path.glob("*.json"))
    assert len(cache_files) == 1, "Expected exactly one cache file"
    data = json.loads(cache_files[0].read_text())
    assert data.get("patient_id") == patient_id, "patient_id must be stored in cache file"

    # invalidate_patient should find and delete this file
    count = narrative_cache.invalidate_patient(patient_id)
    assert count == 1, "invalidate_patient must delete the cache file"
    assert not cache_files[0].exists(), "Cache file must be deleted after invalidation"
