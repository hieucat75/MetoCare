"""Doctor / Clinic / Appointment models (Data_Model_Overview §3.1)."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from ._mixins import TimestampMixin, UUIDPrimaryKey


class Clinic(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "clinics"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(String(512))
    phone: Mapped[str | None] = mapped_column(String(32))


class Doctor(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "doctors"

    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    clinic_id: Mapped[str | None] = mapped_column(ForeignKey("clinics.id"), index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    specialty: Mapped[str | None] = mapped_column(String(128))
    license_no: Mapped[str | None] = mapped_column(String(64))


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
