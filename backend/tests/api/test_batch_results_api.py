"""Gap-1 tests — GET /patients/{patient_id}/lab-batches/{batch_id}/results.

Covers:
  1. Returns only results for the requested batch (no cross-batch leakage)
  2. Results from batch A do not appear in batch B response
  3. 404 when batch belongs to another patient (ownership check)
  4. 200 + empty list for batch with no results
  5. 404 for non-existent batch_id

Pattern: create data directly via POST /lab-results (manual entry) so the
  batch + result rows are fully seeded through the real service layer.
"""

from __future__ import annotations

import datetime as dt
import os

import pytest
from app.core.clock import utcnow
from app.core.security import create_access_token
from app.models.clinical import LabUploadBatch
from app.models.governance import Consent
from app.models.patient import PatientProfile
from app.models.user import User, UserRole


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_consent(db, *, patient_id: str, granted_to: str) -> None:
    """Create an active lab consent (patient self-consent covers PATIENT role)."""
    c = Consent(
        patient_id=patient_id,
        consent_type="lab_access",
        data_scope="lab",
        granted_to=granted_to,
        valid_from=utcnow() - dt.timedelta(hours=1),
        valid_until=utcnow() + dt.timedelta(hours=24),
    )
    db.add(c)
    db.commit()


def _post_batch(client, *, patient_id: str, headers: dict, lab_name: str,
                test_date: str, results: list[dict]) -> dict:
    """POST /patients/{id}/lab-results and return the response JSON."""
    r = client.post(
        f"/api/v1/patients/{patient_id}/lab-results",
        headers=headers,
        json={"lab_name": lab_name, "test_date": test_date, "results": results},
    )
    assert r.status_code == 201, f"setup failed: {r.text}"
    return r.json()


def _batch_results_url(patient_id: str, batch_id: str) -> str:
    return f"/api/v1/patients/{patient_id}/lab-batches/{batch_id}/results"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def patient(db):
    """Primary test patient."""
    user = User(
        email=f"br-patient-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Batch Results Patient",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="Batch Results Patient")
    db.add(profile)
    db.flush()
    _make_consent(db, patient_id=profile.id, granted_to=user.id)
    token = create_access_token(subject=user.id, role="patient")
    return {
        "user_id": user.id,
        "patient_id": profile.id,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def other_patient(db):
    """A completely separate patient — used for ownership/cross-patient tests."""
    user = User(
        email=f"br-other-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Other Batch Patient",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="Other Batch Patient")
    db.add(profile)
    db.flush()
    _make_consent(db, patient_id=profile.id, granted_to=user.id)
    token = create_access_token(subject=user.id, role="patient")
    return {
        "user_id": user.id,
        "patient_id": profile.id,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def batch_a(client, patient):
    """Batch A — Glucose + HbA1c for the primary patient."""
    resp = _post_batch(
        client,
        patient_id=patient["patient_id"],
        headers=patient["headers"],
        lab_name="Lab Alpha",
        test_date="2026-06-01",
        results=[
            {"test_name": "Glucose", "value": 92.0, "unit": "mg/dL"},
            {"test_name": "HbA1c", "value": 5.5, "unit": "%"},
        ],
    )
    return resp


@pytest.fixture
def batch_b(client, patient):
    """Batch B — Cholesterol only, different date — separate session."""
    resp = _post_batch(
        client,
        patient_id=patient["patient_id"],
        headers=patient["headers"],
        lab_name="Lab Beta",
        test_date="2026-05-01",
        results=[
            {"test_name": "Cholesterol", "value": 185.0, "unit": "mg/dL"},
        ],
    )
    return resp


# ---------------------------------------------------------------------------
# Helper: extract batch_id from the POST /lab-results response
# ---------------------------------------------------------------------------

def _get_batch_id(client, *, patient_id: str, headers: dict, resp_json: dict) -> str:
    """Pull the batch_id from one of the result items in the POST response."""
    items = resp_json.get("items", [])
    assert items, "Expected at least one result item"
    # The batch_id is embedded on each result row
    r = client.get(
        f"/api/v1/patients/{patient_id}/lab-results",
        headers=headers,
        params={"limit": 100},
    )
    assert r.status_code == 200
    all_items = r.json()["items"]
    # Match by test_name to find the batch_id for this specific batch's items
    target_names = {it["test_name"] for it in items}
    matches = [i for i in all_items if i["test_name"] in target_names]
    assert matches, f"Could not find result with names {target_names}"
    batch_id = matches[0].get("batch_id")
    assert batch_id, "batch_id was null on result item"
    return batch_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBatchResultsEndpoint:
    """GET /patients/{patient_id}/lab-batches/{batch_id}/results"""

    def test_returns_correct_batch_results(self, client, patient, batch_a):
        """Only results for batch A are returned; correct shape + fields."""
        batch_id = _get_batch_id(
            client,
            patient_id=patient["patient_id"],
            headers=patient["headers"],
            resp_json=batch_a,
        )
        r = client.get(
            _batch_results_url(patient["patient_id"], batch_id),
            headers=patient["headers"],
        )
        assert r.status_code == 200, r.text
        body = r.json()

        # Shape
        assert "batch_id" in body
        assert "patient_id" in body
        assert "total" in body
        assert "items" in body
        assert body["batch_id"] == batch_id
        assert body["patient_id"] == patient["patient_id"]
        assert body["total"] == 2
        assert len(body["items"]) == 2

        # Fields present on each item
        item = body["items"][0]
        for field in ("id", "test_name", "value", "unit", "status", "created_at"):
            assert field in item, f"Missing field: {field}"

        # All items belong to this batch
        for item in body["items"]:
            assert item["batch_id"] == batch_id

        # Biomarkers match what was entered
        names = {it["test_name"] for it in body["items"]}
        assert names == {"Glucose", "HbA1c"}

    def test_no_cross_batch_leakage(self, client, patient, batch_a, batch_b):
        """Results from batch A do not appear in batch B response."""
        batch_a_id = _get_batch_id(
            client,
            patient_id=patient["patient_id"],
            headers=patient["headers"],
            resp_json=batch_a,
        )
        batch_b_id = _get_batch_id(
            client,
            patient_id=patient["patient_id"],
            headers=patient["headers"],
            resp_json=batch_b,
        )
        assert batch_a_id != batch_b_id, "Fixtures produced the same batch_id"

        ra = client.get(
            _batch_results_url(patient["patient_id"], batch_a_id),
            headers=patient["headers"],
        )
        rb = client.get(
            _batch_results_url(patient["patient_id"], batch_b_id),
            headers=patient["headers"],
        )
        assert ra.status_code == 200
        assert rb.status_code == 200

        names_a = {it["test_name"] for it in ra.json()["items"]}
        names_b = {it["test_name"] for it in rb.json()["items"]}

        # Batch A has Glucose + HbA1c; Batch B has Cholesterol — no overlap
        assert "Cholesterol" not in names_a, "Batch B result leaked into Batch A"
        assert "Glucose" not in names_b, "Batch A result leaked into Batch B"
        assert "HbA1c" not in names_b, "Batch A result leaked into Batch B"

    def test_ownership_check_returns_404(self, client, patient, other_patient, batch_a):
        """Patient B cannot access Patient A's batch — must get 404."""
        batch_id = _get_batch_id(
            client,
            patient_id=patient["patient_id"],
            headers=patient["headers"],
            resp_json=batch_a,
        )
        # Request using Patient B's token + Patient A's patient_id
        # First test with patient_id matching but wrong user token (403 from ownership check)
        r = client.get(
            _batch_results_url(patient["patient_id"], batch_id),
            headers=other_patient["headers"],  # Patient B's JWT
        )
        assert r.status_code == 403, f"Expected 403 for cross-patient access, got {r.status_code}: {r.text}"

    def test_ownership_check_via_wrong_patient_id(self, client, patient, other_patient, batch_a):
        """Patient B cannot enumerate Patient A's batch by substituting their own patient_id."""
        batch_id = _get_batch_id(
            client,
            patient_id=patient["patient_id"],
            headers=patient["headers"],
            resp_json=batch_a,
        )
        # Use other_patient's own patient_id path but Patient A's batch_id
        # -> batch not found for that patient_id -> 404
        r = client.get(
            _batch_results_url(other_patient["patient_id"], batch_id),
            headers=other_patient["headers"],
        )
        assert r.status_code == 404, f"Expected 404 for wrong-patient batch_id, got {r.status_code}: {r.text}"

    def test_empty_batch_returns_200_empty_list(self, client, db, patient):
        """A batch that exists but has no results returns 200 + empty items list."""
        # Create an empty batch directly in the DB
        empty_batch = LabUploadBatch(
            patient_id=patient["patient_id"],
            lab_name="Empty Lab",
            test_date=dt.date(2026, 4, 1),
        )
        db.add(empty_batch)
        db.commit()

        r = client.get(
            _batch_results_url(patient["patient_id"], empty_batch.id),
            headers=patient["headers"],
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] == 0
        assert body["items"] == []

    def test_invalid_batch_id_returns_404(self, client, patient):
        """Non-existent batch_id returns 404."""
        r = client.get(
            _batch_results_url(patient["patient_id"], "00000000-0000-0000-0000-000000000000"),
            headers=patient["headers"],
        )
        assert r.status_code == 404, r.text

    def test_unauthenticated_request_returns_401(self, client, patient, batch_a):
        """No token → 401 (or 403 depending on FastAPI/security config)."""
        batch_id = _get_batch_id(
            client,
            patient_id=patient["patient_id"],
            headers=patient["headers"],
            resp_json=batch_a,
        )
        r = client.get(_batch_results_url(patient["patient_id"], batch_id))
        assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"

    def test_response_includes_batch_id_in_schema(self, client, patient, batch_a):
        """Each result item in the response must carry its batch_id field."""
        batch_id = _get_batch_id(
            client,
            patient_id=patient["patient_id"],
            headers=patient["headers"],
            resp_json=batch_a,
        )
        r = client.get(
            _batch_results_url(patient["patient_id"], batch_id),
            headers=patient["headers"],
        )
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert item.get("batch_id") == batch_id, (
                f"item {item['id']} missing/wrong batch_id"
            )
