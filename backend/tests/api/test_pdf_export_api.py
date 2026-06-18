"""T24 API tests — PDF Report Export (7 tests).

Endpoint tested:
  GET /api/v1/patients/{patient_id}/summary.pdf

Test cases:
  1.  test_doctor_with_consent_gets_pdf_200          — 200, content-type application/pdf
  2.  test_pdf_body_starts_with_pdf_header           — body starts with b"%PDF"
  3.  test_pdf_content_disposition_header            — Content-Disposition attachment present
  4.  test_patient_cannot_export_pdf                 — 403
  5.  test_ai_service_cannot_export_pdf              — 403
  6.  test_admin_gets_pdf_without_consent            — 200, application/pdf
  7.  test_unauthenticated_cannot_export_pdf         — 401

Note: ``generate_patient_summary_pdf`` is mocked to return ``b"%PDF-1.4 test"``
      so tests exercise RBAC and routing, not the reportlab rendering path.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from app.core.security import create_access_token
from app.models.governance import Consent
from app.models.patient import PatientProfile
from app.models.user import User, UserRole
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# URL helper
# ---------------------------------------------------------------------------

_PDF_MOCK_BYTES = b"%PDF-1.4 test"


def _pdf_url(patient_id: str) -> str:
    return f"/api/v1/patients/{patient_id}/summary.pdf"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def doctor_user(db):
    """DOCTOR user + JWT."""
    user = User(
        email=f"t24-doctor-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="T24 Doctor",
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
def patient_user(db):
    """PATIENT user + PatientProfile + JWT."""
    user = User(
        email=f"t24-patient-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="T24 Patient",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="T24 Patient")
    db.add(profile)
    db.commit()
    token = create_access_token(subject=user.id, role="patient", mfa=True)
    return {
        "user_id": user.id,
        "patient_id": profile.id,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def ai_service_user(db):
    """AI_SERVICE user + JWT."""
    user = User(
        email=f"t24-ai-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.AI_SERVICE,
        full_name="T24 AI",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="ai_service", mfa=True)
    return {
        "user_id": user.id,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def admin_user(db):
    """INTERNAL_ADMIN user + JWT."""
    user = User(
        email=f"t24-admin-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.INTERNAL_ADMIN,
        full_name="T24 Admin",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="internal_admin", mfa=True)
    return {
        "user_id": user.id,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def consent_for_doctor(db, patient_user, doctor_user):
    """Grant doctor_user active consent (scope='profile') for patient_user."""
    consent = Consent(
        patient_id=patient_user["patient_id"],
        consent_type="data_sharing",
        data_scope="profile",
        granted_to=doctor_user["user_id"],
    )
    db.add(consent)
    db.commit()
    return consent


# ---------------------------------------------------------------------------
# 1. DOCTOR with consent -> 200, content-type application/pdf
# ---------------------------------------------------------------------------

def test_doctor_with_consent_gets_pdf_200(
    client: TestClient, patient_user, doctor_user, consent_for_doctor
):
    """DOCTOR with active consent receives 200 with content-type application/pdf."""
    with patch(
        "app.services.pdf_report.generate_patient_summary_pdf",
        return_value=_PDF_MOCK_BYTES,
    ):
        r = client.get(_pdf_url(patient_user["patient_id"]), headers=doctor_user["headers"])

    assert r.status_code == 200, r.text
    assert "application/pdf" in r.headers.get("content-type", ""), (
        f"Expected application/pdf, got: {r.headers.get('content-type')}"
    )


# ---------------------------------------------------------------------------
# 2. Response body starts with %PDF (valid PDF header)
# ---------------------------------------------------------------------------

def test_pdf_body_starts_with_pdf_header(
    client: TestClient, patient_user, doctor_user, consent_for_doctor
):
    """Response body must start with b'%PDF' -- a valid PDF file signature."""
    with patch(
        "app.services.pdf_report.generate_patient_summary_pdf",
        return_value=_PDF_MOCK_BYTES,
    ):
        r = client.get(_pdf_url(patient_user["patient_id"]), headers=doctor_user["headers"])

    assert r.status_code == 200, r.text
    assert r.content.startswith(b"%PDF"), (
        f"PDF body must start with %PDF; got: {r.content[:20]!r}"
    )


# ---------------------------------------------------------------------------
# 3. Content-Disposition header present with filename
# ---------------------------------------------------------------------------

def test_pdf_content_disposition_header(
    client: TestClient, patient_user, doctor_user, consent_for_doctor
):
    """Response must include Content-Disposition attachment with a filename."""
    with patch(
        "app.services.pdf_report.generate_patient_summary_pdf",
        return_value=_PDF_MOCK_BYTES,
    ):
        r = client.get(_pdf_url(patient_user["patient_id"]), headers=doctor_user["headers"])

    assert r.status_code == 200, r.text
    content_disposition = r.headers.get("content-disposition", "")
    assert "attachment" in content_disposition, (
        f"Expected 'attachment' in Content-Disposition; got: {content_disposition!r}"
    )
    assert "filename=" in content_disposition, (
        f"Expected 'filename=' in Content-Disposition; got: {content_disposition!r}"
    )
    assert patient_user["patient_id"] in content_disposition, (
        f"Patient ID must appear in filename; got: {content_disposition!r}"
    )


# ---------------------------------------------------------------------------
# 4. PATIENT -> 403
# ---------------------------------------------------------------------------

def test_patient_cannot_export_pdf(client: TestClient, patient_user):
    """PATIENT role must receive 403 on the PDF export endpoint."""
    r = client.get(_pdf_url(patient_user["patient_id"]), headers=patient_user["headers"])
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# 5. AI_SERVICE -> 403
# ---------------------------------------------------------------------------

def test_ai_service_cannot_export_pdf(
    client: TestClient, patient_user, ai_service_user
):
    """AI_SERVICE role must receive 403 on the PDF export endpoint."""
    r = client.get(_pdf_url(patient_user["patient_id"]), headers=ai_service_user["headers"])
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# 6. ADMIN -> 200, application/pdf (no consent required)
# ---------------------------------------------------------------------------

def test_admin_gets_pdf_without_consent(
    client: TestClient, patient_user, admin_user
):
    """INTERNAL_ADMIN must receive 200 with PDF content-type, no consent needed."""
    with patch(
        "app.services.pdf_report.generate_patient_summary_pdf",
        return_value=_PDF_MOCK_BYTES,
    ):
        r = client.get(_pdf_url(patient_user["patient_id"]), headers=admin_user["headers"])

    assert r.status_code == 200, r.text
    assert "application/pdf" in r.headers.get("content-type", ""), (
        f"Expected application/pdf, got: {r.headers.get('content-type')}"
    )


# ---------------------------------------------------------------------------
# 7. Unauthenticated -> 401
# ---------------------------------------------------------------------------

def test_unauthenticated_cannot_export_pdf(client: TestClient, patient_user):
    """Requests without a bearer token must receive 401."""
    r = client.get(_pdf_url(patient_user["patient_id"]))
    assert r.status_code == 401, r.text
