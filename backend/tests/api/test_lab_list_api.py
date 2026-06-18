"""T18A — Lab Documents List API tests.

Covers GET /patients/{patient_id}/lab-documents (new endpoint).
"""

from __future__ import annotations

import datetime as dt
import os

import pytest
from app.core.clock import utcnow
from app.core.security import create_access_token
from app.models.clinical import LabDocument
from app.models.governance import Consent
from app.models.patient import PatientProfile
from app.models.user import User, UserRole


def _make_lab_consent(db, *, patient_id, granted_to):
    c = Consent(
        patient_id=patient_id,
        consent_type="lab_access",
        data_scope="lab",
        granted_to=granted_to,
        valid_from=utcnow() - dt.timedelta(hours=1),
        valid_until=utcnow() + dt.timedelta(hours=24),
    )
    db.add(c)
    db.commit()
    return c


def _make_docs(db, *, patient_id, n=1):
    docs = []
    for i in range(n):
        doc = LabDocument(
            patient_id=patient_id,
            storage_key=f"test/rpt_{os.urandom(4).hex()}_{i}.pdf",
            file_type="pdf",
            lab_name=f"Lab {i}",
        )
        db.add(doc)
        docs.append(doc)
    db.commit()
    return docs


@pytest.fixture
def patient_setup(db):
    user = User(
        email=f"lablist-p-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Lab List Patient",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="Lab List Patient")
    db.add(profile)
    db.flush()
    _make_lab_consent(db, patient_id=profile.id, granted_to=user.id)
    token = create_access_token(subject=user.id, role="patient")
    return {
        "user_id": user.id,
        "patient_id": profile.id,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def other_patient_setup(db):
    user = User(
        email=f"lablist-o-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Other Lab Patient",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="Other Lab Patient")
    db.add(profile)
    db.flush()
    _make_lab_consent(db, patient_id=profile.id, granted_to=user.id)
    token = create_access_token(subject=user.id, role="patient")
    return {
        "user_id": user.id,
        "patient_id": profile.id,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def doctor_setup(db):
    user = User(
        email=f"lablist-d-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="Dr. LabList",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="doctor", mfa=True)
    return {"user_id": user.id, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def admin_setup(db):
    user = User(
        email=f"lablist-a-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=UserRole.INTERNAL_ADMIN,
        full_name="Admin LabList",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="internal_admin", mfa=True)
    return {"user_id": user.id, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def patient_docs(db, patient_setup):
    return _make_docs(db, patient_id=patient_setup["patient_id"], n=3)


def test_patient_can_list_own_lab_documents(client, patient_setup, patient_docs):
    """T18A-LL01: Patient lists own lab docs -> 200 with results."""
    r = client.get(
        f"/api/v1/patients/{patient_setup['patient_id']}/lab-documents",
        headers=patient_setup["headers"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 3
    assert all("id" in item for item in body)


def test_patient_cannot_list_other_patients_lab_documents(
    client, patient_setup, other_patient_setup
):
    """T18A-LL02: Patient cannot access another patient's lab docs."""
    r = client.get(
        f"/api/v1/patients/{other_patient_setup['patient_id']}/lab-documents",
        headers=patient_setup["headers"],
    )
    assert r.status_code == 403, r.text


def test_doctor_with_consent_can_list_lab_documents(
    client, db, patient_setup, doctor_setup, patient_docs
):
    """T18A-LL03: Doctor with active lab consent can list patient's lab docs."""
    _make_lab_consent(
        db,
        patient_id=patient_setup["patient_id"],
        granted_to=doctor_setup["user_id"],
    )
    r = client.get(
        f"/api/v1/patients/{patient_setup['patient_id']}/lab-documents",
        headers=doctor_setup["headers"],
    )
    assert r.status_code == 200, r.text
    assert len(r.json()) == 3


def test_doctor_without_consent_cannot_list_lab_documents(
    client, patient_setup, doctor_setup
):
    """T18A-LL04: Doctor without consent gets 403."""
    r = client.get(
        f"/api/v1/patients/{patient_setup['patient_id']}/lab-documents",
        headers=doctor_setup["headers"],
    )
    assert r.status_code == 403, r.text


def test_admin_with_consent_can_list_lab_documents(
    client, db, patient_setup, admin_setup, patient_docs
):
    """T18A-LL05: Admin with consent can list any patient's lab docs.

    Note: the consent service requires an active consent even for admins.
    This mirrors the existing behavior of GET /lab-documents/{id} and
    POST /patients/{id}/lab-documents (see test_lab_api.py).
    """
    _make_lab_consent(
        db,
        patient_id=patient_setup["patient_id"],
        granted_to=admin_setup["user_id"],
    )
    r = client.get(
        f"/api/v1/patients/{patient_setup['patient_id']}/lab-documents",
        headers=admin_setup["headers"],
    )
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


def test_lab_list_pagination(client, patient_setup, patient_docs):
    """T18A-LL06: Pagination (limit/offset) works."""
    r = client.get(
        f"/api/v1/patients/{patient_setup['patient_id']}/lab-documents?limit=2&offset=0",
        headers=patient_setup["headers"],
    )
    assert r.status_code == 200, r.text
    assert len(r.json()) == 2

    r2 = client.get(
        f"/api/v1/patients/{patient_setup['patient_id']}/lab-documents?limit=2&offset=2",
        headers=patient_setup["headers"],
    )
    assert r2.status_code == 200, r2.text
    assert len(r2.json()) == 1


def test_unauthenticated_cannot_list_lab_documents(client, patient_setup):
    """T18A-LL07: No token returns 401."""
    r = client.get(
        f"/api/v1/patients/{patient_setup['patient_id']}/lab-documents"
    )
    assert r.status_code == 401, r.text


def test_lab_list_empty_returns_empty_list(client, patient_setup):
    """T18A-LL08: No documents returns empty list."""
    r = client.get(
        f"/api/v1/patients/{patient_setup['patient_id']}/lab-documents",
        headers=patient_setup["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json() == []
