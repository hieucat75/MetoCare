"""AIConversation model (Data_Model_Overview §3.2).

Every AI interaction logs intent, model, safety_flags, risk_level, escalation —
required by AI_Safety_Guardrail.md §4.8 (logging and review).
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from ._mixins import TimestampMixin, UUIDPrimaryKey


class AIConversation(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "ai_conversations"

    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    intent: Mapped[str | None] = mapped_column(String(64))
    messages: Mapped[str | None] = mapped_column(Text)  # serialized transcript
    risk_level: Mapped[str | None] = mapped_column(String(16))
    escalated_to_doctor: Mapped[bool] = mapped_column(Boolean, default=False)
    model_used: Mapped[str | None] = mapped_column(String(64))
    safety_flags: Mapped[str | None] = mapped_column(Text)  # serialized list
