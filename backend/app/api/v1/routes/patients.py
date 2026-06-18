"""Patient Profile API — GET + PATCH (T12).

Endpoints:
  GET   /patients/{patient_id}/profile   — read patient profile (RBAC)
  PATCH /patients/{patient_id}/profile   — partial update (RBAC + audit)

RBAC matrix:
  GET:   PATIENT (own), DOCTOR (consent-gated), INTERNAL_ADMIN, SUPER_ADMIN
  PATCH: PATIENT (own), DOCTOR, INTERNAL_ADMIN, SUPER_ADMIN
  Blocked (403) for both: AI_SERVICE, CLINIC_ADMIN

All access/mutation decisions and audit are delegated to
``app.services.patient_profile``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, current_user, get_session
from app.schemas.patient import PatientProfileOut, PatientProfileUpdate
from app.services import patient_profile as svc

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
