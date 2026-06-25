"""Consent management routes.

RBAC hardening (T9):
  POST   /consents       — PATIENT only (P0 legal requirement: only the patient
                           may grant consent over their own data)
  DELETE /consents/{id}  — PATIENT only (P0 legal requirement: only the patient
                           may revoke their own consent)

T18A additions:
  GET    /consents       — PATIENT or ADMIN only (list patient's own consents)

DOCTOR / CLINIC_ADMIN / INTERNAL_ADMIN / SUPER_ADMIN / AI_SERVICE are all
blocked from grant and revoke endpoints. This is a hard legal requirement under
Luật BVDLCN Vietnam 2026 — do not relax.

PATIENT ownership: the token's user.id must map to the PatientProfile identified
by patient_id (profile.user_id == user.id). This replaces the previous fragile
has_access(scope="__owner__") check.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, current_user, get_session, require_roles
from app.core.clock import utcnow
from app.models.governance import Consent as ConsentModel
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


# ---------------------------------------------------------------------------
# T18A — GET /patients/{patient_id}/consents
# ---------------------------------------------------------------------------

@router.get("", response_model=list[ConsentOut], summary="List consents for a patient")
def list_consents(
    patient_id: str,
    active_only: bool = Query(
        default=True, description="Filter to active (non-revoked) consents only"
    ),
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> list[ConsentOut]:
    """Return consents for *patient_id*.

    Access rules:
    - **PATIENT** — own consents only (ownership check via user_id).
    - **INTERNAL_ADMIN / SUPER_ADMIN** — unrestricted.
    - **DOCTOR / CLINIC_ADMIN / AI_SERVICE** — always 403 (legal requirement:
      third parties must not enumerate which other parties have consent access).
    """
    allowed_roles = {UserRole.PATIENT, UserRole.INTERNAL_ADMIN, UserRole.SUPER_ADMIN}
    if user.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the patient or an administrator may list consent records.",
        )

    profile = db.get(PatientProfile, patient_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Patient not found.")

    if user.role == UserRole.PATIENT and profile.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You may only view your own consent records.",
        )

    stmt = select(ConsentModel).where(ConsentModel.patient_id == patient_id)
    if active_only:
        now = utcnow()
        stmt = stmt.where(
            (ConsentModel.revoked_at.is_(None)) | (ConsentModel.revoked_at > now),
        )
    records = db.execute(stmt).scalars().all()
    return [ConsentOut.model_validate(r) for r in records]


# ---------------------------------------------------------------------------
# POST /patients/{patient_id}/consents (grant)
# ---------------------------------------------------------------------------

def _validate_granted_to(granted_to: str, db: Session) -> None:
    """granted_to must be the user_id of an active DOCTOR. AC-11."""
    from sqlalchemy import select as _select

    from app.models.user import User as _User
    from app.models.user import UserRole as _UserRole
    target = db.execute(
        _select(_User).where(
            _User.id == granted_to,
            _User.role == _UserRole.DOCTOR,
            _User.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="granted_to must be the user_id of an active doctor.",
        )


@router.post("", response_model=ConsentOut, status_code=201)
def grant_consent(
    patient_id: str,
    payload: ConsentGrant,
    user: CurrentUser = Depends(require_roles(UserRole.PATIENT)),
    db: Session = Depends(get_session),
) -> ConsentOut:
    _enforce_consent_ownership(patient_id, user, db)
    _validate_granted_to(payload.granted_to, db)
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


# ---------------------------------------------------------------------------
# DELETE /patients/{patient_id}/consents/{consent_id} (revoke)
# ---------------------------------------------------------------------------

@router.delete("/{consent_id}", response_model=Message)
def revoke_consent(
    patient_id: str,
    consent_id: str,
    user: CurrentUser = Depends(require_roles(UserRole.PATIENT)),
    db: Session = Depends(get_session),
) -> Message:
    _enforce_consent_ownership(patient_id, user, db)
    # Cross-patient ownership check: verify this consent belongs to the requesting patient.
    consent_rec = db.get(ConsentModel, consent_id)
    if consent_rec is None:
        raise HTTPException(status_code=404, detail="Consent not found.")
    patient_profile = db.execute(
        select(PatientProfile).where(PatientProfile.user_id == user.id)
    ).scalar_one_or_none()
    if patient_profile is None or consent_rec.patient_id != patient_profile.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You may only revoke your own consents.",
        )
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
