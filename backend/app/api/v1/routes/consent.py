"""Consent management routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import current_user_id, get_session
from app.schemas.common import Message
from app.schemas.consent import ConsentGrant, ConsentOut
from app.services import audit, consent

router = APIRouter(prefix="/patients/{patient_id}/consents", tags=["consent"])


@router.post("", response_model=ConsentOut, status_code=201)
def grant_consent(
    patient_id: str,
    payload: ConsentGrant,
    requester_id: str = Depends(current_user_id),
    db: Session = Depends(get_session),
) -> ConsentOut:
    # Only the patient principal may grant consent over their own data.
    if requester_id != patient_id:
        profile_owner = consent.has_access(
            db, patient_id=patient_id, requester_id=requester_id, scope="__owner__"
        )
        if not profile_owner:
            raise HTTPException(status_code=403, detail="Only the patient may grant consent.")
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
        actor_id=requester_id,
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
    requester_id: str = Depends(current_user_id),
    db: Session = Depends(get_session),
) -> Message:
    ok = consent.revoke(db, consent_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Consent not found.")
    audit.record(
        db,
        actor_type="user",
        actor_id=requester_id,
        action="revoke_consent",
        resource_type="consent",
        resource_id=consent_id,
    )
    db.commit()
    return Message(message="revoked")
