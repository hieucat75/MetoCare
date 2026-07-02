"""Marketplace routes (T10) — public doctor browse/detail for patients.

Only VERIFIED, active doctors are ever returned. SUSPENDED/PENDING/REJECTED
doctors are excluded at the service layer.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, current_user, get_session
from app.core.config import MARKETPLACE_DISCLAIMER
from app.schemas.marketplace import DoctorCardOut, DoctorDetailOut
from app.services import doctor_marketplace

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


@router.get(
    "/doctors",
    response_model=list[DoctorCardOut],
    status_code=status.HTTP_200_OK,
    summary="Browse verified doctors (any authenticated user)",
)
def browse_doctors(
    specialty: str | None = Query(default=None),
    name: str | None = Query(default=None),
    min_price: float | None = Query(default=None, ge=0),
    max_price: float | None = Query(default=None, ge=0),
    method: str | None = Query(default=None, description="e.g. chat / video"),
    _user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> list[DoctorCardOut]:
    doctors = doctor_marketplace.browse_doctors(
        db,
        specialty=specialty,
        name=name,
        min_price=min_price,
        max_price=max_price,
        method=method,
    )
    return [DoctorCardOut.model_validate(d) for d in doctors]


@router.get(
    "/doctors/{doctor_id}",
    response_model=DoctorDetailOut,
    status_code=status.HTTP_200_OK,
    summary="Verified doctor detail + next available slot",
)
def doctor_detail(
    doctor_id: str,
    _user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> DoctorDetailOut:
    doctor, next_available = doctor_marketplace.get_doctor_detail(db, doctor_id)
    out = DoctorDetailOut.model_validate(doctor)
    return out.model_copy(
        update={"next_available": next_available, "disclaimer": MARKETPLACE_DISCLAIMER}
    )
