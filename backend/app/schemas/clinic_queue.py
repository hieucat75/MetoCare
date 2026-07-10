"""Clinic check-in & queue schemas (Clinic SaaS C1 M08).

Two deliberately different output shapes (QUEUE-02 / AC-M08-03):
- `ClinicQueueEntryOut` — staff view, full operational fields incl. the
  server-side-decrypted patient display name.
- `ClinicQueueDisplayEntryOut` — public-screen payload: queue number +
  masked initials + status + doctor name ONLY. No service, no full name,
  no patient_id — the Stop Gate "PHI on public screens" boundary is
  enforced by the schema shape itself, not by frontend omission.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


class ClinicQueueEntryOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    clinic_id: str
    branch_id: str
    patient_id: str
    appointment_id: str
    doctor_id: str | None
    service_date: dt.date
    queue_number: int
    status: str
    is_priority: bool
    priority_reason: str | None
    missed_call_count: int
    source: str
    checked_in_at: dt.datetime
    called_at: dt.datetime | None
    consultation_started_at: dt.datetime | None
    completed_at: dt.datetime | None
    left_at: dt.datetime | None
    # Enrichment (QUEUE-02 staff fields), computed server-side by the service.
    patient_display_name: str | None
    doctor_name: str | None
    service_name: str | None
    appointment_start_time: dt.datetime
    waiting_minutes: int
    # BR-M08-04: missed_call_count >= max_missed_calls on an active entry —
    # reception must resolve (call again or leave); doctors can no longer call.
    requires_reception_action: bool
    created_at: dt.datetime
    updated_at: dt.datetime


class ClinicQueueListOut(BaseModel):
    total: int
    items: list[ClinicQueueEntryOut]


class ClinicQueueDisplayEntryOut(BaseModel):
    queue_number: int
    # Masked initials, e.g. "Nguyễn Văn An" -> "N.V.A" (AC-M08-03).
    patient_initials: str
    status: str
    doctor_name: str | None


class ClinicQueueDisplayOut(BaseModel):
    items: list[ClinicQueueDisplayEntryOut]


class ClinicQueueWalkInRequest(BaseModel):
    branch_id: str = Field(min_length=1)
    patient_id: str = Field(min_length=1)
    service_id: str = Field(min_length=1)
    doctor_id: str | None = None
    notes: str | None = Field(default=None, max_length=2000)


class ClinicQueuePriorityRequest(BaseModel):
    is_priority: bool
    # Required — BR-M08-02/AC-M08-04: priority is exclusively a human action
    # WITH a reason. The verbatim reason is stored on the row; audit records
    # only `reason_provided` (M07 PHI-audit discipline).
    reason: str = Field(min_length=1, max_length=500)
