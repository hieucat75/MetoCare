"""DoctorAvailability model (T21 — Booking Scaffold).

Represents a time slot that a doctor has made available for patient bookings.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from ._mixins import _NOW, UUIDPrimaryKey


class DoctorAvailability(UUIDPrimaryKey, Base):
    """A single bookable time slot offered by a doctor.

    - ``is_booked`` flips to True when a BookingAppointment is created against
      this slot.  Double-booking is prevented at the service layer.
    - Naive UTC datetimes are stored (no timezone offset); callers must convert.
    """

    __tablename__ = "doctor_availability"

    doctor_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )
    slot_start: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=False), nullable=False
    )
    slot_end: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=False), nullable=False
    )
    is_booked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW, nullable=False
    )
