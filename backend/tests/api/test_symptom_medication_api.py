"""T15 API tests — Symptom Log + Medication CRUD (RBAC + soft-delete).

Covers:
  POST   /api/v1/patients/{patient_id}/symptoms
  GET    /api/v1/patients/{patient_id}/symptoms
  POST   /api/v1/patients/{patient_id}/medications
  GET    /api/v1/patients/{patient_id}/medications
  DELETE /api/v1/patients/{patient_id}/medications/{med_id}

16 test cases:
  Symptom Log:
   1.  test_patient_creates_symptom_log               — 201, fields verified
   2.  test_patient_cannot_create_symptom_for_another_patient — 403
   3.  test_doctor_creates_symptom_with_consent        — 201
   4.  test_ai_service_cannot_create_symptom           — 403 (critical safety)
   5.  test_patient_lists_own_symptoms                 — 200, items list
   6.  test_symptom_severity_validation                — 422 if severity > 10

  Medication:
   7.  test_patient_adds_medication                    — 201, fields verified
   8.  test_patient_cannot_add_medication_for_another_patient — 403
   9.  test_ai_service_cannot_add_medication           — 403 (critical safety)
  10.  test_patient_lists_medications                  — 200, items list
  11.  test_soft_delete_medication                     — 204
  12.  test_doctor_cannot_delete_medication            — 403
  13.  test_delete_nonexistent_medication              — 404
  14.  test_deleted_medication_not_in_list             — 200, deleted absent
  15.  test_doctor_lists_medications_with_consent      — 200
  16.  test_unauthenticated_cannot_create_symptom      — 401
"""

from __future__ import annotations

import os

import pytest
from app.core.security import create_access_token
from app.models.governance import Consent
from app.models.patient import PatientProfile
from app.models.user import User, UserRole
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def _symptoms_url(patient_id: str) -> str:
    return f"/api/v1/patients/{patient_id}/symptoms"


def _medications_url(patient_id: str) -> str:
    return f"/api/v1/patients/{patient_id}/medications"


def _medication_url(patient_id: str, med_id: str) -> str:
    return f"/api/v1/patients/{patient_id}/medications/{med_id}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def patient_a(db):
    """Primary PATIENT user + PatientProfile + bearer headers."""
    user = User(
        email=f"t15-patient-a-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="T15 Patient A",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="T15 Patient A")
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
        email=f"t15-patient-b-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="T15 Patient B",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="T15 Patient B")
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
    """DOCTOR user + bearer headers."""
    user = User(
        email=f"t15-doctor-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="T15 Doctor",
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
    """INTERNAL_ADMIN bearer headers."""
    admin_id = f"t15-admin-{os.urandom(4).hex()}"
    token = create_access_token(subject=admin_id, role="internal_admin", mfa=True)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def doctor_consent_for_patient_a(db, patient_a, doctor):
    """Grant doctor active consent (scope='profile') for patient_a."""
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
# Symptom Log tests
# ---------------------------------------------------------------------------


# 1
def test_patient_creates_symptom_log(client: TestClient, patient_a):
    """PATIENT can log a symptom for their own profile — 201 with correct fields."""
    r = client.post(
        _symptoms_url(patient_a["patient_id"]),
        headers=patient_a["headers"],
        json={"description": "Headache after exercise", "severity": 4},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["patient_id"] == patient_a["patient_id"]
    assert body["description"] == "Headache after exercise"
    assert body["severity"] == 4
    assert "id" in body
    assert "reported_at" in body
    assert "created_at" in body


# 2
def test_patient_cannot_create_symptom_for_another_patient(
    client: TestClient, patient_a, patient_b
):
    """PATIENT cannot log a symptom on another patient's record — 403."""
    r = client.post(
        _symptoms_url(patient_b["patient_id"]),
        headers=patient_a["headers"],
        json={"description": "Sneak symptom"},
    )
    assert r.status_code == 403, r.text


# 3
def test_doctor_creates_symptom_with_consent(
    client: TestClient, patient_a, doctor, doctor_consent_for_patient_a
):
    """DOCTOR with active consent can log a symptom for a patient — 201."""
    r = client.post(
        _symptoms_url(patient_a["patient_id"]),
        headers=doctor["headers"],
        json={"description": "Doctor-observed shortness of breath", "severity": 6},
    )
    assert r.status_code == 201, r.text
    assert r.json()["patient_id"] == patient_a["patient_id"]


# 4
def test_ai_service_cannot_create_symptom(client: TestClient, patient_a):
    """AI_SERVICE role must be blocked (403) — critical safety check."""
    ai_token = create_access_token(subject=f"ai-{os.urandom(4).hex()}", role="ai_service")
    r = client.post(
        _symptoms_url(patient_a["patient_id"]),
        headers={"Authorization": f"Bearer {ai_token}"},
        json={"description": "AI-fabricated symptom"},
    )
    assert r.status_code == 403, r.text


# 5
def test_patient_lists_own_symptoms(client: TestClient, patient_a):
    """PATIENT can GET their own symptom list — 200, correct structure."""
    # Seed one symptom first
    client.post(
        _symptoms_url(patient_a["patient_id"]),
        headers=patient_a["headers"],
        json={"description": "Fatigue", "severity": 3},
    )

    r = client.get(_symptoms_url(patient_a["patient_id"]), headers=patient_a["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["patient_id"] == patient_a["patient_id"]
    assert isinstance(body["items"], list)
    assert body["total"] >= 1
    # Newest first: most recently added should be first
    assert body["items"][0]["description"] == "Fatigue"


# 6
def test_symptom_severity_validation(client: TestClient, patient_a):
    """severity > 10 must be rejected with 422."""
    r = client.post(
        _symptoms_url(patient_a["patient_id"]),
        headers=patient_a["headers"],
        json={"description": "Over-scale severity", "severity": 11},
    )
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# Medication tests
# ---------------------------------------------------------------------------


# 7
def test_patient_adds_medication(client: TestClient, patient_a):
    """PATIENT can add a medication record — 201 with correct fields."""
    r = client.post(
        _medications_url(patient_a["patient_id"]),
        headers=patient_a["headers"],
        json={"name": "Metformin", "dose": "500mg twice daily", "note": "With meals"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["patient_id"] == patient_a["patient_id"]
    assert body["name"] == "Metformin"
    assert body["dose"] == "500mg twice daily"
    assert body["note"] == "With meals"
    assert "id" in body
    assert "created_at" in body


# 8
def test_patient_cannot_add_medication_for_another_patient(
    client: TestClient, patient_a, patient_b
):
    """PATIENT cannot add a medication to another patient's record — 403."""
    r = client.post(
        _medications_url(patient_b["patient_id"]),
        headers=patient_a["headers"],
        json={"name": "Injected drug"},
    )
    assert r.status_code == 403, r.text


# 9
def test_ai_service_cannot_add_medication(client: TestClient, patient_a):
    """AI_SERVICE must be blocked from adding medications — 403 (CRITICAL SAFETY)."""
    ai_token = create_access_token(subject=f"ai-{os.urandom(4).hex()}", role="ai_service")
    r = client.post(
        _medications_url(patient_a["patient_id"]),
        headers={"Authorization": f"Bearer {ai_token}"},
        json={"name": "AI-prescribed drug", "dose": "9999mg"},
    )
    assert r.status_code == 403, r.text


# 10
def test_patient_lists_medications(client: TestClient, patient_a):
    """PATIENT can GET their own medication list — 200, correct structure."""
    # Seed one medication
    client.post(
        _medications_url(patient_a["patient_id"]),
        headers=patient_a["headers"],
        json={"name": "Aspirin", "dose": "100mg daily"},
    )

    r = client.get(_medications_url(patient_a["patient_id"]), headers=patient_a["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["patient_id"] == patient_a["patient_id"]
    assert isinstance(body["items"], list)
    assert body["total"] >= 1


# 11
def test_soft_delete_medication(client: TestClient, patient_a):
    """PATIENT can soft-delete their own medication — 204, record disappears from list."""
    # Add medication
    add_r = client.post(
        _medications_url(patient_a["patient_id"]),
        headers=patient_a["headers"],
        json={"name": "ToDelete Drug"},
    )
    assert add_r.status_code == 201, add_r.text
    med_id = add_r.json()["id"]

    # Delete it
    del_r = client.delete(
        _medication_url(patient_a["patient_id"], med_id),
        headers=patient_a["headers"],
    )
    assert del_r.status_code == 204, del_r.text

    # Confirm it no longer appears in list
    list_r = client.get(_medications_url(patient_a["patient_id"]), headers=patient_a["headers"])
    assert list_r.status_code == 200, list_r.text
    ids = [item["id"] for item in list_r.json()["items"]]
    assert med_id not in ids, "Soft-deleted medication should not appear in list"


# 12
def test_doctor_cannot_delete_medication(
    client: TestClient, patient_a, doctor, doctor_consent_for_patient_a
):
    """DOCTOR must be blocked from deleting medications — 403 (clinical safety)."""
    # Add a medication as the patient
    add_r = client.post(
        _medications_url(patient_a["patient_id"]),
        headers=patient_a["headers"],
        json={"name": "Doctor-target drug"},
    )
    assert add_r.status_code == 201, add_r.text
    med_id = add_r.json()["id"]

    # Doctor tries to delete — must be rejected
    del_r = client.delete(
        _medication_url(patient_a["patient_id"], med_id),
        headers=doctor["headers"],
    )
    assert del_r.status_code == 403, del_r.text


# 13
def test_delete_nonexistent_medication(client: TestClient, patient_a):
    """Deleting a medication that doesn't exist returns 404."""
    r = client.delete(
        _medication_url(patient_a["patient_id"], "00000000-0000-0000-0000-000000000000"),
        headers=patient_a["headers"],
    )
    assert r.status_code == 404, r.text


# 14
def test_deleted_medication_not_in_list(client: TestClient, patient_a):
    """Soft-deleted medications are excluded from GET /medications list."""
    # Add two medications
    add_r1 = client.post(
        _medications_url(patient_a["patient_id"]),
        headers=patient_a["headers"],
        json={"name": "Keep This"},
    )
    add_r2 = client.post(
        _medications_url(patient_a["patient_id"]),
        headers=patient_a["headers"],
        json={"name": "Delete This"},
    )
    assert add_r1.status_code == 201
    assert add_r2.status_code == 201
    keep_id = add_r1.json()["id"]
    delete_id = add_r2.json()["id"]

    # Delete the second
    client.delete(
        _medication_url(patient_a["patient_id"], delete_id),
        headers=patient_a["headers"],
    )

    # List should contain "Keep This" but not "Delete This"
    list_r = client.get(_medications_url(patient_a["patient_id"]), headers=patient_a["headers"])
    assert list_r.status_code == 200, list_r.text
    ids = [item["id"] for item in list_r.json()["items"]]
    assert keep_id in ids, "'Keep This' should still be in the list"
    assert delete_id not in ids, "'Delete This' should be excluded after soft-delete"


# 15
def test_doctor_lists_medications_with_consent(
    client: TestClient, patient_a, doctor, doctor_consent_for_patient_a
):
    """DOCTOR with active consent can GET patient medication list — 200."""
    # Seed a medication
    client.post(
        _medications_url(patient_a["patient_id"]),
        headers=patient_a["headers"],
        json={"name": "Lisinopril", "dose": "10mg daily"},
    )

    r = client.get(_medications_url(patient_a["patient_id"]), headers=doctor["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["patient_id"] == patient_a["patient_id"]
    assert isinstance(body["items"], list)


# 16
def test_unauthenticated_cannot_create_symptom(client: TestClient, patient_a):
    """Requests without a bearer token must be rejected with 401."""
    r = client.post(
        _symptoms_url(patient_a["patient_id"]),
        json={"description": "Unauthorised attempt"},
    )
    assert r.status_code == 401, r.text


# ---------------------------------------------------------------------------
# PR-D — medication frequency field + PATCH (edit)
# ---------------------------------------------------------------------------


def test_add_medication_with_frequency(client: TestClient, patient_a):
    """PR-D: frequency persists on create and is returned."""
    r = client.post(
        _medications_url(patient_a["patient_id"]),
        headers=patient_a["headers"],
        json={"name": "Metformin", "dose": "500mg", "frequency": "2 lần/ngày", "note": "Sau ăn"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["frequency"] == "2 lần/ngày"


def test_patient_updates_own_medication(client: TestClient, patient_a):
    """PR-D: PATIENT can PATCH their own medication — fields update, others preserved."""
    created = client.post(
        _medications_url(patient_a["patient_id"]),
        headers=patient_a["headers"],
        json={"name": "Metformin", "dose": "500mg", "frequency": "1 lần/ngày"},
    ).json()
    med_id = created["id"]

    r = client.patch(
        _medication_url(patient_a["patient_id"], med_id),
        headers=patient_a["headers"],
        json={"dose": "850mg", "frequency": "2 lần/ngày"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dose"] == "850mg"
    assert body["frequency"] == "2 lần/ngày"
    assert body["name"] == "Metformin"  # unchanged


def test_patient_cannot_update_another_patients_medication(
    client: TestClient, patient_a, patient_b
):
    """PR-D: cross-patient PATCH is blocked (403 on ownership before 404)."""
    created = client.post(
        _medications_url(patient_a["patient_id"]),
        headers=patient_a["headers"],
        json={"name": "Metformin"},
    ).json()
    r = client.patch(
        _medication_url(patient_b["patient_id"], created["id"]),
        headers=patient_a["headers"],
        json={"dose": "999mg"},
    )
    assert r.status_code == 403, r.text


def test_update_nonexistent_medication_404(client: TestClient, patient_a):
    """PR-D: PATCH on a missing medication id → 404."""
    r = client.patch(
        _medication_url(patient_a["patient_id"], "00000000-0000-0000-0000-000000000000"),
        headers=patient_a["headers"],
        json={"dose": "1mg"},
    )
    assert r.status_code == 404, r.text


def test_ai_service_cannot_update_medication(client: TestClient, patient_a):
    """PR-D: AI_SERVICE must be blocked from PATCH (CRITICAL SAFETY) — 403."""
    created = client.post(
        _medications_url(patient_a["patient_id"]),
        headers=patient_a["headers"],
        json={"name": "Metformin"},
    ).json()
    ai_token = create_access_token(subject=f"ai-{os.urandom(4).hex()}", role="ai_service")
    r = client.patch(
        _medication_url(patient_a["patient_id"], created["id"]),
        headers={"Authorization": f"Bearer {ai_token}"},
        json={"dose": "1mg"},
    )
    assert r.status_code == 403, r.text
