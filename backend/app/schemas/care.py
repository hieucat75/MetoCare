"""Doctor / Clinic / Appointment / CarePlan schemas."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Clinic
# ---------------------------------------------------------------------------

class ClinicCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    address: str | None = Field(None, max_length=512)
    phone: str | None = Field(None, max_length=32)


class ClinicOut(BaseModel):
    id: str
    name: str
    address: str | None
    phone: str | None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Doctor
# ---------------------------------------------------------------------------

class DoctorCreate(BaseModel):
    user_id: str | None = None
    clinic_id: str | None = None
    full_name: str = Field(..., min_length=1, max_length=255)
    specialty: str | None = Field(None, max_length=128)
    license_no: str | None = Field(None, max_length=64)


class DoctorUpdate(BaseModel):
    clinic_id: str | None = None
    full_name: str | None = Field(None, max_length=255)
    specialty: str | None = Field(None, max_length=128)
    license_no: str | None = Field(None, max_length=64)


class DoctorOut(BaseModel):
    id: str
    user_id: str | None
    clinic_id: str | None
    full_name: str
    specialty: str | None
    license_no: str | None

    model_config = {"from_attributes": True}


class DoctorSummaryOut(BaseModel):
    """Compact view for patient-facing booking list."""

    id: str
    full_name: str
    specialty: str | None
    clinic_id: str | None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Appointment / Booking
# ---------------------------------------------------------------------------

class AppointmentCreate(BaseModel):
    doctor_id: str
    scheduled_at: dt.datetime
    mode: str = Field("offline", pattern="^(online|offline)$")
    reason: str | None = Field(None, max_length=512)


class AppointmentUpdate(BaseModel):
    scheduled_at: dt.datetime | None = None
    mode: str | None = Field(None, pattern="^(online|offline)$")
    status: str | None = Field(
        None,
        pattern="^(requested|confirmed|cancelled|completed|no_show)$",
    )


class AppointmentOut(BaseModel):
    id: str
    patient_id: str
    doctor_id: str
    scheduled_at: dt.datetime
    mode: str
    status: str
    handoff_reason: str | None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Care Plan  (note-only scaffold; full schema deferred to Blueprint T4)
# ---------------------------------------------------------------------------

class CarePlanNoteCreate(BaseModel):
    """Doctor writes a care note after a consultation."""

    appointment_id: str | None = None
    note: str = Field(..., min_length=1, max_length=4096)
    instructions: str | None = Field(None, max_length=2048)
    follow_up_date: dt.date | None = None


class CarePlanNoteOut(BaseModel):
    id: str
    patient_id: str
    doctor_id: str
    appointment_id: str | None
    note: str
    instructions: str | None
    follow_up_date: dt.date | None

    model_config = {"from_attributes": True}
