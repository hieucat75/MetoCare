"""Consent service — gate access to patient data (Data_Model_Overview §4.5).

A patient always has access to their own data. A third party (doctor/clinic)
must resolve to an active Consent with the right scope + grantee. Every access
decision is audited by the caller.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.models.governance import Consent
from app.models.patient import PatientProfile


class ConsentError(PermissionError):
    """Raised when access is denied by the consent gate."""


def grant(
    db: Session,
    *,
    patient_id: str,
    consent_type: str,
    data_scope: str,
    granted_to: str,
    valid_until: dt.datetime | None = None,
) -> Consent:
    consent = Consent(
        patient_id=patient_id,
        consent_type=consent_type,
        data_scope=data_scope,
        granted_to=granted_to,
        valid_until=valid_until,
    )
    db.add(consent)
    db.flush()
    return consent


def revoke(db: Session, consent_id: str, at: dt.datetime | None = None) -> bool:
    consent = db.get(Consent, consent_id)
    if consent is None:
        return False
    consent.revoked_at = at or utcnow()
    db.flush()
    return True


def has_access(
    db: Session,
    *,
    patient_id: str,
    requester_id: str,
    scope: str,
    at: dt.datetime | None = None,
) -> bool:
    """Return True if requester may read patient data in the given scope.

    The patient themself always has access (either the requester IS the patient
    principal, or the requester is the User who owns the PatientProfile).
    Otherwise an active matching consent is required.
    """
    if requester_id == patient_id:
        return True
    profile = db.get(PatientProfile, patient_id)
    if profile is not None and profile.user_id == requester_id:
        return True
    now = at or utcnow()
    stmt = select(Consent).where(
        Consent.patient_id == patient_id, Consent.granted_to == requester_id
    )
    for consent in db.execute(stmt).scalars():
        if consent.is_active(now, scope, requester_id):
            return True
    return False


def require_access(
    db: Session,
    *,
    patient_id: str,
    requester_id: str,
    scope: str,
    at: dt.datetime | None = None,
) -> None:
    if not has_access(db, patient_id=patient_id, requester_id=requester_id, scope=scope, at=at):
        raise ConsentError(
            f"Requester {requester_id} has no active consent for patient "
            f"{patient_id} scope '{scope}'."
        )
