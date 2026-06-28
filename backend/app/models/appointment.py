"""BookingAppointment model (T21 — Booking Scaffold).

Represents a patient's confirmed booking of a DoctorAvailability slot.

NOTE: The legacy ``Appointment`` model in ``care.py`` (table: ``appointments``)
is a different entity used for doctor handoff / encounter flow.
This model uses the table ``booking_appointments`` to avoid collision.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from ._mixins import TimestampMixin, UUIDPrimaryKey

# Valid status values for BookingAppointment
APPOINTMENT_STATUSES = frozenset({"pending", "confirmed", "cancelled", "completed"})


class BookingAppointment(UUIDPrimaryKey, TimestampMixin, Base):
    """A patient appointment booked against a DoctorAvailability slot.

    Status lifecycle:
      pending   → confirmed   (DOCTOR confirms)
      pending   → cancelled   (DOCTOR or PATIENT cancels)
      confirmed → completed   (DOCTOR marks complete)
      confirmed → cancelled   (DOCTOR cancels)
    PATIENT may only cancel their own *pending* appointment.
    """

    __tablename__ = "booking_appointments"

    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    doctor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    availability_id: Mapped[str] = mapped_column(
        ForeignKey("doctor_availability.id"), index=True, nullable=False, unique=True
    )
    # pending | confirmed | cancelled | completed
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    # Pre-visit summary / notes from the patient
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
