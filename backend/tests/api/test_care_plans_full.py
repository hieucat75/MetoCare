"""T16 — Care Plan API: full RBAC + flow coverage (15 tests).

Endpoints under test (all at /api/v1/care_plans):
  POST   /care_plans                       — create
  GET    /care_plans/{id}                  — read one
  GET    /care_plans                       — list
  PATCH  /care_plans/{id}                  — update
  POST   /care_plans/{id}/approve          — approve

Roles tested: DOCTOR, PATIENT (own + other), AI_SERVICE, CLINIC_ADMIN,
              INTERNAL_ADMIN, unauthenticated.
"""

from __future__ import annotations

import os

import pytest
from app.core.security import create_access_token
from app.models.care import CarePlan, Clinic, Doctor, DoctorClinic, Encounter
from app.models.patient import PatientProfile
from app.models.user import User, UserRole

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def doctor_setup(db):
    """Clinic + doctor user + Doctor record + DoctorClinic link."""
    clinic = Clinic(name=f"Clinic-t16-{os.urandom(4).hex()}", is_active=True)
    db.add(clinic)
    db.flush()

    d_user = User(
        email=f"doctor-t16-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="Dr. T16",
    )
    db.add(d_user)
    db.flush()

    doctor = Doctor(
        user_id=d_user.id,
        clinic_id=clinic.id,
        full_name="Dr. T16",
        is_active=True,
    )
    db.add(doctor)
    db.flush()

    link = DoctorClinic(
        doctor_id=doctor.id, clinic_id=clinic.id, is_primary=True, is_active=True
    )
    db.add(link)
    db.commit()

    token = create_access_token(subject=d_user.id, role="doctor", mfa=True)
    return {
        "clinic_id": clinic.id,
        "doctor_user_id": d_user.id,
        "doctor_id": doctor.id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def patient_setup(db):
    """Patient user + PatientProfile."""
    p_user = User(
        email=f"patient-t16-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Patient T16",
    )
    db.add(p_user)
    db.flush()

    profile = PatientProfile(user_id=p_user.id, full_name="Patient T16")
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
def other_patient_setup(db):
    """A second patient (no overlap with patient_setup)."""
    p_user = User(
        email=f"patient2-t16-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Other Patient T16",
    )
    db.add(p_user)
    db.flush()

    profile = PatientProfile(user_id=p_user.id, full_name="Other Patient T16")
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
def clinic_admin_setup():
    """CLINIC_ADMIN bearer token (no DB record needed for 403 guard tests)."""
    ca_id = f"clinic-admin-t16-{os.urandom(4).hex()}"
    token = create_access_token(subject=ca_id, role="clinic_admin", mfa=True)
    return {"user_id": ca_id, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def admin_setup():
    """INTERNAL_ADMIN bearer token."""
    admin_id = f"admin-t16-{os.urandom(4).hex()}"
    token = create_access_token(subject=admin_id, role="internal_admin", mfa=True)
    return {"user_id": admin_id, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def seeded_care_plan(db, patient_setup, doctor_setup):
    """A DRAFT care plan linked via an encounter for patient_setup/doctor_setup."""
    enc = Encounter(
        patient_id=patient_setup["patient_id"],
        doctor_id=doctor_setup["doctor_id"],
        encounter_type="consultation",
        status="pending_review",
    )
    db.add(enc)
    db.flush()

    plan = CarePlan(
        patient_id=patient_setup["patient_id"],
        encounter_id=enc.id,
        title="T16 Draft Care Plan",
        content="Initial management plan.",
        status="DRAFT",
        ai_generated=False,
        version=1,
    )
    db.add(plan)
    db.commit()
    return plan


# ---------------------------------------------------------------------------
# 1. Create — POST /api/v1/care_plans
# ---------------------------------------------------------------------------


def test_doctor_creates_care_plan(client, doctor_setup, patient_setup):
    """DOCTOR may create a DRAFT care plan — 201."""
    r = client.post(
        "/api/v1/care_plans",
        headers=doctor_setup["headers"],
        json={
            "patient_id": patient_setup["patient_id"],
            "title": "Diabetes Management",
            "status": "DRAFT",
            "content": "Lifestyle modification + metformin.",
            "ai_generated": False,
            "version": 1,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["title"] == "Diabetes Management"
    assert body["status"] == "DRAFT"
    assert body["patient_id"] == patient_setup["patient_id"]


def test_patient_cannot_create_care_plan(client, patient_setup):
    """PATIENT role is forbidden from creating a care plan — 403."""
    r = client.post(
        "/api/v1/care_plans",
        headers=patient_setup["headers"],
        json={
            "patient_id": patient_setup["patient_id"],
            "title": "Self Care Plan",
            "status": "DRAFT",
        },
    )
    assert r.status_code == 403, r.text


def test_ai_service_cannot_create_care_plan(client, patient_setup):
    """AI_SERVICE role is forbidden from creating a care plan — 403."""
    ai_token = create_access_token(
        subject=f"ai-{os.urandom(4).hex()}", role="ai_service", mfa=False
    )
    r = client.post(
        "/api/v1/care_plans",
        headers={"Authorization": f"Bearer {ai_token}"},
        json={
            "patient_id": patient_setup["patient_id"],
            "title": "AI Generated Plan",
            "status": "DRAFT",
            "ai_generated": True,
        },
    )
    assert r.status_code == 403, r.text


def test_clinic_admin_cannot_create_care_plan(client, clinic_admin_setup, patient_setup):
    """CLINIC_ADMIN role is forbidden from creating a care plan — 403."""
    r = client.post(
        "/api/v1/care_plans",
        headers=clinic_admin_setup["headers"],
        json={
            "patient_id": patient_setup["patient_id"],
            "title": "Admin Created Plan",
            "status": "DRAFT",
        },
    )
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# 2. Read one — GET /api/v1/care_plans/{id}
# ---------------------------------------------------------------------------


def test_doctor_reads_care_plan(client, doctor_setup, seeded_care_plan):
    """Assigned DOCTOR can read the care plan — 200."""
    r = client.get(
        f"/api/v1/care_plans/{seeded_care_plan.id}",
        headers=doctor_setup["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["id"] == seeded_care_plan.id


def test_patient_reads_own_care_plan(client, patient_setup, seeded_care_plan):
    """PATIENT can read their own care plan — 200."""
    r = client.get(
        f"/api/v1/care_plans/{seeded_care_plan.id}",
        headers=patient_setup["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["id"] == seeded_care_plan.id


def test_patient_cannot_read_other_patients_care_plan(
    client, other_patient_setup, seeded_care_plan
):
    """PATIENT cannot read another patient's care plan — 403."""
    r = client.get(
        f"/api/v1/care_plans/{seeded_care_plan.id}",
        headers=other_patient_setup["headers"],
    )
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# 3. List — GET /api/v1/care_plans
# ---------------------------------------------------------------------------


def test_doctor_lists_care_plans(client, doctor_setup, patient_setup, seeded_care_plan):
    """DOCTOR can list care plans (filtered by patient) — 200, list."""
    r = client.get(
        "/api/v1/care_plans",
        headers=doctor_setup["headers"],
        params={"patient_id": patient_setup["patient_id"]},
    )
    assert r.status_code == 200, r.text
    ids = [p["id"] for p in r.json()]
    assert seeded_care_plan.id in ids


# ---------------------------------------------------------------------------
# 4. Update — PATCH /api/v1/care_plans/{id}
# ---------------------------------------------------------------------------


def test_doctor_updates_care_plan(client, doctor_setup, seeded_care_plan):
    """Assigned DOCTOR can update the care plan — 200."""
    r = client.patch(
        f"/api/v1/care_plans/{seeded_care_plan.id}",
        headers=doctor_setup["headers"],
        json={"title": "Updated Title", "content": "Revised plan."},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "Updated Title"
    assert body["content"] == "Revised plan."


def test_patient_cannot_update_care_plan(client, patient_setup, seeded_care_plan):
    """PATIENT cannot update a care plan — 403."""
    r = client.patch(
        f"/api/v1/care_plans/{seeded_care_plan.id}",
        headers=patient_setup["headers"],
        json={"title": "Patient Modified"},
    )
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# 5. Approve — POST /api/v1/care_plans/{id}/approve
# ---------------------------------------------------------------------------


def test_doctor_approves_care_plan(client, doctor_setup, seeded_care_plan):
    """Assigned DOCTOR can approve a DRAFT care plan — 200, status=APPROVED."""
    r = client.post(
        f"/api/v1/care_plans/{seeded_care_plan.id}/approve",
        headers=doctor_setup["headers"],
        json={"approved_by_doctor_id": doctor_setup["doctor_id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "APPROVED"
    assert body["approved_by_doctor_id"] == doctor_setup["doctor_id"]
    assert body["approved_at"] is not None


def test_patient_cannot_approve_care_plan(client, patient_setup, doctor_setup, seeded_care_plan):
    """PATIENT cannot approve a care plan — 403."""
    r = client.post(
        f"/api/v1/care_plans/{seeded_care_plan.id}/approve",
        headers=patient_setup["headers"],
        json={"approved_by_doctor_id": doctor_setup["doctor_id"]},
    )
    assert r.status_code == 403, r.text


def test_ai_cannot_approve_care_plan(client, doctor_setup, seeded_care_plan):
    """AI_SERVICE cannot approve a care plan — 403."""
    ai_token = create_access_token(
        subject=f"ai-svc-{os.urandom(4).hex()}", role="ai_service", mfa=False
    )
    r = client.post(
        f"/api/v1/care_plans/{seeded_care_plan.id}/approve",
        headers={"Authorization": f"Bearer {ai_token}"},
        json={"approved_by_doctor_id": doctor_setup["doctor_id"]},
    )
    assert r.status_code == 403, r.text


def test_approve_nonexistent_plan(client, doctor_setup):
    """Approving a non-existent care plan returns 404."""
    r = client.post(
        "/api/v1/care_plans/nonexistent-plan-id-t16/approve",
        headers=doctor_setup["headers"],
        json={"approved_by_doctor_id": doctor_setup["doctor_id"]},
    )
    assert r.status_code == 404, r.text


def test_unauthenticated_cannot_access_care_plan(client, seeded_care_plan):
    """No token → 401 on read endpoint."""
    r = client.get(f"/api/v1/care_plans/{seeded_care_plan.id}")
    assert r.status_code == 401, r.text
