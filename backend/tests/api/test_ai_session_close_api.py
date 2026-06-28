"""T18A — AI Session Close API tests.

Covers POST /ai_sessions/{session_id}/close (new endpoint).
"""

from __future__ import annotations

import os

import pytest
from app.core.security import create_access_token
from app.models.ai import AISession
from app.models.patient import PatientProfile
from app.models.user import User, UserRole


@pytest.fixture
def patient_setup(db):
    user = User(
        email=f"close-patient-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Close Patient",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="Close Patient")
    db.add(profile)
    db.commit()
    token = create_access_token(subject=user.id, role="patient")
    return {
        "user_id": user.id,
        "patient_id": profile.id,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def other_patient_setup(db):
    user = User(
        email=f"close-other-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Other Close Patient",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="Other Close Patient")
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
        email=f"close-doctor-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="Dr. Close",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="doctor", mfa=True)
    return {"user_id": user.id, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def admin_setup(db):
    user = User(
        email=f"close-admin-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=UserRole.INTERNAL_ADMIN,
        full_name="Admin Close",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="internal_admin", mfa=True)
    return {"user_id": user.id, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def patient_session(db, patient_setup):
    session = AISession(
        patient_id=patient_setup["patient_id"],
        session_type="health_assistant",
        escalated_to_doctor=False,
    )
    db.add(session)
    db.commit()
    return session


@pytest.fixture
def other_patient_session(db, other_patient_setup):
    session = AISession(
        patient_id=other_patient_setup["patient_id"],
        session_type="triage",
        escalated_to_doctor=False,
    )
    db.add(session)
    db.commit()
    return session


def test_patient_can_close_own_session(client, patient_setup, patient_session):
    """T18A-SC01: Patient closes their own session -> 204."""
    r = client.post(
        f"/api/v1/ai_sessions/{patient_session.id}/close",
        headers=patient_setup["headers"],
    )
    assert r.status_code == 204, r.text


def test_closed_session_not_returned_by_get(client, patient_setup, patient_session):
    """T18A-SC02: After close, GET returns 404."""
    r = client.post(
        f"/api/v1/ai_sessions/{patient_session.id}/close",
        headers=patient_setup["headers"],
    )
    assert r.status_code == 204, r.text
    r2 = client.get(
        f"/api/v1/ai_sessions/{patient_session.id}",
        headers=patient_setup["headers"],
    )
    assert r2.status_code == 404, r2.text


def test_patient_cannot_close_other_patients_session(client, patient_setup, other_patient_session):
    """T18A-SC03: Patient cannot close another patient's session."""
    r = client.post(
        f"/api/v1/ai_sessions/{other_patient_session.id}/close",
        headers=patient_setup["headers"],
    )
    assert r.status_code == 403, r.text


def test_doctor_can_close_any_session(client, doctor_setup, patient_session):
    """T18A-SC04: Doctor can close any session."""
    r = client.post(
        f"/api/v1/ai_sessions/{patient_session.id}/close",
        headers=doctor_setup["headers"],
    )
    assert r.status_code == 204, r.text


def test_admin_can_close_any_session(client, admin_setup, patient_session):
    """T18A-SC05: Admin can close any session."""
    r = client.post(
        f"/api/v1/ai_sessions/{patient_session.id}/close",
        headers=admin_setup["headers"],
    )
    assert r.status_code == 204, r.text


def test_close_already_closed_session_is_idempotent(client, patient_setup, patient_session):
    """T18A-SC06: Closing an already-closed session is idempotent (204)."""
    client.post(
        f"/api/v1/ai_sessions/{patient_session.id}/close",
        headers=patient_setup["headers"],
    )
    r2 = client.post(
        f"/api/v1/ai_sessions/{patient_session.id}/close",
        headers=patient_setup["headers"],
    )
    assert r2.status_code == 204, r2.text


def test_close_nonexistent_session_returns_404(client, patient_setup):
    """T18A-SC07: Closing non-existent session returns 404."""
    r = client.post(
        "/api/v1/ai_sessions/00000000-0000-0000-0000-000000000000/close",
        headers=patient_setup["headers"],
    )
    assert r.status_code == 404, r.text


def test_unauthenticated_cannot_close_session(client, patient_session):
    """T18A-SC08: No token returns 401."""
    r = client.post(f"/api/v1/ai_sessions/{patient_session.id}/close")
    assert r.status_code == 401, r.text
