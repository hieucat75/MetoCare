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


class User(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False, length=32), default=UserRole.PATIENT, nullable=False
    )
    full_name: Mapped[str | None] = mapped_column(EncryptedString)  # PHI: identity
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # TOTP shared secret, encrypted at rest (set during MFA enrollment).
    mfa_secret: Mapped[str | None] = mapped_column(EncryptedString)
