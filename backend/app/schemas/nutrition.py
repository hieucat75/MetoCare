"""Nutrition log schemas (T18).

NutritionLogCreate — inbound payload for logging a patient meal/snack.
NutritionLogOut    — API response view including audit timestamps.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class NutritionLogCreate(BaseModel):
    description: str = Field(..., min_length=1, max_length=4096)
    meal_type: str | None = Field(
        None,
        pattern=r"^(breakfast|lunch|dinner|snack)$",
        description="One of: breakfast, lunch, dinner, snack",
    )
    calories_kcal: int | None = Field(None, ge=0, le=99999)
    logged_at: dt.datetime | None = None  # defaults to now in service layer


class NutritionLogOut(BaseModel):
    id: str
    patient_id: str
    description: str
    meal_type: str | None
    calories_kcal: int | None
    logged_at: dt.datetime
    created_at: dt.datetime

    model_config = ConfigDict(from_attributes=True)
