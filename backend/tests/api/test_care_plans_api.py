"""T5 API tests — CarePlan endpoints (RBAC + C2 AI guard)."""

from __future__ import annotations

import os

import pytest
from app.core.security import create_access_token
from app.models.care import CarePlan, Clinic, Doctor, DoctorClinic, Encounter
from app.models.patient import PatientProfile
from app.models.user import User, UserRole

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def doctor_setup(db):
    clinic = Clinic(name=f"Clinic-{os.urandom(4).hex()}", is_active=True)
    db.add(clinic)
    db.flush()

    d_user = User(
        email=f"doctor-cp-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="Dr. CarePlan",
    )
    db.add(d_user)
    db.flush()

    doctor = Doctor(
        user_id=d_user.id, clinic_id=clinic.id, full_name="Dr. CarePlan", is_active=True
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
        "doctor_obj": doctor,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def patient_setup(db):
    p_user = User(
        email=f"patient-cp-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Patient CP Test",
    )
    db.add(p_user)
    db.flush()

    profile = PatientProfile(user_id=p_user.id, full_name="Patient CP Test")
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
    p_user = User(
        email=f"patient2-cp-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Patient Other CP",
    )
    db.add(p_user)
    db.flush()

    profile = PatientProfile(user_id=p_user.id, full_name="Patient Other CP")
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
def care_plan_for_patient(db, patient_setup, doctor_setup):
    """Seed a care plan for the patient."""
    enc = Encounter(
        patient_id=patient_setup["patient_id"],
        doctor_id=doctor_setup["doctor_id"],
        encounter_type="consultation",
        status="pending_review",
    )
    db.add(enc)
    db.flush()

    plan = CarePlan(
        patient_id=patient_setup["patient_id"],
        encounter_id=enc.id,
        title="Test Care Plan",
        status="DRAFT",
        ai_generated=False,
        version=1,
    )
    db.add(plan)
    db.commit()
    return plan


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_doctor_creates_care_plan(client, doctor_setup, patient_setup):
    """Doctor can create a care plan — 201."""
    r = client.post(
        "/api/v1/care_plans",
        headers=doctor_setup["headers"],
        json={
            "patient_id": patient_setup["patient_id"],
            "title": "Diabetes Management Plan",
            "status": "DRAFT",
            "content": "Increase physical activity.",
            "ai_generated": False,
            "version": 1,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["title"] == "Diabetes Management Plan"
    assert body["status"] == "DRAFT"
    assert body["ai_generated"] is False


def test_patient_reads_own_care_plan(client, patient_setup, care_plan_for_patient):
    """Patient can read their own care plan — 200."""
    r = client.get(
        f"/api/v1/care_plans/{care_plan_for_patient.id}",
        headers=patient_setup["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["id"] == care_plan_for_patient.id


def test_patient_cannot_read_other_care_plan(client, another_patient_setup, care_plan_for_patient):
    """Patient B cannot read Patient A's care plan — 403."""
    r = client.get(
        f"/api/v1/care_plans/{care_plan_for_patient.id}",
        headers=another_patient_setup["headers"],
    )
    assert r.status_code == 403, r.text


def test_ai_cannot_approve_care_plan(client, care_plan_for_patient):
    """AI_SERVICE caller cannot approve a care plan — 403.

    The AI_SERVICE role is blocked from PATCH /care_plans entirely because
    the endpoint only allows DOCTOR / INTERNAL_ADMIN / SUPER_ADMIN.
    """
    ai_id = f"ai-svc-{os.urandom(4).hex()}"
    ai_token = create_access_token(subject=ai_id, role="ai_service", mfa=False)
    r = client.patch(
        f"/api/v1/care_plans/{care_plan_for_patient.id}",
        headers={"Authorization": f"Bearer {ai_token}"},
        json={"status": "APPROVED"},
    )
    # AI_SERVICE is not in the allowed write roles → 403
    assert r.status_code == 403, r.text
