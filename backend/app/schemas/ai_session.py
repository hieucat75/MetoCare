"""AI Session request/response schemas.

`AISessionOut` and `AIClinicalRecommendationOut` live in `schemas.clinical`
(they are defined there alongside other clinical read schemas).  This module
holds only the **write-side** (input) schema for session creation.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AISessionCreate(BaseModel):
    patient_id: str
    encounter_id: str | None = None
    session_type: str = Field(..., max_length=64)
