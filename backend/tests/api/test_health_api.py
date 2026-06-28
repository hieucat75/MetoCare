"""T9 API tests — Health Metrics RBAC endpoints.

Covers all 3 health metric routes with RBAC enforcement:
  - POST   /patients/{patient_id}/metrics
  - GET    /patients/{patient_id}/metrics
  - GET    /patients/{patient_id}/metrics/trend

Baseline: 248 passing tests. This file adds 12+ tests.
"""

from __future__ import annotations

import datetime as dt
import os

import pytest
from app.core.clock import utcnow
from app.core.security import create_access_token
from app.models.care import Clinic, Doctor, DoctorClinic
from app.models.clinical import HealthMetric
from app.models.governance import Consent
from app.models.patient import PatientProfile
from app.models.user import User, UserRole

# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------

_METRIC_PAYLOAD = {
    "metric_type": "weight",
    "value": 70.5,
    "unit": "kg",
    "measured_at": None,
    "source": "manual",
    "normal_range_min": None,
    "normal_range_max": None,
}

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def patient_setup(db):
    """Patient user + profile + JWT."""
    p_user = User(
        email=f"health-patient-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Health Patient",
    )
    db.add(p_user)
    db.flush()
    profile = PatientProfile(user_id=p_user.id, full_name="Health Patient")
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
    """A second (different) patient."""
    p_user = User(
        email=f"health-patient2-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Health Patient 2",
    )
    db.add(p_user)
    db.flush()
    profile = PatientProfile(user_id=p_user.id, full_name="Health Patient 2")
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
def doctor_setup(db):
    """Doctor user + doctor record + clinic + JWT (MFA=True)."""
    clinic = Clinic(name=f"Health Clinic {os.urandom(4).hex()}", is_active=True)
    db.add(clinic)
    db.flush()

    d_user = User(
        email=f"health-doctor-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="Dr. Health",
    )
    db.add(d_user)
    db.flush()

    doctor = Doctor(user_id=d_user.id, clinic_id=clinic.id, full_name="Dr. Health", is_active=True)
    db.add(doctor)
    db.flush()

    link = DoctorClinic(doctor_id=doctor.id, clinic_id=clinic.id, is_primary=True, is_active=True)
    db.add(link)
    db.commit()

    token = create_access_token(subject=d_user.id, role="doctor", mfa=True)
    return {
        "user_id": d_user.id,
        "doctor_id": doctor.id,
        "clinic_id": clinic.id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def admin_setup(db):
    """INTERNAL_ADMIN user + JWT (MFA=True)."""
    a_user = User(
        email=f"health-admin-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=UserRole.INTERNAL_ADMIN,
        full_name="Health Admin",
    )
    db.add(a_user)
    db.commit()
    token = create_access_token(subject=a_user.id, role="internal_admin", mfa=True)
    return {
        "user_id": a_user.id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def ai_service_setup(db):
    """AI_SERVICE user + JWT."""
    ai_user = User(
        email=f"health-ai-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=UserRole.AI_SERVICE,
        full_name="AI Service",
    )
    db.add(ai_user)
    db.commit()
    token = create_access_token(subject=ai_user.id, role="ai_service")
    return {
        "user_id": ai_user.id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


def _make_consent(db, *, patient_id: str, granted_to: str) -> Consent:
    """Create an active health_metric consent."""
    c = Consent(
        patient_id=patient_id,
        consent_type="health_metric",
        data_scope="health_metric",
        granted_to=granted_to,
        valid_from=utcnow() - dt.timedelta(hours=1),
        valid_until=utcnow() + dt.timedelta(hours=24),
    )
    db.add(c)
    db.flush()
    return c


def _seed_metric(db, *, patient_id: str, metric_type: str = "weight", value: float = 70.0):
    """Directly insert a HealthMetric (bypasses service-layer for test setup)."""
    m = HealthMetric(
        patient_id=patient_id,
        metric_type=metric_type,
        value=value,
        unit="kg",
        measured_at=utcnow(),
        source="manual",
        status="normal",
    )
    db.add(m)
    db.commit()
    return m


# ---------------------------------------------------------------------------
# POST /patients/{patient_id}/metrics
# ---------------------------------------------------------------------------


def test_patient_creates_own_metric(client, db, patient_setup):
    """T9-H01: PATIENT creates a metric for their own profile → 201."""
    r = client.post(
        f"/api/v1/patients/{patient_setup['patient_id']}/metrics",
        headers=patient_setup["headers"],
        json=_METRIC_PAYLOAD,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["metric_type"] == "weight"
    assert body["value"] == 70.5
    assert body["id"]


def test_doctor_creates_metric_for_patient(client, db, patient_setup, doctor_setup):
    """T9-H02: DOCTOR with consent creates a metric for patient → 201."""
    _make_consent(db, patient_id=patient_setup["patient_id"], granted_to=doctor_setup["user_id"])
    db.commit()

    r = client.post(
        f"/api/v1/patients/{patient_setup['patient_id']}/metrics",
        headers=doctor_setup["headers"],
        json=_METRIC_PAYLOAD,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["metric_type"] == "weight"


def test_patient_cannot_create_metric_for_another_patient(
    client, db, patient_setup, another_patient_setup
):
    """T9-H03: PATIENT using their token on another patient's profile → 403."""
    r = client.post(
        f"/api/v1/patients/{another_patient_setup['patient_id']}/metrics",
        headers=patient_setup["headers"],
        json=_METRIC_PAYLOAD,
    )
    assert r.status_code == 403, r.text


def test_ai_service_cannot_create_metric(client, db, patient_setup, ai_service_setup):
    """T9-H04: AI_SERVICE is blocked from creating health metrics → 403."""
    r = client.post(
        f"/api/v1/patients/{patient_setup['patient_id']}/metrics",
        headers=ai_service_setup["headers"],
        json=_METRIC_PAYLOAD,
    )
    assert r.status_code == 403, r.text


def test_unauthenticated_cannot_create_metric(client, db, patient_setup):
    """T9-H05: No bearer token → 401."""
    r = client.post(
        f"/api/v1/patients/{patient_setup['patient_id']}/metrics",
        json=_METRIC_PAYLOAD,
    )
    assert r.status_code == 401, r.text


# ---------------------------------------------------------------------------
# GET /patients/{patient_id}/metrics
# ---------------------------------------------------------------------------


def test_patient_lists_own_metrics(client, db, patient_setup):
    """T9-H06: PATIENT lists their own metrics → 200, list."""
    _seed_metric(db, patient_id=patient_setup["patient_id"])

    r = client.get(
        f"/api/v1/patients/{patient_setup['patient_id']}/metrics",
        headers=patient_setup["headers"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)
    assert len(body) >= 1


def test_patient_cannot_list_another_patients_metrics(
    client, db, patient_setup, another_patient_setup
):
    """T9-H07: PATIENT listing another patient's metrics → 403."""
    r = client.get(
        f"/api/v1/patients/{another_patient_setup['patient_id']}/metrics",
        headers=patient_setup["headers"],
    )
    assert r.status_code == 403, r.text


def test_admin_lists_any_patient_metrics(client, db, patient_setup, admin_setup):
    """T9-H08: INTERNAL_ADMIN may list any patient's metrics → 200."""
    _seed_metric(db, patient_id=patient_setup["patient_id"])
    # Admin needs an active consent record to pass the service-layer consent gate
    _make_consent(db, patient_id=patient_setup["patient_id"], granted_to=admin_setup["user_id"])
    db.commit()

    r = client.get(
        f"/api/v1/patients/{patient_setup['patient_id']}/metrics",
        headers=admin_setup["headers"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)


def test_unauthenticated_cannot_list_metrics(client, db, patient_setup):
    """T9-H09: No bearer token on list endpoint → 401."""
    r = client.get(
        f"/api/v1/patients/{patient_setup['patient_id']}/metrics",
    )
    assert r.status_code == 401, r.text


# ---------------------------------------------------------------------------
# GET /patients/{patient_id}/metrics/trend
# ---------------------------------------------------------------------------


def test_patient_gets_own_trend(client, db, patient_setup):
    """T9-H10: PATIENT gets their own trend → 200, has `count`."""
    _seed_metric(db, patient_id=patient_setup["patient_id"], metric_type="weight", value=70.0)

    r = client.get(
        f"/api/v1/patients/{patient_setup['patient_id']}/metrics/trend",
        headers=patient_setup["headers"],
        params={"metric_type": "weight"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "count" in body
    assert body["metric_type"] == "weight"


def test_patient_cannot_get_another_patients_trend(
    client, db, patient_setup, another_patient_setup
):
    """T9-H11: PATIENT requesting another patient's trend → 403."""
    r = client.get(
        f"/api/v1/patients/{another_patient_setup['patient_id']}/metrics/trend",
        headers=patient_setup["headers"],
        params={"metric_type": "weight"},
    )
    assert r.status_code == 403, r.text


def test_unauthenticated_cannot_get_trend(client, db, patient_setup):
    """T9-H12: No token on trend endpoint → 401."""
    r = client.get(
        f"/api/v1/patients/{patient_setup['patient_id']}/metrics/trend",
        params={"metric_type": "weight"},
    )
    assert r.status_code == 401, r.text


def test_trend_returns_empty_when_no_data(client, db, patient_setup):
    """T9-H13: Trend with no data → 200, count=0."""
    r = client.get(
        f"/api/v1/patients/{patient_setup['patient_id']}/metrics/trend",
        headers=patient_setup["headers"],
        params={"metric_type": "nonexistent_type"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 0


def test_clinic_admin_can_read_metrics(client, db, patient_setup):
    """T9-H14: CLINIC_ADMIN (read-allowed role) can list patient metrics with consent."""
    ca_user = User(
        email=f"health-ca-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.CLINIC_ADMIN,
        full_name="Clinic Admin",
    )
    db.add(ca_user)
    db.commit()
    _make_consent(db, patient_id=patient_setup["patient_id"], granted_to=ca_user.id)
    db.commit()
    token = create_access_token(subject=ca_user.id, role="clinic_admin", mfa=True)
    headers = {"Authorization": f"Bearer {token}"}

    r = client.get(
        f"/api/v1/patients/{patient_setup['patient_id']}/metrics",
        headers=headers,
    )
    assert r.status_code == 200, r.text
