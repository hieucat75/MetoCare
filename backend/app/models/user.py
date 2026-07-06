"""User & identity models (Data_Model_Overview §3.1, Technical_Architecture §4.7)."""

from __future__ import annotations

import enum

from sqlalchemy import Boolean, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.crypto import EncryptedString
from app.core.database import Base

from ._mixins import TimestampMixin, UUIDPrimaryKey


class UserRole(enum.StrEnum):
    PATIENT = "patient"
    DOCTOR = "doctor"
    CLINIC_ADMIN = "clinic_admin"
    INTERNAL_ADMIN = "internal_admin"
    MEDICAL_REVIEWER = "medical_reviewer"
    SUPER_ADMIN = "super_admin"
    AI_SERVICE = "ai_service"  # Internal service account for AI system operations


# Roles for which MFA is mandatory before accessing protected resources.
# DOCTOR is deliberately NOT forced: mandatory enrollment blocked sales-led
# onboarding. Doctors may still enroll MFA voluntarily via /auth/mfa/enroll.
MFA_REQUIRED_ROLES = frozenset(
    {
        UserRole.CLINIC_ADMIN,
        UserRole.INTERNAL_ADMIN,
        UserRole.MEDICAL_REVIEWER,
        UserRole.SUPER_ADMIN,
    }
)


class User(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "users"

    # Email is the identifier for admin/doctor accounts. Patients self-register
    # with a phone number instead, so email is nullable (one of email/phone set).
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    # VN mobile in canonical +84 form; primary identifier for patient self-signup.
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, index=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False, length=32), default=UserRole.PATIENT, nullable=False
    )
    # Optional display field — a failed decrypt falls back to None (UI already
    # falls back further to email/phone; see lib/auth/userDisplay.ts).
    full_name: Mapped[str | None] = mapped_column(
        EncryptedString(on_decrypt_failure="none")
    )  # PHI: identity
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # TOTP shared secret, encrypted at rest (set during MFA enrollment). A
    # failed decrypt falling back to None fails CLOSED (verify_totp treats a
    # missing secret as "no valid code"), so "none" is safe here too.
    mfa_secret: Mapped[str | None] = mapped_column(EncryptedString(on_decrypt_failure="none"))
    # PR-F: notification preferences (in-app delivery toggles).
    notify_medication: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_lab_results: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_doctor_messages: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
