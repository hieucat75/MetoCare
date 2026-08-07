"""Consultation-specific doctor data-sharing consent (grant, read, revoke).

This module is the ONLY place that decides whether a patient has authorised a
doctor to read their data for a given consultation. Every doctor-facing PHI
path must ask ``require_active`` and must honour the categories it returns.

Two independent conditions gate doctor PHI access, and both are required:

1. a care relationship — an active ``ConsultationAccessGrant``
   (``app.services.consultation_access``), and
2. this consent — an active ``ConsultationDataConsent`` for the same
   consultation, doctor and patient.

Neither substitutes for the other. Paying for a consultation does not imply
consent, and consent alone does not create a care relationship.

Audit records here carry identifiers, category keys and version stamps only —
never PHI.
"""

from __future__ import annotations

import datetime as dt

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.domain import consultation_consent_policy as policy
from app.models.consultation import Consultation
from app.models.consultation_consent import ConsultationDataConsent
from app.services import audit


class ConsentRequired(HTTPException):
    """403 — no active consultation-specific sharing consent."""

    def __init__(
        self, detail: str = "No active data-sharing consent for this consultation."
    ) -> None:
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


# ---------------------------------------------------------------------------
# Grant
# ---------------------------------------------------------------------------


def grant(
    db: Session,
    *,
    consultation: Consultation,
    categories: list[str] | tuple[str, ...] | None,
    source: str | None = None,
    client_app_version: str | None = None,
    locale: str | None = None,
    at: dt.datetime | None = None,
) -> ConsultationDataConsent:
    """Record the patient's explicit grant for *consultation*.

    Called inside the consultation-creation transaction, so the two commit or
    roll back together — there is no window in which a consultation exists
    without its consent, and none in which a consent points at a consultation
    that was never created.

    Raises 400 when the requested categories reduce to nothing: a grant that
    authorises no category is not consent, and silently storing one would let a
    client manufacture a row that looks like consent but shares nothing (or,
    worse, that a later reader mistakes for a full grant).
    """
    granted = policy.normalize_categories(categories)
    if not granted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one recognised data category must be granted.",
        )

    # The route requires the client to report both version stamps and rejects
    # any mismatch, so what is stored below is provably the version the patient
    # actually saw — not an assumption the server made on their behalf.
    now = at or utcnow()
    record = ConsultationDataConsent(
        consultation_id=consultation.id,
        patient_id=consultation.patient_id,
        doctor_id=consultation.doctor_id,
        purpose=policy.PURPOSE_DOCTOR_CONSULTATION,
        consent_version=policy.CONSENT_VERSION,
        policy_version=policy.POLICY_VERSION,
        categories=list(granted),
        granted_at=now,
        source=source,
        client_app_version=client_app_version,
        locale=locale,
    )
    db.add(record)
    db.flush()

    entry = audit.record(
        db,
        actor_type="patient",
        actor_id=consultation.patient_id,
        action="consultation_consent_granted",
        resource_type="consultation_data_consent",
        resource_id=record.id,
        severity="info",
        details={
            "consultation_id": consultation.id,
            "doctor_id": consultation.doctor_id,
            "purpose": policy.PURPOSE_DOCTOR_CONSULTATION,
            "consent_version": policy.CONSENT_VERSION,
            "policy_version": policy.POLICY_VERSION,
            "categories": list(granted),
            "source": source,
        },
    )
    record.audit_id = entry.id
    db.flush()
    return record


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def get_for_consultation(db: Session, consultation_id: str) -> ConsultationDataConsent | None:
    """Return the consent row for *consultation_id*, active or not."""
    return db.execute(
        select(ConsultationDataConsent).where(
            ConsultationDataConsent.consultation_id == consultation_id
        )
    ).scalar_one_or_none()


def get_active(
    db: Session,
    *,
    consultation_id: str,
    doctor_id: str,
    patient_id: str,
    at: dt.datetime | None = None,
) -> ConsultationDataConsent | None:
    """Return the ACTIVE consent for this exact (consultation, doctor, patient).

    The doctor and patient are matched explicitly rather than trusted from the
    consultation: a consent recorded for another doctor or another patient must
    never authorise this read, even if some other layer confused the rows.
    """
    record = get_for_consultation(db, consultation_id)
    if record is None:
        return None
    if record.doctor_id != doctor_id or record.patient_id != patient_id:
        return None
    if not record.is_active_at(at or utcnow(), current_consent_version=policy.CONSENT_VERSION):
        return None
    return record


def require_active(
    db: Session,
    *,
    consultation_id: str,
    doctor_id: str,
    patient_id: str,
    at: dt.datetime | None = None,
) -> frozenset[str]:
    """Return the granted categories, or raise 403.

    The returned set is the *complete* authorisation: a caller must expose only
    data belonging to these categories. An empty set is impossible here — it
    would have failed the active check — so callers never have to distinguish
    "no consent" from "consent to nothing".
    """
    record = get_active(
        db,
        consultation_id=consultation_id,
        doctor_id=doctor_id,
        patient_id=patient_id,
        at=at,
    )
    if record is None:
        raise ConsentRequired()
    return record.granted_categories()


# ---------------------------------------------------------------------------
# Revoke
# ---------------------------------------------------------------------------


def restore(
    db: Session,
    *,
    record: ConsultationDataConsent,
    actor_id: str,
    categories: list[str] | tuple[str, ...] | None = None,
    at: dt.datetime | None = None,
) -> ConsultationDataConsent:
    """Re-grant sharing the patient previously withdrew, on the same consultation.

    Revocation must not be a trap. A patient who mis-taps it on a paid,
    in-progress consultation would otherwise have bought a session the doctor
    can no longer be informed for, with no way back — the consultation is
    deliberately not cancelled, so "book again" is not a remedy.

    This is a NEW consent decision, not an undo: the version stamps are refreshed
    to what the patient is agreeing to now, and it is audited as its own grant
    event. The prior revocation stays in the audit trail.
    """
    granted = policy.normalize_categories(
        categories if categories is not None else list(record.granted_categories())
    )
    if not granted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one recognised data category must be granted.",
        )

    now = at or utcnow()
    record.revoked_at = None
    record.granted_at = now
    record.categories = list(granted)
    record.consent_version = policy.CONSENT_VERSION
    record.policy_version = policy.POLICY_VERSION
    db.add(record)

    audit.record(
        db,
        actor_type="patient",
        actor_id=record.patient_id,
        action="consultation_consent_granted",
        resource_type="consultation_data_consent",
        resource_id=record.id,
        severity="info",
        details={
            "consultation_id": record.consultation_id,
            "doctor_id": record.doctor_id,
            "purpose": record.purpose,
            "consent_version": policy.CONSENT_VERSION,
            "policy_version": policy.POLICY_VERSION,
            "categories": list(granted),
            "restored": True,
        },
    )
    db.flush()
    return record


def revoke(
    db: Session,
    *,
    record: ConsultationDataConsent,
    actor_id: str,
    at: dt.datetime | None = None,
) -> bool:
    """Revoke *record*. Returns False when it was already revoked.

    Revocation is deliberately narrow: it stops future reads. It does not
    delete the consent row, the consultation, the doctor's notes, or any other
    clinical or audit record — those have their own retention rules, and a
    patient withdrawing data sharing must not silently erase the record that a
    consultation happened or what a doctor advised during it.
    """
    if record.revoked_at is not None:
        return False
    record.revoked_at = at or utcnow()
    db.add(record)
    audit.record(
        db,
        actor_type="patient",
        actor_id=actor_id,
        action="consultation_consent_revoked",
        resource_type="consultation_data_consent",
        resource_id=record.id,
        severity="warning",
        details={
            "consultation_id": record.consultation_id,
            "doctor_id": record.doctor_id,
            "purpose": record.purpose,
            "consent_version": record.consent_version,
        },
    )
    db.flush()
    return True
