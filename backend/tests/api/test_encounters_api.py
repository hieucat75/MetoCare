"""T5 API tests — Encounter endpoints (RBAC + scope enforcement)."""

from __future__ import annotations

import os

import pytest
from app.core.security import create_access_token
from app.models.care import Clinic, Doctor, DoctorClinic, Encounter
from app.models.patient import PatientProfile
from app.models.user import User, UserRole
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def api_client(client: TestClient) -> TestClient:
    return client


@pytest.fixture
def doctor_setup(db):
    """Create clinic, doctor user, doctor record, and DoctorClinic link."""
    clinic = Clinic(name=f"Clinic-{os.urandom(4).hex()}", is_active=True)
    db.add(clinic)
    db.flush()

    d_user = User(
        email=f"doctor-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="Dr. Test",
    )
    db.add(d_user)
    db.flush()

    doctor = Doctor(user_id=d_user.id, clinic_id=clinic.id, full_name="Dr. Test", is_active=True)
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
    """Create a patient user + patient profile."""
    p_user = User(
        email=f"patient-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Patient Test",
    )
    db.add(p_user)
    db.flush()

    profile = PatientProfile(user_id=p_user.id, full_name="Patient Test")
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
    """Create a second patient (different from the main one)."""
    p_user = User(
        email=f"patient2-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Patient Other",
    )
    db.add(p_user)
    db.flush()

    profile = PatientProfile(user_id=p_user.id, full_name="Patient Other")
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
    admin_id = f"admin-{os.urandom(4).hex()}"
    token = create_access_token(subject=admin_id, role="internal_admin", mfa=True)
    return {"user_id": admin_id, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def encounter_for_patient(db, patient_setup, doctor_setup):
    """Seed an encounter for the patient, assigned to the test doctor."""
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
# Tests
# ---------------------------------------------------------------------------


def test_doctor_can_create_encounter(client, doctor_setup, patient_setup):
    """Doctor POSTs an encounter for a patient — should get 201."""
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


def test_patient_cannot_create_encounter(client, patient_setup):
    """Patients are NOT allowed to create encounters — 403."""
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


def test_patient_reads_own_encounter(client, patient_setup, encounter_for_patient):
    """Patient reads their own encounter — 200."""
    r = client.get(
        f"/api/v1/encounters/{encounter_for_patient.id}",
        headers=patient_setup["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["id"] == encounter_for_patient.id


def test_patient_cannot_read_other_patient_encounter(
    client, another_patient_setup, encounter_for_patient
):
    """Patient A cannot read Patient B's encounter — 403."""
    r = client.get(
        f"/api/v1/encounters/{encounter_for_patient.id}",
        headers=another_patient_setup["headers"],
    )
    assert r.status_code == 403, r.text


def test_doctor_reads_assigned_encounter(client, doctor_setup, encounter_for_patient):
    """Assigned doctor can read the encounter — 200."""
    r = client.get(
        f"/api/v1/encounters/{encounter_for_patient.id}",
        headers=doctor_setup["headers"],
    )
    assert r.status_code == 200, r.text


def test_doctor_cannot_read_unassigned_encounter(client, db, patient_setup, encounter_for_patient):
    """An unrelated doctor cannot read another doctor's encounter — 403."""
    # Create a second doctor with no DoctorClinic link to the patient's encounter
    d2_user = User(
        email=f"doctor2-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="Dr. Unrelated",
    )
    db.add(d2_user)
    db.flush()
    clinic2 = Clinic(name=f"Clinic2-{os.urandom(4).hex()}", is_active=True)
    db.add(clinic2)
    db.flush()
    d2 = Doctor(user_id=d2_user.id, clinic_id=clinic2.id, full_name="Dr. Unrelated", is_active=True)
    db.add(d2)
    db.flush()
    link2 = DoctorClinic(doctor_id=d2.id, clinic_id=clinic2.id, is_primary=True, is_active=True)
    db.add(link2)
    db.commit()

    token2 = create_access_token(subject=d2_user.id, role="doctor", mfa=True)
    r = client.get(
        f"/api/v1/encounters/{encounter_for_patient.id}",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert r.status_code == 403, r.text


def test_admin_reads_any_encounter(client, admin_setup, encounter_for_patient):
    """Internal admin can read any encounter — 200."""
    r = client.get(
        f"/api/v1/encounters/{encounter_for_patient.id}",
        headers=admin_setup["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["id"] == encounter_for_patient.id
