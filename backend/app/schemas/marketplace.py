"""Marketplace schemas (T10).

Public-facing doctor cards/detail for patients. No auth/PHI/payout internals are
exposed — only listing data a patient needs to choose a doctor.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel


class DoctorCardOut(BaseModel):
    """Compact card used in marketplace browse lists."""

    id: str
    full_name: str
    specialty: str | None
    avatar_url: str | None
    consultation_fee: float | None
    hospital_name: str | None
    years_experience: int | None
    languages: str | None
    consultation_methods: str | None
    rating_avg: float
    rating_count: int

    model_config = {"from_attributes": True}


class DoctorDetailOut(DoctorCardOut):
    """Full detail view for a single doctor."""

    bio: str | None
    next_available: dt.datetime | None = None
    disclaimer: str | None = None
