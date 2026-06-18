"""Booking schemas (T21 — Doctor Availability + Appointment Slot API).

Covers:
  AvailabilityCreate  — doctor creates a time slot
  AvailabilityOut     — serialised view of DoctorAvailability
  AppointmentCreate   — patient books a slot
  AppointmentOut      — serialised view of BookingAppointment
  AppointmentPatch    — doctor confirms/cancels or patient cancels
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, field_validator


class AvailabilityCreate(BaseModel):
    """Payload for POST /doctors/{doctor_id}/availability."""

    slot_start: dt.datetime
    slot_end: dt.datetime

    @field_validator("slot_end")
    @classmethod
    def end_after_start(cls, v: dt.datetime, info) -> dt.datetime:  # type: ignore[override]
        start = info.data.get("slot_start")
        if start is not None and v <= start:
            raise ValueError("slot_end must be after slot_start")
        return v


class AvailabilityOut(BaseModel):
    """Serialised DoctorAvailability row."""

    id: str
    doctor_id: str
    slot_start: dt.datetime
    slot_end: dt.datetime
    is_booked: bool
    created_at: dt.datetime

    model_config = ConfigDict(from_attributes=True)


class AppointmentCreate(BaseModel):
    """Payload for POST /appointments — patient books a slot."""

    doctor_id: str
    availability_id: str
    notes: str | None = None


class AppointmentOut(BaseModel):
    """Serialised BookingAppointment row."""

    id: str
    patient_id: str
    doctor_id: str
    availability_id: str
    status: str
    notes: str | None
    created_at: dt.datetime
    updated_at: dt.datetime

    model_config = ConfigDict(from_attributes=True)


class AppointmentPatch(BaseModel):
    """Payload for PATCH /appointments/{id}.

    Allowed status transitions:
    - DOCTOR: pending→confirmed, pending→cancelled, confirmed→cancelled,
              confirmed→completed
    - PATIENT: pending→cancelled (own appointment only)
    """

    status: str

    @field_validator("status")
    @classmethod
    def valid_status(cls, v: str) -> str:
        allowed = {"pending", "confirmed", "cancelled", "completed"}
        if v not in allowed:
            raise ValueError(f"status must be one of {allowed}")
        return v
