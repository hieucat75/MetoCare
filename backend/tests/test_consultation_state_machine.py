"""T10 — Consultation aggregate + state machine tests."""

from __future__ import annotations

import pytest
from app.models.consultation import (
    ConsultationStatus,
    DoctorVerificationStatus,
    PaymentStatus,
)
from app.services import consultation as svc
from app.services import consultation_payment
from fastapi import HTTPException

from tests.consultation_factories import create_doctor, create_patient


def _make(db, **doc_kwargs):
    doctor = create_doctor(db, **doc_kwargs)
    _user, profile = create_patient(db)
    return doctor, profile


def test_create_requires_consent(db):
    doctor, profile = _make(db)
    with pytest.raises(HTTPException) as exc:
        svc.create_consultation(
            db,
            patient_id=profile.id,
            doctor_id=doctor.id,
            data_consent_accepted=False,
        )
    assert exc.value.status_code == 400


def test_create_rejects_unverified_doctor(db):
    doctor, profile = _make(db, verification_status=DoctorVerificationStatus.PENDING_VERIFICATION)
    with pytest.raises(HTTPException) as exc:
        svc.create_consultation(
            db, patient_id=profile.id, doctor_id=doctor.id, data_consent_accepted=True
        )
    assert exc.value.status_code == 403


def test_create_rejects_suspended_doctor(db):
    doctor, profile = _make(db, verification_status=DoctorVerificationStatus.SUSPENDED)
    with pytest.raises(HTTPException) as exc:
        svc.create_consultation(
            db, patient_id=profile.id, doctor_id=doctor.id, data_consent_accepted=True
        )
    assert exc.value.status_code == 403


def test_create_snapshots_price_and_creates_unpaid_payment(db):
    doctor, profile = _make(db, fee=250000.0)
    c = svc.create_consultation(
        db, patient_id=profile.id, doctor_id=doctor.id, data_consent_accepted=True
    )
    assert c.status == ConsultationStatus.REQUESTED
    assert c.consultation_price == 250000.0
    assert c.data_consent_accepted is True and c.data_consent_accepted_at is not None
    payment = consultation_payment.get_payment(db, c.id)
    assert payment is not None
    assert payment.payment_status == PaymentStatus.UNPAID
    # Snapshot is immutable: later fee change does not alter the consultation price.
    doctor.consultation_fee = 999999.0
    db.commit()
    db.refresh(c)
    assert c.consultation_price == 250000.0


def test_confirm_then_start_requires_paid(db):
    doctor, profile = _make(db)
    c = svc.create_consultation(
        db, patient_id=profile.id, doctor_id=doctor.id, data_consent_accepted=True
    )
    svc.confirm(db, c.id, doctor_user_id=doctor.user_id)
    db.refresh(c)
    assert c.status == ConsultationStatus.CONFIRMED
    # start before paid → 409
    with pytest.raises(HTTPException) as exc:
        svc.start(db, c.id, doctor_user_id=doctor.user_id)
    assert exc.value.status_code == 409


def test_full_happy_path_to_completed(db):
    doctor, profile = _make(db)
    c = svc.create_consultation(
        db, patient_id=profile.id, doctor_id=doctor.id, data_consent_accepted=True
    )
    consultation_payment.pay_mock(db, c, patient_profile_id=profile.id)
    db.refresh(c)
    assert c.status == ConsultationStatus.PAID
    svc.start(db, c.id, doctor_user_id=doctor.user_id)
    svc.complete(db, c.id, doctor_user_id=doctor.user_id)
    db.refresh(c)
    assert c.status == ConsultationStatus.COMPLETED
    assert c.completed_at is not None


def test_terminal_status_rejects_further_transitions(db):
    doctor, profile = _make(db)
    c = svc.create_consultation(
        db, patient_id=profile.id, doctor_id=doctor.id, data_consent_accepted=True
    )
    svc.cancel(db, c.id, actor_user_id=doctor.user_id, actor_role="doctor")
    db.refresh(c)
    assert c.status == ConsultationStatus.CANCELLED
    with pytest.raises(HTTPException) as exc:
        svc.confirm(db, c.id, doctor_user_id=doctor.user_id)
    assert exc.value.status_code == 409


def test_confirm_rejects_non_owning_doctor(db):
    doctor, profile = _make(db)
    other = create_doctor(db)
    c = svc.create_consultation(
        db, patient_id=profile.id, doctor_id=doctor.id, data_consent_accepted=True
    )
    with pytest.raises(HTTPException) as exc:
        svc.confirm(db, c.id, doctor_user_id=other.user_id)
    assert exc.value.status_code == 403


def test_patient_cannot_cancel_others_consultation(db):
    doctor, profile = _make(db)
    _u2, other_profile = create_patient(db)
    c = svc.create_consultation(
        db, patient_id=profile.id, doctor_id=doctor.id, data_consent_accepted=True
    )
    with pytest.raises(HTTPException) as exc:
        svc.cancel(
            db,
            c.id,
            actor_user_id="whoever",
            actor_role="patient",
            patient_profile_id=other_profile.id,
        )
    assert exc.value.status_code == 403


def test_create_endpoint_requires_patient_role(db, client):
    doctor, profile = _make(db)
    from tests.consultation_factories import headers

    # A doctor token cannot create a consultation.
    resp = client.post(
        "/api/v1/consultations",
        json={"doctor_id": doctor.id, "data_consent_accepted": True},
        headers=headers(doctor.user_id, "doctor"),
    )
    assert resp.status_code == 403
