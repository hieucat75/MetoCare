"""Doctor / Clinic / Appointment / CarePlan / Encounter models (Data_Model_Overview §3.1)."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.crypto import EncryptedString
from app.core.database import Base

from ._mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKey


class Clinic(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "clinics"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(String(512))
    phone: Mapped[str | None] = mapped_column(String(32))
    # Step 5: Clinic additional fields
    email: Mapped[str | None] = mapped_column(String(255))
    specialty_tags: Mapped[str | None] = mapped_column(Text)  # serialized or comma-separated tags
    operating_hours: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Doctor(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "doctors"

    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    clinic_id: Mapped[str | None] = mapped_column(ForeignKey("clinics.id"), index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    specialty: Mapped[str | None] = mapped_column(String(128))
    license_no: Mapped[str | None] = mapped_column(String(64))
    # Step 5: Doctor additional fields
    bio: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(String(512))
    consultation_fee: Mapped[float | None] = mapped_column(Float)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class DoctorClinic(Base):
    """Step 5: doctor_clinic junction table."""
    __tablename__ = "doctor_clinic"

    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctors.id"), primary_key=True)
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.id"), primary_key=True)
    role_at_clinic: Mapped[str | None] = mapped_column(String(64))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    joined_at: Mapped[dt.date] = mapped_column(Date, default=dt.date.today, nullable=False)
    left_at: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


class Appointment(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "appointments"

    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctors.id"), index=True, nullable=False)
    scheduled_at: Mapped[dt.datetime] = mapped_column(nullable=False)
    mode: Mapped[str] = mapped_column(String(16), default="offline")  # online/offline
    status: Mapped[str] = mapped_column(String(24), default="requested")
    # Set when triage escalates a case to a doctor (doctor handoff).
    handoff_reason: Mapped[str | None] = mapped_column(String(255))


class Encounter(UUIDPrimaryKey, TimestampMixin, SoftDeleteMixin, Base):
    """Step 4: Encounter model."""
    __tablename__ = "encounters"

    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    doctor_id: Mapped[str | None] = mapped_column(
        ForeignKey("doctors.id"), index=True, nullable=True
    )
    appointment_id: Mapped[str | None] = mapped_column(
        ForeignKey("appointments.id"), index=True, nullable=True
    )
    encounter_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # pending_review / in_progress / completed / cancelled
    status: Mapped[str] = mapped_column(String(32), default="pending_review", nullable=False)
    chief_complaint: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(EncryptedString)  # PHI: encrypted
    encounter_date: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=dt.datetime.utcnow
    )


class CarePlan(UUIDPrimaryKey, TimestampMixin, SoftDeleteMixin, Base):
    """Step 4: CarePlan model."""
    __tablename__ = "care_plans"

    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    encounter_id: Mapped[str | None] = mapped_column(
        ForeignKey("encounters.id"), index=True, nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str | None] = mapped_column(EncryptedString)  # PHI: encrypted content
    # DRAFT / PENDING_REVIEW / APPROVED / ACTIVE / SUPERSEDED / ARCHIVED / REJECTED
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", nullable=False)
    approved_by_doctor_id: Mapped[str | None] = mapped_column(
        ForeignKey("doctors.id"), index=True, nullable=True
    )
    approved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class BookingHealthSnapshot(UUIDPrimaryKey, Base):
    """Step 4: BookingHealthSnapshot model (append-only)."""
    __tablename__ = "booking_health_snapshots"

    appointment_id: Mapped[str] = mapped_column(
        ForeignKey("appointments.id"), index=True, nullable=False
    )
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    payload: Mapped[str] = mapped_column(EncryptedString, nullable=False)  # PHI: encrypted snapshot
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=dt.datetime.utcnow, nullable=False
    )
