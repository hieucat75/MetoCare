"""T18A — Consent List API tests.

Covers GET /patients/{patient_id}/consents (new endpoint):
  - Patient can list their own active consents
  - Patient cannot list another patient's consents
  - Doctor/AI_SERVICE are blocked (403)
  - Admin can list any patient's consents
  - active_only filter works (revoked consents excluded by default)
"""

from __future__ import annotations

import os

import pytest
from app.core.clock import utcnow
from app.core.security import create_access_token
from app.models.governance import Consent
from app.models.patient import PatientProfile
from app.models.user import User, UserRole


@pytest.fixture
def patient_setup(db):
    user = User(
        email=f"clist-patient-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Consent List Patient",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="Consent List Patient")
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
def other_patient_setup(db):
    user = User(
        email=f"clist-other-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Other Patient",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="Other Patient")
    db.add(profile)
    db.commit()
    token = create_access_token(subject=user.id, role="patient")
    return {
        "user_id": user.id,
        "patient_id": profile.id,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def doctor_setup(db):
    user = User(
        email=f"clist-doctor-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="Dr. List",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="doctor", mfa=True)
    return {"user_id": user.id, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def admin_setup(db):
    user = User(
        email=f"clist-admin-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=UserRole.INTERNAL_ADMIN,
        full_name="Admin List",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="internal_admin", mfa=True)
    return {"user_id": user.id, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def ai_service_setup(db):
    user = User(
        email=f"clist-ai-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=UserRole.AI_SERVICE,
        full_name="AI Service",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="ai_service")
    return {"user_id": user.id, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def two_consents(db, patient_setup, doctor_setup):
    c1 = Consent(
        patient_id=patient_setup["patient_id"],
        consent_type="lab_access",
        data_scope="lab",
        granted_to=doctor_setup["user_id"],
    )
    c2 = Consent(
        patient_id=patient_setup["patient_id"],
        consent_type="ai_use",
        data_scope="*",
        granted_to=doctor_setup["user_id"],
    )
    db.add(c1)
    db.add(c2)
    db.flush()
    c2.revoked_at = utcnow()
    db.commit()
    return {"active": c1, "revoked": c2}


def test_patient_can_list_own_active_consents(client, patient_setup, two_consents):
    """T18A-CL01: Patient lists their own active consents only."""
    r = client.get(
        f"/api/v1/patients/{patient_setup['patient_id']}/consents",
        headers=patient_setup["headers"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [item["id"] for item in body]
    assert two_consents["active"].id in ids
    assert two_consents["revoked"].id not in ids


def test_patient_can_list_all_consents_with_flag(client, patient_setup, two_consents):
    """T18A-CL02: active_only=false returns all consents."""
    r = client.get(
        f"/api/v1/patients/{patient_setup['patient_id']}/consents?active_only=false",
        headers=patient_setup["headers"],
    )
    assert r.status_code == 200, r.text
    ids = [item["id"] for item in r.json()]
    assert two_consents["active"].id in ids
    assert two_consents["revoked"].id in ids


def test_patient_cannot_list_other_patients_consents(client, patient_setup, other_patient_setup):
    """T18A-CL03: Patient cannot access another patient's consent list."""
    r = client.get(
        f"/api/v1/patients/{other_patient_setup['patient_id']}/consents",
        headers=patient_setup["headers"],
    )
    assert r.status_code == 403, r.text


def test_doctor_cannot_list_patient_consents(client, patient_setup, doctor_setup):
    """T18A-CL04: Doctor is blocked from listing consent records."""
    r = client.get(
        f"/api/v1/patients/{patient_setup['patient_id']}/consents",
        headers=doctor_setup["headers"],
    )
    assert r.status_code == 403, r.text


def test_ai_service_cannot_list_patient_consents(client, patient_setup, ai_service_setup):
    """T18A-CL05: AI_SERVICE is blocked from listing consent records."""
    r = client.get(
        f"/api/v1/patients/{patient_setup['patient_id']}/consents",
        headers=ai_service_setup["headers"],
    )
    assert r.status_code == 403, r.text


def test_admin_can_list_any_patient_consents(client, patient_setup, admin_setup, two_consents):
    """T18A-CL06: Admin can list consents for any patient."""
    r = client.get(
        f"/api/v1/patients/{patient_setup['patient_id']}/consents",
        headers=admin_setup["headers"],
    )
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


def test_unauthenticated_cannot_list_consents(client, patient_setup):
    """T18A-CL07: No token returns 401."""
    r = client.get(f"/api/v1/patients/{patient_setup['patient_id']}/consents")
    assert r.status_code == 401, r.text


def test_list_consents_nonexistent_patient(client, admin_setup):
    """T18A-CL08: Admin lists consents for non-existent patient returns 404."""
    r = client.get(
        "/api/v1/patients/00000000-0000-0000-0000-000000000000/consents",
        headers=admin_setup["headers"],
    )
    assert r.status_code == 404, r.text
