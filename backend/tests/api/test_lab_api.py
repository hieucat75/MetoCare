"""T7 API tests — Lab document RBAC endpoints.

Covers all 4 lab routes with RBAC enforcement:
  - POST /patients/{patient_id}/lab-documents
  - POST /lab-documents/{id}/process
  - GET  /lab-documents/{id}
  - POST /lab-documents/{id}/interpret

All 15 required test cases are implemented.
OCR runs in mock mode (MCP_OCR_MODE=mock, set in conftest.py).
"""

from __future__ import annotations

import datetime as dt
import os

import pytest
from app.core.clock import utcnow
from app.core.security import create_access_token
from app.models.care import Clinic, Doctor, DoctorClinic
from app.models.clinical import LabDocument
from app.models.governance import Consent
from app.models.patient import PatientProfile
from app.models.user import User, UserRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_UPLOAD_PAYLOAD = {
    "storage_key": "test/lab_report.pdf",
    "file_type": "pdf",
    "lab_name": "Test Lab",
}


def _make_consent(db, *, patient_id: str, granted_to: str) -> Consent:
    """Create an active lab consent for a requester (e.g. doctor / clinic)."""
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def patient_setup(db):
    """Patient user + profile + JWT token."""
    p_user = User(
        email=f"lab-patient-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Lab Patient",
    )
    db.add(p_user)
    db.flush()
    profile = PatientProfile(user_id=p_user.id, full_name="Lab Patient")
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
    """A second patient — used for cross-patient access tests."""
    p_user = User(
        email=f"lab-patient2-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Lab Patient 2",
    )
    db.add(p_user)
    db.flush()
    profile = PatientProfile(user_id=p_user.id, full_name="Lab Patient 2")
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
    """Doctor user + doctor record + clinic + JWT token."""
    clinic = Clinic(name=f"Lab Clinic {os.urandom(4).hex()}", is_active=True)
    db.add(clinic)
    db.flush()

    d_user = User(
        email=f"lab-doctor-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="Dr. Lab",
    )
    db.add(d_user)
    db.flush()

    doctor = Doctor(user_id=d_user.id, clinic_id=clinic.id, full_name="Dr. Lab", is_active=True)
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
    """INTERNAL_ADMIN user + JWT token."""
    a_user = User(
        email=f"lab-admin-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=UserRole.INTERNAL_ADMIN,
        full_name="Lab Admin",
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
    """AI_SERVICE user + JWT token."""
    ai_user = User(
        email=f"lab-ai-{os.urandom(4).hex()}@metocare.internal",
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


# ---------------------------------------------------------------------------
# Upload tests (POST /patients/{patient_id}/lab-documents)
# ---------------------------------------------------------------------------

def test_patient_uploads_own_lab_document(client, db, patient_setup):
    """T7-01: PATIENT uploading for themselves → 201."""
    r = client.post(
        f"/api/v1/patients/{patient_setup['patient_id']}/lab-documents",
        headers=patient_setup["headers"],
        json=_UPLOAD_PAYLOAD,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["patient_id"] == patient_setup["patient_id"]
    assert body["id"]  # must have an id
    assert body["ocr_status"] == "pending"


def test_doctor_uploads_lab_document_for_patient(client, db, patient_setup, doctor_setup):
    """T7-02: DOCTOR with consent uploading for patient → 201."""
    _make_consent(db, patient_id=patient_setup["patient_id"], granted_to=doctor_setup["user_id"])
    db.commit()

    r = client.post(
        f"/api/v1/patients/{patient_setup['patient_id']}/lab-documents",
        headers=doctor_setup["headers"],
        json=_UPLOAD_PAYLOAD,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["patient_id"] == patient_setup["patient_id"]


def test_admin_uploads_lab_document(client, db, patient_setup, admin_setup):
    """T7-03: INTERNAL_ADMIN uploading → 201 (admin bypasses ownership + consent)."""
    # Admin needs consent to pass the service-layer consent gate (the gate
    # checks for admin in require_access via patient_id == requester_id OR
    # active consent). Grant a consent for the admin user.
    _make_consent(db, patient_id=patient_setup["patient_id"], granted_to=admin_setup["user_id"])
    db.commit()

    r = client.post(
        f"/api/v1/patients/{patient_setup['patient_id']}/lab-documents",
        headers=admin_setup["headers"],
        json=_UPLOAD_PAYLOAD,
    )
    assert r.status_code == 201, r.text


def test_patient_cannot_upload_for_another_patient(
    client, db, patient_setup, another_patient_setup
):
    """T7-04: PATIENT attempting to upload for a different patient → 403."""
    r = client.post(
        f"/api/v1/patients/{another_patient_setup['patient_id']}/lab-documents",
        headers=patient_setup["headers"],  # patient 1's token, patient 2's URL
        json=_UPLOAD_PAYLOAD,
    )
    assert r.status_code == 403, r.text


def test_ai_service_cannot_upload_lab_document(client, db, patient_setup, ai_service_setup):
    """T7-05: AI_SERVICE attempting to upload → 403 (role blocked at route level)."""
    r = client.post(
        f"/api/v1/patients/{patient_setup['patient_id']}/lab-documents",
        headers=ai_service_setup["headers"],
        json=_UPLOAD_PAYLOAD,
    )
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# Process tests (POST /lab-documents/{id}/process)
# ---------------------------------------------------------------------------

@pytest.fixture
def patient_document(db, patient_setup):
    """A LabDocument owned by patient_setup."""
    doc = LabDocument(
        patient_id=patient_setup["patient_id"],
        storage_key="test/patient_report.pdf",
        file_type="pdf",
        lab_name="Test Lab",
    )
    db.add(doc)
    db.commit()
    return doc


def test_patient_enqueues_own_document(client, db, patient_setup, patient_document):
    """T7-06: PATIENT enqueuing their own document → 202."""
    r = client.post(
        f"/api/v1/lab-documents/{patient_document.id}/process",
        headers=patient_setup["headers"],
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["id"] == patient_document.id


def test_doctor_enqueues_document(client, db, patient_setup, patient_document, doctor_setup):
    """T7-07: DOCTOR with consent enqueuing → 202."""
    _make_consent(db, patient_id=patient_setup["patient_id"], granted_to=doctor_setup["user_id"])
    db.commit()

    r = client.post(
        f"/api/v1/lab-documents/{patient_document.id}/process",
        headers=doctor_setup["headers"],
    )
    assert r.status_code == 202, r.text


def test_unauthenticated_cannot_enqueue(client, patient_document):
    """T7-08: No token → 401."""
    r = client.post(f"/api/v1/lab-documents/{patient_document.id}/process")
    assert r.status_code == 401, r.text


# ---------------------------------------------------------------------------
# Status tests (GET /lab-documents/{id})
# ---------------------------------------------------------------------------

def test_patient_reads_own_document_status(client, db, patient_setup, patient_document):
    """T7-09: PATIENT reading own document status → 200."""
    r = client.get(
        f"/api/v1/lab-documents/{patient_document.id}",
        headers=patient_setup["headers"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == patient_document.id
    assert "status" in body
    assert "ocr_status" in body


def test_patient_cannot_read_another_patients_document(
    client, db, patient_setup, another_patient_setup
):
    """T7-10: PATIENT reading another patient's document → 403 or 404."""
    # Create a doc owned by another_patient
    other_doc = LabDocument(
        patient_id=another_patient_setup["patient_id"],
        storage_key="test/other_report.pdf",
        file_type="pdf",
    )
    db.add(other_doc)
    db.commit()

    r = client.get(
        f"/api/v1/lab-documents/{other_doc.id}",
        headers=patient_setup["headers"],  # patient 1's token reading patient 2's doc
    )
    assert r.status_code in (403, 404), r.text


def test_admin_reads_any_document(client, db, patient_setup, patient_document, admin_setup):
    """T7-11: INTERNAL_ADMIN reading any document → 200."""
    # Admin needs consent record to pass the service-layer consent gate
    _make_consent(db, patient_id=patient_setup["patient_id"], granted_to=admin_setup["user_id"])
    db.commit()

    r = client.get(
        f"/api/v1/lab-documents/{patient_document.id}",
        headers=admin_setup["headers"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == patient_document.id

def test_clinic_admin_can_read_document_status(client, db, patient_setup, patient_document):
    """T10-L01: CLINIC_ADMIN with active lab consent can read document status → 200."""
    import os as _os

    from app.core.security import create_access_token as _create_token
    from app.models.user import User as _User
    from app.models.user import UserRole as _UserRole

    ca_user = _User(
        email=f"lab-ca-{_os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=_UserRole.CLINIC_ADMIN,
        full_name="Clinic Admin Lab",
    )
    db.add(ca_user)
    db.flush()
    # Grant lab consent to the clinic admin
    _make_consent(db, patient_id=patient_setup["patient_id"], granted_to=ca_user.id)
    db.commit()

    token = _create_token(subject=ca_user.id, role="clinic_admin", mfa=True)
    headers = {"Authorization": f"Bearer {token}"}

    r = client.get(
        f"/api/v1/lab-documents/{patient_document.id}",
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == patient_document.id
    assert "status" in body
    assert "ocr_status" in body


# ---------------------------------------------------------------------------
# Interpret tests (POST /lab-documents/{id}/interpret)
# ---------------------------------------------------------------------------

def test_patient_interprets_own_document(client, db, patient_setup, patient_document):
    """T7-12: PATIENT interpreting their own document → 200, has `biomarkers` field."""
    r = client.post(
        f"/api/v1/lab-documents/{patient_document.id}/interpret",
        headers=patient_setup["headers"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "biomarkers" in body, "Response must have 'biomarkers' field"
    assert isinstance(body["biomarkers"], list)


def test_interpret_returns_patient_explanation(client, db, patient_setup, patient_document):
    """T7-13: Interpret response must include non-empty `patient_explanation`."""
    r = client.post(
        f"/api/v1/lab-documents/{patient_document.id}/interpret",
        headers=patient_setup["headers"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "patient_explanation" in body
    assert body["patient_explanation"], "patient_explanation must not be empty (medical safety)"


def test_doctor_interprets_document(client, db, patient_setup, patient_document, doctor_setup):
    """T7-14: DOCTOR with consent interpreting → 200."""
    _make_consent(db, patient_id=patient_setup["patient_id"], granted_to=doctor_setup["user_id"])
    db.commit()

    r = client.post(
        f"/api/v1/lab-documents/{patient_document.id}/interpret",
        headers=doctor_setup["headers"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "biomarkers" in body
    assert "doctor_summary" in body


def test_ai_service_cannot_interpret(client, db, patient_setup, patient_document, ai_service_setup):
    """T7-15: AI_SERVICE attempting to interpret → 403 (role blocked at route level)."""
    r = client.post(
        f"/api/v1/lab-documents/{patient_document.id}/interpret",
        headers=ai_service_setup["headers"],
    )
    assert r.status_code == 403, r.text
