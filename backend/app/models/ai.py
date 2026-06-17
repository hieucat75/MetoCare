"""AI Models: AISession & AIClinicalRecommendation (Data_Model_Overview §3.2).

Splits AI conversations from structured recommendations as defined in
MEDICAL_SAFETY_PACKAGE.md §1.2 and §1.3.
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.crypto import EncryptedString
from app.core.database import Base

from ._mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKey


class RecommendationStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    REVIEWED       = "reviewed"
    ACCEPTED       = "accepted"
    REJECTED       = "rejected"
    SUPERSEDED     = "superseded"


class AISession(UUIDPrimaryKey, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "ai_sessions"

    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    encounter_id: Mapped[str | None] = mapped_column(
        ForeignKey("encounters.id"), index=True, nullable=True
    )
    # health_assistant / lifestyle_coach / lab_explanation / triage
    session_type: Mapped[str] = mapped_column(String(64), nullable=False)
    messages: Mapped[str | None] = mapped_column(EncryptedString)  # PHI: encrypted json transcript
    key_version: Mapped[int | None] = mapped_column(Integer, default=1)
    risk_level: Mapped[str | None] = mapped_column(String(16))  # low / moderate / high / critical
    escalated_to_doctor: Mapped[bool] = mapped_column(Boolean, default=False)
    escalation_reason: Mapped[str | None] = mapped_column(String(255))
    model_used: Mapped[str | None] = mapped_column(String(64))
    safety_flags: Mapped[str | None] = mapped_column(Text)  # JSON list of fired guardrail rules
    input_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    output_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    total_tokens: Mapped[int | None] = mapped_column(Integer, default=0)


# Compatibility alias
AIConversation = AISession


class AIClinicalRecommendation(UUIDPrimaryKey, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "ai_clinical_recommendations"

    session_id: Mapped[str] = mapped_column(
        ForeignKey("ai_sessions.id"), index=True, nullable=False
    )
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    encounter_id: Mapped[str | None] = mapped_column(
        ForeignKey("encounters.id"), index=True, nullable=True
    )
    # lab_interpretation / care_plan_draft / lifestyle_advice / triage_assessment / metabolic_score
    recommendation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str | None] = mapped_column(EncryptedString)  # PHI: encrypted content
    key_version: Mapped[int | None] = mapped_column(Integer, default=1)
    status: Mapped[RecommendationStatus] = mapped_column(
        String(32), default=RecommendationStatus.PENDING_REVIEW, nullable=False
    )
    reviewed_by_doctor_id: Mapped[str | None] = mapped_column(
        ForeignKey("doctors.id"), index=True, nullable=True
    )
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(nullable=True)
    ai_confidence: Mapped[float | None] = mapped_column(Float)
    safety_cleared: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    medical_disclaimer: Mapped[str | None] = mapped_column(Text)
