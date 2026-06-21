"""Live metabolic score API tests — root-cause fix for the dashboard false-empty.

Covers GET /api/v1/patients/{patient_id}/metabolic-score/live:
  1. test_no_metrics_returns_unavailable        — available=False, score=None
  2. test_full_metrics_mgdl_scores              — score computed from mg/dL metrics
  3. test_lab_mmol_glucose_is_converted         — mmol/L glucose → mg/dL before scoring
  4. test_patient_cannot_read_another_patient   — 403 cross-patient
  5. test_ai_service_forbidden                  — AI_SERVICE → 403
  6. test_no_ai_gate_patient_with_metrics       — works with AI feature off (no gate)
"""

from __future__ import annotations

import datetime as dt
import os

import pytest
from app.core.security import create_access_token
from app.models.clinical import HealthMetric
from app.models.patient import PatientProfile
from app.models.user import User, UserRole
from fastapi.testclient import TestClient


def _live_url(patient_id: str) -> str:
    return f"/api/v1/patients/{patient_id}/metabolic-score/live"


def _add_metric(db, patient_id: str, metric_type: str, value: float, unit: str) -> None:
    db.add(
        HealthMetric(
            patient_id=patient_id,
            metric_type=metric_type,
            value=value,
            unit=unit,
            measured_at=dt.datetime(2026, 1, 1, 12, 0, 0),
            source="manual",
            status="normal",
        )
    )
    db.commit()


@pytest.fixture
def patient_setup(db):
    user = User(
        email=f"live-patient-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Live Patient",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(
        user_id=user.id, full_name="Live Patient", waist_cm=104.0, gender="male"
    )
    db.add(profile)
    db.commit()
    token = create_access_token(subject=user.id, role="patient")
    return {
        "user_id": user.id,
        "patient_id": profile.id,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def another_patient_setup(db):
    user = User(
        email=f"live-patient2-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id)
    db.add(profile)
    db.commit()
    token = create_access_token(subject=user.id, role="patient")
    return {"patient_id": profile.id, "headers": {"Authorization": f"Bearer {token}"}}


# ---------------------------------------------------------------------------
# 1. No metrics → unavailable (genuine empty, not a false-empty)
# ---------------------------------------------------------------------------


def test_no_metrics_returns_unavailable(client: TestClient, db):
    """A patient with no waist + no metrics → available=False."""
    user = User(
        email=f"live-empty-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id)  # no waist, no gender
    db.add(profile)
    db.commit()
    token = create_access_token(subject=user.id, role="patient")

    r = client.get(_live_url(profile.id), headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["available"] is False
    assert body["score"] is None


# ---------------------------------------------------------------------------
# 2. Full mg/dL metrics → score reflects the data
# ---------------------------------------------------------------------------


def test_full_metrics_mgdl_scores(client: TestClient, db, patient_setup):
    """High glucose + low HDL + high BP (mg/dL) → a meaningful score with factors."""
    pid = patient_setup["patient_id"]
    _add_metric(db, pid, "fasting_glucose", 140.0, "mg/dL")  # ≥126 → 25 pts
    _add_metric(db, pid, "hdl", 35.0, "mg/dL")  # <40 (male) → 12 pts
    _add_metric(db, pid, "blood_pressure_systolic", 145.0, "mmHg")  # ≥140 → 18 pts

    r = client.get(_live_url(pid), headers=patient_setup["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["available"] is True
    # waist 104 (≥90+12 → 20) + glucose 25 + hdl 12 + bp 18 = 75
    assert body["score"] == 75
    assert body["band"] == "high_concern"
    factor_names = {f["name"] for f in body["factors"]}
    assert {"waist", "fasting_glucose", "hdl", "systolic_bp"} <= factor_names


# ---------------------------------------------------------------------------
# 3. Lab mmol/L glucose is converted to mg/dL before scoring
# ---------------------------------------------------------------------------


def test_lab_mmol_glucose_is_converted(client: TestClient, db, patient_setup):
    """7.5 mmol/L glucose = 135 mg/dL ≥126 → diabetic-range points (not 0)."""
    pid = patient_setup["patient_id"]
    _add_metric(db, pid, "fasting_glucose", 7.5, "mmol/L")  # → ~135 mg/dL → 25 pts

    r = client.get(_live_url(pid), headers=patient_setup["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["available"] is True
    glucose = next(f for f in body["factors"] if f["name"] == "fasting_glucose")
    assert glucose["points"] == 25, body["factors"]


# ---------------------------------------------------------------------------
# 4. Cross-patient access blocked
# ---------------------------------------------------------------------------


def test_patient_cannot_read_another_patient(
    client: TestClient, patient_setup, another_patient_setup
):
    r = client.get(
        _live_url(another_patient_setup["patient_id"]),
        headers=patient_setup["headers"],
    )
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# 5. AI_SERVICE forbidden
# ---------------------------------------------------------------------------


def test_ai_service_forbidden(client: TestClient, patient_setup):
    ai_id = f"ai-{os.urandom(4).hex()}"
    token = create_access_token(subject=ai_id, role="ai_service")
    r = client.get(
        _live_url(patient_setup["patient_id"]),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# 6. Works with the AI feature off — no AI gate on this endpoint
# ---------------------------------------------------------------------------


def test_no_ai_gate_patient_with_metrics(client: TestClient, db, patient_setup):
    """The whole point of the fix: a PATIENT gets a real score without any AI flag."""
    pid = patient_setup["patient_id"]
    _add_metric(db, pid, "fasting_glucose", 95.0, "mg/dL")  # normal → 0 pts

    r = client.get(_live_url(pid), headers=patient_setup["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["available"] is True
    assert isinstance(body["score"], int)
