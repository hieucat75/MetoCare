"""Consultation payment service (Doctor Marketplace MVP, T10).

Mock payment ("Thanh toán thử") for the MVP — no real gateway. Fee split is a
pure function (``compute_fees``); the provider is abstracted so a real gateway
can be swapped in later without touching callers.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.config import compute_fees  # re-exported for callers/tests
from app.models.consultation import (
    Consultation,
    ConsultationPayment,
    ConsultationStatus,
    PaymentProvider,
    PaymentStatus,
)
from app.services import audit, consultation_access

__all__ = ["compute_fees", "get_payment", "pay_mock", "refund"]

# Consultation statuses from which a mock payment may be taken.
_PAYABLE_STATUSES = frozenset({ConsultationStatus.REQUESTED, ConsultationStatus.CONFIRMED})


def get_payment(db: Session, consultation_id: str) -> ConsultationPayment | None:
    return db.execute(
        select(ConsultationPayment).where(
            ConsultationPayment.consultation_id == consultation_id
        )
    ).scalar_one_or_none()


def pay_mock(
    db: Session,
    consultation: Consultation,
    *,
    patient_profile_id: str,
    provider: str = PaymentProvider.MOCK,
) -> ConsultationPayment:
    """Mark a consultation paid via the mock provider.

    - Enforces patient ownership.
    - Requires the consultation to be in a payable state and currently UNPAID.
    - Flips payment → PAID, consultation → PAID, creates an active access grant,
      and audits ``payment_status_change``.
    """
    if consultation.patient_id != patient_profile_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You may only pay for your own consultation.",
        )
    if consultation.status not in _PAYABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Consultation in status '{consultation.status}' cannot be paid.",
        )

    payment = get_payment(db, consultation.id)
    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment record not found for this consultation.",
        )
    if payment.payment_status == PaymentStatus.PAID:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Consultation is already paid.",
        )

    now = utcnow()
    platform_fee, doctor_payout = compute_fees(consultation.consultation_price)
    payment.consultation_price = consultation.consultation_price
    payment.platform_fee = platform_fee
    payment.doctor_payout = doctor_payout
    payment.payment_status = PaymentStatus.PAID
    payment.payment_provider = provider
    payment.provider_ref = f"mock-{consultation.id}"
    payment.paid_at = now
    db.add(payment)

    consultation.status = ConsultationStatus.PAID
    consultation.paid_at = now
    db.add(consultation)

    # Paying unlocks scoped, audited read access for the doctor.
    consultation_access.create_grant(db, consultation)

    audit.record(
        db,
        actor_type="patient",
        actor_id=consultation.patient_id,
        action="payment_status_change",
        resource_type="consultation_payment",
        resource_id=payment.id,
        severity="info",
    )
    db.commit()
    db.refresh(payment)
    return payment


def refund(db: Session, consultation: Consultation) -> ConsultationPayment | None:
    """Refund a paid consultation (used on cancel-after-paid). Idempotent-ish.

    Returns the payment (or None if there is no paid payment to refund). Does not
    commit — the calling transition function commits the whole cancel.
    """
    payment = get_payment(db, consultation.id)
    if payment is None or payment.payment_status != PaymentStatus.PAID:
        return payment
    payment.payment_status = PaymentStatus.REFUNDED
    payment.refunded_at = utcnow()
    db.add(payment)
    audit.record(
        db,
        actor_type="system",
        actor_id=None,
        action="payment_status_change",
        resource_type="consultation_payment",
        resource_id=payment.id,
        severity="warning",
    )
    db.flush()
    return payment
