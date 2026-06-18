"""Triage log schemas (T19).

TriageLogOut              — serialised view of one TriageLog row.
TriageLogHistoryResponse  — paginated history envelope for GET /patients/{id}/triage-history.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


class TriageLogOut(BaseModel):
    """Single triage log entry returned by the history endpoint."""

    id: str
    patient_id: str
    symptom_text: str
    risk_level: str
    action: str
    red_flags: list[Any]
    message: str | None
    created_at: dt.datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("red_flags", mode="before")
    @classmethod
    def parse_red_flags(cls, v: Any) -> list[Any]:
        """Accept a JSON string (from ORM) or an already-parsed list."""
        if v is None:
            return []
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, list) else []
            except (json.JSONDecodeError, ValueError):
                return []
        if isinstance(v, list):
            return v
        return []


class TriageLogHistoryResponse(BaseModel):
    """Response envelope for GET /patients/{patient_id}/triage-history."""

    patient_id: str
    total: int
    items: list[TriageLogOut]
