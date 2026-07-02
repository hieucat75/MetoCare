"""Consultation aggregate + state machine (Doctor Marketplace MVP, T10).

Owns the consultation lifecycle. RBAC/ownership is enforced here (not in routes):
- create: patient-initiated, doctor must be VERIFIED (not SUSPENDED/inactive),
  data-sharing consent required, price snapshotted from the doctor.
- confirm/start/complete: doctor who owns the consultation only.
- cancel: patient (owner) or doctor (owner).

Doctor identity: a DOCTOR caller presents ``user.id``; we resolve their Doctor row
and require ``doctor.id == consultation.doctor_id``.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.config import get_settings
from app.models.consultation import (
    Consultation,
    ConsultationPayment,
    ConsultationStatus,
    ConsultationType,
    DoctorVerificationStatus,
    PaymentProvider,
    PaymentStatus,
)
from app.services import audit, consultation_access, consultation_payment
from app.services.doctor import get_doctor_by_user_id

# Allowed status transitions (source of truth for the state machine).
_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    ConsultationStatus.REQUESTED: frozenset(
        {ConsultationStatus.CONFIRMED, ConsultationStatus.PAID, ConsultationStatus.CANCELLED}
    ),
    ConsultationStatus.CONFIRMED: frozenset(
        {ConsultationStatus.PAID, ConsultationStatus.CANCELLED}
    ),
    ConsultationStatus.PAID: frozenset(
        {
            ConsultationStatus.IN_PROGRESS,
            ConsultationStatus.COMPLETED,
            ConsultationStatus.CANCELLED,
        }
    ),
    ConsultationStatus.IN_PROGRESS: frozenset(
        {ConsultationStatus.COMPLETED, ConsultationStatus.CANCELLED}
    ),
    ConsultationStatus.COMPLETED: frozenset(),
    ConsultationStatus.CANCELLED: frozenset(),
}


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------


def get_consultation_or_404(db: Session, consultation_id: str) -> Consultation:
    consultation = db.get(Consultation, consultation_id)
    if consultation is None or consultation.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Consultation not found."
        )
    return consultation


def _require_transition(current: str, target: str) -> None:
    if target not in _ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Invalid transition {current} → {target}.",
        )


def _resolve_owning_doctor(db: Session, consultation: Consultation, doctor_user_id: str):
    """Resolve the DOCTOR caller's Doctor row and require ownership of the consultation."""
    doctor = get_doctor_by_user_id(db, doctor_user_id)
    if doctor is None or doctor.id != consultation.doctor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this consultation.",
        )
    return doctor


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def create_consultation(
    db: Session,
    *,
    patient_id: str,
    doctor_id: str,
    consultation_type: str = ConsultationType.CHAT,
    data_consent_accepted: bool,
    chief_complaint: str | None = None,
    patient_note: str | None = None,
    booking_appointment_id: str | None = None,
) -> Consultation:
    """Create a REQUESTED consultation + UNPAID payment. Patient-initiated."""
    from app.models.care import Doctor

    if not data_consent_accepted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Data-sharing consent is required to request a consultation.",
        )

    doctor = db.get(Doctor, doctor_id)
    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found."
        )
    if doctor.verification_status != DoctorVerificationStatus.VERIFIED or not doctor.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This doctor is not available for consultations.",
        )

    now = utcnow()
    price = float(doctor.consultation_fee or 0.0)
    platform_fee, doctor_payout = consultation_payment.compute_fees(price)

    consultation = Consultation(
        patient_id=patient_id,
        doctor_id=doctor_id,
        consultation_type=consultation_type,
        status=ConsultationStatus.REQUESTED,
        consultation_price=price,
        data_consent_accepted=True,
        data_consent_accepted_at=now,
        chief_complaint=chief_complaint,
        patient_note=patient_note,
        booking_appointment_id=booking_appointment_id,
    )
    db.add(consultation)
    db.flush()

    payment = ConsultationPayment(
        consultation_id=consultation.id,
        consultation_price=price,
        platform_fee=platform_fee,
        doctor_payout=doctor_payout,
        currency=get_settings().marketplace_currency,
        payment_status=PaymentStatus.UNPAID,
        payment_provider=PaymentProvider.MOCK,
    )
    db.add(payment)

    audit.record(
        db,
        actor_type="patient",
        actor_id=patient_id,
        action="consultation_creation",
        resource_type="consultation",
        resource_id=consultation.id,
        severity="info",
    )
    db.commit()
    db.refresh(consultation)
    return consultation


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------


def confirm(db: Session, consultation_id: str, *, doctor_user_id: str) -> Consultation:
    consultation = get_consultation_or_404(db, consultation_id)
    _resolve_owning_doctor(db, consultation, doctor_user_id)
    _require_transition(consultation.status, ConsultationStatus.CONFIRMED)
    consultation.status = ConsultationStatus.CONFIRMED
    consultation.confirmed_at = utcnow()
    db.add(consultation)
    _audit_status(db, consultation, "doctor", consultation.doctor_id)
    db.commit()
    db.refresh(consultation)
    return consultation


def start(db: Session, consultation_id: str, *, doctor_user_id: str) -> Consultation:
    consultation = get_consultation_or_404(db, consultation_id)
    _resolve_owning_doctor(db, consultation, doctor_user_id)
    if consultation.status != ConsultationStatus.PAID:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Consultation must be PAID before it can start.",
        )
    _require_transition(consultation.status, ConsultationStatus.IN_PROGRESS)
    consultation.status = ConsultationStatus.IN_PROGRESS
    consultation.started_at = utcnow()
    db.add(consultation)
    _audit_status(db, consultation, "doctor", consultation.doctor_id)
    db.commit()
    db.refresh(consultation)
    return consultation


def complete(db: Session, consultation_id: str, *, doctor_user_id: str) -> Consultation:
    consultation = get_consultation_or_404(db, consultation_id)
    _resolve_owning_doctor(db, consultation, doctor_user_id)
    _require_transition(consultation.status, ConsultationStatus.COMPLETED)
    consultation.status = ConsultationStatus.COMPLETED
    consultation.completed_at = utcnow()
    db.add(consultation)
    # Access revoked on completion — subsequent summary reads must 403.
    consultation_access.revoke_on_end(db, consultation)
    _audit_status(db, consultation, "doctor", consultation.doctor_id)
    db.commit()
    db.refresh(consultation)
    return consultation


def cancel(
    db: Session,
    consultation_id: str,
    *,
    actor_user_id: str,
    actor_role: str,
    patient_profile_id: str | None = None,
    reason: str | None = None,
) -> Consultation:
    consultation = get_consultation_or_404(db, consultation_id)

    role = (actor_role or "").lower()
    actor_type = "system"
    actor_id: str | None = None
    if role == "doctor":
        _resolve_owning_doctor(db, consultation, actor_user_id)
        actor_type, actor_id = "doctor", consultation.doctor_id
    elif role == "patient":
        if patient_profile_id is None or consultation.patient_id != patient_profile_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You may only cancel your own consultation.",
            )
        actor_type, actor_id = "patient", consultation.patient_id
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{actor_role}' cannot cancel consultations.",
        )

    _require_transition(consultation.status, ConsultationStatus.CANCELLED)

    was_paid = consultation.status == ConsultationStatus.PAID or (
        consultation.paid_at is not None
    )
    consultation.status = ConsultationStatus.CANCELLED
    consultation.cancelled_at = utcnow()
    consultation.cancel_reason = reason
    db.add(consultation)

    # Refund if money had been taken; revoke any active access grant.
    if was_paid:
        consultation_payment.refund(db, consultation)
    consultation_access.revoke_on_end(db, consultation)

    audit.record(
        db,
        actor_type=actor_type,
        actor_id=actor_id,
        action="consultation_cancelled",
        resource_type="consultation",
        resource_id=consultation.id,
        severity="warning",
    )
    db.commit()
    db.refresh(consultation)
    return consultation


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def list_patient_consultations(db: Session, patient_id: str) -> list[Consultation]:
    rows = db.execute(
        select(Consultation)
        .where(Consultation.patient_id == patient_id, Consultation.deleted_at.is_(None))
        .order_by(Consultation.created_at.desc())
    ).scalars()
    return list(rows)


def list_doctor_consultations(db: Session, doctor_id: str) -> list[Consultation]:
    rows = db.execute(
        select(Consultation)
        .where(Consultation.doctor_id == doctor_id, Consultation.deleted_at.is_(None))
        .order_by(Consultation.created_at.desc())
    ).scalars()
    return list(rows)


def _audit_status(
    db: Session, consultation: Consultation, actor_type: str, actor_id: str | None
) -> None:
    audit.record(
        db,
        actor_type=actor_type,
        actor_id=actor_id,
        action="consultation_status_change",
        resource_type="consultation",
        resource_id=consultation.id,
        severity="info",
    )
