"""T17 — AI Sessions full RBAC/endpoint coverage.

Extends the 6 tests in test_ai_sessions_api.py without duplicating them.

Coverage:
  POST   /ai_sessions                       — create (consent + feature flag)
  GET    /ai_sessions/{id}                  — read single (RBAC-scoped)
  GET    /ai_sessions                       — list (RBAC-scoped)
  GET    /ai_sessions/{id}/recommendations  — list recs (feature-flagged)

RBAC matrix covered here:
  - AI_SERVICE with consent → can create (201)
  - Patient creates session for another patient → denied (403)
  - Doctor without consent → denied (403)
  - Patient reads own session → 200
  - Patient cannot read another patient's session → 403
  - Doctor reads any session → 200 (DOCTOR allowed in _check_session_read_access)
  - Patient lists own sessions → 200
  - Doctor lists sessions (all/any) → 200
  - Unauthenticated → 401
  - Recommendations empty list → 200
"""

from __future__ import annotations

import datetime as dt
import os

import pytest
from app.core.clock import utcnow
from app.core.security import create_access_token
from app.models.ai import AISession
from app.models.governance import Consent
from app.models.patient import PatientProfile
from app.models.user import User, UserRole

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ai_patient(db):
    """Patient A — primary patient for AI session tests."""
    user = User(
        email=f"full-patient-a-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Patient Full A",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="Patient Full A")
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
def ai_patient_b(db):
    """Patient B — used to verify cross-patient isolation."""
    user = User(
        email=f"full-patient-b-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Patient Full B",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="Patient Full B")
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
def ai_doctor(db):
    """DOCTOR user — not linked to any clinic for simplicity."""
    user = User(
        email=f"full-doctor-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="Dr. Full Test",
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
def ai_service_user(db):
    """AI_SERVICE system account."""
    user = User(
        email=f"ai-svc-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=UserRole.AI_SERVICE,
        full_name="AI Service",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="ai_service")
    return {
        "user_id": user.id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def consent_for_ai_service(db, ai_patient, ai_service_user):
    """Grant ai_use consent to the AI service user for patient A."""
    now = utcnow()
    consent = Consent(
        patient_id=ai_patient["patient_id"],
        consent_type="ai_use",
        data_scope="*",
        granted_to=ai_service_user["user_id"],
        valid_from=now - dt.timedelta(hours=1),
        valid_until=now + dt.timedelta(hours=24),
    )
    db.add(consent)
    db.commit()
    return consent


@pytest.fixture
def seeded_session_for_a(db, ai_patient):
    """Directly seeded AI session for patient A (no endpoint call)."""
    session = AISession(
        patient_id=ai_patient["patient_id"],
        session_type="health_assistant",
        escalated_to_doctor=False,
    )
    db.add(session)
    db.commit()
    return session


@pytest.fixture
def seeded_session_for_b(db, ai_patient_b):
    """Directly seeded AI session for patient B."""
    session = AISession(
        patient_id=ai_patient_b["patient_id"],
        session_type="triage",
        escalated_to_doctor=False,
    )
    db.add(session)
    db.commit()
    return session


# ---------------------------------------------------------------------------
# POST /ai_sessions — create
# ---------------------------------------------------------------------------


def test_ai_service_creates_session(
    client, ai_patient, ai_service_user, consent_for_ai_service, monkeypatch
):
    """AI_SERVICE with valid consent + flag on → 201."""
    monkeypatch.setenv("FEATURE_AI_SESSION_ENABLED", "true")
    r = client.post(
        "/api/v1/ai_sessions",
        headers=ai_service_user["headers"],
        json={
            "patient_id": ai_patient["patient_id"],
            "session_type": "triage",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["patient_id"] == ai_patient["patient_id"]
    assert body["session_type"] == "triage"


def test_patient_cannot_create_session_for_another_patient(
    client, ai_patient, ai_patient_b, monkeypatch
):
    """Patient A trying to create a session for Patient B → 403 (consent denied)."""
    monkeypatch.setenv("FEATURE_AI_SESSION_ENABLED", "true")
    r = client.post(
        "/api/v1/ai_sessions",
        headers=ai_patient["headers"],
        json={
            "patient_id": ai_patient_b["patient_id"],
            "session_type": "health_assistant",
        },
    )
    assert r.status_code == 403, r.text
    body = r.json()
    assert "consent" in body["detail"].lower()


def test_doctor_cannot_create_session_without_consent(
    client, ai_patient, ai_doctor, monkeypatch
):
    """DOCTOR without patient consent → 403."""
    monkeypatch.setenv("FEATURE_AI_SESSION_ENABLED", "true")
    r = client.post(
        "/api/v1/ai_sessions",
        headers=ai_doctor["headers"],
        json={
            "patient_id": ai_patient["patient_id"],
            "session_type": "health_assistant",
        },
    )
    assert r.status_code == 403, r.text
    body = r.json()
    assert "consent" in body["detail"].lower()


# ---------------------------------------------------------------------------
# GET /ai_sessions/{id} — single session read
# ---------------------------------------------------------------------------


def test_patient_reads_own_session(client, ai_patient, seeded_session_for_a):
    """Patient can read their own AI session → 200."""
    r = client.get(
        f"/api/v1/ai_sessions/{seeded_session_for_a.id}",
        headers=ai_patient["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["id"] == seeded_session_for_a.id


def test_patient_cannot_read_another_patients_session(
    client, ai_patient, seeded_session_for_b
):
    """Patient A cannot read Patient B's session → 403."""
    r = client.get(
        f"/api/v1/ai_sessions/{seeded_session_for_b.id}",
        headers=ai_patient["headers"],
    )
    assert r.status_code == 403, r.text


def test_doctor_reads_patient_session_with_consent(
    client, ai_doctor, seeded_session_for_a
):
    """DOCTOR role is allowed to read any session (permissive in read-access check) → 200."""
    r = client.get(
        f"/api/v1/ai_sessions/{seeded_session_for_a.id}",
        headers=ai_doctor["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["id"] == seeded_session_for_a.id


def test_unauthenticated_cannot_read_session(client, seeded_session_for_a):
    """No token → 401."""
    r = client.get(f"/api/v1/ai_sessions/{seeded_session_for_a.id}")
    assert r.status_code == 401, r.text


# ---------------------------------------------------------------------------
# GET /ai_sessions — list sessions
# ---------------------------------------------------------------------------


def test_patient_lists_own_sessions(client, ai_patient, seeded_session_for_a):
    """Patient lists their own sessions → 200, list contains their session."""
    r = client.get("/api/v1/ai_sessions", headers=ai_patient["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)
    ids = [s["id"] for s in body]
    assert seeded_session_for_a.id in ids


def test_doctor_lists_patient_sessions(
    client, ai_doctor, seeded_session_for_a, seeded_session_for_b
):
    """DOCTOR (no patient_id filter) → 200, returns list of all sessions."""
    r = client.get("/api/v1/ai_sessions", headers=ai_doctor["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)
    # Both seeded sessions should appear for a doctor (no scope restriction in list)
    ids = [s["id"] for s in body]
    assert seeded_session_for_a.id in ids
    assert seeded_session_for_b.id in ids


# ---------------------------------------------------------------------------
# GET /ai_sessions/{id}/recommendations — empty list
# ---------------------------------------------------------------------------


def test_list_recommendations_empty(
    client, ai_patient, seeded_session_for_a, monkeypatch
):
    """Patient with flag on and no recs seeded → 200, empty list."""
    monkeypatch.setenv("FEATURE_AI_CLINICAL_RECS_ENABLED", "true")
    r = client.get(
        f"/api/v1/ai_sessions/{seeded_session_for_a.id}/recommendations",
        headers=ai_patient["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json() == []
