"""Consultation-scoped read-access control (Doctor Marketplace MVP, T10).

A doctor may read a patient's data only when BOTH of the following hold:

1. **Care relationship** — an active ``ConsultationAccessGrant`` scoped to this
   consultation + patient. Created on payment, revoked when the consultation is
   COMPLETED or CANCELLED, or when the doctor is suspended/rejected.
2. **Patient consent** — an active ``ConsultationDataConsent`` for the same
   consultation (``app.services.consultation_consent``), which also decides
   *which categories* of data may be returned.

Having paid for a consultation is not consent, and consent does not by itself
create a care relationship. Every view is audited
(``doctor_view_patient_data``); denials are audited too, without PHI.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.models.care import Doctor
from app.models.consultation import (
    Consultation,
    ConsultationAccessGrant,
    DoctorVerificationStatus,
)
from app.services import audit, consultation_consent


@dataclass(frozen=True)
class DoctorConsultationAccess:
    """An authorised read: the consultation plus the categories consented to.

    Callers must treat ``allowed_categories`` as the complete authorisation and
    return nothing outside it.
    """

    consultation: Consultation
    allowed_categories: frozenset[str]

    @property
    def patient_id(self) -> str:
        return self.consultation.patient_id


def create_grant(db: Session, consultation: Consultation) -> ConsultationAccessGrant:
    """Create an active (granted, not revoked, not expired) access grant."""
    grant = ConsultationAccessGrant(
        consultation_id=consultation.id,
        doctor_id=consultation.doctor_id,
        patient_id=consultation.patient_id,
        granted_at=utcnow(),
    )
    db.add(grant)
    db.flush()
    return grant


def get_active_grant(
    db: Session, *, doctor_id: str, consultation_id: str, patient_id: str | None = None
) -> ConsultationAccessGrant | None:
    """Return the active grant scoped to consultation + doctor (+ patient), else None."""
    stmt = select(ConsultationAccessGrant).where(
        ConsultationAccessGrant.consultation_id == consultation_id,
        ConsultationAccessGrant.doctor_id == doctor_id,
        ConsultationAccessGrant.revoked_at.is_(None),
    )
    if patient_id is not None:
        stmt = stmt.where(ConsultationAccessGrant.patient_id == patient_id)
    now = utcnow()
    for grant in db.execute(stmt).scalars():
        if grant.is_active(now=now):
            return grant
    return None


def assert_doctor_can_view(
    db: Session, *, doctor: Doctor, consultation_id: str
) -> DoctorConsultationAccess:
    """Authorize a doctor to view the consultation's patient data.

    Raises 404 if the consultation is missing, 403 if the doctor does not own
    it, is not a verified active doctor, has no active scoped grant, or the
    patient has not given (or has revoked) consultation-specific sharing
    consent. On success, records a ``doctor_view_patient_data`` audit event and
    returns the consultation together with the consented categories.
    """
    consultation = db.get(Consultation, consultation_id)
    if consultation is None or consultation.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Consultation not found."
        )
    # Scope: the consultation must belong to this doctor.
    if consultation.doctor_id != doctor.id:
        _audit_denied(db, doctor.id, consultation_id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this consultation.",
        )
    # Defense-in-depth: only a currently VERIFIED + active doctor may view PHI.
    # A suspended/rejected/deactivated doctor is denied even if a stale grant
    # somehow survives (grants are also revoked on suspend/reject).
    if (
        doctor.verification_status != DoctorVerificationStatus.VERIFIED
        or not doctor.is_active
    ):
        _audit_denied(db, doctor.id, consultation_id, consultation.patient_id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is not permitted to view patient data.",
        )
    grant = get_active_grant(
        db,
        doctor_id=doctor.id,
        consultation_id=consultation_id,
        patient_id=consultation.patient_id,
    )
    if grant is None:
        _audit_denied(db, doctor.id, consultation_id, consultation.patient_id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active access grant for this consultation.",
        )
    # Second, independent condition: the patient's explicit, consultation-specific
    # sharing consent. A care relationship alone authorises nothing.
    try:
        allowed_categories = consultation_consent.require_active(
            db,
            consultation_id=consultation_id,
            doctor_id=doctor.id,
            patient_id=consultation.patient_id,
        )
    except consultation_consent.ConsentRequired:
        _audit_denied(db, doctor.id, consultation_id, consultation.patient_id)
        raise
    # Every successful view is audited.
    audit.record(
        db,
        actor_type="doctor",
        actor_id=doctor.id,
        action="doctor_view_patient_data",
        resource_type="patient_profile",
        resource_id=consultation.patient_id,
        severity="info",
    )
    db.commit()
    return DoctorConsultationAccess(
        consultation=consultation, allowed_categories=allowed_categories
    )


def revoke_on_end(db: Session, consultation: Consultation) -> None:
    """Revoke every active grant for a consultation (on COMPLETED / CANCELLED)."""
    now = utcnow()
    grants = db.execute(
        select(ConsultationAccessGrant).where(
            ConsultationAccessGrant.consultation_id == consultation.id,
            ConsultationAccessGrant.revoked_at.is_(None),
        )
    ).scalars()
    revoked_any = False
    for grant in grants:
        grant.revoked_at = now
        revoked_any = True
    if revoked_any:
        audit.record(
            db,
            actor_type="system",
            actor_id=None,
            action="consultation_access_revoke",
            resource_type="consultation",
            resource_id=consultation.id,
            severity="info",
        )
    db.flush()


def revoke_all_for_doctor(db: Session, doctor_id: str) -> int:
    """Revoke every active grant held by a doctor (on suspend / reject).

    Returns the number of grants revoked. Callers own the transaction/commit.
    """
    now = utcnow()
    grants = db.execute(
        select(ConsultationAccessGrant).where(
            ConsultationAccessGrant.doctor_id == doctor_id,
            ConsultationAccessGrant.revoked_at.is_(None),
        )
    ).scalars()
    revoked_count = 0
    for grant in grants:
        grant.revoked_at = now
        revoked_count += 1
    if revoked_count:
        audit.record(
            db,
            actor_type="admin",
            actor_id=None,
            action="consultation_access_revoke",
            resource_type="doctor",
            resource_id=doctor_id,
            severity="warning",
        )
    db.flush()
    return revoked_count


def _audit_denied(
    db: Session, doctor_id: str, consultation_id: str, patient_id: str | None = None
) -> None:
    audit.record(
        db,
        actor_type="doctor",
        actor_id=doctor_id,
        action="doctor_view_patient_data",
        resource_type="patient_profile",
        resource_id=patient_id or consultation_id,
        outcome="denied",
        severity="warning",
    )
    db.commit()
