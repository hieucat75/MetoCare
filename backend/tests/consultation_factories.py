"""Shared factories for Doctor Marketplace (T10) tests.

Plain helper functions (not fixtures) so any test module can seed synthetic
doctors/patients + mint tokens without duplicating boilerplate.
"""

from __future__ import annotations

import os

from app.core.security import create_access_token
from app.domain.consultation_consent_policy import CATEGORIES as _POLICY_CATEGORIES
from app.models.care import Doctor
from app.models.consultation import DoctorVerificationStatus
from app.models.patient import PatientProfile
from app.models.user import User, UserRole

# Full data-sharing grant — what a patient who accepted the whole booking modal
# consents to. Tests needing a narrower grant pass their own subset.
CONSENT_ALL_CATEGORIES: list[str] = list(_POLICY_CATEGORIES)


def consent_payload(categories: list[str] | None = None, **overrides) -> dict:
    """A valid ``data_sharing_consent`` request body for POST /consultations.

    Both version stamps are required by the schema and must match the server's
    current values, so they default to the real ones here; a test exercising the
    stale-client path overrides them explicitly.
    """
    from app.domain.consultation_consent_policy import CONSENT_VERSION, POLICY_VERSION

    body = {
        "accepted": True,
        "categories": categories if categories is not None else CONSENT_ALL_CATEGORIES,
        "consent_version": CONSENT_VERSION,
        "policy_version": POLICY_VERSION,
        "source": "web",
    }
    body.update(overrides)
    return body


def restore_payload(categories: list[str] | None = None, **overrides) -> dict:
    """A valid body for POST /consultations/{id}/data-sharing-consent.

    Re-sharing is its own consent decision, so the client must echo the version
    stamps it rendered — the same rule booking follows.
    """
    from app.domain.consultation_consent_policy import CONSENT_VERSION, POLICY_VERSION

    body: dict = {
        "accepted": True,
        "consent_version": CONSENT_VERSION,
        "policy_version": POLICY_VERSION,
    }
    if categories is not None:
        body["categories"] = categories
    body.update(overrides)
    return body


def _uid() -> str:
    return os.urandom(5).hex()


def create_doctor(
    db,
    *,
    verification_status: str = DoctorVerificationStatus.VERIFIED,
    is_active: bool = True,
    fee: float = 200000.0,
    specialty: str = "Nội tiết",
    methods: str = "chat,video",
    full_name: str | None = None,
) -> Doctor:
    """Create a User(DOCTOR) + Doctor row and return the Doctor."""
    uid = _uid()
    name = full_name or f"BS Test {uid}"
    is_verified = verification_status == DoctorVerificationStatus.VERIFIED
    user = User(
        email=f"dr-{uid}@clinic.vn",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name=name,
        is_active=True,
        mfa_enabled=True,
    )
    db.add(user)
    db.flush()
    doctor = Doctor(
        user_id=user.id,
        full_name=name,
        specialty=specialty,
        consultation_fee=fee,
        consultation_methods=methods,
        verification_status=verification_status,
        is_verified=is_verified,
        is_active=is_active,
    )
    db.add(doctor)
    db.commit()
    db.refresh(doctor)
    return doctor


def create_patient(db, *, full_name: str | None = None) -> tuple[User, PatientProfile]:
    uid = _uid()
    name = full_name or f"Bệnh nhân {uid}"
    user = User(
        email=f"pt-{uid}@example.vn",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name=name,
        is_active=True,
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name=name, risk_segment="medium")
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return user, profile


def headers(user_id: str, role: str, *, mfa: bool = True) -> dict[str, str]:
    token = create_access_token(subject=user_id, role=role, mfa=mfa)
    return {"Authorization": f"Bearer {token}"}
