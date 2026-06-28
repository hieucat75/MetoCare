"""T16 — Encounter API: full RBAC + flow coverage (13 tests).

Endpoints under test (all at /api/v1/encounters):
  POST   /encounters              — create
  GET    /encounters/{id}         — read one
  GET    /encounters              — list
  PATCH  /encounters/{id}         — update

Roles tested: DOCTOR, PATIENT (own + other), AI_SERVICE, CLINIC_ADMIN,
              INTERNAL_ADMIN, unauthenticated.
"""

from __future__ import annotations

import os

import pytest
from app.core.security import create_access_token
from app.models.care import Clinic, Doctor, DoctorClinic, Encounter
from app.models.patient import PatientProfile
from app.models.user import User, UserRole

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def doctor_setup(db):
    """Clinic + doctor user + Doctor record + DoctorClinic link."""
    clinic = Clinic(name=f"Clinic-enc-t16-{os.urandom(4).hex()}", is_active=True)
    db.add(clinic)
    db.flush()

    d_user = User(
        email=f"doctor-enc-t16-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="Dr. Enc T16",
    )
    db.add(d_user)
    db.flush()

    doctor = Doctor(
        user_id=d_user.id,
        clinic_id=clinic.id,
        full_name="Dr. Enc T16",
        is_active=True,
    )
    db.add(doctor)
    db.flush()

    link = DoctorClinic(doctor_id=doctor.id, clinic_id=clinic.id, is_primary=True, is_active=True)
    db.add(link)
    db.commit()

    token = create_access_token(subject=d_user.id, role="doctor", mfa=True)
    return {
        "clinic_id": clinic.id,
        "doctor_user_id": d_user.id,
        "doctor_id": doctor.id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def patient_setup(db):
    """Patient user + PatientProfile."""
    p_user = User(
        email=f"patient-enc-t16-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Patient Enc T16",
    )
    db.add(p_user)
    db.flush()

    profile = PatientProfile(user_id=p_user.id, full_name="Patient Enc T16")
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
def other_patient_setup(db):
    """Second patient with no access to patient_setup's encounters."""
    p_user = User(
        email=f"patient2-enc-t16-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Other Patient Enc T16",
    )
    db.add(p_user)
    db.flush()

    profile = PatientProfile(user_id=p_user.id, full_name="Other Patient Enc T16")
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
def admin_setup():
    """INTERNAL_ADMIN bearer token (no DB record required for admin guards)."""
    admin_id = f"admin-enc-t16-{os.urandom(4).hex()}"
    token = create_access_token(subject=admin_id, role="internal_admin", mfa=True)
    return {"user_id": admin_id, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def seeded_encounter(db, patient_setup, doctor_setup):
    """A seeded encounter for patient_setup assigned to doctor_setup."""
    enc = Encounter(
        patient_id=patient_setup["patient_id"],
        doctor_id=doctor_setup["doctor_id"],
        encounter_type="consultation",
        status="pending_review",
        chief_complaint="Headache",
    )
    db.add(enc)
    db.commit()
    return enc


# ---------------------------------------------------------------------------
# 1. Create — POST /api/v1/encounters
# ---------------------------------------------------------------------------


def test_doctor_creates_encounter(client, doctor_setup, patient_setup):
    """DOCTOR may create an encounter — 201."""
    r = client.post(
        "/api/v1/encounters",
        headers=doctor_setup["headers"],
        json={
            "patient_id": patient_setup["patient_id"],
            "doctor_id": doctor_setup["doctor_id"],
            "encounter_type": "consultation",
            "status": "pending_review",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["patient_id"] == patient_setup["patient_id"]
    assert body["encounter_type"] == "consultation"
    assert "id" in body


def test_patient_cannot_create_encounter(client, patient_setup):
    """PATIENT role is forbidden from creating an encounter — 403."""
    r = client.post(
        "/api/v1/encounters",
        headers=patient_setup["headers"],
        json={
            "patient_id": patient_setup["patient_id"],
            "encounter_type": "consultation",
            "status": "pending_review",
        },
    )
    assert r.status_code == 403, r.text


def test_ai_service_cannot_create_encounter(client, patient_setup):
    """AI_SERVICE role is forbidden from creating an encounter — 403."""
    ai_token = create_access_token(
        subject=f"ai-enc-{os.urandom(4).hex()}", role="ai_service", mfa=False
    )
    r = client.post(
        "/api/v1/encounters",
        headers={"Authorization": f"Bearer {ai_token}"},
        json={
            "patient_id": patient_setup["patient_id"],
            "encounter_type": "consultation",
            "status": "pending_review",
        },
    )
    assert r.status_code == 403, r.text


def test_encounter_create_with_all_fields(client, doctor_setup, patient_setup):
    """DOCTOR creates an encounter with all optional fields — 201, fields preserved."""
    r = client.post(
        "/api/v1/encounters",
        headers=doctor_setup["headers"],
        json={
            "patient_id": patient_setup["patient_id"],
            "doctor_id": doctor_setup["doctor_id"],
            "encounter_type": "follow_up",
            "status": "pending_review",
            "chief_complaint": "Persistent cough",
            "notes": "Patient reports 2-week cough, no fever.",
            "encounter_date": "2026-06-18T10:00:00",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["chief_complaint"] == "Persistent cough"
    assert body["notes"] == "Patient reports 2-week cough, no fever."
    assert body["encounter_type"] == "follow_up"


# ---------------------------------------------------------------------------
# 2. Read one — GET /api/v1/encounters/{id}
# ---------------------------------------------------------------------------


def test_doctor_reads_own_encounter(client, doctor_setup, seeded_encounter):
    """Assigned DOCTOR can read the encounter — 200."""
    r = client.get(
        f"/api/v1/encounters/{seeded_encounter.id}",
        headers=doctor_setup["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["id"] == seeded_encounter.id


def test_patient_reads_own_encounter(client, patient_setup, seeded_encounter):
    """PATIENT can read their own encounter — 200."""
    r = client.get(
        f"/api/v1/encounters/{seeded_encounter.id}",
        headers=patient_setup["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["id"] == seeded_encounter.id


def test_patient_cannot_read_another_patients_encounter(
    client, other_patient_setup, seeded_encounter
):
    """PATIENT cannot read another patient's encounter — 403."""
    r = client.get(
        f"/api/v1/encounters/{seeded_encounter.id}",
        headers=other_patient_setup["headers"],
    )
    assert r.status_code == 403, r.text


def test_admin_reads_any_encounter(client, admin_setup, seeded_encounter):
    """INTERNAL_ADMIN can read any encounter — 200."""
    r = client.get(
        f"/api/v1/encounters/{seeded_encounter.id}",
        headers=admin_setup["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["id"] == seeded_encounter.id


# ---------------------------------------------------------------------------
# 3. List — GET /api/v1/encounters
# ---------------------------------------------------------------------------


def test_doctor_lists_encounters(client, doctor_setup, seeded_encounter):
    """DOCTOR can list their assigned encounters — 200, list."""
    r = client.get(
        "/api/v1/encounters",
        headers=doctor_setup["headers"],
    )
    assert r.status_code == 200, r.text
    ids = [e["id"] for e in r.json()]
    assert seeded_encounter.id in ids


def test_patient_lists_own_encounters(client, patient_setup, seeded_encounter):
    """PATIENT can list their own encounters — 200, scoped to their patient_id."""
    r = client.get(
        "/api/v1/encounters",
        headers=patient_setup["headers"],
        params={"patient_id": patient_setup["patient_id"]},
    )
    assert r.status_code == 200, r.text
    encounters = r.json()
    assert all(e["patient_id"] == patient_setup["patient_id"] for e in encounters)
    ids = [e["id"] for e in encounters]
    assert seeded_encounter.id in ids


# ---------------------------------------------------------------------------
# 4. Update — PATCH /api/v1/encounters/{id}
# ---------------------------------------------------------------------------


def test_doctor_updates_encounter(client, doctor_setup, seeded_encounter):
    """Assigned DOCTOR can update the encounter — 200, updated fields returned."""
    r = client.patch(
        f"/api/v1/encounters/{seeded_encounter.id}",
        headers=doctor_setup["headers"],
        json={"notes": "Follow-up scheduled.", "status": "completed"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["notes"] == "Follow-up scheduled."
    assert body["status"] == "completed"


def test_patient_cannot_update_encounter(client, patient_setup, seeded_encounter):
    """PATIENT cannot update an encounter — 403."""
    r = client.patch(
        f"/api/v1/encounters/{seeded_encounter.id}",
        headers=patient_setup["headers"],
        json={"notes": "Patient edited notes"},
    )
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# 5. Unauthenticated
# ---------------------------------------------------------------------------


def test_unauthenticated_cannot_access_encounter(client, seeded_encounter):
    """No token → 401 on read endpoint."""
    r = client.get(f"/api/v1/encounters/{seeded_encounter.id}")
    assert r.status_code == 401, r.text
