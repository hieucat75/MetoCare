"""T10 — Consultation payment tests (fees, mock-pay, refund, provider abstraction)."""

from __future__ import annotations

import pytest
from app.core.config import compute_fees
from app.models.consultation import (
    ConsultationStatus,
    PaymentProvider,
    PaymentStatus,
)
from app.services import consultation as svc
from app.services import consultation_payment
from fastapi import HTTPException

from tests.consultation_factories import CONSENT_ALL_CATEGORIES, create_doctor, create_patient


def _consult(db, fee=200000.0):
    doctor = create_doctor(db, fee=fee)
    _u, profile = create_patient(db)
    c = svc.create_consultation(
        db, patient_id=profile.id, doctor_id=doctor.id, data_consent_accepted=True,
        consent_categories=CONSENT_ALL_CATEGORIES
    )
    return doctor, profile, c


def test_compute_fees_default_rate():
    platform_fee, payout = compute_fees(200000.0)
    assert platform_fee == 30000.0  # 15%
    assert payout == 170000.0
    assert platform_fee + payout == 200000.0


def test_compute_fees_zero_price():
    assert compute_fees(0.0) == (0.0, 0.0)


def test_pay_mock_marks_paid_and_splits_fees(db):
    doctor, profile, c = _consult(db, fee=200000.0)
    payment = consultation_payment.pay_mock(db, c, patient_profile_id=profile.id)
    assert payment.payment_status == PaymentStatus.PAID
    assert payment.payment_provider == PaymentProvider.MOCK
    assert payment.platform_fee == 30000.0
    assert payment.doctor_payout == 170000.0
    assert payment.paid_at is not None
    db.refresh(c)
    assert c.status == ConsultationStatus.PAID


def test_pay_mock_rejects_non_owner(db):
    doctor, profile, c = _consult(db)
    _u2, other = create_patient(db)
    with pytest.raises(HTTPException) as exc:
        consultation_payment.pay_mock(db, c, patient_profile_id=other.id)
    assert exc.value.status_code == 403


def test_pay_mock_double_pay_conflict(db):
    doctor, profile, c = _consult(db)
    consultation_payment.pay_mock(db, c, patient_profile_id=profile.id)
    db.refresh(c)
    with pytest.raises(HTTPException) as exc:
        consultation_payment.pay_mock(db, c, patient_profile_id=profile.id)
    assert exc.value.status_code == 409


def test_refund_on_cancel_after_paid(db):
    doctor, profile, c = _consult(db)
    consultation_payment.pay_mock(db, c, patient_profile_id=profile.id)
    db.refresh(c)
    svc.cancel(
        db,
        c.id,
        actor_user_id="x",
        actor_role="patient",
        patient_profile_id=profile.id,
        reason="changed mind",
    )
    payment = consultation_payment.get_payment(db, c.id)
    assert payment.payment_status == PaymentStatus.REFUNDED
    assert payment.refunded_at is not None


def test_provider_abstraction_allows_alternate_provider(db):
    doctor, profile, c = _consult(db)
    payment = consultation_payment.pay_mock(
        db, c, patient_profile_id=profile.id, provider=PaymentProvider.MANUAL
    )
    assert payment.payment_provider == PaymentProvider.MANUAL
