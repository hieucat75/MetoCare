"""K2 Slice 1 dependencies — feature flag, object-level ownership, doctor
verification status (MEDICATION_K2_KNOWLEDGE_API_IMPLEMENTATION_PLAN.md §4,
§12; ADR-15 §K.1).

Read-only. No function here mutates any row.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, current_user, get_session
from app.core.feature_flags import FeatureFlag, is_enabled
from app.models.clinical import Medication
from app.models.consultation import DoctorVerificationStatus
from app.models.patient import PatientProfile
from app.services.doctor import get_doctor_by_user_id

_FEATURE_UNAVAILABLE_DETAIL = "Medication knowledge lookup is currently unavailable."


def require_medication_knowledge_read_enabled() -> None:
    """Router-level gate (ADR-15 §K.1) — mirrors
    `deps_clinic_saas.require_clinic_saas_enabled`. Fails closed: 503 when
    `FeatureFlag.MEDICATION_KNOWLEDGE_RETRIEVAL` is off, before any handler
    or service code runs."""
    if not is_enabled(FeatureFlag.MEDICATION_KNOWLEDGE_RETRIEVAL):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_FEATURE_UNAVAILABLE_DETAIL,
        )


def require_own_medication(
    medication_id: str,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> Medication:
    """Endpoint #1's object-level authorization (K2 plan §4, §12 BOLA
    threat model). `medication_id` must resolve to a non-soft-deleted
    medication owned by the authenticated caller's own `patient_profile.id`.

    Returns the SAME 404 whether the id doesn't exist, belongs to another
    patient, or is soft-deleted — deliberately, so the status code alone
    never leaks whether a given id exists (K2 plan §8, §12: a 403/404 split
    would itself be the leak). Never called with a role other than PATIENT
    already enforced upstream by `require_roles`, but does not itself
    trust that — it only ever proves ownership, nothing about role.

    Single JOIN query (not a two-step lookup) — a two-query "resolve
    medication, then separately resolve profile" shape would run one query
    for a nonexistent id and two for an existing-but-not-owned one, a
    query-count timing difference an attacker could sample even though the
    response itself is identical. One query removes that side channel.
    """
    medication = (
        db.query(Medication)
        .join(PatientProfile, PatientProfile.id == Medication.patient_id)
        .filter(
            Medication.id == medication_id,
            Medication.deleted_at.is_(None),
            PatientProfile.user_id == user.id,
        )
        .first()
    )
    if medication is not None:
        return medication
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def require_verified_doctor(
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> None:
    """Endpoint #2's verification-status gate (K2 plan §4, PTH decision
    2026-07-22): `require_roles(DOCTOR)` alone is not sufficient — the
    caller's own `Doctor.verification_status` must be `VERIFIED` AND
    `Doctor.is_active` must be `True`. Same established defense-in-depth
    pattern as `consultation.py:119` and `consultation_access.py:80-83`
    (the latter's own comment: "a suspended/rejected/deactivated doctor is
    denied even if a stale grant somehow survives") — added 2026-07-23
    after independent review flagged this endpoint as the one clinical-
    content access point in this codebase checking verification_status
    without also checking is_active. Same 403, same generic body,
    regardless of which of the three reasons (no Doctor row, not VERIFIED,
    not active) applies — never reveals which one to a caller who
    shouldn't have access at all."""
    doctor = get_doctor_by_user_id(db, user.id)
    if (
        doctor is None
        or doctor.verification_status != DoctorVerificationStatus.VERIFIED
        or not doctor.is_active
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized.",
        )
