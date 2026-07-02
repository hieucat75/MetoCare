"""Consultation-scoped read-access control (Doctor Marketplace MVP, T10).

A doctor may read a patient's summary ONLY through an active
``ConsultationAccessGrant`` scoped to a specific consultation + patient. Every
view is audited (``doctor_view_patient_data``). Grants are created on payment and
revoked when the consultation is COMPLETED or CANCELLED.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.models.care import Doctor
from app.models.consultation import Consultation, ConsultationAccessGrant
from app.services import audit


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
) -> Consultation:
    """Authorize a doctor to view the consultation's patient data.

    Raises 404 if the consultation is missing, 403 if the doctor does not own it
    or has no active scoped grant. On success, records a
    ``doctor_view_patient_data`` audit event and returns the consultation.
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
    return consultation


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
