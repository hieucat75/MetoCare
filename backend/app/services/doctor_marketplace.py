"""Doctor marketplace service (T10).

Browse/detail for patients (VERIFIED doctors only) and self-service marketplace
profile editing + verification submission for doctors.
"""

from __future__ import annotations

import datetime as dt

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.models.availability import DoctorAvailability
from app.models.care import Doctor
from app.models.consultation import DoctorVerificationStatus
from app.services import audit

# Fields a doctor may self-edit on their marketplace listing.
_EDITABLE_FIELDS = frozenset(
    {
        "full_name",
        "bio",
        "avatar_url",
        "consultation_fee",
        "specialty",
        "years_experience",
        "languages",
        "hospital_name",
        "consultation_methods",
    }
)


def browse_doctors(
    db: Session,
    *,
    specialty: str | None = None,
    name: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    method: str | None = None,
) -> list[Doctor]:
    """Return VERIFIED, active doctors matching the given filters."""
    stmt = select(Doctor).where(
        Doctor.verification_status == DoctorVerificationStatus.VERIFIED,
        Doctor.is_active.is_(True),
    )
    if specialty:
        stmt = stmt.where(Doctor.specialty == specialty)
    if name:
        stmt = stmt.where(Doctor.full_name.ilike(f"%{name}%"))
    if min_price is not None:
        stmt = stmt.where(Doctor.consultation_fee >= min_price)
    if max_price is not None:
        stmt = stmt.where(Doctor.consultation_fee <= max_price)
    if method:
        stmt = stmt.where(Doctor.consultation_methods.ilike(f"%{method}%"))
    stmt = stmt.order_by(Doctor.rating_avg.desc(), Doctor.full_name.asc())
    return list(db.execute(stmt).scalars())


def get_doctor_detail(db: Session, doctor_id: str) -> tuple[Doctor, dt.datetime | None]:
    """Return a VERIFIED doctor + their next available booking slot (or None)."""
    doctor = db.get(Doctor, doctor_id)
    if (
        doctor is None
        or doctor.verification_status != DoctorVerificationStatus.VERIFIED
        or not doctor.is_active
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found.")
    next_available = _next_available_slot(db, doctor)
    return doctor, next_available


def _next_available_slot(db: Session, doctor: Doctor) -> dt.datetime | None:
    """Earliest future, un-booked availability slot for this doctor (via user_id)."""
    if not doctor.user_id:
        return None
    now = utcnow().replace(tzinfo=None)  # DoctorAvailability.slot_start is naive
    slot = db.execute(
        select(DoctorAvailability.slot_start)
        .where(
            DoctorAvailability.doctor_id == doctor.user_id,
            DoctorAvailability.is_booked.is_(False),
            DoctorAvailability.slot_start >= now,
        )
        .order_by(DoctorAvailability.slot_start.asc())
        .limit(1)
    ).scalar_one_or_none()
    return slot


def update_my_marketplace_profile(db: Session, doctor: Doctor, data: dict) -> Doctor:
    """Apply partial update to allowed marketplace fields only."""
    for field, value in data.items():
        if field in _EDITABLE_FIELDS and value is not None:
            setattr(doctor, field, value)
    db.add(doctor)
    db.commit()
    db.refresh(doctor)
    return doctor


def submit_for_verification(db: Session, doctor: Doctor) -> Doctor:
    """Doctor submits their completed profile for admin verification."""
    doctor.verification_status = DoctorVerificationStatus.PENDING_VERIFICATION
    doctor.is_verified = False
    db.add(doctor)
    audit.record(
        db,
        actor_type="doctor",
        actor_id=doctor.id,
        action="doctor_verification_submitted",
        resource_type="doctor",
        resource_id=doctor.id,
        severity="info",
    )
    db.commit()
    db.refresh(doctor)
    return doctor
