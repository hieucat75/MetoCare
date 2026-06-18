"""Booking service (T21 — Doctor Availability + Appointment Slot API).

Functions:
  add_availability       — doctor adds a time slot
  list_available_slots   — list open (not booked) slots for a doctor
  book_slot              — patient books a slot → BookingAppointment
  list_appointments      — list appointments (filtered by patient or doctor)
  update_appointment     — update appointment status
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import BookingAppointment
from app.models.availability import DoctorAvailability
from app.schemas.booking import AppointmentPatch, AvailabilityCreate


def add_availability(
    db: Session,
    *,
    doctor_id: str,
    data: AvailabilityCreate,
) -> DoctorAvailability:
    """Create a new availability slot for a doctor.

    No overlap check is enforced at this layer (MVP scaffold).
    Full overlap detection can be added in a follow-up sprint.
    """
    slot = DoctorAvailability(
        doctor_id=doctor_id,
        slot_start=data.slot_start,
        slot_end=data.slot_end,
        is_booked=False,
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return slot


def list_available_slots(
    db: Session,
    *,
    doctor_id: str,
) -> list[DoctorAvailability]:
    """Return all open (not yet booked) slots for a given doctor."""
    rows = db.execute(
        select(DoctorAvailability)
        .where(
            DoctorAvailability.doctor_id == doctor_id,
            DoctorAvailability.is_booked == False,  # noqa: E712
        )
        .order_by(DoctorAvailability.slot_start)
    ).scalars().all()
    return list(rows)


def book_slot(
    db: Session,
    *,
    patient_profile_id: str,
    doctor_id: str,
    availability_id: str,
    notes: str | None = None,
) -> BookingAppointment:
    """Book an availability slot for a patient.

    Raises:
        404 — slot not found or does not belong to the given doctor
        409 — slot is already booked (double-booking prevention)
    """
    slot = db.get(DoctorAvailability, availability_id)
    if slot is None or slot.doctor_id != doctor_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Availability slot not found.",
        )
    if slot.is_booked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This slot has already been booked.",
        )

    # Mark slot as booked
    slot.is_booked = True
    db.add(slot)

    appt = BookingAppointment(
        patient_id=patient_profile_id,
        doctor_id=doctor_id,
        availability_id=availability_id,
        status="pending",
        notes=notes,
    )
    db.add(appt)
    db.commit()
    db.refresh(appt)
    return appt


def list_appointments(
    db: Session,
    *,
    patient_id: str | None = None,
    doctor_id: str | None = None,
) -> list[BookingAppointment]:
    """Return appointments filtered by patient and/or doctor.

    At least one of patient_id / doctor_id should be provided.
    """
    stmt = select(BookingAppointment).order_by(BookingAppointment.created_at.desc())
    if patient_id is not None:
        stmt = stmt.where(BookingAppointment.patient_id == patient_id)
    if doctor_id is not None:
        stmt = stmt.where(BookingAppointment.doctor_id == doctor_id)
    return list(db.execute(stmt).scalars().all())


def update_appointment(
    db: Session,
    *,
    appointment_id: str,
    patch: AppointmentPatch,
    requester_role: str,
    requester_id: str,
    patient_profile_id: str | None = None,
) -> BookingAppointment:
    """Update appointment status with role-based transition rules.

    DOCTOR: can set confirmed, cancelled, completed (any non-terminal status).
    PATIENT: can only set cancelled on their own *pending* appointment.

    Args:
        appointment_id: the appointment to update
        patch: new status value
        requester_role: 'doctor' | 'patient'
        requester_id: user id of the caller
        patient_profile_id: resolved PatientProfile.id for PATIENT callers

    Raises:
        404 — appointment not found
        403 — forbidden transition or not their appointment
        422 — invalid status transition
    """
    appt = db.get(BookingAppointment, appointment_id)
    if appt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found.",
        )

    new_status = patch.status

    if requester_role == "doctor":
        # Doctor must own this appointment
        if appt.doctor_id != requester_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You may only manage your own appointments.",
            )
        allowed_transitions = {"confirmed", "cancelled", "completed"}
        if new_status not in allowed_transitions:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Doctor may set status to: {allowed_transitions}",
            )

    elif requester_role == "patient":
        # Patient must own this appointment
        if patient_profile_id is None or appt.patient_id != patient_profile_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You may only manage your own appointments.",
            )
        if new_status != "cancelled":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Patients may only cancel their own pending appointments.",
            )
        if appt.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Patients may only cancel appointments that are still pending.",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{requester_role}' cannot update appointments.",
        )

    appt.status = new_status
    db.add(appt)
    db.commit()
    db.refresh(appt)
    return appt
