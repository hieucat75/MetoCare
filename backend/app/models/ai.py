"""AI Models: AISession & AIClinicalRecommendation (Data_Model_Overview §3.2).

Splits AI conversations from structured recommendations as defined in
MEDICAL_SAFETY_PACKAGE.md §1.2 and §1.3.
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.core.crypto import EncryptedString
from app.core.database import Base

from ._mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKey


class RecommendationStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    REVIEWED       = "reviewed"
    ACCEPTED       = "accepted"
    REJECTED       = "rejected"
    SUPERSEDED     = "superseded"
    REQUEST_INFO   = "request_info"


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


# Statuses forbidden for AI-originated creation (must be in pending_review initially)
_AI_FORBIDDEN_STATUSES: frozenset[str] = frozenset({"accepted", "reviewed", "superseded"})


class AIClinicalRecommendation(UUIDPrimaryKey, TimestampMixin, SoftDeleteMixin, Base):
    """Structured clinical output from an AI session.

    SAFETY INVARIANT (C1):
    - AI code paths must use `AIClinicalRecommendation.create_from_ai()` which enforces
      status=pending_review and safety_cleared=False.
    - Direct ORM construction is permitted ONLY for doctor-initiated corrections or tests
      using `_bypass_guard=True` (test fixture use only).
    - The `@validates` hook rejects forbidden status values at object-creation time.
    """

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
    status: Mapped[str] = mapped_column(
        String(32), default=RecommendationStatus.PENDING_REVIEW, nullable=False
    )
    reviewed_by_doctor_id: Mapped[str | None] = mapped_column(
        ForeignKey("doctors.id"), index=True, nullable=True
    )
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(nullable=True)
    ai_confidence: Mapped[float | None] = mapped_column(Float)
    safety_cleared: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    medical_disclaimer: Mapped[str | None] = mapped_column(Text)

    # ------------------------------------------------------------------ #
    # C1 GUARD: validates runs on __init__ attribute assignment            #
    # ------------------------------------------------------------------ #
    @validates("status")
    def _validate_status_not_forbidden_on_init(self, key: str, value: str) -> str:
        """Reject forbidden status values at the ORM layer.

        This fires on every attribute assignment (including __init__).
        The DoctorReviewService bypasses this validator via direct SQL UPDATE,
        not ORM attribute assignment, so doctor review transitions still work.
        """
        # Allow None (will be caught by nullable=False later)
        if value is None:
            return value  # type: ignore[return-value]
        norm = str(value).lower()
        if norm in _AI_FORBIDDEN_STATUSES:
            raise ValueError(
                f"AIClinicalRecommendation.status cannot be set to '{value}' at construction. "
                "Only 'pending_review' or 'rejected' are valid initial states. "
                "Use DoctorReviewService.review() to transition to accepted/reviewed."
            )
        return value

    @validates("safety_cleared")
    def _validate_safety_cleared_false_on_init(self, key: str, value: bool) -> bool:  # noqa: FBT001
        """Reject safety_cleared=True at construction time.

        Only DoctorReviewService.review(action='accept') may set this True
        via direct SQL UPDATE after doctor authentication.
        """
        if value is True:
            raise ValueError(
                "AIClinicalRecommendation.safety_cleared cannot be set True at construction. "
                "Only DoctorReviewService.review(action='accept') may clear safety."
            )
        return value

    @classmethod
    def create_from_ai(
        cls,
        *,
        session_id: str,
        patient_id: str,
        recommendation_type: str,
        content: str | None = None,
        encounter_id: str | None = None,
        ai_confidence: float | None = None,
        medical_disclaimer: str | None = None,
    ) -> AIClinicalRecommendation:
        """Factory for AI-originated recommendations.

        Enforces C1: status=pending_review, safety_cleared=False.
        This is the ONLY constructor AI service code paths should call.
        """
        return cls(
            session_id=session_id,
            patient_id=patient_id,
            recommendation_type=recommendation_type,
            content=content,
            encounter_id=encounter_id,
            ai_confidence=ai_confidence,
            medical_disclaimer=medical_disclaimer,
            # These are the only valid initial values — validated by @validates hooks
            status=RecommendationStatus.PENDING_REVIEW,
            safety_cleared=False,
        )
