"""Doctor self-service routes — Phase 4A.

Endpoints:
  GET   /doctors/me            DOCTOR + MFA — own profile
  PATCH /doctors/me            DOCTOR + MFA — update bio/specialty/fee/avatar
  GET   /doctors/me/patients   DOCTOR + MFA — consented + encounter-assigned patients
  GET   /doctors/me/dashboard  DOCTOR + MFA — aggregate counts

All four endpoints require:
  1. DOCTOR role (require_roles gate)
  2. MFA-verified session (require_mfa gate — mfa=True in JWT)

A DOCTOR token issued before MFA verification carries mfa=False and is
rejected at require_mfa with 403. This is enforced at the dependency layer,
not in frontend redirects.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_session, require_mfa, require_roles
from app.models.user import UserRole
from app.schemas.consultation import ConsultationOut
from app.schemas.doctor import (
    DoctorDashboardOut,
    DoctorMarketplaceUpdate,
    DoctorPatientItem,
    DoctorProfileOut,
    DoctorProfileUpdate,
)
from app.services import consultation as consult_svc
from app.services import doctor_marketplace
from app.services.doctor import (
    _require_doctor,
    get_doctor_dashboard,
    list_doctor_patients,
    update_doctor_profile,
)

router = APIRouter(tags=["doctor"])

_doctor_mfa = require_roles(UserRole.DOCTOR)


# ---------------------------------------------------------------------------
# GET /doctors/me
# ---------------------------------------------------------------------------


@router.get(
    "/doctors/me",
    response_model=DoctorProfileOut,
    status_code=status.HTTP_200_OK,
    summary="Get own doctor profile (DOCTOR + MFA)",
)
def get_my_profile(
    user: CurrentUser = Depends(_doctor_mfa),
    _mfa: CurrentUser = Depends(require_mfa),
    db: Session = Depends(get_session),
) -> DoctorProfileOut:
    doc = _require_doctor(db, user.id)
    return DoctorProfileOut.model_validate(doc)


# ---------------------------------------------------------------------------
# PATCH /doctors/me
# ---------------------------------------------------------------------------


@router.patch(
    "/doctors/me",
    response_model=DoctorProfileOut,
    status_code=status.HTTP_200_OK,
    summary="Update own doctor profile (DOCTOR + MFA)",
)
def patch_my_profile(
    payload: DoctorProfileUpdate,
    user: CurrentUser = Depends(_doctor_mfa),
    _mfa: CurrentUser = Depends(require_mfa),
    db: Session = Depends(get_session),
) -> DoctorProfileOut:
    doc = _require_doctor(db, user.id)
    updated = update_doctor_profile(db, doc, payload.model_dump(exclude_none=True))
    db.commit()
    return DoctorProfileOut.model_validate(updated)


# ---------------------------------------------------------------------------
# GET /doctors/me/patients
# ---------------------------------------------------------------------------


@router.get(
    "/doctors/me/patients",
    response_model=list[DoctorPatientItem],
    status_code=status.HTTP_200_OK,
    summary="List consented / assigned patients (DOCTOR + MFA)",
)
def list_my_patients(
    risk: str | None = Query(default=None, description="Filter by risk_segment (high/medium/low)"),
    has_pending_review: bool = Query(default=False, description="Only patients with pending items"),
    user: CurrentUser = Depends(_doctor_mfa),
    _mfa: CurrentUser = Depends(require_mfa),
    db: Session = Depends(get_session),
) -> list[DoctorPatientItem]:
    doc = _require_doctor(db, user.id)
    patients = list_doctor_patients(
        db,
        doctor_id=doc.id,
        doctor_user_id=user.id,
        risk=risk,
        has_pending_review=has_pending_review,
    )
    return [DoctorPatientItem(**p) for p in patients]


# ---------------------------------------------------------------------------
# GET /doctors/me/dashboard
# ---------------------------------------------------------------------------


@router.get(
    "/doctors/me/dashboard",
    response_model=DoctorDashboardOut,
    status_code=status.HTTP_200_OK,
    summary="Doctor dashboard aggregate (DOCTOR + MFA)",
)
def get_my_dashboard(
    user: CurrentUser = Depends(_doctor_mfa),
    _mfa: CurrentUser = Depends(require_mfa),
    db: Session = Depends(get_session),
) -> DoctorDashboardOut:
    doc = _require_doctor(db, user.id)
    data = get_doctor_dashboard(db, doctor_id=doc.id, doctor_user_id=user.id)
    return DoctorDashboardOut(**data)


# ---------------------------------------------------------------------------
# T10 — Marketplace self-service
# ---------------------------------------------------------------------------


@router.patch(
    "/doctors/me/marketplace",
    response_model=DoctorProfileOut,
    status_code=status.HTTP_200_OK,
    summary="Update own marketplace listing (DOCTOR + MFA)",
)
def patch_my_marketplace(
    payload: DoctorMarketplaceUpdate,
    user: CurrentUser = Depends(_doctor_mfa),
    _mfa: CurrentUser = Depends(require_mfa),
    db: Session = Depends(get_session),
) -> DoctorProfileOut:
    doc = _require_doctor(db, user.id)
    updated = doctor_marketplace.update_my_marketplace_profile(
        db, doc, payload.model_dump(exclude_none=True)
    )
    return DoctorProfileOut.model_validate(updated)


@router.post(
    "/doctors/me/submit-verification",
    response_model=DoctorProfileOut,
    status_code=status.HTTP_200_OK,
    summary="Submit marketplace profile for verification (DOCTOR + MFA)",
)
def submit_my_verification(
    user: CurrentUser = Depends(_doctor_mfa),
    _mfa: CurrentUser = Depends(require_mfa),
    db: Session = Depends(get_session),
) -> DoctorProfileOut:
    doc = _require_doctor(db, user.id)
    updated = doctor_marketplace.submit_for_verification(db, doc)
    return DoctorProfileOut.model_validate(updated)


@router.get(
    "/doctors/me/consultations",
    response_model=list[ConsultationOut],
    status_code=status.HTTP_200_OK,
    summary="List own consultations (DOCTOR + MFA)",
)
def list_my_consultations(
    user: CurrentUser = Depends(_doctor_mfa),
    _mfa: CurrentUser = Depends(require_mfa),
    db: Session = Depends(get_session),
) -> list[ConsultationOut]:
    doc = _require_doctor(db, user.id)
    rows = consult_svc.list_doctor_consultations(db, doc.id)
    return [ConsultationOut.model_validate(r) for r in rows]
