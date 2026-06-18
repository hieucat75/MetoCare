"""T21 API tests — Doctor Availability + Appointment Booking (12 tests).

Endpoints tested:
  POST   /api/v1/doctors/{doctor_id}/availability
  GET    /api/v1/doctors/{doctor_id}/availability
  POST   /api/v1/appointments
  GET    /api/v1/patients/{patient_id}/appointments
  PATCH  /api/v1/appointments/{appointment_id}

Test cases:
  1.  test_doctor_can_add_availability_slot             → 201
  2.  test_patient_can_list_available_slots             → 200
  3.  test_non_doctor_cannot_add_availability           → 403
  4.  test_patient_can_book_slot                        → 201
  5.  test_booking_marks_slot_as_booked                 → is_booked=True
  6.  test_cannot_double_book_same_slot                 → 409
  7.  test_patient_can_view_own_appointments            → 200
  8.  test_patient_cannot_view_other_patients_appointments → 403
  9.  test_doctor_can_view_appointment_queue            → 200
  10. test_doctor_can_confirm_appointment               → 200 status=confirmed
  11. test_patient_can_cancel_own_pending_appointment   → 200 status=cancelled
  12. test_unauthenticated_returns_401                  → 401
"""

from __future__ import annotations

import datetime as dt
import os

import pytest
from app.core.security import create_access_token
from app.models.appointment import BookingAppointment
from app.models.availability import DoctorAvailability
from app.models.patient import PatientProfile
from app.models.user import User, UserRole
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def _avail_url(doctor_id: str) -> str:
    return f"/api/v1/doctors/{doctor_id}/availability"


def _appt_url() -> str:
    return "/api/v1/appointments"


def _appt_detail_url(appt_id: str) -> str:
    return f"/api/v1/appointments/{appt_id}"


def _patient_appts_url(patient_id: str) -> str:
    return f"/api/v1/patients/{patient_id}/appointments"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def doctor_user(db):
    """DOCTOR user + JWT.  Returns user_id, headers."""
    user = User(
        email=f"t21-doctor-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="T21 Doctor",
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
    """A second, unrelated DOCTOR user."""
    user = User(
        email=f"t21-doctor2-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="T21 Doctor 2",
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
def patient_user(db):
    """PATIENT user + PatientProfile + JWT."""
    user = User(
        email=f"t21-patient-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="T21 Patient",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="T21 Patient")
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
def another_patient(db):
    """A second, unrelated PATIENT user + PatientProfile."""
    user = User(
        email=f"t21-patient2-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="T21 Patient 2",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="T21 Patient 2")
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
def admin_headers():
    """INTERNAL_ADMIN bearer headers (JWT only)."""
    admin_id = f"admin-{os.urandom(4).hex()}"
    token = create_access_token(subject=admin_id, role="internal_admin", mfa=True)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Helper — seed an availability slot directly
# ---------------------------------------------------------------------------

def _seed_availability(db, doctor_id: str, *, is_booked: bool = False) -> DoctorAvailability:
    base = dt.datetime(2026, 9, 1, 9, 0, 0)
    slot = DoctorAvailability(
        doctor_id=doctor_id,
        slot_start=base,
        slot_end=base + dt.timedelta(hours=1),
        is_booked=is_booked,
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return slot


def _seed_appointment(
    db,
    *,
    patient_id: str,
    doctor_id: str,
    availability_id: str,
    status: str = "pending",
) -> BookingAppointment:
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
# 1. Doctor can add availability slot → 201
# ---------------------------------------------------------------------------

def test_doctor_can_add_availability_slot(client: TestClient, doctor_user):
    """DOCTOR adds a slot for their own user_id → 201 with slot in response."""
    payload = {
        "slot_start": "2026-09-01T09:00:00",
        "slot_end": "2026-09-01T10:00:00",
    }
    r = client.post(
        _avail_url(doctor_user["user_id"]),
        json=payload,
        headers=doctor_user["headers"],
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["doctor_id"] == doctor_user["user_id"]
    assert body["is_booked"] is False
    assert "id" in body
    assert "slot_start" in body
    assert "slot_end" in body


# ---------------------------------------------------------------------------
# 2. Patient can list available slots → 200
# ---------------------------------------------------------------------------

def test_patient_can_list_available_slots(client: TestClient, db, doctor_user, patient_user):
    """PATIENT can GET open slots for a doctor — 200 with items list."""
    _seed_availability(db, doctor_user["user_id"])

    r = client.get(
        _avail_url(doctor_user["user_id"]),
        headers=patient_user["headers"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)
    assert len(body) >= 1
    slot = body[0]
    assert "id" in slot
    assert slot["doctor_id"] == doctor_user["user_id"]
    assert slot["is_booked"] is False


# ---------------------------------------------------------------------------
# 3. Non-doctor cannot add availability → 403
# ---------------------------------------------------------------------------

def test_non_doctor_cannot_add_availability(client: TestClient, patient_user):
    """PATIENT trying to POST availability → 403."""
    payload = {
        "slot_start": "2026-09-02T09:00:00",
        "slot_end": "2026-09-02T10:00:00",
    }
    r = client.post(
        _avail_url(patient_user["user_id"]),
        json=payload,
        headers=patient_user["headers"],
    )
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# 4. Patient can book a slot → 201
# ---------------------------------------------------------------------------

def test_patient_can_book_slot(client: TestClient, db, doctor_user, patient_user):
    """PATIENT books an available slot → 201 with appointment in response."""
    slot = _seed_availability(db, doctor_user["user_id"])

    payload = {
        "doctor_id": doctor_user["user_id"],
        "availability_id": slot.id,
        "notes": "Pre-visit: mild chest discomfort for 2 days.",
    }
    r = client.post(_appt_url(), json=payload, headers=patient_user["headers"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["patient_id"] == patient_user["patient_id"]
    assert body["doctor_id"] == doctor_user["user_id"]
    assert body["availability_id"] == slot.id
    assert body["status"] == "pending"
    assert body["notes"] == payload["notes"]


# ---------------------------------------------------------------------------
# 5. Booking marks slot as is_booked=True
# ---------------------------------------------------------------------------

def test_booking_marks_slot_as_booked(client: TestClient, db, doctor_user, patient_user):
    """After a successful booking, DoctorAvailability.is_booked becomes True."""
    slot = _seed_availability(db, doctor_user["user_id"])
    assert slot.is_booked is False

    payload = {
        "doctor_id": doctor_user["user_id"],
        "availability_id": slot.id,
    }
    r = client.post(_appt_url(), json=payload, headers=patient_user["headers"])
    assert r.status_code == 201, r.text

    # Refresh from DB
    db.expire(slot)
    db.refresh(slot)
    assert slot.is_booked is True


# ---------------------------------------------------------------------------
# 6. Cannot double-book same slot → 409
# ---------------------------------------------------------------------------

def test_cannot_double_book_same_slot(
    client: TestClient, db, doctor_user, patient_user, another_patient
):
    """Second booking of the same slot → 409 Conflict."""
    slot = _seed_availability(db, doctor_user["user_id"])

    payload = {
        "doctor_id": doctor_user["user_id"],
        "availability_id": slot.id,
    }

    # First booking succeeds
    r1 = client.post(_appt_url(), json=payload, headers=patient_user["headers"])
    assert r1.status_code == 201, r1.text

    # Second booking (by a different patient) → 409
    r2 = client.post(_appt_url(), json=payload, headers=another_patient["headers"])
    assert r2.status_code == 409, r2.text


# ---------------------------------------------------------------------------
# 7. Patient can view own appointments → 200
# ---------------------------------------------------------------------------

def test_patient_can_view_own_appointments(client: TestClient, db, doctor_user, patient_user):
    """PATIENT can GET their own appointments — 200 with list."""
    slot = _seed_availability(db, doctor_user["user_id"])
    _seed_appointment(
        db,
        patient_id=patient_user["patient_id"],
        doctor_id=doctor_user["user_id"],
        availability_id=slot.id,
    )

    r = client.get(
        _patient_appts_url(patient_user["patient_id"]),
        headers=patient_user["headers"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)
    assert len(body) >= 1
    appt = body[0]
    assert "id" in appt
    assert appt["patient_id"] == patient_user["patient_id"]
    assert appt["doctor_id"] == doctor_user["user_id"]
    assert "status" in appt


# ---------------------------------------------------------------------------
# 8. Patient cannot view other patient's appointments → 403
# ---------------------------------------------------------------------------

def test_patient_cannot_view_other_patients_appointments(
    client: TestClient, db, doctor_user, patient_user, another_patient
):
    """PATIENT A cannot GET PATIENT B's appointments — 403."""
    slot = _seed_availability(db, doctor_user["user_id"])
    _seed_appointment(
        db,
        patient_id=another_patient["patient_id"],
        doctor_id=doctor_user["user_id"],
        availability_id=slot.id,
    )

    r = client.get(
        _patient_appts_url(another_patient["patient_id"]),
        headers=patient_user["headers"],  # patient_user trying to see another_patient's data
    )
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# 9. Doctor can view their appointment queue → 200
# ---------------------------------------------------------------------------

def test_doctor_can_view_appointment_queue(
    client: TestClient, db, doctor_user, patient_user, admin_headers
):
    """DOCTOR can GET appointments for a patient where they are the doctor — 200."""
    slot = _seed_availability(db, doctor_user["user_id"])
    _seed_appointment(
        db,
        patient_id=patient_user["patient_id"],
        doctor_id=doctor_user["user_id"],
        availability_id=slot.id,
    )

    r = client.get(
        _patient_appts_url(patient_user["patient_id"]),
        headers=doctor_user["headers"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)
    # All returned appointments should belong to this doctor
    for appt in body:
        assert appt["doctor_id"] == doctor_user["user_id"]


# ---------------------------------------------------------------------------
# 10. Doctor can confirm appointment → 200 status=confirmed
# ---------------------------------------------------------------------------

def test_doctor_can_confirm_appointment(
    client: TestClient, db, doctor_user, patient_user
):
    """DOCTOR PATCHes appointment to confirmed — 200 with status=confirmed."""
    slot = _seed_availability(db, doctor_user["user_id"])
    appt = _seed_appointment(
        db,
        patient_id=patient_user["patient_id"],
        doctor_id=doctor_user["user_id"],
        availability_id=slot.id,
        status="pending",
    )

    r = client.patch(
        _appt_detail_url(appt.id),
        json={"status": "confirmed"},
        headers=doctor_user["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "confirmed"


# ---------------------------------------------------------------------------
# 11. Patient can cancel own pending appointment → 200 status=cancelled
# ---------------------------------------------------------------------------

def test_patient_can_cancel_own_pending_appointment(
    client: TestClient, db, doctor_user, patient_user
):
    """PATIENT PATCHes own pending appointment to cancelled — 200."""
    slot = _seed_availability(db, doctor_user["user_id"])
    appt = _seed_appointment(
        db,
        patient_id=patient_user["patient_id"],
        doctor_id=doctor_user["user_id"],
        availability_id=slot.id,
        status="pending",
    )

    r = client.patch(
        _appt_detail_url(appt.id),
        json={"status": "cancelled"},
        headers=patient_user["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"


# ---------------------------------------------------------------------------
# 12. Unauthenticated → 401
# ---------------------------------------------------------------------------

def test_unauthenticated_returns_401(client: TestClient, doctor_user):
    """Request without a bearer token → 401."""
    r = client.get(_avail_url(doctor_user["user_id"]))
    assert r.status_code == 401, r.text
