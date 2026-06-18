"""Booking API routes (T21 — Doctor Availability + Appointment Slot).

Endpoints:
  POST   /doctors/{doctor_id}/availability      DOCTOR (own)
  GET    /doctors/{doctor_id}/availability      PATIENT / DOCTOR / ADMIN
  POST   /appointments                          PATIENT only
  GET    /patients/{patient_id}/appointments    PATIENT(own) / DOCTOR(own patients) / ADMIN
  PATCH  /appointments/{appointment_id}         DOCTOR(confirm/cancel) / PATIENT(cancel pending)

RBAC:
  AI_SERVICE   → 403 on all booking endpoints
  CLINIC_ADMIN → 403 on all booking endpoints
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, current_user, get_session
from app.models.patient import PatientProfile
from app.models.user import UserRole
from app.schemas.booking import (
    AppointmentCreate,
    AppointmentOut,
    AppointmentPatch,
    AvailabilityCreate,
    AvailabilityOut,
)
from app.services import booking as booking_svc

router = APIRouter(tags=["booking"])

# ---------------------------------------------------------------------------
# Role helpers
# ---------------------------------------------------------------------------

_BLOCKED_ROLES: frozenset[str] = frozenset({
    UserRole.AI_SERVICE,
    UserRole.CLINIC_ADMIN,
})

_ADMIN_ROLES: frozenset[str] = frozenset({
    UserRole.INTERNAL_ADMIN,
    UserRole.SUPER_ADMIN,
})


def _require_not_blocked(user: CurrentUser) -> None:
    """Raise 403 for roles that are blocked from all booking endpoints."""
    if user.role in _BLOCKED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{user.role}' is not permitted to access booking endpoints.",
        )


def _resolve_patient_profile(db: Session, user_id: str) -> PatientProfile:
    """Return the PatientProfile for a PATIENT user.  Raises 404 if not found."""
    from sqlalchemy import select

    profile = db.execute(
        select(PatientProfile).where(PatientProfile.user_id == user_id)
    ).scalar_one_or_none()
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient profile not found.",
        )
    return profile


# ---------------------------------------------------------------------------
# POST /doctors/{doctor_id}/availability — DOCTOR only (own slots)
# ---------------------------------------------------------------------------

@router.post(
    "/doctors/{doctor_id}/availability",
    response_model=AvailabilityOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add an availability slot (DOCTOR only)",
)
def add_availability(
    doctor_id: str,
    payload: AvailabilityCreate,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> AvailabilityOut:
    """Create a new time slot that the doctor is available for booking.

    - Only the owning DOCTOR may call this endpoint.
    - AI_SERVICE and CLINIC_ADMIN are always 403.
    """
    _require_not_blocked(user)

    if user.role != UserRole.DOCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only doctors may add availability slots.",
        )
    if user.id != doctor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You may only add slots for your own doctor account.",
        )

    slot = booking_svc.add_availability(db, doctor_id=doctor_id, data=payload)
    return AvailabilityOut.model_validate(slot)


# ---------------------------------------------------------------------------
# GET /doctors/{doctor_id}/availability — PATIENT / DOCTOR / ADMIN
# ---------------------------------------------------------------------------

@router.get(
    "/doctors/{doctor_id}/availability",
    response_model=list[AvailabilityOut],
    status_code=status.HTTP_200_OK,
    summary="List open availability slots for a doctor",
)
def list_availability(
    doctor_id: str,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> list[AvailabilityOut]:
    """Return all open (not yet booked) slots for a given doctor.

    Accessible by PATIENT, DOCTOR, INTERNAL_ADMIN, SUPER_ADMIN.
    AI_SERVICE and CLINIC_ADMIN → 403.
    """
    _require_not_blocked(user)

    # Only PATIENT, DOCTOR, and ADMIN roles may list slots
    allowed = {UserRole.PATIENT, UserRole.DOCTOR} | _ADMIN_ROLES
    if user.role not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{user.role}' is not permitted to view availability slots.",
        )

    slots = booking_svc.list_available_slots(db, doctor_id=doctor_id)
    return [AvailabilityOut.model_validate(s) for s in slots]


# ---------------------------------------------------------------------------
# POST /appointments — PATIENT only
# ---------------------------------------------------------------------------

@router.post(
    "/appointments",
    response_model=AppointmentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Book an availability slot (PATIENT only)",
)
def book_appointment(
    payload: AppointmentCreate,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> AppointmentOut:
    """Patient books a doctor's availability slot.

    - Only PATIENT role may call this.
    - Returns 409 if the slot is already booked.
    """
    _require_not_blocked(user)

    if user.role != UserRole.PATIENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only patients may book appointments.",
        )

    profile = _resolve_patient_profile(db, user.id)

    appt = booking_svc.book_slot(
        db,
        patient_profile_id=profile.id,
        doctor_id=payload.doctor_id,
        availability_id=payload.availability_id,
        notes=payload.notes,
    )
    return AppointmentOut.model_validate(appt)


# ---------------------------------------------------------------------------
# GET /patients/{patient_id}/appointments
# ---------------------------------------------------------------------------

@router.get(
    "/patients/{patient_id}/appointments",
    response_model=list[AppointmentOut],
    status_code=status.HTTP_200_OK,
    summary="List appointments for a patient",
)
def list_patient_appointments(
    patient_id: str,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> list[AppointmentOut]:
    """Return appointments for the given patient_id.

    Access rules:
    - PATIENT: own appointments only (patient_id must match their profile)
    - DOCTOR: their own patients' appointments (doctor_id filtered by caller)
    - INTERNAL_ADMIN / SUPER_ADMIN: any patient
    - AI_SERVICE / CLINIC_ADMIN: 403
    """
    _require_not_blocked(user)

    if user.role == UserRole.PATIENT:
        profile = _resolve_patient_profile(db, user.id)
        if profile.id != patient_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Patients may only view their own appointments.",
            )
        appts = booking_svc.list_appointments(db, patient_id=patient_id)

    elif user.role == UserRole.DOCTOR:
        # Doctor sees appointments for this patient where they are the doctor
        appts = booking_svc.list_appointments(
            db, patient_id=patient_id, doctor_id=user.id
        )

    elif user.role in _ADMIN_ROLES:
        appts = booking_svc.list_appointments(db, patient_id=patient_id)

    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{user.role}' is not permitted.",
        )

    return [AppointmentOut.model_validate(a) for a in appts]


# ---------------------------------------------------------------------------
# PATCH /appointments/{appointment_id}
# ---------------------------------------------------------------------------

@router.patch(
    "/appointments/{appointment_id}",
    response_model=AppointmentOut,
    status_code=status.HTTP_200_OK,
    summary="Update appointment status",
)
def patch_appointment(
    appointment_id: str,
    payload: AppointmentPatch,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> AppointmentOut:
    """Update appointment status.

    DOCTOR:  confirm, cancel, or complete their appointments.
    PATIENT: cancel their own *pending* appointment only.
    All others → 403.
    """
    _require_not_blocked(user)

    if user.role not in {UserRole.DOCTOR, UserRole.PATIENT}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{user.role}' may not update appointments.",
        )

    patient_profile_id: str | None = None
    if user.role == UserRole.PATIENT:
        profile = _resolve_patient_profile(db, user.id)
        patient_profile_id = profile.id

    appt = booking_svc.update_appointment(
        db,
        appointment_id=appointment_id,
        patch=payload,
        requester_role=user.role,
        requester_id=user.id,
        patient_profile_id=patient_profile_id,
    )
    return AppointmentOut.model_validate(appt)
