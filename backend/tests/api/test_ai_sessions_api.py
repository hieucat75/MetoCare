"""T5 API tests — AISession endpoints (C3 feature flags + ConsentGuard + RBAC)."""

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
def patient_setup(db):
    p_user = User(
        email=f"patient-ai-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Patient AI Test",
    )
    db.add(p_user)
    db.flush()

    profile = PatientProfile(user_id=p_user.id, full_name="Patient AI Test")
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
        email=f"patient2-ai-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Patient AI Other",
    )
    db.add(p_user)
    db.flush()

    profile = PatientProfile(user_id=p_user.id, full_name="Patient AI Other")
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
def grant_ai_consent_for_patient(db, patient_setup):
    """Grant ai_use consent so patient can create AI sessions."""
    now = utcnow()
    consent = Consent(
        patient_id=patient_setup["patient_id"],
        consent_type="ai_use",
        data_scope="*",
        granted_to=patient_setup["user_id"],  # self-consent
        valid_from=now - dt.timedelta(hours=1),
        valid_until=now + dt.timedelta(hours=24),
    )
    db.add(consent)
    db.commit()
    return consent


@pytest.fixture
def ai_session_for_patient(db, patient_setup):
    """Seed an AI session for the patient directly (bypassing endpoint)."""
    session = AISession(
        patient_id=patient_setup["patient_id"],
        session_type="health_assistant",
        escalated_to_doctor=False,
    )
    db.add(session)
    db.commit()
    return session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_create_ai_session_flag_enabled(
    client, patient_setup, grant_ai_consent_for_patient, monkeypatch
):
    """When AI_SESSION_ENABLED flag is on + consent exists → 201."""
    monkeypatch.setenv("FEATURE_AI_SESSION_ENABLED", "true")
    r = client.post(
        "/api/v1/ai_sessions",
        headers=patient_setup["headers"],
        json={
            "patient_id": patient_setup["patient_id"],
            "session_type": "health_assistant",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["patient_id"] == patient_setup["patient_id"]
    assert body["session_type"] == "health_assistant"


def test_create_ai_session_flag_disabled_returns_503(
    client, patient_setup, grant_ai_consent_for_patient, monkeypatch
):
    """When AI_SESSION_ENABLED flag is off → 503 with feature name in detail."""
    monkeypatch.setenv("FEATURE_AI_SESSION_ENABLED", "false")
    r = client.post(
        "/api/v1/ai_sessions",
        headers=patient_setup["headers"],
        json={
            "patient_id": patient_setup["patient_id"],
            "session_type": "health_assistant",
        },
    )
    assert r.status_code == 503, r.text
    body = r.json()
    assert "disabled" in body["detail"].lower()


def test_create_ai_session_no_consent_returns_403(client, patient_setup, monkeypatch, db):
    """Consent gate: a non-self actor without consent → 403.

    When a doctor (or any non-patient actor) tries to create an AI session on
    behalf of a patient without active consent, the ConsentGuard must deny access.
    """
    monkeypatch.setenv("FEATURE_AI_SESSION_ENABLED", "true")
    # Create an unrelated doctor who has NO consent from the patient
    from app.models.user import User, UserRole
    d_user = User(
        email=f"doctor-noconsent-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="Dr. NoConsent",
    )
    db.add(d_user)
    db.commit()
    doctor_token = create_access_token(subject=d_user.id, role="doctor", mfa=True)
    r = client.post(
        "/api/v1/ai_sessions",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={
            "patient_id": patient_setup["patient_id"],
            "session_type": "health_assistant",
        },
    )
    assert r.status_code == 403, r.text
    body = r.json()
    assert "consent" in body["detail"].lower()


def test_patient_reads_own_ai_session(client, patient_setup, ai_session_for_patient):
    """Patient can read their own AI session — 200."""
    r = client.get(
        f"/api/v1/ai_sessions/{ai_session_for_patient.id}",
        headers=patient_setup["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["id"] == ai_session_for_patient.id


def test_patient_cannot_read_other_ai_session(
    client, another_patient_setup, ai_session_for_patient
):
    """Patient B cannot read Patient A's AI session — 403."""
    r = client.get(
        f"/api/v1/ai_sessions/{ai_session_for_patient.id}",
        headers=another_patient_setup["headers"],
    )
    assert r.status_code == 403, r.text


def test_list_recommendations_scoped(
    client, patient_setup, ai_session_for_patient, monkeypatch
):
    """Recommendations endpoint gated by AI_CLINICAL_RECS_ENABLED flag."""
    # Flag off → 503
    monkeypatch.setenv("FEATURE_AI_CLINICAL_RECS_ENABLED", "false")
    r = client.get(
        f"/api/v1/ai_sessions/{ai_session_for_patient.id}/recommendations",
        headers=patient_setup["headers"],
    )
    assert r.status_code == 503, r.text

    # Flag on → 200 (empty list — no recs seeded)
    monkeypatch.setenv("FEATURE_AI_CLINICAL_RECS_ENABLED", "true")
    r2 = client.get(
        f"/api/v1/ai_sessions/{ai_session_for_patient.id}/recommendations",
        headers=patient_setup["headers"],
    )
    assert r2.status_code == 200, r2.text
    assert isinstance(r2.json(), list)
