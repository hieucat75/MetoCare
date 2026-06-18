"""Triage log model (T19).

TriageLog records a triage assessment run by the AI triage engine for a
patient. Each POST /ai/triage call by a PATIENT caller results in one row here.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from ._mixins import TimestampMixin, UUIDPrimaryKey


class TriageLog(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "triage_logs"

    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    # Free-text symptom description sent by the patient
    symptom_text: Mapped[str] = mapped_column(Text, nullable=False)
    # low / moderate / high / emergency
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    # self_monitor / suggest_booking / doctor_handoff / emergency_escalation
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    # JSON list of red-flag strings (may be NULL / empty for non-emergency results)
    red_flags: Mapped[str | None] = mapped_column(Text)
    # AI-generated message to the patient
    message: Mapped[str | None] = mapped_column(Text)
