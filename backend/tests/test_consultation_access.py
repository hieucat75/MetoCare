"""T10 — Consultation-scoped access tests.

Hard rules: no access before PAID; access after; revoked on end; every view
audited; scoped to consultation+patient (no cross-patient leak).
"""

from __future__ import annotations

import pytest
from app.models.governance import AuditLog
from app.services import consultation as svc
from app.services import consultation_access, consultation_payment
from fastapi import HTTPException
from sqlalchemy import select

from tests.consultation_factories import (
    CONSENT_ALL_CATEGORIES,
    create_doctor,
    create_patient,
    headers,
)


def _paid_consult(db):
    doctor = create_doctor(db)
    _u, profile = create_patient(db)
    c = svc.create_consultation(
        db, patient_id=profile.id, doctor_id=doctor.id, data_consent_accepted=True,
        consent_categories=CONSENT_ALL_CATEGORIES
    )
    return doctor, profile, c


def _view_audit_count(db, patient_id):
    return len(
        db.execute(
            select(AuditLog).where(
                AuditLog.action == "doctor_view_patient_data",
                AuditLog.resource_id == patient_id,
            )
        ).scalars().all()
    )


def test_no_access_before_paid(db):
    doctor, profile, c = _paid_consult(db)
    with pytest.raises(HTTPException) as exc:
        consultation_access.assert_doctor_can_view(db, doctor=doctor, consultation_id=c.id)
    assert exc.value.status_code == 403


def test_access_after_paid_and_audited(db):
    doctor, profile, c = _paid_consult(db)
    consultation_payment.pay_mock(db, c, patient_profile_id=profile.id)
    before = _view_audit_count(db, profile.id)
    consultation_access.assert_doctor_can_view(db, doctor=doctor, consultation_id=c.id)
    consultation_access.assert_doctor_can_view(db, doctor=doctor, consultation_id=c.id)
    # Every successful view is audited.
    assert _view_audit_count(db, profile.id) == before + 2


def test_access_revoked_on_complete(db):
    doctor, profile, c = _paid_consult(db)
    consultation_payment.pay_mock(db, c, patient_profile_id=profile.id)
    consultation_access.assert_doctor_can_view(db, doctor=doctor, consultation_id=c.id)
    svc.complete(db, c.id, doctor_user_id=doctor.user_id)
    with pytest.raises(HTTPException) as exc:
        consultation_access.assert_doctor_can_view(db, doctor=doctor, consultation_id=c.id)
    assert exc.value.status_code == 403


def test_access_revoked_on_cancel(db):
    doctor, profile, c = _paid_consult(db)
    consultation_payment.pay_mock(db, c, patient_profile_id=profile.id)
    svc.cancel(
        db, c.id, actor_user_id="x", actor_role="patient", patient_profile_id=profile.id
    )
    with pytest.raises(HTTPException) as exc:
        consultation_access.assert_doctor_can_view(db, doctor=doctor, consultation_id=c.id)
    assert exc.value.status_code == 403


def test_no_cross_consultation_leak(db):
    """A doctor with a grant on consultation A cannot read consultation B (other doctor)."""
    doctor_a, profile, c_a = _paid_consult(db)
    consultation_payment.pay_mock(db, c_a, patient_profile_id=profile.id)
    # Second doctor + their own paid consultation with a DIFFERENT patient.
    doctor_b, profile_b, c_b = _paid_consult(db)
    consultation_payment.pay_mock(db, c_b, patient_profile_id=profile_b.id)
    # doctor_a tries to view doctor_b's consultation → 403 (not the owning doctor).
    with pytest.raises(HTTPException) as exc:
        consultation_access.assert_doctor_can_view(db, doctor=doctor_a, consultation_id=c_b.id)
    assert exc.value.status_code == 403


def test_patient_summary_endpoint_scoped_and_revoked(db, client):
    doctor, profile, c = _paid_consult(db)
    consultation_payment.pay_mock(db, c, patient_profile_id=profile.id)
    doc_headers = headers(doctor.user_id, "doctor")
    url = f"/api/v1/consultations/{c.id}/patient-summary"
    # 200 while active
    assert client.get(url, headers=doc_headers).status_code == 200
    # Complete → grant revoked → 403
    svc.complete(db, c.id, doctor_user_id=doctor.user_id)
    assert client.get(url, headers=doc_headers).status_code == 403


def test_patient_summary_endpoint_rejects_patient_role(db, client):
    doctor, profile, c = _paid_consult(db)
    consultation_payment.pay_mock(db, c, patient_profile_id=profile.id)
    # Even the owning patient is rejected by the DOCTOR-only role gate.
    from app.models.patient import PatientProfile

    owner_id = db.get(PatientProfile, profile.id).user_id
    resp = client.get(
        f"/api/v1/consultations/{c.id}/patient-summary",
        headers=headers(owner_id, "patient"),
    )
    assert resp.status_code == 403
