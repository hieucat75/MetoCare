"""Shared factories for Doctor Marketplace (T10) tests.

Plain helper functions (not fixtures) so any test module can seed synthetic
doctors/patients + mint tokens without duplicating boilerplate.
"""

from __future__ import annotations

import os

from app.core.security import create_access_token
from app.models.care import Doctor
from app.models.consultation import DoctorVerificationStatus
from app.models.patient import PatientProfile
from app.models.user import User, UserRole


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
