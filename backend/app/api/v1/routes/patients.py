"""Patient Profile API — GET + PATCH (T12) + Metabolic Score History (T13)
+ Symptom Log + Medication CRUD (T15).

Endpoints:
  GET    /patients/{patient_id}/profile                       — read patient profile (RBAC)
  PATCH  /patients/{patient_id}/profile                       — partial update (RBAC + audit)
  GET    /patients/{patient_id}/metabolic-scores              — paginated score history + trend
  POST   /patients/{patient_id}/symptoms                      — log symptom (RBAC)
  GET    /patients/{patient_id}/symptoms                      — list symptoms (paginated)
  POST   /patients/{patient_id}/medications                   — add medication (RBAC)
  GET    /patients/{patient_id}/medications                   — list active medications (paginated)
  DELETE /patients/{patient_id}/medications/{med_id}          — soft-delete medication

RBAC matrix (symptom + medication writes):
  Allowed: PATIENT (own), DOCTOR (consent-gated), INTERNAL_ADMIN, SUPER_ADMIN
  Blocked write: AI_SERVICE (critical safety), CLINIC_ADMIN
  Blocked delete: DOCTOR (clinical safety — cannot remove patient medication history)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, current_user, get_session
from app.models.user import UserRole
from app.schemas.medication import MedicationCreate, MedicationOut
from app.schemas.nutrition import NutritionLogCreate, NutritionLogOut
from app.schemas.patient import PatientProfileOut, PatientProfileUpdate
from app.schemas.risk_score import RiskScoreHistoryResponse, RiskScoreOut
from app.schemas.symptom import SymptomLogCreate, SymptomLogOut
from app.services import audit
from app.services import medication as medication_svc
from app.services import nutrition_log as nutrition_log_svc
from app.services import patient_profile as svc
from app.services import risk_score as risk_score_svc
from app.services import symptom_log as symptom_log_svc
from app.services.consent import ConsentError, require_access

router = APIRouter(prefix="/patients", tags=["patients"])

# ---------------------------------------------------------------------------
# RBAC helpers shared by T15 endpoints
# ---------------------------------------------------------------------------

_BLOCKED_WRITE_ROLES: frozenset[str] = frozenset({
    UserRole.AI_SERVICE,
    UserRole.CLINIC_ADMIN,
})

_ADMIN_ROLES: frozenset[str] = frozenset({
    UserRole.INTERNAL_ADMIN,
    UserRole.SUPER_ADMIN,
})


def _check_write_access(
    db,
    *,
    patient_id: str,
    requester,
    scope: str = "profile",
) -> None:
    """Raise 403 for blocked roles; enforce ownership/consent for others."""
    from fastapi import HTTPException
    from fastapi import status as http_status

    if requester.role in _BLOCKED_WRITE_ROLES:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail=f"Role '{requester.role}' is not permitted to write clinical data.",
        )

    if requester.role in _ADMIN_ROLES:
        return

    if requester.role == UserRole.PATIENT:
        # Ownership check: resolve patient profile → compare user_id
        from app.models.patient import PatientProfile
        profile = db.get(PatientProfile, patient_id)
        if profile is None or profile.user_id != requester.id:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="You may only access your own clinical records.",
            )
        return

    if requester.role == UserRole.DOCTOR:
        try:
            require_access(db, patient_id=patient_id, requester_id=requester.id, scope=scope)
        except ConsentError as exc:
            from fastapi import HTTPException  # noqa: F811
            from fastapi import status as http_status
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail=str(exc),
            ) from exc
        return

    from fastapi import HTTPException  # noqa: F811
    from fastapi import status as http_status
    raise HTTPException(
        status_code=http_status.HTTP_403_FORBIDDEN,
        detail=f"Role '{requester.role}' is not permitted.",
    )


def _check_read_access(
    db,
    *,
    patient_id: str,
    requester,
    scope: str = "profile",
) -> None:
    """Same as write access but also blocks AI_SERVICE for read."""
    _check_write_access(db, patient_id=patient_id, requester=requester, scope=scope)


@router.get(
    "/{patient_id}/profile",
    response_model=PatientProfileOut,
    status_code=status.HTTP_200_OK,
    summary="Read patient profile",
)
def get_patient_profile(
    patient_id: str,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> PatientProfileOut:
    """Retrieve the profile for *patient_id*.

    Access rules:
    - **PATIENT** — own profile only.
    - **DOCTOR** — consent-gated (active consent with ``scope='profile'`` required).
    - **INTERNAL_ADMIN / SUPER_ADMIN** — unrestricted.
    - **AI_SERVICE / CLINIC_ADMIN** — always 403.
    """
    profile = svc.get_profile(db, patient_id=patient_id, requester=user)
    return PatientProfileOut.model_validate(profile)


@router.patch(
    "/{patient_id}/profile",
    response_model=PatientProfileOut,
    status_code=status.HTTP_200_OK,
    summary="Update patient profile (partial)",
)
def patch_patient_profile(
    patient_id: str,
    payload: PatientProfileUpdate,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> PatientProfileOut:
    """Partially update the profile for *patient_id*.

    Only fields that are explicitly included in the request body are written.
    Every successful update produces an ``AuditLog`` entry with
    ``action='update_profile'``.

    Access rules:
    - **PATIENT** — own profile only.
    - **DOCTOR / INTERNAL_ADMIN / SUPER_ADMIN** — any patient.
    - **AI_SERVICE / CLINIC_ADMIN** — always 403.
    """
    data = payload.model_dump(exclude_unset=True)
    profile = svc.update_profile(db, patient_id=patient_id, requester=user, data=data)
    return PatientProfileOut.model_validate(profile)


@router.get(
    "/{patient_id}/metabolic-scores",
    response_model=RiskScoreHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get metabolic score history + trend",
)
def get_metabolic_score_history(
    patient_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> RiskScoreHistoryResponse:
    """Return paginated metabolic score history and a directional trend.

    Access rules (same as patient profile):
    - **PATIENT** — own history only.
    - **DOCTOR** — consent-gated (scope=\'profile\').
    - **INTERNAL_ADMIN / SUPER_ADMIN** — unrestricted.
    - **AI_SERVICE / CLINIC_ADMIN** — always 403.
    """
    # Reuse the profile RBAC check: it raises 403/404 for blocked/missing patients.
    # We don\'t return the profile — just validate access.
    svc.get_profile(db, patient_id=patient_id, requester=user)

    total, items = risk_score_svc.get_history(
        db, patient_id=patient_id, limit=limit, offset=offset
    )
    trend = risk_score_svc.compute_trend(items)

    return RiskScoreHistoryResponse(
        patient_id=patient_id,
        total=total,
        items=[RiskScoreOut.model_validate(item) for item in items],
        trend=trend,
    )


# ---------------------------------------------------------------------------
# T15 — Symptom Log endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/{patient_id}/symptoms",
    response_model=SymptomLogOut,
    status_code=status.HTTP_201_CREATED,
    summary="Log a symptom for a patient",
)
def create_symptom_log(
    patient_id: str,
    payload: SymptomLogCreate,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> SymptomLogOut:
    """Log a self-reported symptom for *patient_id*.

    Access rules:
    - **PATIENT** — own record only.
    - **DOCTOR** — consent-gated (scope='profile').
    - **INTERNAL_ADMIN / SUPER_ADMIN** — unrestricted.
    - **AI_SERVICE / CLINIC_ADMIN** — always 403 (safety critical).

    Produces an ``AuditLog`` entry with ``action='log_symptom'``.
    """
    _check_write_access(db, patient_id=patient_id, requester=user)

    data = payload.model_dump(exclude_unset=False)
    record = symptom_log_svc.create_symptom(db, patient_id=patient_id, data=data)

    audit.record(
        db,
        actor_type=user.role,
        actor_id=user.id,
        action="log_symptom",
        resource_type="symptom_log",
        resource_id=record.id,
        outcome="success",
        severity="info",
    )
    db.commit()

    return SymptomLogOut.model_validate(record)


@router.get(
    "/{patient_id}/symptoms",
    status_code=status.HTTP_200_OK,
    summary="List symptoms for a patient (paginated)",
)
def list_symptom_logs(
    patient_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> dict:
    """Return paginated symptom logs for *patient_id* (newest first).

    Access rules: same as POST /symptoms.
    """
    _check_read_access(db, patient_id=patient_id, requester=user)

    total, items = symptom_log_svc.list_symptoms(
        db, patient_id=patient_id, limit=limit, offset=offset
    )

    return {
        "patient_id": patient_id,
        "total": total,
        "items": [SymptomLogOut.model_validate(item) for item in items],
    }


# ---------------------------------------------------------------------------
# T15 — Medication endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/{patient_id}/medications",
    response_model=MedicationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a medication record for a patient",
)
def add_medication(
    patient_id: str,
    payload: MedicationCreate,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> MedicationOut:
    """Add a medication record for *patient_id*.

    Access rules:
    - **PATIENT** — own record only.
    - **DOCTOR** — consent-gated (scope='profile').
    - **INTERNAL_ADMIN / SUPER_ADMIN** — unrestricted.
    - **AI_SERVICE** — always 403 (CRITICAL SAFETY: AI must never add medications).
    - **CLINIC_ADMIN** — always 403.

    Produces an ``AuditLog`` entry with ``action='add_medication'``.
    """
    _check_write_access(db, patient_id=patient_id, requester=user)

    data = payload.model_dump(exclude_unset=False)
    record = medication_svc.add_medication(db, patient_id=patient_id, data=data)

    audit.record(
        db,
        actor_type=user.role,
        actor_id=user.id,
        action="add_medication",
        resource_type="medication",
        resource_id=record.id,
        outcome="success",
        severity="info",
    )
    db.commit()

    return MedicationOut.model_validate(record)


@router.get(
    "/{patient_id}/medications",
    status_code=status.HTTP_200_OK,
    summary="List active medications for a patient (paginated)",
)
def list_medications(
    patient_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> dict:
    """Return paginated active medication records for *patient_id*.

    Only non-deleted (``deleted_at IS NULL``) records are returned.
    Access rules: same as POST /medications.
    """
    _check_read_access(db, patient_id=patient_id, requester=user)

    total, items = medication_svc.list_medications(
        db, patient_id=patient_id, limit=limit, offset=offset
    )

    return {
        "patient_id": patient_id,
        "total": total,
        "items": [MedicationOut.model_validate(item) for item in items],
    }


@router.delete(
    "/{patient_id}/medications/{med_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a medication record",
)
def delete_medication(
    patient_id: str,
    med_id: str,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> None:
    """Soft-delete a medication record (sets ``deleted_at``).

    Access rules:
    - **PATIENT** — own record only.
    - **INTERNAL_ADMIN / SUPER_ADMIN** — unrestricted.
    - **DOCTOR** — always 403 (clinical safety: doctors must not remove patient
      medication history).
    - **AI_SERVICE / CLINIC_ADMIN** — always 403.

    Produces an ``AuditLog`` entry with ``action='delete_medication'``.
    """
    from fastapi import HTTPException
    from fastapi import status as http_status

    # Doctor-specific block (clinical safety)
    if user.role == UserRole.DOCTOR:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Doctors are not permitted to delete medication records (clinical safety).",
        )

    # General write-access check (blocks AI_SERVICE, CLINIC_ADMIN; enforces ownership)
    _check_write_access(db, patient_id=patient_id, requester=user)

    medication_svc.delete_medication(db, patient_id=patient_id, med_id=med_id)

    audit.record(
        db,
        actor_type=user.role,
        actor_id=user.id,
        action="delete_medication",
        resource_type="medication",
        resource_id=med_id,
        outcome="success",
        severity="info",
    )
    db.commit()

# ---------------------------------------------------------------------------
# T18 — Nutrition Log endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/{patient_id}/nutrition",
    response_model=NutritionLogOut,
    status_code=status.HTTP_201_CREATED,
    summary="Log a meal/snack for a patient",
)
def create_nutrition_log(
    patient_id: str,
    payload: NutritionLogCreate,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> NutritionLogOut:
    """Record a meal or snack for *patient_id*.

    Access rules:
    - **PATIENT** — own record only.
    - **DOCTOR** — consent-gated (scope='profile').
    - **INTERNAL_ADMIN / SUPER_ADMIN** — unrestricted.
    - **AI_SERVICE / CLINIC_ADMIN** — always 403.

    Produces an ``AuditLog`` entry with ``action='log_nutrition'``.
    """
    _check_write_access(db, patient_id=patient_id, requester=user)

    data = payload.model_dump(exclude_unset=False)
    record = nutrition_log_svc.create_log(db, patient_id=patient_id, data=data)

    audit.record(
        db,
        actor_type=user.role,
        actor_id=user.id,
        action="log_nutrition",
        resource_type="nutrition_log",
        resource_id=record.id,
        outcome="success",
        severity="info",
    )
    db.commit()

    return NutritionLogOut.model_validate(record)


@router.get(
    "/{patient_id}/nutrition",
    status_code=status.HTTP_200_OK,
    summary="List nutrition logs for a patient (paginated, newest first)",
)
def list_nutrition_logs(
    patient_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> dict:
    """Return paginated nutrition logs for *patient_id* (newest first).

    Access rules: same as POST /nutrition.
    """
    _check_read_access(db, patient_id=patient_id, requester=user)

    total, items = nutrition_log_svc.list_logs(
        db, patient_id=patient_id, limit=limit, offset=offset
    )

    return {
        "patient_id": patient_id,
        "total": total,
        "items": [NutritionLogOut.model_validate(item) for item in items],
    }
