"""T5 unit tests — RBAC helpers (app/core/rbac.py)."""

from __future__ import annotations

import os

import pytest
from app.core.rbac import assert_doctor_assigned, assert_patient_owns
from app.models.care import Clinic, Doctor, DoctorClinic
from app.models.patient import PatientProfile
from app.models.user import User, UserRole
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def patient_profile(db):
    user = User(
        email=f"rbac-patient-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="RBAC Patient",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="RBAC Patient")
    db.add(profile)
    db.commit()
    return profile


@pytest.fixture
def doctor_with_clinic(db):
    clinic = Clinic(name=f"RBAC-Clinic-{os.urandom(4).hex()}", is_active=True)
    db.add(clinic)
    db.flush()

    d_user = User(
        email=f"rbac-doctor-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="RBAC Doctor",
    )
    db.add(d_user)
    db.flush()

    doctor = Doctor(
        user_id=d_user.id, clinic_id=clinic.id, full_name="RBAC Doctor", is_active=True
    )
    db.add(doctor)
    db.flush()

    link = DoctorClinic(doctor_id=doctor.id, clinic_id=clinic.id, is_primary=True, is_active=True)
    db.add(link)
    db.commit()

    return {"clinic_id": clinic.id, "doctor_user_id": d_user.id, "doctor_id": doctor.id}


# ---------------------------------------------------------------------------
# assert_patient_owns
# ---------------------------------------------------------------------------

def test_patient_own_resource_passes(patient_profile):
    """Patient accessing their own resource (user_id matches) — no exception."""
    # The function checks current_user_id vs patient_id (the PatientProfile id or user_id)
    # Here we simulate: patient's user_id == patient profile user_id → pass
    assert_patient_owns(
        current_user_id=patient_profile.user_id,
        patient_id=patient_profile.user_id,  # ownership by user_id
        role=UserRole.PATIENT,
    )  # Should not raise


def test_patient_other_resource_raises_403(patient_profile):
    """Patient accessing another patient's resource — 403."""
    with pytest.raises(HTTPException) as exc_info:
        assert_patient_owns(
            current_user_id="stranger-user-id",
            patient_id=patient_profile.user_id,
            role=UserRole.PATIENT,
        )
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# assert_doctor_assigned
# ---------------------------------------------------------------------------

def test_doctor_assigned_passes(db, doctor_with_clinic):
    """Doctor with active DoctorClinic to the patient's clinic — no exception."""
    assert_doctor_assigned(
        db,
        current_user_id=doctor_with_clinic["doctor_user_id"],
        patient_clinic_id=doctor_with_clinic["clinic_id"],
        role=UserRole.DOCTOR,
    )  # Should not raise


def test_doctor_unassigned_raises_403(db, doctor_with_clinic):
    """Doctor with no DoctorClinic link to this clinic — 403."""
    with pytest.raises(HTTPException) as exc_info:
        assert_doctor_assigned(
            db,
            current_user_id=doctor_with_clinic["doctor_user_id"],
            patient_clinic_id="nonexistent-clinic-id",
            role=UserRole.DOCTOR,
        )
    assert exc_info.value.status_code == 403


def test_doctor_direct_assignment_passes(db, doctor_with_clinic):
    """Doctor is directly assigned (assigned_doctor_user_id matches) — no exception."""
    assert_doctor_assigned(
        db,
        current_user_id=doctor_with_clinic["doctor_user_id"],
        patient_clinic_id=None,  # No clinic scope
        role=UserRole.DOCTOR,
        assigned_doctor_user_id=doctor_with_clinic["doctor_user_id"],
    )  # Should not raise


# ---------------------------------------------------------------------------
# Admin bypass
# ---------------------------------------------------------------------------

def test_admin_bypass(patient_profile):
    """INTERNAL_ADMIN bypasses patient-own check."""
    assert_patient_owns(
        current_user_id="some-admin-id",
        patient_id=patient_profile.user_id,
        role=UserRole.INTERNAL_ADMIN,
    )  # Should not raise


def test_super_admin_bypass(db, doctor_with_clinic):
    """SUPER_ADMIN bypasses doctor-assigned check."""
    assert_doctor_assigned(
        db,
        current_user_id="super-admin-id",
        patient_clinic_id="any-clinic",
        role=UserRole.SUPER_ADMIN,
    )  # Should not raise


def test_medical_reviewer_read_bypass(patient_profile):
    """MEDICAL_REVIEWER bypasses patient-own read check."""
    assert_patient_owns(
        current_user_id="reviewer-id",
        patient_id=patient_profile.user_id,
        role=UserRole.MEDICAL_REVIEWER,
    )  # Should not raise
