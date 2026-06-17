"""Consent management routes.

RBAC hardening (T9):
  POST   /consents       — PATIENT only (P0 legal requirement: only the patient
                           may grant consent over their own data)
  DELETE /consents/{id}  — PATIENT only (P0 legal requirement: only the patient
                           may revoke their own consent)

DOCTOR / CLINIC_ADMIN / INTERNAL_ADMIN / SUPER_ADMIN / AI_SERVICE are all
blocked from grant and revoke endpoints. This is a hard legal requirement under
Luật BVDLCN Vietnam 2026 — do not relax.

PATIENT ownership: the token's user.id must map to the PatientProfile identified
by patient_id (profile.user_id == user.id). This replaces the previous fragile
has_access(scope="__owner__") check.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_session, require_roles
from app.models.patient import PatientProfile
from app.models.user import UserRole
from app.schemas.common import Message
from app.schemas.consent import ConsentGrant, ConsentOut
from app.services import audit, consent

router = APIRouter(prefix="/patients/{patient_id}/consents", tags=["consent"])


def _enforce_consent_ownership(patient_id: str, user: CurrentUser, db: Session) -> None:
    """Verify that the authenticated PATIENT token owns the PatientProfile.

    Raises 404 if the profile doesn't exist, 403 if it belongs to a different user.
    """
    profile = db.get(PatientProfile, patient_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Patient not found.")
    if profile.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You may only manage consent for your own patient profile.",
        )


@router.post("", response_model=ConsentOut, status_code=201)
def grant_consent(
    patient_id: str,
    payload: ConsentGrant,
    user: CurrentUser = Depends(require_roles(UserRole.PATIENT)),
    db: Session = Depends(get_session),
) -> ConsentOut:
    _enforce_consent_ownership(patient_id, user, db)
    c = consent.grant(
        db,
        patient_id=patient_id,
        consent_type=payload.consent_type,
        data_scope=payload.data_scope,
        granted_to=payload.granted_to,
        valid_until=payload.valid_until,
    )
    audit.record(
        db,
        actor_type="user",
        actor_id=user.id,
        action="grant_consent",
        resource_type="consent",
        resource_id=c.id,
    )
    db.commit()
    return ConsentOut.model_validate(c)


@router.delete("/{consent_id}", response_model=Message)
def revoke_consent(
    patient_id: str,
    consent_id: str,
    user: CurrentUser = Depends(require_roles(UserRole.PATIENT)),
    db: Session = Depends(get_session),
) -> Message:
    _enforce_consent_ownership(patient_id, user, db)
    ok = consent.revoke(db, consent_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Consent not found.")
    audit.record(
        db,
        actor_type="user",
        actor_id=user.id,
        action="revoke_consent",
        resource_type="consent",
        resource_id=consent_id,
    )
    db.commit()
    return Message(message="revoked")
