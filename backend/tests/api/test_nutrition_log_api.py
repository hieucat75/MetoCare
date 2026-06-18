"""T18 API tests — Nutrition Log CRUD + RBAC.

Covers:
  POST /api/v1/patients/{patient_id}/nutrition  — create log
  GET  /api/v1/patients/{patient_id}/nutrition  — list logs (paginated)

10 test cases:
  1.  test_patient_logs_nutrition                     — 201, fields verified
  2.  test_patient_cannot_log_for_another_patient     — 403
  3.  test_doctor_logs_with_consent                   — 201
  4.  test_ai_service_cannot_log_nutrition            — 403 (safety critical)
  5.  test_patient_lists_nutrition_logs               — 200, items list
  6.  test_nutrition_log_ordered_newest_first         — first item has latest logged_at
  7.  test_unauthenticated_cannot_log_nutrition       — 401
  8.  test_log_with_all_optional_fields               — 201, all fields present
  9.  test_log_minimal_fields                         — 201, optional fields null
  10. test_pagination_limit                           — 200, respects limit param
"""

from __future__ import annotations

import datetime as dt
import os

import pytest
from app.core.security import create_access_token
from app.models.governance import Consent
from app.models.patient import PatientProfile
from app.models.user import User, UserRole
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def _nutrition_url(patient_id: str) -> str:
    return f"/api/v1/patients/{patient_id}/nutrition"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def patient_a(db):
    """Primary PATIENT user + PatientProfile + bearer headers."""
    user = User(
        email=f"t18-patient-a-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="T18 Patient A",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="T18 Patient A")
    db.add(profile)
    db.commit()
    token = create_access_token(subject=user.id, role="patient")
    return {
        "user_id": user.id,
        "patient_id": profile.id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def patient_b(db):
    """Second unrelated PATIENT user + PatientProfile."""
    user = User(
        email=f"t18-patient-b-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="T18 Patient B",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="T18 Patient B")
    db.add(profile)
    db.commit()
    token = create_access_token(subject=user.id, role="patient")
    return {
        "user_id": user.id,
        "patient_id": profile.id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def doctor(db):
    """DOCTOR user + bearer headers."""
    user = User(
        email=f"t18-doctor-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="T18 Doctor",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="doctor", mfa=True)
    return {
        "user_id": user.id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def doctor_consent_for_patient_a(db, patient_a, doctor):
    """Grant doctor active consent (scope='profile') for patient_a."""
    consent = Consent(
        patient_id=patient_a["patient_id"],
        consent_type="data_sharing",
        data_scope="profile",
        granted_to=doctor["user_id"],
    )
    db.add(consent)
    db.commit()
    return consent


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


# 1
def test_patient_logs_nutrition(client: TestClient, patient_a):
    """PATIENT can log a meal for their own profile — 201 with correct fields."""
    r = client.post(
        _nutrition_url(patient_a["patient_id"]),
        headers=patient_a["headers"],
        json={"description": "Pho bo with extra broth", "meal_type": "lunch"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["patient_id"] == patient_a["patient_id"]
    assert body["description"] == "Pho bo with extra broth"
    assert body["meal_type"] == "lunch"
    assert "id" in body
    assert "logged_at" in body
    assert "created_at" in body


# 2
def test_patient_cannot_log_for_another_patient(
    client: TestClient, patient_a, patient_b
):
    """PATIENT cannot log nutrition on another patient's record — 403."""
    r = client.post(
        _nutrition_url(patient_b["patient_id"]),
        headers=patient_a["headers"],
        json={"description": "Stolen breakfast"},
    )
    assert r.status_code == 403, r.text


# 3
def test_doctor_logs_with_consent(
    client: TestClient, patient_a, doctor, doctor_consent_for_patient_a
):
    """DOCTOR with active consent can log nutrition for a patient — 201."""
    r = client.post(
        _nutrition_url(patient_a["patient_id"]),
        headers=doctor["headers"],
        json={"description": "Doctor-observed meal plan", "meal_type": "dinner"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["patient_id"] == patient_a["patient_id"]


# 4
def test_ai_service_cannot_log_nutrition(client: TestClient, patient_a):
    """AI_SERVICE role must be blocked (403) — safety check."""
    ai_token = create_access_token(
        subject=f"ai-{os.urandom(4).hex()}", role="ai_service"
    )
    r = client.post(
        _nutrition_url(patient_a["patient_id"]),
        headers={"Authorization": f"Bearer {ai_token}"},
        json={"description": "AI-generated meal log"},
    )
    assert r.status_code == 403, r.text


# 5
def test_patient_lists_nutrition_logs(client: TestClient, patient_a):
    """PATIENT can GET their own nutrition list — 200, correct structure."""
    # Seed one log
    client.post(
        _nutrition_url(patient_a["patient_id"]),
        headers=patient_a["headers"],
        json={"description": "Morning oatmeal", "meal_type": "breakfast"},
    )

    r = client.get(_nutrition_url(patient_a["patient_id"]), headers=patient_a["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["patient_id"] == patient_a["patient_id"]
    assert isinstance(body["items"], list)
    assert body["total"] >= 1


# 6
def test_nutrition_log_ordered_newest_first(client: TestClient, patient_a):
    """Nutrition logs returned newest logged_at first."""
    old_time = "2026-01-01T08:00:00+00:00"
    new_time = "2026-06-15T12:00:00+00:00"

    client.post(
        _nutrition_url(patient_a["patient_id"]),
        headers=patient_a["headers"],
        json={"description": "Old breakfast", "logged_at": old_time},
    )
    client.post(
        _nutrition_url(patient_a["patient_id"]),
        headers=patient_a["headers"],
        json={"description": "Recent lunch", "logged_at": new_time},
    )

    r = client.get(_nutrition_url(patient_a["patient_id"]), headers=patient_a["headers"])
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    # newest first: "Recent lunch" should appear before "Old breakfast"
    descriptions = [i["description"] for i in items]
    assert descriptions.index("Recent lunch") < descriptions.index("Old breakfast"), (
        "Logs should be ordered newest logged_at first"
    )


# 7
def test_unauthenticated_cannot_log_nutrition(client: TestClient, patient_a):
    """Requests without a bearer token must be rejected with 401."""
    r = client.post(
        _nutrition_url(patient_a["patient_id"]),
        json={"description": "Unauthenticated snack"},
    )
    assert r.status_code == 401, r.text


# 8
def test_log_with_all_optional_fields(client: TestClient, patient_a):
    """Logging with all optional fields returns 201 and all fields in the response."""
    logged_at = "2026-06-18T07:30:00+00:00"
    r = client.post(
        _nutrition_url(patient_a["patient_id"]),
        headers=patient_a["headers"],
        json={
            "description": "Full English breakfast",
            "meal_type": "breakfast",
            "calories_kcal": 850,
            "logged_at": logged_at,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["description"] == "Full English breakfast"
    assert body["meal_type"] == "breakfast"
    assert body["calories_kcal"] == 850
    # logged_at should be preserved (timezone-aware parsing may normalise format)
    assert body["logged_at"] is not None


# 9
def test_log_minimal_fields(client: TestClient, patient_a):
    """Logging with only description returns 201 and optional fields are null."""
    r = client.post(
        _nutrition_url(patient_a["patient_id"]),
        headers=patient_a["headers"],
        json={"description": "Mystery snack"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["description"] == "Mystery snack"
    assert body["meal_type"] is None
    assert body["calories_kcal"] is None


# 10
def test_pagination_limit(client: TestClient, patient_a):
    """GET /nutrition respects the `limit` query parameter."""
    # Seed 5 logs
    for i in range(5):
        client.post(
            _nutrition_url(patient_a["patient_id"]),
            headers=patient_a["headers"],
            json={"description": f"Meal {i}"},
        )

    # Request only 3
    r = client.get(
        _nutrition_url(patient_a["patient_id"]),
        headers=patient_a["headers"],
        params={"limit": 3},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["items"]) == 3
    assert body["total"] >= 5
