"""Patient profile service — read and update PatientProfile with RBAC + audit.

Security_Compliance_Framework + Data_Model_Overview §3.2.

Rules enforced here (not in the route):
  - 404  if the PatientProfile does not exist.
  - 403  if the requester is not authorised to access / mutate the record.
  - audit.record() on every successful PATCH.

RBAC matrix:
  GET:   PATIENT (own), DOCTOR (consent-gated), INTERNAL_ADMIN, SUPER_ADMIN
  PATCH: PATIENT (own), DOCTOR, INTERNAL_ADMIN, SUPER_ADMIN
  Blocked from both: AI_SERVICE, CLINIC_ADMIN (and any unlisted role).
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.models.patient import PatientProfile
from app.models.user import UserRole
from app.services import audit
from app.services.consent import ConsentError, require_access

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_BLOCKED_ROLES: frozenset[str] = frozenset({
    UserRole.AI_SERVICE,
    UserRole.CLINIC_ADMIN,
})

_ADMIN_ROLES: frozenset[str] = frozenset({
    UserRole.INTERNAL_ADMIN,
    UserRole.SUPER_ADMIN,
})


def _fetch_profile(db: Session, patient_id: str) -> PatientProfile:
    profile = db.get(PatientProfile, patient_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found.",
        )
    return profile


def _check_blocked(role: str) -> None:
    """Raise 403 immediately for roles that are never allowed."""
    if role in _BLOCKED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{role}' is not permitted to access patient profiles.",
        )


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------


def get_profile(
    db: Session,
    *,
    patient_id: str,
    requester: CurrentUser,
) -> PatientProfile:
    """Return the PatientProfile for *patient_id*, enforcing RBAC.

    Raises:
        404  — patient does not exist.
        403  — requester is blocked or does not own / have consent for the record.
    """
    _check_blocked(requester.role)

    profile = _fetch_profile(db, patient_id)

    if requester.role in _ADMIN_ROLES:
        # INTERNAL_ADMIN / SUPER_ADMIN: unrestricted read
        return profile

    if requester.role == UserRole.PATIENT:
        # Patient may only read their own profile
        if profile.user_id != requester.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this patient profile.",
            )
        return profile

    if requester.role == UserRole.DOCTOR:
        # Doctor: consent-gated via consent service
        try:
            require_access(
                db,
                patient_id=patient_id,
                requester_id=requester.id,
                scope="profile",
            )
        except ConsentError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(exc),
            ) from exc
        return profile

    # Any other unlisted role is denied
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Role '{requester.role}' is not permitted to read patient profiles.",
    )


def update_profile(
    db: Session,
    *,
    patient_id: str,
    requester: CurrentUser,
    data: dict,
) -> PatientProfile:
    """Apply a partial update to the PatientProfile, with RBAC + audit.

    Raises:
        404  — patient does not exist.
        403  — requester is blocked or does not own the record.
    """
    _check_blocked(requester.role)

    profile = _fetch_profile(db, patient_id)

    # Ownership check for PATIENT
    if requester.role == UserRole.PATIENT:
        if profile.user_id != requester.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You may only update your own patient profile.",
            )

    elif requester.role not in (_ADMIN_ROLES | {UserRole.DOCTOR}):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{requester.role}' is not permitted to update patient profiles.",
        )

    # Apply only the fields that were explicitly set (exclude_unset handled by route)
    for field, value in data.items():
        setattr(profile, field, value)

    db.flush()

    # Audit record — required on every successful PATCH
    audit.record(
        db,
        actor_type=requester.role,
        actor_id=requester.id,
        action="update_profile",
        resource_type="patient_profile",
        resource_id=patient_id,
        outcome="success",
        severity="info",
    )

    db.commit()
    db.refresh(profile)
    return profile
