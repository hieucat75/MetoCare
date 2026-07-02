"""Doctor verification service — admin workflow (T10).

Admins approve/reject/suspend doctors. ``verification_status`` is the source of
truth; the legacy ``is_verified`` boolean is mirrored on every transition.
Only VERIFIED doctors appear in the marketplace and can receive consultations.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.care import Doctor
from app.models.consultation import DoctorVerificationStatus
from app.services import audit


def list_by_status(db: Session, status_filter: str | None = None) -> list[Doctor]:
    """List doctors, optionally filtered by verification_status."""
    stmt = select(Doctor)
    if status_filter:
        stmt = stmt.where(Doctor.verification_status == status_filter)
    stmt = stmt.order_by(Doctor.created_at.desc())
    return list(db.execute(stmt).scalars())


def list_pending(db: Session) -> list[Doctor]:
    return list_by_status(db, DoctorVerificationStatus.PENDING_VERIFICATION)


def _get_doctor_or_404(db: Session, doctor_id: str) -> Doctor:
    doctor = db.get(Doctor, doctor_id)
    if doctor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found.")
    return doctor


def _set_status(
    db: Session,
    doctor_id: str,
    *,
    new_status: str,
    is_verified: bool,
    actor_id: str,
) -> Doctor:
    doctor = _get_doctor_or_404(db, doctor_id)
    doctor.verification_status = new_status
    doctor.is_verified = is_verified  # keep legacy mirror in sync
    db.add(doctor)
    audit.record(
        db,
        actor_type="admin",
        actor_id=actor_id,
        action="doctor_profile_approval",
        resource_type="doctor",
        resource_id=doctor_id,
        severity="warning",
    )
    db.commit()
    db.refresh(doctor)
    return doctor


def approve(db: Session, doctor_id: str, *, actor_id: str) -> Doctor:
    return _set_status(
        db,
        doctor_id,
        new_status=DoctorVerificationStatus.VERIFIED,
        is_verified=True,
        actor_id=actor_id,
    )


def reject(db: Session, doctor_id: str, *, actor_id: str) -> Doctor:
    return _set_status(
        db,
        doctor_id,
        new_status=DoctorVerificationStatus.REJECTED,
        is_verified=False,
        actor_id=actor_id,
    )


def suspend(db: Session, doctor_id: str, *, actor_id: str) -> Doctor:
    return _set_status(
        db,
        doctor_id,
        new_status=DoctorVerificationStatus.SUSPENDED,
        is_verified=False,
        actor_id=actor_id,
    )
