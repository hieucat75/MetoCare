"""Symptom log schemas (T15).

SymptomLogCreate — inbound payload for logging a patient symptom.
SymptomLogOut    — API response view including audit timestamps.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class SymptomLogCreate(BaseModel):
    description: str = Field(..., min_length=1, max_length=2048)
    severity: int | None = Field(None, ge=0, le=10)
    reported_at: dt.datetime | None = None  # default: now (set in service)


class SymptomLogOut(BaseModel):
    id: str
    patient_id: str
    description: str
    severity: int | None
    reported_at: dt.datetime
    created_at: dt.datetime

    model_config = ConfigDict(from_attributes=True)
