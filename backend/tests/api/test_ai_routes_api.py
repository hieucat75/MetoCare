"""T8 API tests — AI routes auth + RBAC enforcement.

Covers all 3 AI consumer routes:
  - POST /api/v1/ai/chat
  - POST /api/v1/ai/triage
  - POST /api/v1/ai/metabolic-score

All 12 required test cases are implemented.
AI runs in mock mode (MCP_AI_MODE=mock, set in conftest.py).
"""

from __future__ import annotations

import os

import pytest
from app.core.security import create_access_token
from app.models.patient import PatientProfile
from app.models.user import User, UserRole

# ---------------------------------------------------------------------------
# Minimal valid payloads
# ---------------------------------------------------------------------------

_CHAT_PAYLOAD = {"message": "Xin chào bác sĩ"}

_TRIAGE_PAYLOAD = {
    "symptom_text": "Đau đầu nhẹ",
    "vitals": [],
    "reported_severity": None,
}

_SCORE_PAYLOAD = {
    "waist_cm": 85.0,
    "fasting_glucose": 5.5,
    "is_male": True,
}

# ---------------------------------------------------------------------------
# Unsafe mock provider — forces output guardrail to fire (blocked=True)
# ---------------------------------------------------------------------------


class _UnsafeMockProvider:
    """Returns a response containing a prohibited diagnosis assertion.

    The output guardrail in the LLM gateway will BLOCK this and set
    blocked=True in the ChatResponse.  Matches DIAGNOSIS_ASSERTION_PATTERNS:
    r"bạn (\u0111ã |chắc chắn )?bị (tiểu đường|...)"
    """

    name = "unsafe-mock"

    def complete(self, messages, *, system=None, max_tokens=512, temperature=0.2):
        from app.llm.base import LLMResponse

        return LLMResponse(
            text="Bạn đã bị tiểu đường rồi, nên uống Metformin 500mg.",
            model="unsafe-mock-1",
            prompt_tokens=5,
            completion_tokens=10,
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def patient_setup(db):
    """PATIENT user + JWT headers."""
    p_user = User(
        email=f"ai-patient-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="AI Patient Test",
    )
    db.add(p_user)
    db.flush()
    profile = PatientProfile(user_id=p_user.id, full_name="AI Patient Test")
    db.add(profile)
    db.commit()
    token = create_access_token(subject=p_user.id, role="patient")
    return {
        "user_id": p_user.id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def doctor_setup(db):
    """DOCTOR user + JWT headers."""
    d_user = User(
        email=f"ai-doctor-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="AI Doctor Test",
    )
    db.add(d_user)
    db.commit()
    token = create_access_token(subject=d_user.id, role="doctor", mfa=True)
    return {
        "user_id": d_user.id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def ai_service_setup(db):
    """AI_SERVICE user + JWT headers."""
    svc_user = User(
        email=f"ai-service-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.AI_SERVICE,
        full_name="AI Service Account",
    )
    db.add(svc_user)
    db.commit()
    token = create_access_token(subject=svc_user.id, role="ai_service")
    return {
        "user_id": svc_user.id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


# ---------------------------------------------------------------------------
# Chat tests (POST /api/v1/ai/chat)
# ---------------------------------------------------------------------------


def test_patient_can_chat(client, patient_setup):
    """PATIENT with valid JWT → 200 with text field."""
    r = client.post(
        "/api/v1/ai/chat",
        headers=patient_setup["headers"],
        json=_CHAT_PAYLOAD,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "text" in body


def test_doctor_can_chat(client, doctor_setup):
    """DOCTOR with valid JWT → 200."""
    r = client.post(
        "/api/v1/ai/chat",
        headers=doctor_setup["headers"],
        json=_CHAT_PAYLOAD,
    )
    assert r.status_code == 200, r.text


def test_ai_service_cannot_chat(client, ai_service_setup):
    """AI_SERVICE role → 403 (blocked from consumer routes)."""
    r = client.post(
        "/api/v1/ai/chat",
        headers=ai_service_setup["headers"],
        json=_CHAT_PAYLOAD,
    )
    assert r.status_code == 403, r.text


def test_unauthenticated_cannot_chat(client):
    """No Authorization header → 401."""
    r = client.post("/api/v1/ai/chat", json=_CHAT_PAYLOAD)
    assert r.status_code == 401, r.text


def test_chat_blocked_message_returns_blocked_true(client, patient_setup, monkeypatch):
    """Output guardrail fires on unsafe LLM response → 200 with blocked=True.

    Injects an unsafe provider that returns a prohibited diagnosis assertion.
    The gateway output guardrail blocks it and sets blocked=True in the response.
    """
    monkeypatch.setattr("app.llm.gateway.get_provider", lambda: _UnsafeMockProvider())
    from app.llm import reset_gateway

    reset_gateway()
    r = client.post(
        "/api/v1/ai/chat",
        headers=patient_setup["headers"],
        json={"message": "Tôi bị bệnh gì?"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("blocked") is True


# ---------------------------------------------------------------------------
# Triage tests (POST /api/v1/ai/triage)
# ---------------------------------------------------------------------------


def test_patient_can_triage(client, patient_setup):
    """PATIENT with valid JWT → 200 with risk_level field."""
    r = client.post(
        "/api/v1/ai/triage",
        headers=patient_setup["headers"],
        json=_TRIAGE_PAYLOAD,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "risk_level" in body


def test_doctor_can_triage(client, doctor_setup):
    """DOCTOR with valid JWT → 200."""
    r = client.post(
        "/api/v1/ai/triage",
        headers=doctor_setup["headers"],
        json=_TRIAGE_PAYLOAD,
    )
    assert r.status_code == 200, r.text


def test_ai_service_cannot_triage(client, ai_service_setup):
    """AI_SERVICE role → 403."""
    r = client.post(
        "/api/v1/ai/triage",
        headers=ai_service_setup["headers"],
        json=_TRIAGE_PAYLOAD,
    )
    assert r.status_code == 403, r.text


def test_unauthenticated_cannot_triage(client):
    """No Authorization header → 401."""
    r = client.post("/api/v1/ai/triage", json=_TRIAGE_PAYLOAD)
    assert r.status_code == 401, r.text


# ---------------------------------------------------------------------------
# Metabolic score tests (POST /api/v1/ai/metabolic-score)
# ---------------------------------------------------------------------------


def test_patient_can_score(client, patient_setup):
    """PATIENT with valid JWT → 200 with score and band fields."""
    r = client.post(
        "/api/v1/ai/metabolic-score",
        headers=patient_setup["headers"],
        json=_SCORE_PAYLOAD,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "score" in body
    assert "band" in body


def test_ai_service_cannot_score(client, ai_service_setup):
    """AI_SERVICE role → 403."""
    r = client.post(
        "/api/v1/ai/metabolic-score",
        headers=ai_service_setup["headers"],
        json=_SCORE_PAYLOAD,
    )
    assert r.status_code == 403, r.text


def test_unauthenticated_cannot_score(client):
    """No Authorization header → 401."""
    r = client.post("/api/v1/ai/metabolic-score", json=_SCORE_PAYLOAD)
    assert r.status_code == 401, r.text
