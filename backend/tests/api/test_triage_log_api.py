"""T19 API tests — Triage Log persistence + history RBAC.

Covers:
  POST /api/v1/ai/triage          — persistence side-effect for PATIENT callers
  GET  /api/v1/patients/{patient_id}/triage-history

10 test cases:
  1.  test_triage_saved_for_patient               — after POST, record in DB
  2.  test_triage_not_saved_for_non_patient       — doctor caller, no persistence
  3.  test_patient_reads_triage_history           — 200, items list
  4.  test_patient_cannot_read_another_patients_history — 403
  5.  test_doctor_reads_history_with_consent      — 200
  6.  test_admin_reads_any_history                — 200
  7.  test_ai_service_cannot_read_history         — 403
  8.  test_empty_triage_history                   — 200, empty list
  9.  test_red_flags_serialized_correctly         — emergency triage, red_flags not empty
  10. test_triage_history_ordered_newest_first    — multiple logs, newest first
"""

from __future__ import annotations

import datetime as _dt
import json
import os

import pytest
from app.core.security import create_access_token
from app.models.governance import Consent
from app.models.patient import PatientProfile
from app.models.triage_log import TriageLog
from app.models.user import User, UserRole
from fastapi.testclient import TestClient
from sqlalchemy import select

# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

_TRIAGE_URL = "/api/v1/ai/triage"


def _history_url(patient_id: str) -> str:
    return f"/api/v1/patients/{patient_id}/triage-history"


# ---------------------------------------------------------------------------
# Minimal valid triage payloads
# ---------------------------------------------------------------------------

_LOW_TRIAGE_PAYLOAD = {
    "symptom_text": "Đau đầu nhẹ, không sốt",
    "vitals": [],
    "reported_severity": None,
}

# Emergency-level triage — contains red-flag keyword "đau ngực"
_EMERGENCY_TRIAGE_PAYLOAD = {
    "symptom_text": "Đau ngực dữ dội, khó thở",
    "vitals": [],
    "reported_severity": 10,
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def patient_a(db):
    """Primary PATIENT user + PatientProfile + bearer headers."""
    user = User(
        email=f"t19-patient-a-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="T19 Patient A",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="T19 Patient A")
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
def patient_b(db):
    """Second unrelated PATIENT user + PatientProfile."""
    user = User(
        email=f"t19-patient-b-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="T19 Patient B",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="T19 Patient B")
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
def doctor(db):
    """DOCTOR user + bearer headers (no PatientProfile)."""
    user = User(
        email=f"t19-doctor-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="T19 Doctor",
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
    """INTERNAL_ADMIN bearer headers (JWT only, no DB row needed)."""
    admin_id = f"admin-{os.urandom(4).hex()}"
    token = create_access_token(subject=admin_id, role="internal_admin", mfa=True)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def doctor_consent_for_patient_a(db, patient_a, doctor):
    """Grant the doctor active consent (scope='profile') for patient_a."""
    consent = Consent(
        patient_id=patient_a["patient_id"],
        consent_type="data_sharing",
        data_scope="profile",
        granted_to=doctor["user_id"],
    )
    db.add(consent)
    db.commit()
    return consent


# ---------------------------------------------------------------------------
# Helper — seed TriageLog rows directly (bypasses route / feature flag)
# ---------------------------------------------------------------------------

def _seed_triage_logs(
    db,
    patient_id: str,
    count: int = 1,
    *,
    risk_level: str = "low",
    action: str = "self_monitor",
    red_flags: list[str] | None = None,
    base_offset_minutes: int = 0,
) -> list[TriageLog]:
    """Insert TriageLog rows directly into the DB for test setup."""
    base = _dt.datetime(2026, 1, 1, 0, 0, 0, tzinfo=_dt.UTC)
    rows = []
    for i in range(count):
        row = TriageLog(
            patient_id=patient_id,
            symptom_text=f"Test symptom {i}",
            risk_level=risk_level,
            action=action,
            red_flags=json.dumps(red_flags) if red_flags else None,
            message="Test message",
        )
        row.created_at = base + _dt.timedelta(minutes=base_offset_minutes + i)
        db.add(row)
        db.flush()
        rows.append(row)
    db.commit()
    return rows


# ---------------------------------------------------------------------------
# 1. Triage saved for PATIENT caller
# ---------------------------------------------------------------------------

def test_triage_saved_for_patient(client: TestClient, db, patient_a):
    """POST /ai/triage as PATIENT → TriageLog row written to DB."""
    r = client.post(
        _TRIAGE_URL,
        headers=patient_a["headers"],
        json=_LOW_TRIAGE_PAYLOAD,
    )
    assert r.status_code == 200, r.text

    row = db.execute(
        select(TriageLog).where(TriageLog.patient_id == patient_a["patient_id"])
    ).scalar_one_or_none()

    assert row is not None, "Expected a TriageLog row to be persisted"
    assert row.risk_level == r.json()["risk_level"]
    assert row.action == r.json()["action"]
    assert row.symptom_text == _LOW_TRIAGE_PAYLOAD["symptom_text"]


# ---------------------------------------------------------------------------
# 2. Triage NOT saved for non-PATIENT caller (DOCTOR)
# ---------------------------------------------------------------------------

def test_triage_not_saved_for_non_patient(client: TestClient, db, doctor):
    """POST /ai/triage as DOCTOR → no TriageLog row created."""
    r = client.post(
        _TRIAGE_URL,
        headers=doctor["headers"],
        json=_LOW_TRIAGE_PAYLOAD,
    )
    assert r.status_code == 200, r.text

    # Doctor has no PatientProfile; no TriageLog row should exist for their user_id
    count = db.execute(
        select(TriageLog).where(TriageLog.patient_id == doctor["user_id"])
    ).scalar_one_or_none()
    assert count is None, "No TriageLog should be saved for a DOCTOR caller"


# ---------------------------------------------------------------------------
# 3. PATIENT reads own triage history
# ---------------------------------------------------------------------------

def test_patient_reads_triage_history(client: TestClient, db, patient_a):
    """PATIENT can GET their own triage history — 200 with items list."""
    _seed_triage_logs(db, patient_a["patient_id"])

    r = client.get(_history_url(patient_a["patient_id"]), headers=patient_a["headers"])
    assert r.status_code == 200, r.text

    body = r.json()
    assert body["patient_id"] == patient_a["patient_id"]
    assert body["total"] >= 1
    assert isinstance(body["items"], list)
    item = body["items"][0]
    assert "id" in item
    assert "symptom_text" in item
    assert "risk_level" in item
    assert "action" in item
    assert "red_flags" in item
    assert "created_at" in item


# ---------------------------------------------------------------------------
# 4. PATIENT cannot read another patient's history
# ---------------------------------------------------------------------------

def test_patient_cannot_read_another_patients_history(
    client: TestClient, patient_a, patient_b
):
    """PATIENT A cannot GET PATIENT B's triage history — 403."""
    r = client.get(
        _history_url(patient_b["patient_id"]),
        headers=patient_a["headers"],
    )
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# 5. DOCTOR reads history with consent
# ---------------------------------------------------------------------------

def test_doctor_reads_history_with_consent(
    client: TestClient, db, patient_a, doctor, doctor_consent_for_patient_a
):
    """DOCTOR with active consent can GET patient triage history — 200."""
    _seed_triage_logs(db, patient_a["patient_id"])

    r = client.get(
        _history_url(patient_a["patient_id"]),
        headers=doctor["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["patient_id"] == patient_a["patient_id"]


# ---------------------------------------------------------------------------
# 6. ADMIN reads any history
# ---------------------------------------------------------------------------

def test_admin_reads_any_history(client: TestClient, db, patient_a, admin_headers):
    """INTERNAL_ADMIN can GET any patient's triage history — 200."""
    _seed_triage_logs(db, patient_a["patient_id"])

    r = client.get(_history_url(patient_a["patient_id"]), headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["patient_id"] == patient_a["patient_id"]


# ---------------------------------------------------------------------------
# 7. AI_SERVICE cannot read history
# ---------------------------------------------------------------------------

def test_ai_service_cannot_read_history(client: TestClient, patient_a):
    """AI_SERVICE role → 403 on triage-history endpoint."""
    ai_id = f"ai-{os.urandom(4).hex()}"
    token = create_access_token(subject=ai_id, role="ai_service")
    r = client.get(
        _history_url(patient_a["patient_id"]),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# 8. Empty triage history returns 200 with empty list
# ---------------------------------------------------------------------------

def test_empty_triage_history(client: TestClient, db, admin_headers):
    """When there are no records, history returns 200 with empty items list."""
    # Use a fresh patient with no triage history
    new_user = User(
        email=f"t19-empty-{os.urandom(4).hex()}@example.com",
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
    assert body["total"] == 0
    assert body["items"] == []
    assert body["patient_id"] == new_profile.id


# ---------------------------------------------------------------------------
# 9. Red flags serialized correctly for emergency triage
# ---------------------------------------------------------------------------

def test_red_flags_serialized_correctly(client: TestClient, db, patient_a):
    """Emergency triage with red-flag symptoms → red_flags list not empty in history."""
    # POST an emergency triage (contains red-flag keyword "đau ngực")
    r = client.post(
        _TRIAGE_URL,
        headers=patient_a["headers"],
        json=_EMERGENCY_TRIAGE_PAYLOAD,
    )
    assert r.status_code == 200, r.text
    assert r.json()["risk_level"] == "emergency"

    # Fetch history and check red_flags is a non-empty list
    history = client.get(
        _history_url(patient_a["patient_id"]), headers=patient_a["headers"]
    )
    assert history.status_code == 200, history.text
    items = history.json()["items"]
    # Find the emergency entry
    emergency_items = [i for i in items if i["risk_level"] == "emergency"]
    assert emergency_items, "Expected at least one emergency triage log"
    assert isinstance(emergency_items[0]["red_flags"], list)
    assert len(emergency_items[0]["red_flags"]) > 0, "Emergency log must have red_flags"


# ---------------------------------------------------------------------------
# 10. Triage history ordered newest first
# ---------------------------------------------------------------------------

def test_triage_history_ordered_newest_first(
    client: TestClient, db, patient_a, admin_headers
):
    """Multiple triage logs are returned newest-first (created_at DESC)."""
    # Seed 3 logs with staggered created_at (oldest first in insert order)
    rows = _seed_triage_logs(db, patient_a["patient_id"], count=3, base_offset_minutes=0)

    r = client.get(_history_url(patient_a["patient_id"]), headers=admin_headers)
    assert r.status_code == 200, r.text

    items = r.json()["items"]
    # Items include our seeded rows; filter by known IDs to check ordering
    seeded_ids = {row.id for row in rows}
    seeded_items = [i for i in items if i["id"] in seeded_ids]
    assert len(seeded_items) == 3

    # created_at should be in descending order among our seeded items
    timestamps = [i["created_at"] for i in seeded_items]
    assert timestamps == sorted(timestamps, reverse=True), (
        "Triage history must be ordered newest-first (created_at DESC)"
    )
