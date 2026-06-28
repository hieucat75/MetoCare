"""T9 API tests — Consent Routes RBAC endpoints.

Covers both consent routes with RBAC enforcement:
  - POST   /patients/{patient_id}/consents          (grant)
  - DELETE /patients/{patient_id}/consents/{id}     (revoke)

P0 legal requirement: DOCTOR/ADMIN/AI_SERVICE MUST NOT be able to grant or
revoke patient consent. All such attempts must return 403.
"""

from __future__ import annotations

import os

import pytest
from app.core.security import create_access_token
from app.models.care import Clinic, Doctor, DoctorClinic
from app.models.governance import Consent
from app.models.patient import PatientProfile
from app.models.user import User, UserRole

# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------


def _grant_payload(granted_to: str) -> dict:
    return {
        "consent_type": "lab_access",
        "data_scope": "lab",
        "granted_to": granted_to,
        "valid_until": None,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def patient_setup(db):
    """Patient user + profile + JWT."""
    p_user = User(
        email=f"consent-patient-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Consent Patient",
    )
    db.add(p_user)
    db.flush()
    profile = PatientProfile(user_id=p_user.id, full_name="Consent Patient")
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
    """A second patient."""
    p_user = User(
        email=f"consent-patient2-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Consent Patient 2",
    )
    db.add(p_user)
    db.flush()
    profile = PatientProfile(user_id=p_user.id, full_name="Consent Patient 2")
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
    """Doctor user + doctor record + clinic + JWT (MFA=True)."""
    clinic = Clinic(name=f"Consent Clinic {os.urandom(4).hex()}", is_active=True)
    db.add(clinic)
    db.flush()

    d_user = User(
        email=f"consent-doctor-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="Dr. Consent",
    )
    db.add(d_user)
    db.flush()

    doctor = Doctor(user_id=d_user.id, clinic_id=clinic.id, full_name="Dr. Consent", is_active=True)
    db.add(doctor)
    db.flush()

    link = DoctorClinic(doctor_id=doctor.id, clinic_id=clinic.id, is_primary=True, is_active=True)
    db.add(link)
    db.commit()

    token = create_access_token(subject=d_user.id, role="doctor", mfa=True)
    return {
        "user_id": d_user.id,
        "doctor_id": doctor.id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def admin_setup(db):
    """INTERNAL_ADMIN user + JWT."""
    a_user = User(
        email=f"consent-admin-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=UserRole.INTERNAL_ADMIN,
        full_name="Consent Admin",
    )
    db.add(a_user)
    db.commit()
    token = create_access_token(subject=a_user.id, role="internal_admin", mfa=True)
    return {
        "user_id": a_user.id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def ai_service_setup(db):
    """AI_SERVICE user + JWT."""
    ai_user = User(
        email=f"consent-ai-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=UserRole.AI_SERVICE,
        full_name="AI Service",
    )
    db.add(ai_user)
    db.commit()
    token = create_access_token(subject=ai_user.id, role="ai_service")
    return {
        "user_id": ai_user.id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def patient_consent(db, patient_setup, doctor_setup):
    """An existing active consent granted by patient to doctor."""
    c = Consent(
        patient_id=patient_setup["patient_id"],
        consent_type="lab_access",
        data_scope="lab",
        granted_to=doctor_setup["user_id"],
    )
    db.add(c)
    db.commit()
    return c


# ---------------------------------------------------------------------------
# POST /patients/{patient_id}/consents (grant)
# ---------------------------------------------------------------------------


def test_patient_grants_consent_for_own_data(client, db, patient_setup, doctor_setup):
    """T9-C01: PATIENT grants consent for their own profile → 201."""
    r = client.post(
        f"/api/v1/patients/{patient_setup['patient_id']}/consents",
        headers=patient_setup["headers"],
        json=_grant_payload(doctor_setup["user_id"]),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["patient_id"] == patient_setup["patient_id"]
    assert body["granted_to"] == doctor_setup["user_id"]
    assert body["id"]


def test_patient_cannot_grant_consent_for_another_patient(
    client, db, patient_setup, another_patient_setup, doctor_setup
):
    """T9-C02: PATIENT using their token on another patient's profile → 403."""
    r = client.post(
        f"/api/v1/patients/{another_patient_setup['patient_id']}/consents",
        headers=patient_setup["headers"],  # patient 1 token, patient 2 path
        json=_grant_payload(doctor_setup["user_id"]),
    )
    assert r.status_code == 403, r.text


def test_doctor_cannot_grant_consent(client, db, patient_setup, doctor_setup):
    """T9-C03: DOCTOR attempting to grant consent → 403 (P0 legal violation)."""
    r = client.post(
        f"/api/v1/patients/{patient_setup['patient_id']}/consents",
        headers=doctor_setup["headers"],
        json=_grant_payload(doctor_setup["user_id"]),
    )
    assert r.status_code == 403, r.text


def test_admin_cannot_grant_consent(client, db, patient_setup, admin_setup, doctor_setup):
    """T9-C04: INTERNAL_ADMIN attempting to grant consent → 403 (P0 legal violation)."""
    r = client.post(
        f"/api/v1/patients/{patient_setup['patient_id']}/consents",
        headers=admin_setup["headers"],
        json=_grant_payload(doctor_setup["user_id"]),
    )
    assert r.status_code == 403, r.text


def test_ai_service_cannot_grant_consent(client, db, patient_setup, ai_service_setup, doctor_setup):
    """T9-C05: AI_SERVICE attempting to grant consent → 403."""
    r = client.post(
        f"/api/v1/patients/{patient_setup['patient_id']}/consents",
        headers=ai_service_setup["headers"],
        json=_grant_payload(doctor_setup["user_id"]),
    )
    assert r.status_code == 403, r.text


def test_unauthenticated_cannot_grant_consent(client, db, patient_setup, doctor_setup):
    """T9-C06: No bearer token → 401."""
    r = client.post(
        f"/api/v1/patients/{patient_setup['patient_id']}/consents",
        json=_grant_payload(doctor_setup["user_id"]),
    )
    assert r.status_code == 401, r.text


# ---------------------------------------------------------------------------
# DELETE /patients/{patient_id}/consents/{consent_id} (revoke)
# ---------------------------------------------------------------------------


def test_patient_revokes_own_consent(client, db, patient_setup, patient_consent):
    """T9-C07: PATIENT revokes their own consent → 200."""
    r = client.delete(
        f"/api/v1/patients/{patient_setup['patient_id']}/consents/{patient_consent.id}",
        headers=patient_setup["headers"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["message"] == "revoked"


def test_doctor_cannot_revoke_consent(client, db, patient_setup, patient_consent, doctor_setup):
    """T9-C08: DOCTOR attempting to revoke consent → 403 (P0 legal violation)."""
    r = client.delete(
        f"/api/v1/patients/{patient_setup['patient_id']}/consents/{patient_consent.id}",
        headers=doctor_setup["headers"],
    )
    assert r.status_code == 403, r.text


def test_admin_cannot_revoke_consent(client, db, patient_setup, patient_consent, admin_setup):
    """T9-C09: INTERNAL_ADMIN attempting to revoke consent → 403 (P0 legal violation)."""
    r = client.delete(
        f"/api/v1/patients/{patient_setup['patient_id']}/consents/{patient_consent.id}",
        headers=admin_setup["headers"],
    )
    assert r.status_code == 403, r.text


def test_revoke_nonexistent_consent(client, db, patient_setup):
    """T9-C10: Patient revoking a consent ID that does not exist → 404."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    r = client.delete(
        f"/api/v1/patients/{patient_setup['patient_id']}/consents/{fake_id}",
        headers=patient_setup["headers"],
    )
    assert r.status_code == 404, r.text


def test_unauthenticated_cannot_revoke_consent(client, db, patient_setup, patient_consent):
    """T9-C11: No bearer token on revoke endpoint → 401."""
    r = client.delete(
        f"/api/v1/patients/{patient_setup['patient_id']}/consents/{patient_consent.id}",
    )
    assert r.status_code == 401, r.text


def test_ai_service_cannot_revoke_consent(
    client, db, patient_setup, patient_consent, ai_service_setup
):
    """T10-C01: AI_SERVICE attempting to revoke consent → 403 (P0 legal violation)."""
    r = client.delete(
        f"/api/v1/patients/{patient_setup['patient_id']}/consents/{patient_consent.id}",
        headers=ai_service_setup["headers"],
    )
    assert r.status_code == 403, r.text


def test_patient_cannot_revoke_another_patients_consent(
    client, db, patient_setup, another_patient_setup, doctor_setup
):
    """T10-C02: PATIENT using their own path but a consent_id that belongs to another patient → 403.

    This tests the cross-patient consent ownership check: patient A correctly
    uses their own patient_id in the URL path but attempts to revoke a consent
    UUID that belongs to patient B. The route-level cross-patient check must
    block this with 403.
    """
    # Create a consent owned by another_patient
    other_consent = Consent(
        patient_id=another_patient_setup["patient_id"],
        consent_type="lab_access",
        data_scope="lab",
        granted_to=doctor_setup["user_id"],
    )
    db.add(other_consent)
    db.commit()

    # patient_setup uses their OWN patient_id in the path, but targets another patient's consent_id
    r = client.delete(
        f"/api/v1/patients/{patient_setup['patient_id']}/consents/{other_consent.id}",
        headers=patient_setup["headers"],  # patient 1's token on patient 1's path
    )
    assert r.status_code == 403, r.text


def test_patient_revoke_another_patients_consent_is_forbidden(
    client, db, patient_setup, another_patient_setup, doctor_setup
):
    """T9-C12: PATIENT revoking consent under another patient's profile → 403."""
    # Consent belongs to another_patient, not patient_setup
    other_consent = Consent(
        patient_id=another_patient_setup["patient_id"],
        consent_type="lab_access",
        data_scope="lab",
        granted_to=doctor_setup["user_id"],
    )
    db.add(other_consent)
    db.commit()

    r = client.delete(
        f"/api/v1/patients/{another_patient_setup['patient_id']}/consents/{other_consent.id}",
        headers=patient_setup["headers"],  # patient 1's token
    )
    assert r.status_code == 403, r.text
