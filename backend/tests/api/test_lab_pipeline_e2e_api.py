"""T14 — Lab Pipeline E2E Flow Tests.

Covers the full HTTP API flow at each stage:
  POST /patients/{id}/lab-documents       → register (201)
  POST /lab-documents/{id}/process        → enqueue (202)
  GET  /lab-documents/{id}                → status  (200)
  POST /lab-documents/{id}/interpret      → interpret (200)

All 15 test cases are implemented.
OCR and AI run in mock mode (MCP_OCR_MODE=mock / MCP_AI_MODE=mock via conftest.py).
Worker is synchronous in tests via get_worker().drain().
"""

from __future__ import annotations

import datetime as dt
import os

import pytest
from app.core.clock import utcnow
from app.core.security import create_access_token
from app.models.care import Clinic, Doctor, DoctorClinic
from app.models.governance import Consent
from app.models.patient import PatientProfile
from app.models.user import User, UserRole
from app.services.lab_pipeline import get_worker

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_LAB_PAYLOAD = {
    "storage_key": "s3://test/lab.pdf",
    "file_type": "pdf",
    "lab_name": "Test Lab",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _grant_lab_consent(db, *, patient_id: str, granted_to: str) -> Consent:
    """Create an active lab consent record for *granted_to* on *patient_id*."""
    c = Consent(
        patient_id=patient_id,
        consent_type="lab_access",
        data_scope="lab",
        granted_to=granted_to,
        valid_from=utcnow() - dt.timedelta(hours=1),
        valid_until=utcnow() + dt.timedelta(hours=24),
    )
    db.add(c)
    db.flush()
    return c


def _register_doc(client, *, patient_id: str, headers: dict) -> str:
    """POST register and return the new document id."""
    r = client.post(
        f"/api/v1/patients/{patient_id}/lab-documents",
        headers=headers,
        json=_LAB_PAYLOAD,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def patient_setup(db):
    """Patient user + profile + JWT headers."""
    user = User(
        email=f"e2e-patient-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="E2E Patient",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="E2E Patient")
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
    """A second patient — used for cross-patient ownership tests."""
    user = User(
        email=f"e2e-patient2-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="E2E Patient 2",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="E2E Patient 2")
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
    """Doctor user + clinic association + JWT headers."""
    clinic = Clinic(name=f"E2E Clinic {os.urandom(4).hex()}", is_active=True)
    db.add(clinic)
    db.flush()

    d_user = User(
        email=f"e2e-doctor-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="Dr. E2E",
    )
    db.add(d_user)
    db.flush()

    doctor = Doctor(
        user_id=d_user.id,
        clinic_id=clinic.id,
        full_name="Dr. E2E",
        is_active=True,
    )
    db.add(doctor)
    db.flush()

    link = DoctorClinic(
        doctor_id=doctor.id,
        clinic_id=clinic.id,
        is_primary=True,
        is_active=True,
    )
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
    """CLINIC_ADMIN user + JWT headers."""
    user = User(
        email=f"e2e-admin-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.CLINIC_ADMIN,
        full_name="E2E Clinic Admin",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="clinic_admin", mfa=True)
    return {
        "user_id": user.id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def ai_service_setup(db):
    """AI_SERVICE user + JWT headers."""
    user = User(
        email=f"e2e-ai-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=UserRole.AI_SERVICE,
        full_name="AI Service E2E",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="ai_service")
    return {
        "user_id": user.id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


# ---------------------------------------------------------------------------
# 1. Register — role tests
# ---------------------------------------------------------------------------


def test_register_document_as_patient(client, db, patient_setup):
    """T14-01: Patient registers own lab document → 201 + LabDocumentOut."""
    r = client.post(
        f"/api/v1/patients/{patient_setup['patient_id']}/lab-documents",
        headers=patient_setup["headers"],
        json=_LAB_PAYLOAD,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["patient_id"] == patient_setup["patient_id"]
    assert body["id"]
    assert body["ocr_status"] == "pending"
    assert body["status"] == "uploaded"


def test_register_document_as_doctor(client, db, patient_setup, doctor_setup):
    """T14-02: Doctor with lab consent registers document for patient → 201."""
    _grant_lab_consent(
        db,
        patient_id=patient_setup["patient_id"],
        granted_to=doctor_setup["user_id"],
    )
    db.commit()

    r = client.post(
        f"/api/v1/patients/{patient_setup['patient_id']}/lab-documents",
        headers=doctor_setup["headers"],
        json=_LAB_PAYLOAD,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["patient_id"] == patient_setup["patient_id"]
    assert body["id"]


def test_register_document_ai_service_blocked(client, db, patient_setup, ai_service_setup):
    """T14-03: AI_SERVICE role is blocked from register → 403."""
    r = client.post(
        f"/api/v1/patients/{patient_setup['patient_id']}/lab-documents",
        headers=ai_service_setup["headers"],
        json=_LAB_PAYLOAD,
    )
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# 2. Enqueue — process endpoint
# ---------------------------------------------------------------------------


def test_enqueue_document_returns_202(client, db, patient_setup):
    """T14-04: Enqueue own document → 202 + enqueued=True."""
    doc_id = _register_doc(
        client, patient_id=patient_setup["patient_id"], headers=patient_setup["headers"]
    )

    r = client.post(f"/api/v1/lab-documents/{doc_id}/process", headers=patient_setup["headers"])
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["id"] == doc_id
    assert body["enqueued"] is True
    assert body["status"] == "ocr_pending"


def test_enqueue_idempotent(client, db, patient_setup):
    """T14-05: Second enqueue call on same document → 202 + enqueued=False."""
    doc_id = _register_doc(
        client, patient_id=patient_setup["patient_id"], headers=patient_setup["headers"]
    )

    r1 = client.post(f"/api/v1/lab-documents/{doc_id}/process", headers=patient_setup["headers"])
    assert r1.status_code == 202, r1.text
    assert r1.json()["enqueued"] is True

    r2 = client.post(f"/api/v1/lab-documents/{doc_id}/process", headers=patient_setup["headers"])
    assert r2.status_code == 202, r2.text
    assert r2.json()["enqueued"] is False


# ---------------------------------------------------------------------------
# 3. Status check
# ---------------------------------------------------------------------------


def test_document_status_after_enqueue(client, db, patient_setup):
    """T14-06: Status check after enqueue → 200 + status is ocr_pending or uploaded."""
    doc_id = _register_doc(
        client, patient_id=patient_setup["patient_id"], headers=patient_setup["headers"]
    )
    client.post(f"/api/v1/lab-documents/{doc_id}/process", headers=patient_setup["headers"])

    r = client.get(f"/api/v1/lab-documents/{doc_id}", headers=patient_setup["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == doc_id
    assert body["status"] in ("uploaded", "ocr_pending", "ocr_done", "interpreted")
    assert "ocr_status" in body


# ---------------------------------------------------------------------------
# 4. Interpret
# ---------------------------------------------------------------------------


def test_interpret_document_returns_biomarkers(client, db, patient_setup):
    """T14-07: Interpret own document → 200 + non-empty biomarkers list."""
    doc_id = _register_doc(
        client, patient_id=patient_setup["patient_id"], headers=patient_setup["headers"]
    )

    r = client.post(
        f"/api/v1/lab-documents/{doc_id}/interpret",
        headers=patient_setup["headers"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "biomarkers" in body
    assert isinstance(body["biomarkers"], list)
    assert len(body["biomarkers"]) > 0, "Mock interpreter must return at least one biomarker"
    assert "patient_explanation" in body
    assert body["patient_explanation"], "patient_explanation must be non-empty"


def test_interpret_document_ai_service_blocked(client, db, patient_setup, ai_service_setup):
    """T14-08: AI_SERVICE role is blocked from interpret → 403."""
    doc_id = _register_doc(
        client, patient_id=patient_setup["patient_id"], headers=patient_setup["headers"]
    )

    r = client.post(
        f"/api/v1/lab-documents/{doc_id}/interpret",
        headers=ai_service_setup["headers"],
    )
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# 5. Full pipeline flow
# ---------------------------------------------------------------------------


def test_full_pipeline_flow(client, db, patient_setup):
    """T14-09: Full register → enqueue → status → interpret flow with state verification."""
    headers = patient_setup["headers"]
    patient_id = patient_setup["patient_id"]

    # Step 1: Register
    r_reg = client.post(
        f"/api/v1/patients/{patient_id}/lab-documents",
        headers=headers,
        json=_LAB_PAYLOAD,
    )
    assert r_reg.status_code == 201, r_reg.text
    doc_id = r_reg.json()["id"]
    assert r_reg.json()["status"] == "uploaded"

    # Step 2: Enqueue
    r_proc = client.post(f"/api/v1/lab-documents/{doc_id}/process", headers=headers)
    assert r_proc.status_code == 202, r_proc.text
    assert r_proc.json()["enqueued"] is True
    assert r_proc.json()["status"] == "ocr_pending"

    # Drain the worker so OCR+interpret runs synchronously
    get_worker().drain()

    # Step 3: Status check — should now be interpreted
    r_status = client.get(f"/api/v1/lab-documents/{doc_id}", headers=headers)
    assert r_status.status_code == 200, r_status.text
    assert r_status.json()["status"] == "interpreted"

    # Step 4: Interpret → returns structured biomarkers
    r_interp = client.post(f"/api/v1/lab-documents/{doc_id}/interpret", headers=headers)
    assert r_interp.status_code == 200, r_interp.text
    body = r_interp.json()
    assert "biomarkers" in body
    assert isinstance(body["biomarkers"], list)
    assert "patient_explanation" in body
    assert "doctor_summary" in body


# ---------------------------------------------------------------------------
# 6. Ownership / RBAC
# ---------------------------------------------------------------------------


def test_patient_cannot_process_another_patients_document(
    client, db, patient_setup, another_patient_setup
):
    """T14-10: Patient enqueuing another patient's document → 403."""
    # Register a doc for patient_setup
    doc_id = _register_doc(
        client,
        patient_id=patient_setup["patient_id"],
        headers=patient_setup["headers"],
    )

    # another_patient tries to process it
    r = client.post(
        f"/api/v1/lab-documents/{doc_id}/process",
        headers=another_patient_setup["headers"],
    )
    assert r.status_code == 403, r.text


def test_patient_cannot_read_another_patients_document_status(
    client, db, patient_setup, another_patient_setup
):
    """T14-11: Patient reading another patient's document status → 403 (or 404)."""
    # Register a doc for patient_setup
    doc_id = _register_doc(
        client,
        patient_id=patient_setup["patient_id"],
        headers=patient_setup["headers"],
    )

    # another_patient tries to read its status
    r = client.get(
        f"/api/v1/lab-documents/{doc_id}",
        headers=another_patient_setup["headers"],
    )
    assert r.status_code in (403, 404), r.text


def test_clinic_admin_can_read_document_status(client, db, patient_setup, admin_setup):
    """T14-12: CLINIC_ADMIN with active lab consent can read document status → 200."""
    # Register a doc
    doc_id = _register_doc(
        client,
        patient_id=patient_setup["patient_id"],
        headers=patient_setup["headers"],
    )
    # Grant consent to the clinic admin
    _grant_lab_consent(
        db,
        patient_id=patient_setup["patient_id"],
        granted_to=admin_setup["user_id"],
    )
    db.commit()

    r = client.get(
        f"/api/v1/lab-documents/{doc_id}",
        headers=admin_setup["headers"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == doc_id
    assert "status" in body
    assert "ocr_status" in body


# ---------------------------------------------------------------------------
# 7. Auth guard
# ---------------------------------------------------------------------------


def test_unauthenticated_cannot_register_document(client, db, patient_setup):
    """T14-13: No token → 401 on register endpoint."""
    r = client.post(
        f"/api/v1/patients/{patient_setup['patient_id']}/lab-documents",
        json=_LAB_PAYLOAD,
    )
    assert r.status_code == 401, r.text


# ---------------------------------------------------------------------------
# 8. 404 edge cases
# ---------------------------------------------------------------------------


def test_process_nonexistent_document(client, db, patient_setup):
    """T14-14: Process a document that doesn't exist → 404."""
    r = client.post(
        "/api/v1/lab-documents/nonexistent-doc-id/process",
        headers=patient_setup["headers"],
    )
    assert r.status_code == 404, r.text


def test_interpret_not_found(client, db, patient_setup):
    """T14-15: Interpret a document that doesn't exist → 404."""
    r = client.post(
        "/api/v1/lab-documents/nonexistent-doc-id/interpret",
        headers=patient_setup["headers"],
    )
    assert r.status_code == 404, r.text
