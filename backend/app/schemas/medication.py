"""Medication schemas (T15).

MedicationCreate — inbound payload for adding a patient medication record.
MedicationOut    — API response view including audit timestamp.

SAFETY NOTE: AI must NEVER create or modify medication records.
This is enforced at the RBAC layer (AI_SERVICE → 403 on all write endpoints).
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class MedicationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    dose: str | None = Field(None, max_length=128)
    frequency: str | None = Field(None, max_length=128)
    note: str | None = Field(None, max_length=1024)


class MedicationUpdate(BaseModel):
    """Partial update for a medication record (PR-D). All fields optional."""

    name: str | None = Field(None, min_length=1, max_length=255)
    dose: str | None = Field(None, max_length=128)
    frequency: str | None = Field(None, max_length=128)
    note: str | None = Field(None, max_length=1024)


class MedicationOut(BaseModel):
    id: str
    patient_id: str
    name: str
    dose: str | None
    frequency: str | None
    note: str | None
    created_at: dt.datetime

    model_config = ConfigDict(from_attributes=True)


class MedicationAdherenceCreate(BaseModel):
    scheduled_time: dt.datetime | None = None
    taken_at: dt.datetime | None = None
    skipped: bool = False
    note: str | None = Field(None, max_length=1024)


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
