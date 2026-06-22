"""Clinical Insight Engine API tests (PA-11).

Covers GET /api/v1/patients/{id}/insights, /insights/{metric_type}, /health-summary:
  AC1–AC4 — every abnormal metric insight has meaning + trend + risk + lifestyle + follow-up
  AC5/AC6 — health-summary returns what-changed buckets + overall summary
  AC7     — works with AI disabled (CLINICAL_INSIGHT_AI default off)
  AC8     — no prohibited (diagnosis/prescription/dose) language; disclaimer present
  RBAC    — cross-patient blocked; feature flag off → 404
"""

from __future__ import annotations

import datetime as dt
import os

import pytest
from app.core.feature_flags import FeatureFlag, is_enabled
from app.domain.guardrails import check_output
from app.domain.policies import DISCLAIMER_VI
from app.models.clinical import HealthMetric
from app.models.patient import PatientProfile
from app.models.user import User, UserRole
from fastapi.testclient import TestClient

_DAY = dt.timedelta(days=30)


def _insights_url(pid: str) -> str:
    return f"/api/v1/patients/{pid}/insights"


def _add_metric(db, pid, metric_type, value, unit, status, *, days_ago=0):
    db.add(
        HealthMetric(
            patient_id=pid,
            metric_type=metric_type,
            value=value,
            unit=unit,
            measured_at=dt.datetime(2026, 6, 1, 12, 0, 0) - days_ago * _DAY,
            source="manual",
            status=status,
        )
    )
    db.commit()


@pytest.fixture
def patient_setup(db):
    user = User(
        email=f"insight-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Insight Patient",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="Insight Patient", gender="male")
    db.add(profile)
    db.commit()
    from app.core.security import create_access_token

    token = create_access_token(subject=user.id, role="patient")
    return {"patient_id": profile.id, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def other_patient(db):
    user = User(
        email=f"insight2-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id)
    db.add(profile)
    db.commit()
    from app.core.security import create_access_token

    token = create_access_token(subject=user.id, role="patient")
    return {"patient_id": profile.id, "headers": {"Authorization": f"Bearer {token}"}}


def _seed_abnormal(db, pid):
    # TSH very low (thyroid), fasting glucose high, LDL high — the dashboard examples.
    _add_metric(db, pid, "tsh", 0.03, "mIU/L", "low")
    _add_metric(db, pid, "fasting_glucose", 5.73, "mmol/L", "high")
    _add_metric(db, pid, "ldl", 3.59, "mmol/L", "high")


# --------------------------------------------------------------------------- #
# AC1–AC4: every abnormal metric has all five guidance fields
# --------------------------------------------------------------------------- #

def test_every_abnormal_metric_has_all_fields(client: TestClient, db, patient_setup):
    pid = patient_setup["patient_id"]
    _seed_abnormal(db, pid)

    r = client.get(_insights_url(pid), headers=patient_setup["headers"])
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) == 3  # all three are abnormal
    for it in items:
        assert it["meaning"].strip()                       # AC1 meaning
        assert it["trend"]["label"].strip()                # AC2 trend
        assert len(it["risks"]) >= 1                        # AC3 risk
        assert len(it["lifestyle"]) >= 1                   # AC4 lifestyle
        assert it["follow_up"].strip()                     # AC4 follow-up
        assert it["priority"] in {"monitor", "watch", "see_doctor"}
        assert it["disclaimer"] == DISCLAIMER_VI


# --------------------------------------------------------------------------- #
# AC2: trend direction + improvement vs previous reading
# --------------------------------------------------------------------------- #

def test_trend_improvement_detected(client: TestClient, db, patient_setup):
    pid = patient_setup["patient_id"]
    # LDL dropped 4.50 → 3.59 mmol/L (still high, but lower = better)
    _add_metric(db, pid, "ldl", 4.50, "mmol/L", "high", days_ago=2)
    _add_metric(db, pid, "ldl", 3.59, "mmol/L", "high", days_ago=0)

    r = client.get(f"/api/v1/patients/{pid}/insights/ldl", headers=patient_setup["headers"])
    assert r.status_code == 200, r.text
    t = r.json()["trend"]
    assert t["direction"] == "down"
    assert t["improved"] is True
    assert t["pct"] is not None and t["pct"] < 0


# --------------------------------------------------------------------------- #
# AC5/AC6: health summary — what changed + overall
# --------------------------------------------------------------------------- #

def test_health_summary_shape(client: TestClient, db, patient_setup):
    pid = patient_setup["patient_id"]
    _add_metric(db, pid, "ldl", 4.50, "mmol/L", "high", days_ago=2)
    _add_metric(db, pid, "ldl", 3.59, "mmol/L", "high", days_ago=0)
    _add_metric(db, pid, "fasting_glucose", 4.8, "mmol/L", "normal", days_ago=2)
    _add_metric(db, pid, "fasting_glucose", 5.9, "mmol/L", "high", days_ago=0)

    r = client.get(f"/api/v1/patients/{pid}/health-summary", headers=patient_setup["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["abnormal_count"] >= 1
    assert body["overall_risk"] in {"low", "medium", "high"}
    assert body["top_action"].strip()
    assert any("LDL" in s for s in body["improved"])     # LDL improved
    assert any("Đường" in s for s in body["worsened"])   # glucose worsened
    assert body["disclaimer"] == DISCLAIMER_VI


# --------------------------------------------------------------------------- #
# AC7: works with AI disabled (default)
# --------------------------------------------------------------------------- #

def test_works_without_ai(client: TestClient, db, patient_setup):
    assert is_enabled(FeatureFlag.CLINICAL_INSIGHT_AI) is False  # v1 rules-only
    pid = patient_setup["patient_id"]
    _seed_abnormal(db, pid)
    r = client.get(_insights_url(pid), headers=patient_setup["headers"])
    assert r.status_code == 200
    assert len(r.json()) == 3  # rules path produced content with no AI provider


# --------------------------------------------------------------------------- #
# AC8: no prohibited language; disclaimer present
# --------------------------------------------------------------------------- #

def test_no_prohibited_language(client: TestClient, db, patient_setup):
    pid = patient_setup["patient_id"]
    _seed_abnormal(db, pid)
    r = client.get(_insights_url(pid), headers=patient_setup["headers"])
    for it in r.json():
        for text in [it["meaning"], it["follow_up"], *it["risks"], *it["lifestyle"]]:
            assert check_output(text).allowed, f"prohibited language: {text!r}"


# --------------------------------------------------------------------------- #
# RBAC + flag gating
# --------------------------------------------------------------------------- #

def test_cross_patient_forbidden(client: TestClient, patient_setup, other_patient):
    r = client.get(_insights_url(other_patient["patient_id"]), headers=patient_setup["headers"])
    assert r.status_code == 403, r.text


def test_metric_detail_404_when_no_readings(client: TestClient, patient_setup):
    r = client.get(
        f"/api/v1/patients/{patient_setup['patient_id']}/insights/hba1c",
        headers=patient_setup["headers"],
    )
    assert r.status_code == 404, r.text


def test_feature_flag_off_returns_404(client: TestClient, patient_setup, monkeypatch):
    monkeypatch.setenv("FEATURE_CLINICAL_INSIGHT", "false")
    r = client.get(_insights_url(patient_setup["patient_id"]), headers=patient_setup["headers"])
    assert r.status_code == 404, r.text
