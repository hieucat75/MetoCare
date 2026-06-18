"""T13 API tests — Metabolic Score History (save + trend + RBAC).

Covers:
  POST /api/v1/ai/metabolic-score  — persistence side-effect
  GET  /api/v1/patients/{patient_id}/metabolic-scores

10 test cases:
  1.  test_score_saved_on_patient_compute          — record persisted in DB
  2.  test_score_not_saved_when_no_patient_profile — doctor caller, no persistence
  3.  test_patient_reads_own_history               — 200, items list
  4.  test_patient_cannot_read_another_patients_history — 403
  5.  test_doctor_reads_history_with_consent        — 200
  6.  test_admin_reads_any_history                 — 200
  7.  test_ai_service_cannot_read_history          — 403
  8.  test_empty_history_returns_insufficient_data — trend = "insufficient_data"
  9.  test_trend_worsening                         — scores [30, 42] → "worsening"
  10. test_trend_improving                         — scores [60, 42] → "improving"
"""

from __future__ import annotations

import os

import pytest
from app.core.security import create_access_token
from app.models.clinical import RiskScore
from app.models.governance import Consent
from app.models.patient import PatientProfile
from app.models.user import User, UserRole
from fastapi.testclient import TestClient
from sqlalchemy import select

# ---------------------------------------------------------------------------
# Minimal valid metabolic-score payload
# ---------------------------------------------------------------------------

_SCORE_PAYLOAD = {
    "waist_cm": 95.0,
    "hba1c": 6.8,
    "triglyceride": 210.0,
    "systolic_bp": 142.0,
    "is_male": True,
}

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def patient_setup(db):
    """PATIENT user + profile + JWT."""
    user = User(
        email=f"t13-patient-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="T13 Patient",
    )
    db.add(user)
    db.flush()

    profile = PatientProfile(user_id=user.id, full_name="T13 Patient", waist_cm=95.0)
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
def another_patient_setup(db):
    """Second unrelated PATIENT + profile."""
    user = User(
        email=f"t13-patient2-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="T13 Other Patient",
    )
    db.add(user)
    db.flush()

    profile = PatientProfile(user_id=user.id, full_name="T13 Other Patient")
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
def doctor_setup(db):
    """DOCTOR user + JWT."""
    user = User(
        email=f"t13-doctor-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="T13 Doctor",
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
def admin_headers():
    """INTERNAL_ADMIN bearer headers (JWT only)."""
    admin_id = f"admin-{os.urandom(4).hex()}"
    token = create_access_token(subject=admin_id, role="internal_admin", mfa=True)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def consent_for_doctor(db, patient_setup, doctor_setup):
    """Grant the doctor active consent (scope='profile') for the primary patient."""
    consent = Consent(
        patient_id=patient_setup["patient_id"],
        consent_type="data_sharing",
        data_scope="profile",
        granted_to=doctor_setup["user_id"],
    )
    db.add(consent)
    db.commit()
    return consent


def _history_url(patient_id: str) -> str:
    return f"/api/v1/patients/{patient_id}/metabolic-scores"


def _score_url() -> str:
    return "/api/v1/ai/metabolic-score"


# ---------------------------------------------------------------------------
# Helper — seed RiskScore rows directly
# ---------------------------------------------------------------------------


def _seed_scores(db, patient_id: str, scores: list[int]) -> list[RiskScore]:
    """Insert RiskScore rows with the given metabolic_score values (oldest first).

    Each row receives an explicit ``created_at`` offset so ordering by
    ``created_at DESC`` is deterministic even on SQLite (where all rows in the
    same transaction share the same ``CURRENT_TIMESTAMP``).
    """
    import datetime as _dt

    base = _dt.datetime(2026, 1, 1, 0, 0, 0, tzinfo=_dt.UTC)
    rows = []
    for i, s in enumerate(scores):
        row = RiskScore(
            patient_id=patient_id,
            metabolic_score=s,
            band="fair",
            top_risks="[]",
        )
        # Assign created_at explicitly: oldest score gets earliest timestamp.
        row.created_at = base + _dt.timedelta(minutes=i)
        db.add(row)
        db.flush()
        rows.append(row)
    db.commit()
    return rows


# ---------------------------------------------------------------------------
# 1. Score saved on PATIENT compute
# ---------------------------------------------------------------------------


def test_score_saved_on_patient_compute(client: TestClient, db, patient_setup):
    """POST /ai/metabolic-score as PATIENT → RiskScore row written to DB."""
    r = client.post(
        _score_url(),
        headers=patient_setup["headers"],
        json=_SCORE_PAYLOAD,
    )
    assert r.status_code == 200, r.text

    row = db.execute(
        select(RiskScore).where(RiskScore.patient_id == patient_setup["patient_id"])
    ).scalar_one_or_none()

    assert row is not None, "Expected a RiskScore row to be persisted"
    assert row.metabolic_score == r.json()["score"]
    assert row.band == r.json()["band"]


# ---------------------------------------------------------------------------
# 2. Score NOT saved when caller has no PatientProfile (e.g. DOCTOR)
# ---------------------------------------------------------------------------


def test_score_not_saved_when_no_patient_profile(client: TestClient, db, doctor_setup):
    """POST /ai/metabolic-score as DOCTOR → no RiskScore row created."""
    r = client.post(
        _score_url(),
        headers=doctor_setup["headers"],
        json=_SCORE_PAYLOAD,
    )
    assert r.status_code == 200, r.text

    # Doctor has no PatientProfile; no row should exist for their user_id-derived patient_id
    count = db.execute(
        select(RiskScore).where(RiskScore.patient_id == doctor_setup["user_id"])
    ).scalar_one_or_none()
    assert count is None, "No RiskScore should be saved for a DOCTOR caller"


# ---------------------------------------------------------------------------
# 3. PATIENT reads own history
# ---------------------------------------------------------------------------


def test_patient_reads_own_history(client: TestClient, db, patient_setup):
    """PATIENT can GET their own metabolic score history — 200 with items list."""
    _seed_scores(db, patient_setup["patient_id"], [42])

    r = client.get(_history_url(patient_setup["patient_id"]), headers=patient_setup["headers"])
    assert r.status_code == 200, r.text

    body = r.json()
    assert body["patient_id"] == patient_setup["patient_id"]
    assert body["total"] >= 1
    assert isinstance(body["items"], list)
    assert "trend" in body


# ---------------------------------------------------------------------------
# 4. PATIENT cannot read another patient's history
# ---------------------------------------------------------------------------


def test_patient_cannot_read_another_patients_history(
    client: TestClient, patient_setup, another_patient_setup
):
    """PATIENT A cannot GET PATIENT B's history — 403."""
    r = client.get(
        _history_url(another_patient_setup["patient_id"]),
        headers=patient_setup["headers"],
    )
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# 5. DOCTOR reads history with consent
# ---------------------------------------------------------------------------


def test_doctor_reads_history_with_consent(
    client: TestClient, db, patient_setup, doctor_setup, consent_for_doctor
):
    """DOCTOR with active consent can GET patient history — 200."""
    _seed_scores(db, patient_setup["patient_id"], [35])

    r = client.get(
        _history_url(patient_setup["patient_id"]),
        headers=doctor_setup["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["patient_id"] == patient_setup["patient_id"]


# ---------------------------------------------------------------------------
# 6. ADMIN reads any history
# ---------------------------------------------------------------------------


def test_admin_reads_any_history(client: TestClient, db, patient_setup, admin_headers):
    """INTERNAL_ADMIN can GET any patient's history — 200."""
    _seed_scores(db, patient_setup["patient_id"], [50])

    r = client.get(_history_url(patient_setup["patient_id"]), headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["patient_id"] == patient_setup["patient_id"]


# ---------------------------------------------------------------------------
# 7. AI_SERVICE cannot read history
# ---------------------------------------------------------------------------


def test_ai_service_cannot_read_history(client: TestClient, patient_setup):
    """AI_SERVICE role → 403 on history endpoint."""
    ai_id = f"ai-{os.urandom(4).hex()}"
    token = create_access_token(subject=ai_id, role="ai_service")
    r = client.get(
        _history_url(patient_setup["patient_id"]),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# 8. Empty history returns "insufficient_data" trend
# ---------------------------------------------------------------------------


def test_empty_history_returns_insufficient_data(
    client: TestClient, db, patient_setup, admin_headers
):
    """When there are no records, trend must be 'insufficient_data'."""
    # Use a brand-new patient with no history
    new_user = User(
        email=f"t13-empty-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
    )
    db.add(new_user)
    db.flush()
    new_profile = PatientProfile(user_id=new_user.id)
    db.add(new_profile)
    db.commit()

    r = client.get(_history_url(new_profile.id), headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["trend"] == "insufficient_data"
    assert body["total"] == 0
    assert body["items"] == []


# ---------------------------------------------------------------------------
# 9. Trend: worsening (scores [30 then 42] → most-recent 42 > 30 by 12)
# ---------------------------------------------------------------------------


def test_trend_worsening(client: TestClient, db, patient_setup, admin_headers):
    """When last score > previous by >5 → trend = 'worsening'."""
    # Seed oldest first: 30, then 42 (newest)
    _seed_scores(db, patient_setup["patient_id"], [30, 42])

    r = client.get(_history_url(patient_setup["patient_id"]), headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    # Items are ordered newest-first; last=42, previous=30 → delta=+12 → worsening
    assert body["trend"] == "worsening", f"Expected worsening, got: {body['trend']}"


# ---------------------------------------------------------------------------
# 10. Trend: improving (scores [60 then 42] → most-recent 42 < 60 by 18)
# ---------------------------------------------------------------------------


def test_trend_improving(client: TestClient, db, patient_setup, admin_headers):
    """When last score < previous by >5 → trend = 'improving'."""
    # Seed oldest first: 60, then 42 (newest)
    _seed_scores(db, patient_setup["patient_id"], [60, 42])

    r = client.get(_history_url(patient_setup["patient_id"]), headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    # Items ordered newest-first; last=42, previous=60 → delta=-18 → improving
    assert body["trend"] == "improving", f"Expected improving, got: {body['trend']}"
