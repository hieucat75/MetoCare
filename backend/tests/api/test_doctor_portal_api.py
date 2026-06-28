"""T22 API tests — Doctor Portal Summary API (10 tests).

Endpoints tested:
  GET /api/v1/patients/{patient_id}/summary   — pre-visit patient summary
  GET /api/v1/doctors/me/appointments         — doctor's own appointment list

Test cases:
  1.  test_doctor_with_consent_gets_summary          — 200 + all top-level keys present
  2.  test_summary_vitals_is_list                    — vitals.latest is a list (may be empty)
  3.  test_summary_medications_only_active           — deleted meds excluded
  4.  test_patient_cannot_access_summary             — 403
  5.  test_ai_service_cannot_access_summary          — 403
  6.  test_doctor_without_consent_gets_403           — 403
  7.  test_admin_gets_summary_without_consent        — 200 (no consent needed)
  8.  test_doctor_lists_own_appointments             — 200, list
  9.  test_patient_cannot_list_doctor_appointments   — 403
  10. test_unauthenticated_cannot_access             — 401
"""

from __future__ import annotations

import datetime as dt
import os

import pytest
from app.core.security import create_access_token
from app.models.appointment import BookingAppointment
from app.models.availability import DoctorAvailability
from app.models.clinical import Medication
from app.models.governance import Consent
from app.models.patient import PatientProfile
from app.models.user import User, UserRole
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def _summary_url(patient_id: str) -> str:
    return f"/api/v1/patients/{patient_id}/summary"


def _doctor_appointments_url() -> str:
    return "/api/v1/doctors/me/appointments"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def doctor_user(db):
    """DOCTOR user + JWT."""
    user = User(
        email=f"t22-doctor-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="T22 Doctor",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="doctor", mfa=True)
    return {
        "user_id": user.id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def another_doctor(db):
    """A second DOCTOR with no relationship to the test patient."""
    user = User(
        email=f"t22-doctor2-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="T22 Doctor 2",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="doctor", mfa=True)
    return {
        "user_id": user.id,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def patient_user(db):
    """PATIENT user + PatientProfile + JWT."""
    user = User(
        email=f"t22-patient-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="T22 Patient",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="T22 Patient")
    db.add(profile)
    db.commit()
    token = create_access_token(subject=user.id, role="patient", mfa=True)
    return {
        "user_id": user.id,
        "patient_id": profile.id,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def ai_service_user(db):
    """AI_SERVICE user + JWT."""
    user = User(
        email=f"t22-ai-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.AI_SERVICE,
        full_name="T22 AI",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="ai_service", mfa=True)
    return {
        "user_id": user.id,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def admin_user(db):
    """INTERNAL_ADMIN user + JWT."""
    user = User(
        email=f"t22-admin-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.INTERNAL_ADMIN,
        full_name="T22 Admin",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="internal_admin", mfa=True)
    return {
        "user_id": user.id,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def consent_for_doctor(db, patient_user, doctor_user):
    """Grant doctor_user active consent (scope='profile') for patient_user."""
    consent = Consent(
        patient_id=patient_user["patient_id"],
        consent_type="data_sharing",
        data_scope="profile",
        granted_to=doctor_user["user_id"],
    )
    db.add(consent)
    db.commit()
    return consent


def _seed_availability(db, doctor_id: str) -> DoctorAvailability:
    """Seed a future availability slot for *doctor_id*."""
    slot = DoctorAvailability(
        doctor_id=doctor_id,
        slot_start=dt.datetime.utcnow() + dt.timedelta(days=3),
        slot_end=dt.datetime.utcnow() + dt.timedelta(days=3, hours=1),
        is_booked=False,
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return slot


def _seed_appointment(
    db,
    patient_id: str,
    doctor_id: str,
    availability_id: str,
    status: str = "pending",
) -> BookingAppointment:
    """Seed a BookingAppointment and mark the availability slot as booked."""
    slot = db.get(DoctorAvailability, availability_id)
    if slot:
        slot.is_booked = True
        db.add(slot)
    appt = BookingAppointment(
        patient_id=patient_id,
        doctor_id=doctor_id,
        availability_id=availability_id,
        status=status,
    )
    db.add(appt)
    db.commit()
    db.refresh(appt)
    return appt


# ---------------------------------------------------------------------------
# 1. DOCTOR with consent → 200, all top-level keys present
# ---------------------------------------------------------------------------


def test_doctor_with_consent_gets_summary(
    client: TestClient, patient_user, doctor_user, consent_for_doctor
):
    """DOCTOR with active consent receives 200 with all expected top-level keys."""
    r = client.get(_summary_url(patient_user["patient_id"]), headers=doctor_user["headers"])
    assert r.status_code == 200, r.text
    body = r.json()

    expected_keys = {
        "patient_id",
        "generated_at",
        "vitals",
        "lab_documents",
        "metabolic_score",
        "medications",
        "symptoms",
        "nutrition",
        "upcoming_appointments",
        "active_care_plans",
    }
    assert expected_keys.issubset(body.keys()), f"Missing keys: {expected_keys - body.keys()}"
    assert body["patient_id"] == patient_user["patient_id"]


# ---------------------------------------------------------------------------
# 2. vitals.latest is a list (may be empty — not an error)
# ---------------------------------------------------------------------------


def test_summary_vitals_is_list(client: TestClient, patient_user, doctor_user, consent_for_doctor):
    """vitals.latest must be a list; an empty list is valid (no metrics yet)."""
    r = client.get(_summary_url(patient_user["patient_id"]), headers=doctor_user["headers"])
    assert r.status_code == 200, r.text
    vitals = r.json()["vitals"]
    assert "latest" in vitals
    assert isinstance(vitals["latest"], list)
    assert "trend" in vitals


# ---------------------------------------------------------------------------
# 3. medications only contains active records (not soft-deleted)
# ---------------------------------------------------------------------------


def test_summary_medications_only_active(
    client: TestClient, db, patient_user, doctor_user, consent_for_doctor
):
    """Soft-deleted medications must NOT appear in the summary medications list."""
    from app.core.clock import utcnow

    # Add one active + one deleted medication
    active_med = Medication(
        patient_id=patient_user["patient_id"],
        name="Metformin",
        dose="500mg",
    )
    deleted_med = Medication(
        patient_id=patient_user["patient_id"],
        name="OldDrug",
        dose="100mg",
        deleted_at=utcnow(),
    )
    db.add_all([active_med, deleted_med])
    db.commit()

    r = client.get(_summary_url(patient_user["patient_id"]), headers=doctor_user["headers"])
    assert r.status_code == 200, r.text

    med_names = [m["name"] for m in r.json()["medications"]]
    assert "Metformin" in med_names, "Active medication must appear"
    assert "OldDrug" not in med_names, "Deleted medication must NOT appear"


# ---------------------------------------------------------------------------
# 4. PATIENT → 403
# ---------------------------------------------------------------------------


def test_patient_cannot_access_summary(client: TestClient, patient_user):
    """PATIENT role must receive 403 on the summary endpoint."""
    r = client.get(_summary_url(patient_user["patient_id"]), headers=patient_user["headers"])
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# 5. AI_SERVICE → 403
# ---------------------------------------------------------------------------


def test_ai_service_cannot_access_summary(client: TestClient, patient_user, ai_service_user):
    """AI_SERVICE role must receive 403 on the summary endpoint."""
    r = client.get(_summary_url(patient_user["patient_id"]), headers=ai_service_user["headers"])
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# 6. DOCTOR without consent → 403
# ---------------------------------------------------------------------------


def test_doctor_without_consent_gets_403(client: TestClient, patient_user, another_doctor):
    """DOCTOR without an active consent record for the patient must receive 403."""
    r = client.get(_summary_url(patient_user["patient_id"]), headers=another_doctor["headers"])
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# 7. ADMIN → 200 (no consent needed)
# ---------------------------------------------------------------------------


def test_admin_gets_summary_without_consent(client: TestClient, patient_user, admin_user):
    """INTERNAL_ADMIN must receive 200 without any consent record."""
    r = client.get(_summary_url(patient_user["patient_id"]), headers=admin_user["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["patient_id"] == patient_user["patient_id"]


# ---------------------------------------------------------------------------
# 8. DOCTOR lists own appointments → 200, list
# ---------------------------------------------------------------------------


def test_doctor_lists_own_appointments(client: TestClient, db, doctor_user, patient_user):
    """DOCTOR calling GET /doctors/me/appointments receives 200 with a list."""
    slot = _seed_availability(db, doctor_user["user_id"])
    _seed_appointment(
        db,
        patient_id=patient_user["patient_id"],
        doctor_id=doctor_user["user_id"],
        availability_id=slot.id,
    )

    r = client.get(_doctor_appointments_url(), headers=doctor_user["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)
    # All returned appointments belong to this doctor
    for appt in body:
        assert appt["doctor_id"] == doctor_user["user_id"]
        assert "id" in appt
        assert "status" in appt


# ---------------------------------------------------------------------------
# 9. PATIENT → 403 on doctor appointments endpoint
# ---------------------------------------------------------------------------


def test_patient_cannot_list_doctor_appointments(client: TestClient, patient_user):
    """PATIENT role must receive 403 on the doctor appointments endpoint."""
    r = client.get(_doctor_appointments_url(), headers=patient_user["headers"])
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# 10. Unauthenticated → 401 on both endpoints
# ---------------------------------------------------------------------------


def test_unauthenticated_cannot_access_summary_or_appointments(client: TestClient, patient_user):
    """Requests without a bearer token must receive 401."""
    r1 = client.get(_summary_url(patient_user["patient_id"]))
    assert r1.status_code == 401, r1.text

    r2 = client.get(_doctor_appointments_url())
    assert r2.status_code == 401, r2.text
