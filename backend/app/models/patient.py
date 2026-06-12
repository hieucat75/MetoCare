"""PatientProfile model (Data_Model_Overview §3.2).

Classification: Sensitive health data. Access must be consent-gated + audited
(enforced at the service layer, not the model).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Date, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from ._mixins import TimestampMixin, UUIDPrimaryKey


class PatientProfile(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "patient_profiles"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255))
    dob: Mapped[dt.date | None] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(String(16))
    height_cm: Mapped[float | None] = mapped_column(Float)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    waist_cm: Mapped[float | None] = mapped_column(Float)
    # Stored as text/JSON-ish for the foundation; structured tables come later.
    known_conditions: Mapped[str | None] = mapped_column(Text)
    allergies: Mapped[str | None] = mapped_column(Text)
    family_history: Mapped[str | None] = mapped_column(Text)
    lifestyle_profile: Mapped[str | None] = mapped_column(Text)
    risk_segment: Mapped[str | None] = mapped_column(String(64))
