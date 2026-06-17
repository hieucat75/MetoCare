"""CarePlan API endpoints (T5 / C4 RBAC).

RBAC rules:
  - PATIENT: read own care plans only.
  - DOCTOR: create + read + update; must be assigned.
  - AI_SERVICE: may NOT approve (status transitions to APPROVED/ACTIVE forbidden).
  - INTERNAL_ADMIN / SUPER_ADMIN: full access.
  - MEDICAL_REVIEWER: read-only.

Safety (C2):
  - AI_SERVICE role callers may not set status to APPROVED / ACTIVE / PENDING_REVIEW.
  - PATCH cannot be used to approve a plan by non-doctor callers.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, current_user, get_session
from app.core.rbac import _is_admin, assert_doctor_assigned
from app.models.care import CarePlan, CarePlanStatus, Doctor, Encounter
from app.models.patient import PatientProfile
from app.models.user import UserRole
from app.schemas.care import CarePlanCreate, CarePlanOut, CarePlanUpdate
from app.services import audit

router = APIRouter(prefix="/care_plans", tags=["care_plans"])

# Statuses that non-doctor callers (including AI) may NEVER set
_DOCTOR_ONLY_STATUSES = frozenset({
    CarePlanStatus.PENDING_REVIEW,
    CarePlanStatus.APPROVED,
    CarePlanStatus.ACTIVE,
    CarePlanStatus.SUPERSEDED,
    CarePlanStatus.ARCHIVED,
})

_DOCTOR_ROLES = frozenset({UserRole.DOCTOR, UserRole.INTERNAL_ADMIN, UserRole.SUPER_ADMIN})


def _check_care_plan_read_access(
    db: Session,
    plan: CarePlan,
    user: CurrentUser,
) -> None:
    """Raise 403 if the caller may not read this care plan."""
    role = user.role
    if _is_admin(role):
        return
    if role == UserRole.PATIENT:
        profile = db.get(PatientProfile, plan.patient_id)
        if profile is None or profile.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this care plan.",
            )
        return
    if role in (UserRole.DOCTOR, UserRole.CLINIC_ADMIN):
        patient_clinic_id: str | None = None
        assigned_user_id: str | None = None
        if plan.approved_by_doctor_id:
            doc = db.get(Doctor, plan.approved_by_doctor_id)
            if doc is not None:
                patient_clinic_id = doc.clinic_id
                assigned_user_id = doc.user_id
        # Also check encounter doctor
        if plan.encounter_id and assigned_user_id is None:
            enc = db.get(Encounter, plan.encounter_id)
            if enc is not None and enc.doctor_id:
                doc = db.get(Doctor, enc.doctor_id)
                if doc is not None:
                    patient_clinic_id = doc.clinic_id
                    assigned_user_id = doc.user_id
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
        detail="Insufficient permissions to access this care plan.",
    )


@router.post("", response_model=CarePlanOut, status_code=status.HTTP_201_CREATED)
def create_care_plan(
    payload: CarePlanCreate,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> CarePlanOut:
    """Create a care plan. Allowed: DOCTOR, INTERNAL_ADMIN, SUPER_ADMIN.

    AI_SERVICE may not create plans with forbidden statuses (C2 guard).
    """
    if user.role not in _DOCTOR_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only doctors or admins may create care plans.",
        )

    # Verify patient exists
    profile = db.get(PatientProfile, payload.patient_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")

    # Enforce C2: status defaults to DRAFT; non-doctor may not set elevated statuses
    target_status = payload.status or CarePlanStatus.DRAFT
    if user.role not in {UserRole.DOCTOR, UserRole.INTERNAL_ADMIN, UserRole.SUPER_ADMIN}:
        if str(target_status).upper() in {s.upper() for s in _DOCTOR_ONLY_STATUSES}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot create a care plan with an elevated status.",
            )

    plan = CarePlan(
        patient_id=payload.patient_id,
        encounter_id=payload.encounter_id,
        title=payload.title,
        content=payload.content,
        status=target_status,
        ai_generated=payload.ai_generated,
        version=payload.version,
    )
    db.add(plan)
    db.flush()
    audit.record(
        db,
        actor_type=user.role,
        actor_id=user.id,
        action="care_plan.create",
        resource_type="care_plan",
        resource_id=plan.id,
        outcome="success",
        severity="info",
    )
    db.commit()
    db.refresh(plan)
    return CarePlanOut.model_validate(plan)


@router.get("/{care_plan_id}", response_model=CarePlanOut)
def get_care_plan(
    care_plan_id: str,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> CarePlanOut:
    """Read a single care plan (RBAC-scoped)."""
    plan = db.get(CarePlan, care_plan_id)
    if plan is None or plan.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Care plan not found.")
    _check_care_plan_read_access(db, plan, user)
    audit.record(
        db,
        actor_type=user.role,
        actor_id=user.id,
        action="care_plan.read",
        resource_type="care_plan",
        resource_id=care_plan_id,
        outcome="success",
        severity="info",
    )
    db.commit()
    return CarePlanOut.model_validate(plan)


@router.get("", response_model=list[CarePlanOut])
def list_care_plans(
    patient_id: str | None = Query(default=None),
    encounter_id: str | None = Query(default=None),
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> list[CarePlanOut]:
    """List care plans, scoped by role."""
    role = user.role

    if role == UserRole.PATIENT:
        if patient_id is None:
            profile = db.execute(
                select(PatientProfile).where(PatientProfile.user_id == user.id)
            ).scalar_one_or_none()
            if profile is None:
                return []
            patient_id = profile.id
        else:
            profile = db.get(PatientProfile, patient_id)
            if profile is None or profile.user_id != user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You may only list your own care plans.",
                )

    stmt = select(CarePlan).where(CarePlan.deleted_at.is_(None))
    if patient_id:
        stmt = stmt.where(CarePlan.patient_id == patient_id)
    if encounter_id:
        stmt = stmt.where(CarePlan.encounter_id == encounter_id)

    plans = db.execute(stmt).scalars().all()
    return [CarePlanOut.model_validate(p) for p in plans]


@router.patch("/{care_plan_id}", response_model=CarePlanOut)
def update_care_plan(
    care_plan_id: str,
    payload: CarePlanUpdate,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> CarePlanOut:
    """Update a care plan. Only DOCTOR/ADMIN. AI cannot approve (C2).

    PATCH status to APPROVED requires DOCTOR role.
    """
    plan = db.get(CarePlan, care_plan_id)
    if plan is None or plan.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Care plan not found.")

    if user.role not in _DOCTOR_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only doctors or admins may update care plans.",
        )

    # C2: block AI_SERVICE from approving (role guard above already does this,
    # but belt-and-suspenders: block APPROVED status for non-doctor roles)
    if payload.status is not None:
        new_status = str(payload.status).upper()
        if new_status in {s.upper() for s in _DOCTOR_ONLY_STATUSES}:
            if user.role not in {UserRole.DOCTOR, UserRole.INTERNAL_ADMIN, UserRole.SUPER_ADMIN}:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cannot set this care plan status without doctor authority.",
                )

    # Doctors must be assigned
    if user.role == UserRole.DOCTOR:
        assigned_user_id: str | None = None
        patient_clinic_id: str | None = None
        if plan.approved_by_doctor_id:
            doc = db.get(Doctor, plan.approved_by_doctor_id)
            if doc is not None:
                assigned_user_id = doc.user_id
                patient_clinic_id = doc.clinic_id
        if plan.encounter_id and assigned_user_id is None:
            enc = db.get(Encounter, plan.encounter_id)
            if enc is not None and enc.doctor_id:
                doc2 = db.get(Doctor, enc.doctor_id)
                if doc2 is not None:
                    assigned_user_id = doc2.user_id
                    patient_clinic_id = doc2.clinic_id
        assert_doctor_assigned(
            db,
            user.id,
            patient_clinic_id,
            role=user.role,
            assigned_doctor_user_id=assigned_user_id,
        )

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(plan, field, value)
    db.flush()
    audit.record(
        db,
        actor_type=user.role,
        actor_id=user.id,
        action="care_plan.update",
        resource_type="care_plan",
        resource_id=care_plan_id,
        outcome="success",
        severity="info",
    )
    db.commit()
    db.refresh(plan)
    return CarePlanOut.model_validate(plan)
