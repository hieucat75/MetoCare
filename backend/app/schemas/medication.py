"""Medication schemas (T15).

MedicationCreate — inbound payload for adding a patient medication record.
MedicationOut    — API response view including audit timestamp.

SAFETY NOTE: AI must NEVER create or modify medication records.
This is enforced at the RBAC layer (AI_SERVICE → 403 on all write endpoints).
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MedicationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    dose: str | None = Field(None, max_length=128)
    frequency: str | None = Field(None, max_length=128)
    note: str | None = Field(None, max_length=1024)


class MedicationUpdate(BaseModel):
    """Partial update for a medication record (PR-D). All fields optional.

    P0 (PR-S2): also accepts a lifecycle transition. RBAC rules for the
    target state (Plan §6.1 — e.g. on_hold is doctor-only) are enforced in
    the service layer, not here.
    """

    name: str | None = Field(None, min_length=1, max_length=255)
    dose: str | None = Field(None, max_length=128)
    frequency: str | None = Field(None, max_length=128)
    note: str | None = Field(None, max_length=1024)
    lifecycle_status: str | None = Field(None, max_length=32)
    status_reason: str | None = Field(None, max_length=1024)


class MedicationOut(BaseModel):
    id: str
    patient_id: str
    name: str
    dose: str | None
    frequency: str | None
    note: str | None
    created_at: dt.datetime

    # P0 additive fields (Plan §5.1) — existing clients ignore unknown keys.
    lifecycle_status: str = "active"
    verification_status: str = "patient_reported"
    source_type: str = "patient_manual"
    medication_category: str = "conventional_drug"
    status_reason: str | None = None

    model_config = ConfigDict(from_attributes=True)


class NonAdherenceReportIn(BaseModel):
    """Body for POST /medications/{id}/report-non-adherence (Plan §5.4)."""

    note: str | None = Field(None, max_length=1024)


class MedicationAdherenceCreate(BaseModel):
    scheduled_time: dt.datetime | None = None
    taken_at: dt.datetime | None = None
    skipped: bool = False
    note: str | None = Field(None, max_length=1024)

    @model_validator(mode="after")
    def taken_and_skipped_are_exclusive(self) -> MedicationAdherenceCreate:
        if self.taken_at is not None and self.skipped:
            raise ValueError("A dose cannot be both taken and skipped.")
        return self


class MedicationAdherenceOut(BaseModel):
    id: str
    medication_id: str
    patient_id: str
    scheduled_time: dt.datetime | None
    taken_at: dt.datetime | None
    skipped: bool
    note: str | None
    created_at: dt.datetime

    model_config = ConfigDict(from_attributes=True)


class TodayMedicationOut(BaseModel):
    medication_id: str
    name: str
    dose: str | None
    frequency: str | None
    taken_today: bool
    skipped_today: bool
    last_taken_at: dt.datetime | None


class AdherenceSummaryOut(BaseModel):
    total_doses_logged: int
    taken: int
    skipped: int
    adherence_rate: float
    today_medications: list[TodayMedicationOut]
    current_streak: int
    longest_streak: int
    weekly_rate: float
    last_taken_at: dt.datetime | None
