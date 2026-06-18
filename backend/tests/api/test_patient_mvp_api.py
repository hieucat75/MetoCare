"""PA-03 — Patient App MVP API tests.

Covers the two core gaps identified during deploy smoke testing:

1. GET /auth/me → returns ``patient_profile_id`` for PATIENT callers
2. PATCH /patients/{id}/profile → upsert (creates profile on first call)
3. Notification endpoints for patient (smoke — full coverage in test_notifications_api.py)

Test cases (8):
  1. test_me_patient_no_profile              — PATIENT with no profile → patient_profile_id: null
  2. test_me_patient_with_profile            — PATIENT with profile → patient_profile_id is UUID
  3. test_me_doctor_no_patient_profile_id    — DOCTOR → patient_profile_id: null
  4. test_patient_profile_upsert_creates_on_first_patch  — PATCH → profile created, 200
  5. test_patient_profile_upsert_updates_on_second_patch — second PATCH updates existing
  6. test_notifications_list_patient         — GET /notifications → 200, list
  7. test_notifications_mark_read            — PATCH /notifications/{id}/read → 200
  8. test_notifications_unauthenticated      — GET /notifications without token → 401
"""

from __future__ import annotations

import os

import pytest  # noqa: F401
from app.core.security import create_access_token
from app.models.notification import Notification
from app.models.patient import PatientProfile
from app.models.user import User, UserRole
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

_ME_URL = "/api/v1/auth/me"
_NOTIF_URL = "/api/v1/notifications"


def _profile_url(patient_id: str) -> str:
    return f"/api/v1/patients/{patient_id}/profile"


def _notif_read_url(notif_id: str) -> str:
    return f"/api/v1/notifications/{notif_id}/read"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def patient_no_profile(db):
    """PATIENT user with NO PatientProfile — the first-launch scenario."""
    user = User(
        email=f"pa03-noprofile-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="No-Profile Patient",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="patient")
    return {
        "user_id": user.id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def patient_with_profile(db):
    """PATIENT user WITH an existing PatientProfile."""
    user = User(
        email=f"pa03-profile-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Profile Patient",
    )
    db.add(user)
    db.flush()

    profile = PatientProfile(
        user_id=user.id,
        full_name="Profile Patient",
        gender="female",
        height_cm=162.0,
        weight_kg=55.0,
    )
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
def doctor_ctx(db):
    """DOCTOR user (no patient profile, MFA verified)."""
    user = User(
        email=f"pa03-doctor-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="Dr. PA03",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="doctor", mfa=True)
    return {
        "user_id": user.id,
        "headers": {"Authorization": f"Bearer {token}"},
    }


# ---------------------------------------------------------------------------
# 1. GET /auth/me — patient with NO profile
# ---------------------------------------------------------------------------


def test_me_patient_no_profile(client: TestClient, patient_no_profile):
    """PATIENT with no PatientProfile → GET /auth/me returns patient_profile_id: null."""
    r = client.get(_ME_URL, headers=patient_no_profile["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == patient_no_profile["user_id"]
    assert body["role"] == "patient"
    assert "patient_profile_id" in body
    assert body["patient_profile_id"] is None


# ---------------------------------------------------------------------------
# 2. GET /auth/me — patient WITH profile
# ---------------------------------------------------------------------------


def test_me_patient_with_profile(client: TestClient, patient_with_profile):
    """PATIENT with existing PatientProfile → GET /auth/me returns patient_profile_id (UUID)."""
    r = client.get(_ME_URL, headers=patient_with_profile["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == patient_with_profile["user_id"]
    assert body["role"] == "patient"
    assert "patient_profile_id" in body
    pid = body["patient_profile_id"]
    assert pid is not None
    assert pid == patient_with_profile["patient_id"]
    # Must look like a UUID (length 36, contains dashes)
    assert len(pid) == 36
    assert pid.count("-") == 4


# ---------------------------------------------------------------------------
# 3. GET /auth/me — doctor → patient_profile_id always null
# ---------------------------------------------------------------------------


def test_me_doctor_no_patient_profile_id(client: TestClient, doctor_ctx):
    """DOCTOR calling GET /auth/me → patient_profile_id is always null."""
    r = client.get(_ME_URL, headers=doctor_ctx["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "doctor"
    assert body.get("patient_profile_id") is None


# ---------------------------------------------------------------------------
# 4. PATCH /patients/{user_id}/profile — upsert: creates profile on first call
# ---------------------------------------------------------------------------


def test_patient_profile_upsert_creates_on_first_patch(
    client: TestClient, db, patient_no_profile
):
    """PATIENT with no profile: PATCH /patients/{user_id}/profile → 200, profile auto-created."""
    user_id = patient_no_profile["user_id"]

    r = client.patch(
        _profile_url(user_id),
        headers=patient_no_profile["headers"],
        json={"full_name": "Onboarded Patient", "gender": "male", "weight_kg": 72.0},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["full_name"] == "Onboarded Patient"
    assert body["gender"] == "male"
    assert body["weight_kg"] == 72.0
    assert "id" in body
    assert body["user_id"] == user_id

    # Verify the record was actually persisted in the DB
    db.expire_all()
    from sqlalchemy import select

    profile = db.execute(
        select(PatientProfile).where(PatientProfile.user_id == user_id)
    ).scalar_one_or_none()
    assert profile is not None, "PatientProfile should have been created in DB"
    assert profile.full_name == "Onboarded Patient"


# ---------------------------------------------------------------------------
# 5. PATCH /patients/{patient_id}/profile — upsert: second call updates
# ---------------------------------------------------------------------------


def test_patient_profile_upsert_updates_on_second_patch(
    client: TestClient, patient_with_profile
):
    """Second PATCH on existing profile → updates fields correctly."""
    patient_id = patient_with_profile["patient_id"]
    headers = patient_with_profile["headers"]

    # First verify baseline
    r = client.get(_profile_url(patient_id), headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["weight_kg"] == 55.0

    # Update weight_kg
    r2 = client.patch(
        _profile_url(patient_id),
        headers=headers,
        json={"weight_kg": 58.5},
    )
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["weight_kg"] == 58.5
    # height_cm must be unchanged
    assert body["height_cm"] == 162.0


# ---------------------------------------------------------------------------
# 6. GET /notifications — patient list
# ---------------------------------------------------------------------------


def test_notifications_list_patient(client: TestClient, db, patient_with_profile):
    """PATIENT GET /notifications → 200, returns a list."""
    # Seed a notification directly
    notif = Notification(
        user_id=patient_with_profile["user_id"],
        type="system",
        title="PA-03 Test",
        body="Test notification body.",
    )
    db.add(notif)
    db.commit()

    r = client.get(_NOTIF_URL, headers=patient_with_profile["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)
    assert len(body) >= 1
    # All returned notifications belong to this user
    for item in body:
        assert item["user_id"] == patient_with_profile["user_id"]


# ---------------------------------------------------------------------------
# 7. PATCH /notifications/{id}/read — patient marks notification read
# ---------------------------------------------------------------------------


def test_notifications_mark_read(client: TestClient, db, patient_with_profile):
    """PATIENT PATCH /notifications/{id}/read → 200, is_read=True, read_at set."""
    notif = Notification(
        user_id=patient_with_profile["user_id"],
        type="appointment_reminder",
        title="Mark Me Read",
        body="Read this.",
        is_read=False,
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)

    r = client.patch(_notif_read_url(notif.id), headers=patient_with_profile["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == notif.id
    assert body["is_read"] is True
    assert body["read_at"] is not None


# ---------------------------------------------------------------------------
# 8. GET /notifications — unauthenticated → 401
# ---------------------------------------------------------------------------


def test_notifications_unauthenticated(client: TestClient):
    """GET /notifications without bearer token → 401."""
    r = client.get(_NOTIF_URL)
    assert r.status_code == 401, r.text
