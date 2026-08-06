"""Action-first patient dashboard API (BRD §I). Patient-owned (self only)."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_session, require_roles
from app.models.patient import PatientProfile
from app.models.user import UserRole
from app.services import patient_dashboard

router = APIRouter(tags=["dashboard"])

_PatientOnly = require_roles(UserRole.PATIENT)


class DoseDueOut(BaseModel):
    dose_id: str
    schedule_id: str
    scheduled_utc: dt.datetime
    local_render: str | None
    state: str


class ActionOut(BaseModel):
    type: str
    title_vi: str
    count: int
    route: str


class DashboardOut(BaseModel):
    patient_id: str
    generated_at: dt.datetime
    doses_due: list[DoseDueOut]
    doses_due_count: int
    pending_document_reviews: int
    active_medications: int
    recently_confirmed: int
    actions: list[ActionOut]
    empty_state: bool


@router.get("/patients/{patient_id}/dashboard", response_model=DashboardOut)
def get_dashboard(
    patient_id: str,
    user: CurrentUser = Depends(_PatientOnly),
    db: Session = Depends(get_session),
) -> DashboardOut:
    profile = db.execute(
        select(PatientProfile).where(PatientProfile.user_id == user.id)
    ).scalars().first()
    if profile is None or profile.id != patient_id:
        raise HTTPException(status_code=403, detail="Không có quyền với hồ sơ này.")
    result = patient_dashboard.build_dashboard(db, patient_id=patient_id)
    db.commit()  # build_dashboard materializes doses + sweeps missed
    return DashboardOut(**result)
