import os
from unittest.mock import patch

import pytest
from app.models.ai import AIClinicalRecommendation, AISession, RecommendationStatus
from app.models.care import Doctor
from app.models.user import User, UserRole
from app.services.doctor_review import DoctorReviewService


@pytest.fixture
def test_setup(db):
    p_user = User(
        email=f"pat-status-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Patient Status",
    )
    d_user = User(
        email=f"doc-status-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="Dr. Status",
    )
    db.add_all([p_user, d_user])
    db.flush()

    doctor = Doctor(user_id=d_user.id, full_name="Dr. Status")
    db.add(doctor)
    db.flush()

    session = AISession(patient_id=p_user.id, session_type="triage")
    db.add(session)
    db.flush()

    db.commit()
    return {"patient_user": p_user, "doctor_user": d_user, "doctor": doctor, "session": session}


def test_recommendation_status_machine_rules(db, test_setup):
    service = DoctorReviewService(db)

    # 1. Create a recommendation with pending_review status
    rec = AIClinicalRecommendation(
        session_id=test_setup["session"].id,
        patient_id=test_setup["patient_user"].id,
        recommendation_type="triage_assessment",
        content="Normal",
        status=RecommendationStatus.PENDING_REVIEW,
    )
    db.add(rec)
    db.commit()

    # 2. DOCTOR accepts recommendation (enable DOCTOR_REVIEW_GATE for test)
    with patch("app.services.doctor_review.is_enabled", return_value=True):
        service.review(rec.id, "accept", test_setup["doctor_user"])
    db.refresh(rec)
    assert rec.status == RecommendationStatus.ACCEPTED

    # 3. Trying to review an already ACCEPTED recommendation -> ValueError (blocked transition)
    with patch("app.services.doctor_review.is_enabled", return_value=True):
        with pytest.raises(ValueError) as exc:
            service.review(rec.id, "reject", test_setup["doctor_user"])
        assert "is not in pending_review status" in str(exc.value)

    # 4. Try to submit a non-existent recommendation as AI_SERVICE -> ValueError
    ai_svc_user = User(
        email=f"aisvc-status-{os.urandom(4).hex()}@internal",
        password_hash="x",
        role=UserRole.AI_SERVICE,
        full_name="AI Service",
    )
    db.add(ai_svc_user)
    db.flush()
    with pytest.raises(ValueError):
        service.submit_for_review("non_existent_id", ai_svc_user)
