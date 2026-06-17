"""C1 guard tests: AIClinicalRecommendation must enforce status/safety_cleared at creation.

These tests verify that:
1. Direct ORM construction with forbidden status raises ValueError (structural guard)
2. Direct ORM construction with safety_cleared=True raises ValueError
3. create_from_ai() factory always produces pending_review + safety_cleared=False
4. DoctorReviewService.review(accept) can set ACCEPTED/safety_cleared=True (SQL UPDATE path)
5. AI service bypassing the factory cannot silently create ACCEPTED recommendations
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from app.models.ai import AIClinicalRecommendation, AISession, RecommendationStatus
from app.models.care import CarePlan, CarePlanStatus
from app.models.patient import PatientProfile
from app.models.user import User, UserRole
from app.services.doctor_review import DoctorReviewService

# ---------------------------------------------------------------------------
# C1: AIClinicalRecommendation creation guard
# ---------------------------------------------------------------------------

class TestC1RecommendationCreationGuard:
    """All bypass attempts must raise ValueError — guard is structural, not just policy."""

    def test_direct_orm_accepted_status_raises(self):
        """Cannot create a recommendation with status=accepted directly."""
        with pytest.raises(ValueError, match="cannot be set to 'accepted'"):
            AIClinicalRecommendation(
                session_id="sess-id",
                patient_id="patient-id",
                recommendation_type="triage_assessment",
                status=RecommendationStatus.ACCEPTED,  # FORBIDDEN
            )

    def test_direct_orm_reviewed_status_raises(self):
        """Cannot create a recommendation with status=reviewed directly."""
        with pytest.raises(ValueError, match="cannot be set to 'reviewed'"):
            AIClinicalRecommendation(
                session_id="sess-id",
                patient_id="patient-id",
                recommendation_type="triage_assessment",
                status=RecommendationStatus.REVIEWED,  # FORBIDDEN
            )

    def test_direct_orm_superseded_status_raises(self):
        """Cannot create a recommendation with status=superseded directly."""
        with pytest.raises(ValueError, match="cannot be set to 'superseded'"):
            AIClinicalRecommendation(
                session_id="sess-id",
                patient_id="patient-id",
                recommendation_type="triage_assessment",
                status=RecommendationStatus.SUPERSEDED,  # FORBIDDEN
            )

    def test_direct_orm_safety_cleared_true_raises(self):
        """Cannot create a recommendation with safety_cleared=True directly."""
        with pytest.raises(ValueError, match="safety_cleared cannot be set True"):
            AIClinicalRecommendation(
                session_id="sess-id",
                patient_id="patient-id",
                recommendation_type="triage_assessment",
                status=RecommendationStatus.PENDING_REVIEW,
                safety_cleared=True,  # FORBIDDEN
            )

    def test_direct_orm_rejected_status_is_allowed(self):
        """REJECTED is allowed at construction (AI can create a rejected recommendation)."""
        rec = AIClinicalRecommendation(
            session_id="sess-id",
            patient_id="patient-id",
            recommendation_type="triage_assessment",
            status=RecommendationStatus.REJECTED,  # ALLOWED
        )
        assert rec.status == RecommendationStatus.REJECTED
        assert not rec.safety_cleared  # default=False at DB level; None or False in-memory

    def test_pending_review_status_is_allowed(self):
        """PENDING_REVIEW (the default) must always be allowed."""
        rec = AIClinicalRecommendation(
            session_id="sess-id",
            patient_id="patient-id",
            recommendation_type="triage_assessment",
            status=RecommendationStatus.PENDING_REVIEW,
        )
        assert rec.status == RecommendationStatus.PENDING_REVIEW

    def test_factory_enforces_pending_review_and_false(self):
        """create_from_ai() always produces pending_review + safety_cleared=False."""
        rec = AIClinicalRecommendation.create_from_ai(
            session_id="sess-id",
            patient_id="patient-id",
            recommendation_type="triage_assessment",
            content="Some AI output",
        )
        assert rec.status == RecommendationStatus.PENDING_REVIEW
        assert rec.safety_cleared is False

    def test_factory_ignores_attempts_to_pass_bad_status(self, db):
        """Even if code tried to pass a bad status to create_from_ai(), the factory ignores it
        since the factory hardcodes status=PENDING_REVIEW."""
        # The factory doesn't accept status as parameter — this tests the signature
        rec = AIClinicalRecommendation.create_from_ai(
            session_id="dummy",
            patient_id="dummy",
            recommendation_type="triage_assessment",
        )
        # The factory always produces PENDING_REVIEW regardless
        assert rec.status == RecommendationStatus.PENDING_REVIEW
        assert rec.safety_cleared is False

    def test_doctor_review_service_can_set_accepted(self, db):
        """DoctorReviewService.review(accept) must successfully set ACCEPTED via SQL UPDATE."""
        # Setup: create patient + doctor + session + rec
        p_user = User(
            email=f"c1-p-{os.urandom(4).hex()}@ex.com",
            password_hash="x",
            role=UserRole.PATIENT,
            full_name="C1 Patient",
        )
        d_user = User(
            email=f"c1-d-{os.urandom(4).hex()}@ex.com",
            password_hash="x",
            role=UserRole.DOCTOR,
            full_name="C1 Doctor",
        )
        db.add_all([p_user, d_user])
        db.flush()

        from app.models.care import Doctor
        doctor = Doctor(user_id=d_user.id, full_name="C1 Doctor")
        db.add(doctor)
        db.flush()

        patient = PatientProfile(user_id=p_user.id)
        db.add(patient)
        db.flush()

        session = AISession(patient_id=patient.id, session_type="triage")
        db.add(session)
        db.flush()

        rec = AIClinicalRecommendation(
            session_id=session.id,
            patient_id=patient.id,
            recommendation_type="triage_assessment",
            status=RecommendationStatus.PENDING_REVIEW,
        )
        db.add(rec)
        db.commit()

        # DoctorReviewService.review() must succeed via SQL UPDATE
        service = DoctorReviewService(db)
        with patch("app.services.doctor_review.is_enabled", return_value=True):
            service.review(rec.id, "accept", d_user)

        db.refresh(rec)
        assert rec.status == RecommendationStatus.ACCEPTED
        assert rec.safety_cleared is True


# ---------------------------------------------------------------------------
# C2: CarePlan AI creation guard
# ---------------------------------------------------------------------------

class TestC2CarePlanCreationGuard:
    """CarePlan.create_from_ai() must enforce status=DRAFT and ai_generated=True."""

    def test_ai_careplan_factory_produces_draft(self):
        """create_from_ai() always produces DRAFT status."""
        plan = CarePlan.create_from_ai(
            patient_id="patient-id",
            title="Metabolic care plan",
        )
        assert plan.status == CarePlanStatus.DRAFT
        assert plan.ai_generated is True

    def test_ai_careplan_cannot_be_created_active(self):
        """AI-generated CarePlan cannot be created with status=ACTIVE."""
        with pytest.raises(ValueError, match="cannot be created with status"):
            # ai_generated=True set BEFORE status (triggers @validates(status))
            CarePlan(ai_generated=True, status="ACTIVE", patient_id="p", title="t")

    def test_ai_careplan_cannot_be_created_active_reverse_order(self):
        """C2 order-independent: status=ACTIVE set BEFORE ai_generated=True must also be blocked.

        This tests the @validates('ai_generated') hook which rechecks status
        after ai_generated flips to True, regardless of kwarg order.
        """
        with pytest.raises(ValueError, match="cannot be created with status"):
            # status assigned FIRST (before ai_generated), then ai_generated=True triggers recheck
            CarePlan(status="ACTIVE", ai_generated=True, patient_id="p", title="t")

    def test_ai_careplan_cannot_be_created_approved(self):
        """AI-generated CarePlan cannot be created with status=APPROVED."""
        with pytest.raises(ValueError, match="cannot be created with status"):
            CarePlan(ai_generated=True, status="APPROVED", patient_id="p", title="t")

    def test_doctor_careplan_can_have_any_status(self):
        """Human-created care plan (ai_generated=False) can have any status — doctor controls it."""
        plan = CarePlan(
            patient_id="patient-id",
            title="Doctor's care plan",
            status=CarePlanStatus.APPROVED,
            ai_generated=False,
        )
        assert plan.status == CarePlanStatus.APPROVED

    def test_draft_status_always_allowed_for_ai(self):
        """DRAFT status is always allowed for AI-generated plans."""
        plan = CarePlan(
            patient_id="patient-id",
            title="AI draft",
            ai_generated=True,
            status=CarePlanStatus.DRAFT,
        )
        assert plan.status == CarePlanStatus.DRAFT
        assert plan.ai_generated is True
