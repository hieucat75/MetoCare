"""API tests for POST /care_plans/{care_plan_id}/approve."""

from __future__ import annotations

import os

import pytest
from app.core.security import create_access_token
from app.models.care import CarePlan, Clinic, Doctor, DoctorClinic, Encounter
from app.models.patient import PatientProfile
from app.models.user import User, UserRole


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
def care_plan_for_patient(db, patient_setup, doctor_setup):
    """Seed a draft care plan for the patient."""
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


def test_doctor_approves_care_plan(client, doctor_setup, patient_setup, care_plan_for_patient):
    """DOCTOR + DRAFT plan -> 200, status=APPROVED."""
    r = client.post(
        f"/api/v1/care_plans/{care_plan_for_patient.id}/approve",
        headers=doctor_setup["headers"],
        json={"approved_by_doctor_id": doctor_setup["doctor_id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "APPROVED"
    assert body["approved_by_doctor_id"] == doctor_setup["doctor_id"]
    assert body["approved_at"] is not None


def test_patient_cannot_approve_care_plan(
    client, patient_setup, doctor_setup, care_plan_for_patient
):
    """PATIENT -> 403."""
    r = client.post(
        f"/api/v1/care_plans/{care_plan_for_patient.id}/approve",
        headers=patient_setup["headers"],
        json={"approved_by_doctor_id": doctor_setup["doctor_id"]},
    )
    assert r.status_code == 403, r.text


def test_ai_cannot_approve_care_plan_via_approve_ep(client, doctor_setup, care_plan_for_patient):
    """AI_SERVICE -> 403."""
    ai_id = f"ai-svc-{os.urandom(4).hex()}"
    ai_token = create_access_token(subject=ai_id, role="ai_service", mfa=False)
    r = client.post(
        f"/api/v1/care_plans/{care_plan_for_patient.id}/approve",
        headers={"Authorization": f"Bearer {ai_token}"},
        json={"approved_by_doctor_id": doctor_setup["doctor_id"]},
    )
    assert r.status_code == 403, r.text


def test_approve_already_approved_plan(client, db, doctor_setup, care_plan_for_patient):
    """Approving an already approved plan -> 409."""
    # Move status to APPROVED first via DB update to bypass validator
    from sqlalchemy import update
    db.execute(
        update(CarePlan)
        .where(CarePlan.id == care_plan_for_patient.id)
        .values(status="APPROVED")
    )
    db.commit()

    r = client.post(
        f"/api/v1/care_plans/{care_plan_for_patient.id}/approve",
        headers=doctor_setup["headers"],
        json={"approved_by_doctor_id": doctor_setup["doctor_id"]},
    )
    assert r.status_code == 409, r.text


def test_unauthenticated_cannot_approve(client, doctor_setup, care_plan_for_patient):
    """no token -> 401."""
    r = client.post(
        f"/api/v1/care_plans/{care_plan_for_patient.id}/approve",
        json={"approved_by_doctor_id": doctor_setup["doctor_id"]},
    )
    assert r.status_code == 401, r.text
