"""PA-05 API tests — POST /api/v1/ai/explain (patient-safe explanation).

AC coverage:
  1. PATIENT + explanation_type=metabolic_score → 200, disclaimer present
  2. PATIENT + explanation_type=health_metric   → 200, plain_language_summary non-empty
  3. DOCTOR caller                              → 403
  4. ADMIN (CLINIC_ADMIN) caller               → 403
  5. No auth token                              → 401
  6. PATIENT with another patient's patient_id  → 403
  7. Unknown explanation_type                   → 422
  8. Disclaimer always non-empty regardless of input
"""

from __future__ import annotations

import os

import pytest
from app.core.security import create_access_token
from app.models.patient import PatientProfile
from app.models.user import User, UserRole

_BASE_URL = "/api/v1/ai/explain"

_DISCLAIMER_TEXT = (
    "This explanation is for informational purposes only and is not a medical "
    "diagnosis. Always consult your doctor for medical advice."
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def patient_a(db):
    """Primary PATIENT user with PatientProfile. Returns ids + headers."""
    user = User(
        email=f"explain-patient-a-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Patient A Explain Test",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="Patient A Explain Test")
    db.add(profile)
    db.commit()
    token = create_access_token(subject=user.id, role="patient")
    return {
        "user_id": user.id,
        "patient_id": profile.id,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def patient_b(db):
    """A second PATIENT user with PatientProfile (for ownership mismatch test)."""
    user = User(
        email=f"explain-patient-b-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Patient B Explain Test",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="Patient B Explain Test")
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
    """DOCTOR user + JWT headers."""
    user = User(
        email=f"explain-doctor-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="Doctor Explain Test",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="doctor", mfa=True)
    return {"headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def admin_setup(db):
    """CLINIC_ADMIN user + JWT headers."""
    user = User(
        email=f"explain-admin-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.CLINIC_ADMIN,
        full_name="Admin Explain Test",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="clinic_admin", mfa=True)
    return {"headers": {"Authorization": f"Bearer {token}"}}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _explain_payload(patient_id: str, explanation_type: str, **ctx_kwargs) -> dict:
    return {
        "patient_id": str(patient_id),
        "explanation_type": explanation_type,
        "context": ctx_kwargs,
    }


# ---------------------------------------------------------------------------
# AC-1: PATIENT + metabolic_score → 200, disclaimer present
# ---------------------------------------------------------------------------


def test_explain_patient_metabolic_score(client, patient_a):
    """PATIENT calling /ai/explain with metabolic_score → 200, disclaimer present."""
    payload = _explain_payload(
        patient_a["patient_id"],
        "metabolic_score",
        score=72,
        trend="improving",
    )
    r = client.post(_BASE_URL, headers=patient_a["headers"], json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["explanation_type"] == "metabolic_score"
    assert body["disclaimer"] == _DISCLAIMER_TEXT
    assert body["safety_level"] == "informational"
    assert body["plain_language_summary"]  # non-empty
    assert body["generated_at"]


# ---------------------------------------------------------------------------
# AC-2: PATIENT + health_metric → 200, plain_language_summary non-empty
# ---------------------------------------------------------------------------


def test_explain_patient_health_metric(client, patient_a):
    """PATIENT calling /ai/explain with health_metric → 200, summary non-empty."""
    payload = _explain_payload(
        patient_a["patient_id"],
        "health_metric",
        metric_type="blood_glucose",
        value=7.2,
        unit="mmol/L",
    )
    r = client.post(_BASE_URL, headers=patient_a["headers"], json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["explanation_type"] == "health_metric"
    assert len(body["plain_language_summary"]) > 0
    assert body["disclaimer"] == _DISCLAIMER_TEXT


# ---------------------------------------------------------------------------
# AC-3: DOCTOR caller → 403
# ---------------------------------------------------------------------------


def test_explain_doctor_forbidden(client, doctor_setup, patient_a):
    """DOCTOR calling /ai/explain → 403 (PATIENT-only endpoint)."""
    payload = _explain_payload(patient_a["patient_id"], "general_summary")
    r = client.post(_BASE_URL, headers=doctor_setup["headers"], json=payload)
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# AC-4: ADMIN caller → 403
# ---------------------------------------------------------------------------


def test_explain_admin_forbidden(client, admin_setup, patient_a):
    """CLINIC_ADMIN calling /ai/explain → 403 (PATIENT-only endpoint)."""
    payload = _explain_payload(patient_a["patient_id"], "general_summary")
    r = client.post(_BASE_URL, headers=admin_setup["headers"], json=payload)
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# AC-5: Unauthenticated → 401
# ---------------------------------------------------------------------------


def test_explain_unauthenticated(client, patient_a):
    """No Authorization header → 401."""
    payload = _explain_payload(patient_a["patient_id"], "general_summary")
    r = client.post(_BASE_URL, json=payload)
    assert r.status_code == 401, r.text


# ---------------------------------------------------------------------------
# AC-6: PATIENT calls with another patient's patient_id → 403
# ---------------------------------------------------------------------------


def test_explain_wrong_patient_id(client, patient_a, patient_b):
    """PATIENT A calling /ai/explain with PATIENT B's patient_id → 403."""
    payload = _explain_payload(patient_b["patient_id"], "general_summary")
    r = client.post(_BASE_URL, headers=patient_a["headers"], json=payload)
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# AC-7: Unknown explanation_type → 422
# ---------------------------------------------------------------------------


def test_explain_invalid_type(client, patient_a):
    """Invalid explanation_type value → 422 Unprocessable Entity."""
    payload = _explain_payload(patient_a["patient_id"], "totally_invalid_type")
    r = client.post(_BASE_URL, headers=patient_a["headers"], json=payload)
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# AC-8: Disclaimer is always present for all valid explanation_types
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "explanation_type",
    ["metabolic_score", "health_metric", "lab_result", "general_summary"],
)
def test_explain_disclaimer_always_present(client, patient_a, explanation_type):
    """Disclaimer field must be non-empty for every valid explanation_type."""
    payload = _explain_payload(patient_a["patient_id"], explanation_type)
    r = client.post(_BASE_URL, headers=patient_a["headers"], json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["disclaimer"], "disclaimer must never be empty"
    assert len(body["disclaimer"]) > 20  # at least a meaningful sentence
