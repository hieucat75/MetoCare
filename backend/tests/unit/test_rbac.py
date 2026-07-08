"""T5 unit tests — RBAC helpers (app/core/rbac.py)."""

from __future__ import annotations

import os

import pytest
from app.core.rbac import (
    assert_clinic_membership,
    assert_clinic_writable,
    assert_doctor_assigned,
    assert_doctor_clinic_scope_for_patient,
    assert_patient_owns,
    require_clinic_roles,
)
from app.models.care import Clinic, Doctor, DoctorClinic
from app.models.clinic import (
    ClinicMembership,
    ClinicMembershipStatus,
    ClinicPatientRelationship,
    ClinicPatientRelationshipStatus,
    ClinicRole,
)
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

    doctor = Doctor(user_id=d_user.id, clinic_id=clinic.id, full_name="RBAC Doctor", is_active=True)
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


# ---------------------------------------------------------------------------
# assert_clinic_membership (Clinic SaaS Phase C0 — replaces the assert_clinic_scope
# stub that used to accept ANY clinic_admin role for ANY clinic id)
# ---------------------------------------------------------------------------


@pytest.fixture
def clinic_with_member(db):
    clinic = Clinic(name=f"RBAC-C0-Clinic-{os.urandom(4).hex()}", is_active=True)
    db.add(clinic)
    db.flush()

    user = User(
        email=f"rbac-c0-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.CLINIC_ADMIN,
        full_name="RBAC Clinic Member",
    )
    db.add(user)
    db.flush()

    membership = ClinicMembership(
        user_id=user.id,
        clinic_id=clinic.id,
        roles=[ClinicRole.ADMIN],
        branch_ids=[],
        status=ClinicMembershipStatus.ACTIVE,
    )
    db.add(membership)
    db.commit()
    return {"clinic_id": clinic.id, "user_id": user.id, "clinic": clinic}


def test_assert_clinic_membership_passes_for_active_member(db, clinic_with_member):
    membership = assert_clinic_membership(
        db,
        clinic_with_member["user_id"],
        clinic_with_member["clinic_id"],
        role=UserRole.CLINIC_ADMIN,
    )
    assert membership is not None
    assert membership.clinic_id == clinic_with_member["clinic_id"]


def test_assert_clinic_membership_rejects_any_clinic_admin_for_any_clinic(db, clinic_with_member):
    """The bug this replaces: the old stub accepted ANY clinic_admin role for
    ANY clinic id. A CLINIC_ADMIN platform role with NO membership row at this
    clinic must now be rejected."""
    with pytest.raises(HTTPException) as exc_info:
        assert_clinic_membership(
            db, "some-other-clinic-admin-user-id", clinic_with_member["clinic_id"],
            role=UserRole.CLINIC_ADMIN,
        )
    assert exc_info.value.status_code == 403


def test_assert_clinic_membership_enforces_required_roles(db, clinic_with_member):
    """Membership exists (roles=["admin"]) but the action requires "owner"."""
    with pytest.raises(HTTPException) as exc_info:
        assert_clinic_membership(
            db,
            clinic_with_member["user_id"],
            clinic_with_member["clinic_id"],
            role=UserRole.CLINIC_ADMIN,
            required_roles=[ClinicRole.OWNER],
        )
    assert exc_info.value.status_code == 403


def test_assert_clinic_membership_admin_platform_role_bypasses(db, clinic_with_member):
    """INTERNAL_ADMIN/SUPER_ADMIN bypass — their cross-tenant access is the
    separate, always-audited `require_platform_override` path, never this."""
    result = assert_clinic_membership(
        db, "any-user-id", clinic_with_member["clinic_id"], role=UserRole.SUPER_ADMIN
    )
    assert result is None


def test_assert_clinic_membership_medical_reviewer_does_not_bypass(db, clinic_with_member):
    """Codex PR #96 review (P2): the docstring says only INTERNAL_ADMIN/
    SUPER_ADMIN bypass, but the code used to call the broader `_is_admin`
    (which also covers MEDICAL_REVIEWER, a read-only reviewer role with no
    business bypassing clinic-tenant membership). A MEDICAL_REVIEWER with no
    membership row at this clinic must be rejected like any other caller."""
    with pytest.raises(HTTPException) as exc_info:
        assert_clinic_membership(
            db,
            "some-reviewer-user-id",
            clinic_with_member["clinic_id"],
            role=UserRole.MEDICAL_REVIEWER,
        )
    assert exc_info.value.status_code == 403


def test_require_clinic_roles_rejects_insufficient_role():
    with pytest.raises(HTTPException) as exc_info:
        require_clinic_roles([ClinicRole.NURSE], ClinicRole.OWNER, ClinicRole.ADMIN)
    assert exc_info.value.status_code == 403


def test_require_clinic_roles_passes_with_matching_role():
    require_clinic_roles([ClinicRole.OWNER], ClinicRole.OWNER, ClinicRole.ADMIN)  # no raise


def test_assert_clinic_writable_blocks_suspended_and_deactivated(clinic_with_member):
    clinic = clinic_with_member["clinic"]

    clinic.status = "active"
    assert_clinic_writable(clinic)  # no raise


# ---------------------------------------------------------------------------
# assert_doctor_clinic_scope_for_patient (Clinic SaaS Phase C0 — closes the
# cross-clinic Clinical Copilot gap, THREAT_MODEL.md §10)
# ---------------------------------------------------------------------------


def test_assert_doctor_clinic_scope_noop_for_unlinked_patient(db, patient_profile):
    """A patient with zero ClinicPatientRelationship rows (every patient in
    production today) is unaffected — no exception, regardless of who the
    doctor is."""
    assert_doctor_clinic_scope_for_patient(
        db, doctor_user_id="any-doctor-user-id", patient_id=patient_profile.id
    )  # no raise


def test_assert_doctor_clinic_scope_passes_for_same_clinic_doctor(
    db, patient_profile, clinic_with_member
):
    clinic_id = clinic_with_member["clinic_id"]
    db.add(
        ClinicPatientRelationship(
            patient_id=patient_profile.id,
            clinic_id=clinic_id,
            patient_code="PT-0001",
            status=ClinicPatientRelationshipStatus.ACTIVE,
        )
    )
    doctor_user = User(
        email=f"rbac-c0-doctor-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="RBAC C0 Doctor",
    )
    db.add(doctor_user)
    db.flush()
    db.add(
        ClinicMembership(
            user_id=doctor_user.id,
            clinic_id=clinic_id,
            roles=[ClinicRole.DOCTOR],
            branch_ids=[],
            status=ClinicMembershipStatus.ACTIVE,
        )
    )
    db.commit()

    assert_doctor_clinic_scope_for_patient(
        db, doctor_user_id=doctor_user.id, patient_id=patient_profile.id
    )  # no raise — same clinic, real doctor-role membership


def test_assert_doctor_clinic_scope_rejects_cross_clinic_doctor(
    db, patient_profile, clinic_with_member
):
    """The exact scenario THREAT_MODEL.md §10 describes: a doctor with an
    active consent record (checked elsewhere) but who belongs to a
    DIFFERENT clinic than the one that actually treats this patient."""
    patient_clinic_id = clinic_with_member["clinic_id"]
    db.add(
        ClinicPatientRelationship(
            patient_id=patient_profile.id,
            clinic_id=patient_clinic_id,
            patient_code="PT-0002",
            status=ClinicPatientRelationshipStatus.ACTIVE,
        )
    )
    other_clinic = Clinic(name=f"RBAC-C0-OtherClinic-{os.urandom(4).hex()}", is_active=True)
    db.add(other_clinic)
    db.flush()
    doctor_user = User(
        email=f"rbac-c0-otherdoctor-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="RBAC C0 Other-Clinic Doctor",
    )
    db.add(doctor_user)
    db.flush()
    db.add(
        ClinicMembership(
            user_id=doctor_user.id,
            clinic_id=other_clinic.id,
            roles=[ClinicRole.DOCTOR],
            branch_ids=[],
            status=ClinicMembershipStatus.ACTIVE,
        )
    )
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        assert_doctor_clinic_scope_for_patient(
            db, doctor_user_id=doctor_user.id, patient_id=patient_profile.id
        )
    assert exc_info.value.status_code == 403


def test_assert_doctor_clinic_scope_rejects_non_doctor_role_member(
    db, patient_profile, clinic_with_member
):
    """Membership at the RIGHT clinic is not enough on its own — the caller
    must actually hold the `doctor` role there (RBAC_MATRIX.md M14: Clinical
    Copilot is Doctor-only, no Owner/Admin override)."""
    clinic_id = clinic_with_member["clinic_id"]
    db.add(
        ClinicPatientRelationship(
            patient_id=patient_profile.id,
            clinic_id=clinic_id,
            patient_code="PT-0003",
            status=ClinicPatientRelationshipStatus.ACTIVE,
        )
    )
    db.commit()

    # clinic_with_member["user_id"] holds only the "admin" role at this clinic.
    with pytest.raises(HTTPException) as exc_info:
        assert_doctor_clinic_scope_for_patient(
            db, doctor_user_id=clinic_with_member["user_id"], patient_id=patient_profile.id
        )
    assert exc_info.value.status_code == 403


def test_assert_clinic_writable_blocks_suspended_and_deactivated_statuses(clinic_with_member):
    clinic = clinic_with_member["clinic"]

    clinic.status = "suspended"
    with pytest.raises(HTTPException) as exc_info:
        assert_clinic_writable(clinic)
    assert exc_info.value.status_code == 403

    clinic.status = "deactivated"
    with pytest.raises(HTTPException) as exc_info:
        assert_clinic_writable(clinic)
    assert exc_info.value.status_code == 403
