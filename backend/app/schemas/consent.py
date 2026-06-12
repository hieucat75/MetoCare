"""Consent schemas."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel


class ConsentGrant(BaseModel):
    consent_type: str = "data_sharing"
    data_scope: str = "*"
    granted_to: str
    valid_until: dt.datetime | None = None


class ConsentOut(BaseModel):
    id: str
    patient_id: str
    data_scope: str
    granted_to: str

    model_config = {"from_attributes": True}
