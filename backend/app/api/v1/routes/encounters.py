"""Encounter API endpoints (T5 / C4 RBAC).

RBAC rules:
  - PATIENT: read own encounters only (patient_id matches PatientProfile.user_id).
  - DOCTOR: create + read + update; must have DoctorClinic relation or be the assigned doctor.
  - CLINIC_ADMIN: read all encounters in own clinic (scoped by clinic).
  - INTERNAL_ADMIN / SUPER_ADMIN: full access.
  - MEDICAL_REVIEWER: read-only, any encounter.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, current_user, get_session
from app.core.rbac import _is_admin, assert_doctor_assigned
from app.models.care import Doctor, Encounter
from app.models.patient import PatientProfile
from app.models.user import UserRole
from app.schemas.care import EncounterCreate, EncounterOut, EncounterUpdate
from app.services import audit

router = APIRouter(prefix="/encounters", tags=["encounters"])


def _resolve_patient_profile(db: Session, patient_id: str) -> PatientProfile:
    profile = db.get(PatientProfile, patient_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")
    return profile


def _check_encounter_read_access(
    db: Session,
    encounter: Encounter,
    user: CurrentUser,
) -> None:
    """Raise 403 if the caller may not read this encounter."""
    role = user.role
    if _is_admin(role):
        return
    if role == UserRole.PATIENT:
        profile = db.get(PatientProfile, encounter.patient_id)
        if profile is None or profile.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this encounter.",
            )
        return
    if role in (UserRole.DOCTOR, UserRole.CLINIC_ADMIN):
        # Resolve assigned doctor user_id
        assigned_user_id: str | None = None
        if encounter.doctor_id:
            doc = db.get(Doctor, encounter.doctor_id)
            if doc is not None:
                assigned_user_id = doc.user_id
        # Get patient clinic (from doctor primary clinic, loose scope)
        patient_clinic_id: str | None = None
        if encounter.doctor_id:
            doc = db.get(Doctor, encounter.doctor_id)
            if doc is not None:
                patient_clinic_id = doc.clinic_id
        assert_doctor_assigned(
            db,
            user.id,
            patient_clinic_id,
            role=role,
            assigned_doctor_user_id=assigned_user_id,
        )
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient permissions to access this encounter.",
    )


@router.post("", response_model=EncounterOut, status_code=status.HTTP_201_CREATED)
def create_encounter(
    payload: EncounterCreate,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> EncounterOut:
    """Create an encounter. Allowed: DOCTOR, CLINIC_ADMIN, INTERNAL_ADMIN, SUPER_ADMIN."""
    allowed_roles = {
        UserRole.DOCTOR,
        UserRole.CLINIC_ADMIN,
        UserRole.INTERNAL_ADMIN,
        UserRole.SUPER_ADMIN,
    }
    if user.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only doctors or clinic admins may create encounters.",
        )
    # Ensure patient exists
    _resolve_patient_profile(db, payload.patient_id)

    encounter = Encounter(
        patient_id=payload.patient_id,
        doctor_id=payload.doctor_id,
        appointment_id=payload.appointment_id,
        encounter_type=payload.encounter_type,
        status=payload.status,
        chief_complaint=payload.chief_complaint,
        notes=payload.notes,
        encounter_date=payload.encounter_date or dt.datetime.now(dt.UTC).replace(tzinfo=None),
    )
    db.add(encounter)
    db.flush()
    audit.record(
        db,
        actor_type=user.role,
        actor_id=user.id,
        action="encounter.create",
        resource_type="encounter",
        resource_id=encounter.id,
        outcome="success",
        severity="info",
    )
    db.commit()
    db.refresh(encounter)
    return EncounterOut.model_validate(encounter)


@router.get("/{encounter_id}", response_model=EncounterOut)
def get_encounter(
    encounter_id: str,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> EncounterOut:
    """Read a single encounter (RBAC-scoped)."""
    encounter = db.get(Encounter, encounter_id)
    if encounter is None or encounter.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Encounter not found.")
    _check_encounter_read_access(db, encounter, user)
    audit.record(
        db,
        actor_type=user.role,
        actor_id=user.id,
        action="encounter.read",
        resource_type="encounter",
        resource_id=encounter_id,
        outcome="success",
        severity="info",
    )
    db.commit()
    return EncounterOut.model_validate(encounter)


@router.get("", response_model=list[EncounterOut])
def list_encounters(
    patient_id: str | None = Query(default=None),
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> list[EncounterOut]:
    """List encounters, scoped by role.

    PATIENT: may only list their own patient_id (required).
    DOCTOR/CLINIC_ADMIN: may list by patient_id (optional).
    ADMIN/REVIEWER: unrestricted.
    """
    role = user.role

    if role == UserRole.PATIENT:
        # Patient must provide their own patient_id or we derive it
        if patient_id is None:
            profile = db.execute(
                select(PatientProfile).where(PatientProfile.user_id == user.id)
            ).scalar_one_or_none()
            if profile is None:
                return []
            patient_id = profile.id
        else:
            # Verify ownership
            profile = db.get(PatientProfile, patient_id)
            if profile is None or profile.user_id != user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You may only list your own encounters.",
                )

    stmt = select(Encounter).where(Encounter.deleted_at.is_(None))
    if patient_id:
        stmt = stmt.where(Encounter.patient_id == patient_id)

    encounters = db.execute(stmt).scalars().all()
    # For doctors, filter to assigned encounters only
    if role == UserRole.DOCTOR and patient_id is None:
        doctor_row = db.execute(
            select(Doctor).where(Doctor.user_id == user.id)
        ).scalar_one_or_none()
        if doctor_row is not None:
            encounters = [e for e in encounters if e.doctor_id == doctor_row.id]
        else:
            encounters = []

    return [EncounterOut.model_validate(e) for e in encounters]


@router.patch("/{encounter_id}", response_model=EncounterOut)
def update_encounter(
    encounter_id: str,
    payload: EncounterUpdate,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> EncounterOut:
    """Update an encounter. Allowed: DOCTOR (assigned), INTERNAL_ADMIN, SUPER_ADMIN."""
    encounter = db.get(Encounter, encounter_id)
    if encounter is None or encounter.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Encounter not found.")

    write_roles = {UserRole.DOCTOR, UserRole.INTERNAL_ADMIN, UserRole.SUPER_ADMIN}
    if user.role not in write_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only doctors or admins may update encounters.",
        )

    # Doctors must be assigned
    if user.role == UserRole.DOCTOR:
        assigned_user_id: str | None = None
        patient_clinic_id: str | None = None
        if encounter.doctor_id:
            doc = db.get(Doctor, encounter.doctor_id)
            if doc is not None:
                assigned_user_id = doc.user_id
                patient_clinic_id = doc.clinic_id
        assert_doctor_assigned(
            db,
            user.id,
            patient_clinic_id,
            role=user.role,
            assigned_doctor_user_id=assigned_user_id,
        )

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(encounter, field, value)
    db.flush()
    audit.record(
        db,
        actor_type=user.role,
        actor_id=user.id,
        action="encounter.update",
        resource_type="encounter",
        resource_id=encounter_id,
        outcome="success",
        severity="info",
    )
    db.commit()
    db.refresh(encounter)
    return EncounterOut.model_validate(encounter)
