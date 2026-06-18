"""T12 API tests — Patient Profile endpoints (GET + PATCH + RBAC).

Covers:
  GET  /patients/{patient_id}/profile
  PATCH /patients/{patient_id}/profile

12 test cases:
  1.  test_patient_reads_own_profile                  — 200, has id field
  2.  test_patient_cannot_read_another_patients_profile — 403
  3.  test_doctor_reads_patient_profile               — 200 (with consent)
  4.  test_admin_reads_any_profile                    — 200
  5.  test_ai_service_cannot_read_profile             — 403
  6.  test_unauthenticated_cannot_read_profile        — 401
  7.  test_patient_updates_own_profile                — 200, fields updated
  8.  test_patient_cannot_update_another_patients_profile — 403
  9.  test_doctor_updates_patient_profile             — 200
  10. test_ai_service_cannot_update_profile           — 403
  11. test_partial_update_preserves_other_fields      — 200, only changed
  12. test_update_profile_creates_audit_record        — audit row in db
"""

from __future__ import annotations

import os

import pytest
from app.core.security import create_access_token
from app.models.governance import AuditLog, Consent
from app.models.patient import PatientProfile
from app.models.user import User, UserRole
from fastapi.testclient import TestClient
from sqlalchemy import select

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def patient_setup(db):
    """Primary patient user + profile + JWT."""
    p_user = User(
        email=f"pp-patient-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Profile Patient",
    )
    db.add(p_user)
    db.flush()

    profile = PatientProfile(
        user_id=p_user.id,
        full_name="Profile Patient",
        gender="male",
        height_cm=175.0,
        weight_kg=70.0,
    )
    db.add(profile)
    db.commit()

    token = create_access_token(subject=p_user.id, role="patient")
    return {
        "user_id": p_user.id,
        "patient_id": profile.id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def another_patient_setup(db):
    """Second (unrelated) patient user + profile + JWT."""
    p_user = User(
        email=f"pp-patient2-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Other Patient",
    )
    db.add(p_user)
    db.flush()

    profile = PatientProfile(user_id=p_user.id, full_name="Other Patient")
    db.add(profile)
    db.commit()

    token = create_access_token(subject=p_user.id, role="patient")
    return {
        "user_id": p_user.id,
        "patient_id": profile.id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def doctor_setup(db):
    """Doctor user + JWT + consent granted to patient profile."""
    d_user = User(
        email=f"pp-doctor-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="Dr. Profile",
    )
    db.add(d_user)
    db.commit()

    token = create_access_token(subject=d_user.id, role="doctor", mfa=True)
    return {
        "user_id": d_user.id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def admin_setup():
    """INTERNAL_ADMIN bearer token (no DB row needed — JWT-only)."""
    admin_id = f"admin-{os.urandom(4).hex()}"
    token = create_access_token(subject=admin_id, role="internal_admin", mfa=True)
    return {
        "user_id": admin_id,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def consent_for_doctor(db, patient_setup, doctor_setup):
    """Grant the doctor active consent (scope='profile') for the primary patient."""
    consent = Consent(
        patient_id=patient_setup["patient_id"],
        consent_type="data_sharing",
        data_scope="profile",
        granted_to=doctor_setup["user_id"],
    )
    db.add(consent)
    db.commit()
    return consent


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _profile_url(patient_id: str) -> str:
    return f"/api/v1/patients/{patient_id}/profile"


# ---------------------------------------------------------------------------
# GET tests
# ---------------------------------------------------------------------------


def test_patient_reads_own_profile(client: TestClient, patient_setup):
    """PATIENT can read their own profile — 200 with id field."""
    r = client.get(_profile_url(patient_setup["patient_id"]), headers=patient_setup["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == patient_setup["patient_id"]
    assert body["user_id"] == patient_setup["user_id"]
    assert "full_name" in body
    # address / family_history / lifestyle_profile intentionally excluded (T12)
    assert "address" not in body
    assert "family_history" not in body
    assert "lifestyle_profile" not in body


def test_patient_cannot_read_another_patients_profile(
    client: TestClient, patient_setup, another_patient_setup
):
    """PATIENT A cannot read PATIENT B's profile — 403."""
    r = client.get(
        _profile_url(another_patient_setup["patient_id"]),
        headers=patient_setup["headers"],
    )
    assert r.status_code == 403, r.text


def test_doctor_reads_patient_profile(
    client: TestClient, patient_setup, doctor_setup, consent_for_doctor
):
    """DOCTOR with active consent can read the patient's profile — 200."""
    r = client.get(
        _profile_url(patient_setup["patient_id"]),
        headers=doctor_setup["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["id"] == patient_setup["patient_id"]


def test_admin_reads_any_profile(client: TestClient, patient_setup, admin_setup):
    """INTERNAL_ADMIN can read any patient profile — 200."""
    r = client.get(_profile_url(patient_setup["patient_id"]), headers=admin_setup["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["id"] == patient_setup["patient_id"]


def test_ai_service_cannot_read_profile(client: TestClient, patient_setup):
    """AI_SERVICE is blocked from reading profiles — 403."""
    ai_id = f"ai-{os.urandom(4).hex()}"
    token = create_access_token(subject=ai_id, role="ai_service")
    r = client.get(
        _profile_url(patient_setup["patient_id"]),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403, r.text


def test_unauthenticated_cannot_read_profile(client: TestClient, patient_setup):
    """No bearer token → 401."""
    r = client.get(_profile_url(patient_setup["patient_id"]))
    assert r.status_code == 401, r.text


# ---------------------------------------------------------------------------
# PATCH tests
# ---------------------------------------------------------------------------


def test_patient_updates_own_profile(client: TestClient, patient_setup):
    """PATIENT can PATCH their own profile — 200, updated fields returned."""
    r = client.patch(
        _profile_url(patient_setup["patient_id"]),
        headers=patient_setup["headers"],
        json={"full_name": "Updated Name", "weight_kg": 72.5},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["full_name"] == "Updated Name"
    assert body["weight_kg"] == 72.5


def test_patient_cannot_update_another_patients_profile(
    client: TestClient, patient_setup, another_patient_setup
):
    """PATIENT A cannot PATCH PATIENT B's profile — 403."""
    r = client.patch(
        _profile_url(another_patient_setup["patient_id"]),
        headers=patient_setup["headers"],
        json={"full_name": "Hijacked"},
    )
    assert r.status_code == 403, r.text


def test_doctor_updates_patient_profile(
    client: TestClient, patient_setup, doctor_setup
):
    """DOCTOR can PATCH any patient's profile — 200."""
    r = client.patch(
        _profile_url(patient_setup["patient_id"]),
        headers=doctor_setup["headers"],
        json={"known_conditions": "Type 2 Diabetes"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["known_conditions"] == "Type 2 Diabetes"


def test_ai_service_cannot_update_profile(client: TestClient, patient_setup):
    """AI_SERVICE is blocked from updating profiles — 403."""
    ai_id = f"ai-{os.urandom(4).hex()}"
    token = create_access_token(subject=ai_id, role="ai_service")
    r = client.patch(
        _profile_url(patient_setup["patient_id"]),
        headers={"Authorization": f"Bearer {token}"},
        json={"weight_kg": 99.0},
    )
    assert r.status_code == 403, r.text


def test_partial_update_preserves_other_fields(client: TestClient, patient_setup):
    """Partial PATCH only changes supplied fields; others are untouched — 200."""
    # First, read the current profile to capture baseline height
    r_get = client.get(_profile_url(patient_setup["patient_id"]), headers=patient_setup["headers"])
    assert r_get.status_code == 200, r_get.text
    original_height = r_get.json()["height_cm"]

    # Update only weight_kg
    r = client.patch(
        _profile_url(patient_setup["patient_id"]),
        headers=patient_setup["headers"],
        json={"weight_kg": 68.0},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["weight_kg"] == 68.0
    # height_cm must not have changed
    assert body["height_cm"] == original_height


def test_update_profile_creates_audit_record(
    client: TestClient, db, patient_setup
):
    """Every successful PATCH must produce an AuditLog row with action='update_profile'."""
    r = client.patch(
        _profile_url(patient_setup["patient_id"]),
        headers=patient_setup["headers"],
        json={"allergies": "Peanuts"},
    )
    assert r.status_code == 200, r.text

    audit_row = db.execute(
        select(AuditLog).where(
            AuditLog.action == "update_profile",
            AuditLog.resource_id == patient_setup["patient_id"],
        )
    ).scalar_one_or_none()

    assert audit_row is not None, "Expected an AuditLog row for update_profile"
    assert audit_row.outcome == "success"
    assert audit_row.resource_type == "patient_profile"
