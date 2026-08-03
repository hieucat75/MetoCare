"""Patient self-service account API: data export + account deletion.

GDPR data-subject rights (DIST-RC compliance slice). Both endpoints are
patient-only and strictly self-scoped: the caller may act on their OWN patient
profile only. BOLA enforcement mirrors dashboard.py exactly (resolve the
caller's PatientProfile by user_id, then compare ids).
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_session, require_roles
from app.models.patient import PatientProfile
from app.models.user import UserRole
from app.services import account as account_svc
from app.services import audit

router = APIRouter(tags=["account"])

_PatientOnly = require_roles(UserRole.PATIENT)


def _assert_owns(db: Session, *, user: CurrentUser, patient_id: str) -> None:
    """403 unless the caller owns ``patient_id`` (dashboard.py pattern)."""
    profile = (
        db.execute(select(PatientProfile).where(PatientProfile.user_id == user.id))
        .scalars()
        .first()
    )
    if profile is None or profile.id != patient_id:
        raise HTTPException(status_code=403, detail="Không có quyền với hồ sơ này.")


@router.get("/patients/{patient_id}/export")
def export_account_data(
    patient_id: str,
    request: Request,
    user: CurrentUser = Depends(_PatientOnly),
    db: Session = Depends(get_session),
) -> JSONResponse:
    """Download a JSON bundle of the caller's own data (GDPR portability)."""
    _assert_owns(db, user=user, patient_id=patient_id)

    generated_at = dt.datetime.now(dt.UTC)
    bundle = account_svc.build_export_bundle(
        db, user_id=user.id, patient_id=patient_id, generated_at=generated_at
    )

    audit.record(
        db,
        actor_type="user",
        actor_id=user.id,
        action="account_export",
        resource_type="patient_profile",
        resource_id=patient_id,
        ip_address=request.client.host if request.client else None,
    )
    db.commit()

    return JSONResponse(
        content=jsonable_encoder(bundle),
        headers={
            "Content-Disposition": f'attachment; filename="metocare-export-{patient_id}.json"'
        },
    )


@router.delete("/patients/{patient_id}/account", status_code=status.HTTP_200_OK)
def delete_account(
    patient_id: str,
    request: Request,
    user: CurrentUser = Depends(_PatientOnly),
    db: Session = Depends(get_session),
) -> dict:
    """Soft-delete + anonymize the caller's account (GDPR erasure). Idempotent."""
    _assert_owns(db, user=user, patient_id=patient_id)

    account_svc.delete_account(db, user_id=user.id, patient_id=patient_id)

    audit.record(
        db,
        actor_type="user",
        actor_id=user.id,
        action="account_deleted",
        resource_type="patient_profile",
        resource_id=patient_id,
        ip_address=request.client.host if request.client else None,
    )
    db.commit()

    return {"status": "deleted", "patient_id": patient_id}
