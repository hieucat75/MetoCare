"""Patient Profile API — GET + PATCH (T12) + Metabolic Score History (T13).

Endpoints:
  GET   /patients/{patient_id}/profile           — read patient profile (RBAC)
  PATCH /patients/{patient_id}/profile           — partial update (RBAC + audit)
  GET   /patients/{patient_id}/metabolic-scores  — paginated score history + trend

RBAC matrix (profile):
  GET/PATCH: PATIENT (own), DOCTOR (consent-gated), INTERNAL_ADMIN, SUPER_ADMIN
  Blocked:   AI_SERVICE, CLINIC_ADMIN

RBAC matrix (metabolic-scores):
  GET: PATIENT (own), DOCTOR (consent-gated), INTERNAL_ADMIN, SUPER_ADMIN
  Blocked: AI_SERVICE, CLINIC_ADMIN
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, current_user, get_session
from app.schemas.patient import PatientProfileOut, PatientProfileUpdate
from app.schemas.risk_score import RiskScoreHistoryResponse, RiskScoreOut
from app.services import patient_profile as svc
from app.services import risk_score as risk_score_svc

router = APIRouter(prefix="/patients", tags=["patients"])


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
