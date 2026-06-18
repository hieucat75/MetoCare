"""Nutrition log model (T18).

NutritionLog records a meal/snack eaten by a patient. It is a simple
free-text log with optional structured fields (meal type, calorie estimate).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from ._mixins import TimestampMixin, UUIDPrimaryKey


class NutritionLog(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "nutrition_logs"

    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    # "breakfast" | "lunch" | "dinner" | "snack" | None
    meal_type: Mapped[str | None] = mapped_column(String(32))
    # free-text description of what was eaten
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # optional calorie estimate
    calories_kcal: Mapped[int | None] = mapped_column(Integer)
    # when the meal was eaten (not when it was logged)
    logged_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
