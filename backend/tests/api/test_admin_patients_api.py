"""Admin — Patient Records Management API tests.

Covers:
  GET   /admin/patients                — list, search, filter, pagination
  GET   /admin/patients/{patient_id}   — detail (profile + summary + consent + audit)
  PATCH /admin/patients/{patient_id}/status — activate/deactivate

RBAC matrix:
  - INTERNAL_ADMIN / SUPER_ADMIN: full access
  - DOCTOR / PATIENT / AI_SERVICE: 403 on all endpoints
"""

from __future__ import annotations

import datetime as dt
import os

import pytest
from app.core.security import create_access_token
from app.models.clinical import LabResult, Medication
from app.models.consent import TermsConsent
from app.models.patient import PatientProfile
from app.models.user import User, UserRole
from app.services import admin_patients as admin_patients_service

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def super_admin(db):
    user = User(
        email=f"sa-adminpt-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=UserRole.SUPER_ADMIN,
        full_name="Super Admin",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="super_admin", mfa=True)
    return {"user_id": user.id, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def internal_admin(db):
    user = User(
        email=f"ia-adminpt-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=UserRole.INTERNAL_ADMIN,
        full_name="Internal Admin",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="internal_admin", mfa=True)
    return {"user_id": user.id, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def doctor_user(db):
    user = User(
        email=f"doctor-adminpt-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="doctor")
    return {"user_id": user.id, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def ai_service_user(db):
    user = User(
        email=f"ai-adminpt-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=UserRole.AI_SERVICE,
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="ai_service")
    return {"user_id": user.id, "headers": {"Authorization": f"Bearer {token}"}}


def _make_patient(
    db,
    *,
    full_name: str = "Nguyen Van A",
    phone: str = "+84900000001",
    gender: str = "male",
    dob: str = "1990-01-01",
    is_active: bool = True,
    with_lab: bool = False,
    with_medication: bool = False,
    with_consent: bool = False,
):
    user = User(
        email=f"patient-adminpt-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name=full_name,
        is_active=is_active,
    )
    db.add(user)
    db.commit()

    profile = PatientProfile(
        user_id=user.id,
        full_name=full_name,
        phone=phone,
        gender=gender,
        dob=dob,
    )
    db.add(profile)
    db.commit()

    if with_lab:
        db.add(
            LabResult(
                patient_id=profile.id,
                test_name="Glucose",
                value=90.0,
                unit="mg/dL",
                test_date=dt.date.today(),
            )
        )
    if with_medication:
        db.add(Medication(patient_id=profile.id, name="Metformin", dose="500mg"))
    if with_consent:
        db.add(
            TermsConsent(
                user_id=user.id,
                terms_version="1.0",
                privacy_version="1.0",
                accepted_at=dt.datetime.now(dt.UTC),
            )
        )
    db.commit()

    return {"user": user, "profile": profile}


@pytest.fixture
def patient_alice(db):
    """Active patient, has lab + medication + valid consent."""
    return _make_patient(
        db,
        full_name="Alice Nguyen",
        phone="+84911111111",
        gender="female",
        dob="1985-06-15",
        with_lab=True,
        with_medication=True,
        with_consent=True,
    )


@pytest.fixture
def patient_bob(db):
    """Inactive (blocked) patient, no clinical data, no consent."""
    return _make_patient(
        db,
        full_name="Bob Tran",
        phone="+84922222222",
        gender="male",
        dob="2001-03-10",
        is_active=False,
    )


# ---------------------------------------------------------------------------
# List — RBAC
# ---------------------------------------------------------------------------


def test_super_admin_lists_patients(client, super_admin, patient_alice, patient_bob):
    r = client.get("/api/v1/admin/patients", headers=super_admin["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert "total" in body and "items" in body
    assert body["total"] >= 2


def test_internal_admin_lists_patients(client, internal_admin, patient_alice):
    r = client.get("/api/v1/admin/patients", headers=internal_admin["headers"])
    assert r.status_code == 200, r.text


def test_doctor_cannot_list_patients(client, doctor_user):
    r = client.get("/api/v1/admin/patients", headers=doctor_user["headers"])
    assert r.status_code == 403, r.text


def test_patient_cannot_list_patients(client, patient_alice):
    user = patient_alice["user"]
    token = create_access_token(subject=user.id, role="patient")
    r = client.get(
        "/api/v1/admin/patients", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 403, r.text


def test_ai_service_cannot_list_patients(client, ai_service_user):
    r = client.get("/api/v1/admin/patients", headers=ai_service_user["headers"])
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# List — search / filter / pagination
# ---------------------------------------------------------------------------


def test_search_matches_by_name(client, super_admin, patient_alice, patient_bob):
    r = client.get(
        "/api/v1/admin/patients",
        params={"search": "Alice"},
        headers=super_admin["headers"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [item["id"] for item in body["items"]]
    assert patient_alice["profile"].id in ids
    assert patient_bob["profile"].id not in ids


def test_search_matches_by_phone(client, super_admin, patient_alice):
    r = client.get(
        "/api/v1/admin/patients",
        params={"search": "911111111"},
        headers=super_admin["headers"],
    )
    assert r.status_code == 200, r.text
    ids = [item["id"] for item in r.json()["items"]]
    assert patient_alice["profile"].id in ids


def test_filter_by_status_inactive(client, super_admin, patient_alice, patient_bob):
    r = client.get(
        "/api/v1/admin/patients",
        params={"status": "inactive"},
        headers=super_admin["headers"],
    )
    assert r.status_code == 200, r.text
    ids = [item["id"] for item in r.json()["items"]]
    assert patient_bob["profile"].id in ids
    assert patient_alice["profile"].id not in ids


def test_filter_by_gender(client, super_admin, patient_alice, patient_bob):
    r = client.get(
        "/api/v1/admin/patients",
        params={"gender": "female"},
        headers=super_admin["headers"],
    )
    assert r.status_code == 200, r.text
    ids = [item["id"] for item in r.json()["items"]]
    assert patient_alice["profile"].id in ids
    assert patient_bob["profile"].id not in ids


def test_filter_has_labs(client, super_admin, patient_alice, patient_bob):
    r = client.get(
        "/api/v1/admin/patients",
        params={"has_labs": "true"},
        headers=super_admin["headers"],
    )
    assert r.status_code == 200, r.text
    ids = [item["id"] for item in r.json()["items"]]
    assert patient_alice["profile"].id in ids
    assert patient_bob["profile"].id not in ids


def test_filter_has_consent(client, super_admin, patient_alice, patient_bob):
    r = client.get(
        "/api/v1/admin/patients",
        params={"has_consent": "false"},
        headers=super_admin["headers"],
    )
    assert r.status_code == 200, r.text
    ids = [item["id"] for item in r.json()["items"]]
    assert patient_bob["profile"].id in ids
    assert patient_alice["profile"].id not in ids


def test_pagination_limit(client, super_admin, patient_alice, patient_bob):
    r = client.get(
        "/api/v1/admin/patients",
        params={"limit": 1, "skip": 0},
        headers=super_admin["headers"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["items"]) == 1
    assert body["total"] >= 2


def test_list_response_excludes_phi_detail_fields(client, super_admin, patient_alice):
    """List rows must not include known_conditions/allergies/address (detail-only)."""
    r = client.get("/api/v1/admin/patients", headers=super_admin["headers"])
    assert r.status_code == 200, r.text
    for item in r.json()["items"]:
        assert "known_conditions" not in item
        assert "allergies" not in item
        assert "address" not in item
        assert "password_hash" not in item


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------


def test_super_admin_gets_patient_detail(client, super_admin, patient_alice):
    pid = patient_alice["profile"].id
    r = client.get(f"/api/v1/admin/patients/{pid}", headers=super_admin["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == pid
    assert body["full_name"] == "Alice Nguyen"
    assert body["consent_status"] == "valid"
    assert "summary" in body
    assert "password_hash" not in body


def test_doctor_cannot_get_patient_detail(client, doctor_user, patient_alice):
    pid = patient_alice["profile"].id
    r = client.get(f"/api/v1/admin/patients/{pid}", headers=doctor_user["headers"])
    assert r.status_code == 403, r.text


def test_get_nonexistent_patient_returns_404(client, super_admin):
    r = client.get(
        "/api/v1/admin/patients/00000000-0000-0000-0000-000000000000",
        headers=super_admin["headers"],
    )
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# Status update
# ---------------------------------------------------------------------------


def test_super_admin_blocks_patient(client, super_admin, patient_bob):
    """patient_bob starts inactive; activating then deactivating round-trips."""
    pid = patient_bob["profile"].id
    r = client.patch(
        f"/api/v1/admin/patients/{pid}/status",
        headers=super_admin["headers"],
        json={"is_active": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is True

    r2 = client.patch(
        f"/api/v1/admin/patients/{pid}/status",
        headers=super_admin["headers"],
        json={"is_active": False},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["is_active"] is False


def test_doctor_cannot_update_patient_status(client, doctor_user, patient_alice):
    pid = patient_alice["profile"].id
    r = client.patch(
        f"/api/v1/admin/patients/{pid}/status",
        headers=doctor_user["headers"],
        json={"is_active": False},
    )
    assert r.status_code == 403, r.text


def test_update_status_nonexistent_patient_returns_404(client, super_admin):
    r = client.patch(
        "/api/v1/admin/patients/00000000-0000-0000-0000-000000000000/status",
        headers=super_admin["headers"],
        json={"is_active": False},
    )
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# Regression — status update must not 500 when the target patient falls
# outside the list-search candidate window (PR #85 review finding).
# ---------------------------------------------------------------------------


def test_status_update_succeeds_for_patient_outside_candidate_window(
    client, super_admin, db, monkeypatch
):
    """The route must not rebuild its response via list_patients()/search,
    which is bounded by _CANDIDATE_LIMIT (ordered by created_at desc) — a
    patient outside that window previously caused a committed write followed
    by an unhandled IndexError -> 500.
    """
    monkeypatch.setattr(admin_patients_service, "_CANDIDATE_LIMIT", 1)

    now = dt.datetime.now(dt.UTC)
    older = _make_patient(db, full_name="Older Outside Window", phone="+84933333331")
    newer = _make_patient(db, full_name="Newer Inside Window", phone="+84933333332")
    older["profile"].created_at = now - dt.timedelta(days=1)
    newer["profile"].created_at = now
    db.add_all([older["profile"], newer["profile"]])
    db.commit()

    pid = older["profile"].id
    r = client.patch(
        f"/api/v1/admin/patients/{pid}/status",
        headers=super_admin["headers"],
        json={"is_active": False},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == pid
    assert body["is_active"] is False

    db.expire_all()
    db_user = db.get(User, older["user"].id)
    assert db_user.is_active is False, "DB status must match the response, not just avoid a crash"
