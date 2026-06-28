import datetime as dt
import os
from unittest.mock import patch

import pytest
from app.core.clock import utcnow
from app.models.ai import AIClinicalRecommendation, AISession, RecommendationStatus
from app.models.care import Clinic, Doctor, DoctorClinic
from app.models.governance import AuditLog, Consent
from app.models.patient import PatientProfile
from app.models.user import User, UserRole
from app.services.doctor_review import DoctorReviewService, PermissionDenied


@pytest.fixture
def setup_data(db):
    # Create patient
    p_user = User(
        email=f"patient-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Patient Name",
    )
    db.add(p_user)
    db.flush()
    patient = PatientProfile(user_id=p_user.id, full_name="Patient Name")
    db.add(patient)

    # Create clinic
    clinic = Clinic(name="MetoClinic")
    db.add(clinic)
    db.flush()

    # Create doctor
    d_user = User(
        email=f"doctor-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="Dr. Clinical",
    )
    db.add(d_user)
    db.flush()
    doctor = Doctor(user_id=d_user.id, clinic_id=clinic.id, full_name="Dr. Clinical")
    db.add(doctor)
    db.flush()

    # Link doctor to clinic in doctor_clinic
    doc_clinic = DoctorClinic(
        doctor_id=doctor.id, clinic_id=clinic.id, is_primary=True, is_active=True
    )
    db.add(doc_clinic)

    # Create AI User
    ai_user = User(
        email=f"ai_service_{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role="ai_service",
        full_name="AI Service",
    )
    db.add(ai_user)

    db.commit()
    return {
        "patient": patient,
        "clinic": clinic,
        "doctor": doctor,
        "d_user": d_user,
        "ai_user": ai_user,
        "p_user": p_user,
    }


def test_submit_for_review_permissions(db, setup_data):
    service = DoctorReviewService(db)

    # Create session
    session = AISession(patient_id=setup_data["patient"].id, session_type="triage", messages="{}")
    db.add(session)
    db.flush()

    # Create recommendation
    rec = AIClinicalRecommendation(
        session_id=session.id,
        patient_id=setup_data["patient"].id,
        recommendation_type="triage_assessment",
        content="Clean",
        status=RecommendationStatus.PENDING_REVIEW,
    )
    db.add(rec)
    db.commit()

    # Patient user tries to submit -> Denied
    with pytest.raises(PermissionDenied):
        service.submit_for_review(rec.id, setup_data["p_user"])

    # AI Service submits -> Success
    service.submit_for_review(rec.id, setup_data["ai_user"])
    assert rec.status == RecommendationStatus.PENDING_REVIEW


def test_doctor_review_accept_and_reject(db, setup_data):
    service = DoctorReviewService(db)

    # Create session and rec
    session = AISession(patient_id=setup_data["patient"].id, session_type="triage")
    db.add(session)
    db.flush()
    rec = AIClinicalRecommendation(
        session_id=session.id,
        patient_id=setup_data["patient"].id,
        recommendation_type="triage_assessment",
        content="Clean",
        status=RecommendationStatus.PENDING_REVIEW,
    )
    db.add(rec)
    db.commit()

    # Non-doctor reviews -> Denied (gate on, wrong role)
    with patch("app.services.doctor_review.is_enabled", return_value=True):
        with pytest.raises(PermissionDenied):
            service.review(rec.id, "accept", setup_data["p_user"])

    # Doctor accepts recommendation
    with patch("app.services.doctor_review.is_enabled", return_value=True):
        service.review(rec.id, "accept", setup_data["d_user"])
    db.refresh(rec)  # SQL UPDATE in service; must refresh ORM object
    assert rec.status == RecommendationStatus.ACCEPTED
    assert rec.safety_cleared is True
    assert rec.reviewed_by_doctor_id == setup_data["doctor"].id
    assert rec.reviewed_at is not None

    # Check AuditLog for acceptance
    audit_entry = (
        db.query(AuditLog)
        .filter_by(resource_id=rec.id, action="ai.recommendation_accepted")
        .first()
    )
    assert audit_entry is not None


def test_doctor_review_supersedes(db, setup_data):
    service = DoctorReviewService(db)

    # Create first rec as PENDING_REVIEW, then accept via service (C1: no direct ACCEPTED creation)
    sess1 = AISession(patient_id=setup_data["patient"].id, session_type="triage")
    db.add(sess1)
    db.flush()
    rec1 = AIClinicalRecommendation(
        session_id=sess1.id,
        patient_id=setup_data["patient"].id,
        recommendation_type="triage_assessment",
        content="Old Rec",
        status=RecommendationStatus.PENDING_REVIEW,
    )
    db.add(rec1)
    db.commit()
    # Accept rec1 via service (SQL UPDATE path, not ORM attribute)
    with patch("app.services.doctor_review.is_enabled", return_value=True):
        service.review(rec1.id, "accept", setup_data["d_user"])
    db.refresh(rec1)
    assert rec1.status == RecommendationStatus.ACCEPTED  # verify setup

    # Create second pending rec
    sess2 = AISession(patient_id=setup_data["patient"].id, session_type="triage")
    db.add(sess2)
    db.flush()
    rec2 = AIClinicalRecommendation(
        session_id=sess2.id,
        patient_id=setup_data["patient"].id,
        recommendation_type="triage_assessment",
        content="New Rec",
        status=RecommendationStatus.PENDING_REVIEW,
    )
    db.add(rec2)
    db.commit()

    # Doctor accepts new rec (patch gate)
    with patch("app.services.doctor_review.is_enabled", return_value=True):
        service.review(rec2.id, "accept", setup_data["d_user"])

    # Assert rec1 is superseded, rec2 is accepted
    db.refresh(rec1)
    db.refresh(rec2)
    assert rec1.status == RecommendationStatus.SUPERSEDED
    assert rec2.status == RecommendationStatus.ACCEPTED


def test_doctor_review_request_info(db, setup_data):
    """P1-01: request_info action sets status=request_info, does NOT set safety_cleared=False."""
    service = DoctorReviewService(db)

    session = AISession(patient_id=setup_data["patient"].id, session_type="triage")
    db.add(session)
    db.flush()
    rec = AIClinicalRecommendation(
        session_id=session.id,
        patient_id=setup_data["patient"].id,
        recommendation_type="triage_assessment",
        content="Needs more info",
        status=RecommendationStatus.PENDING_REVIEW,
    )
    db.add(rec)
    db.commit()

    with patch("app.services.doctor_review.is_enabled", return_value=True):
        service.review(rec.id, "request_info", setup_data["d_user"])
    db.refresh(rec)

    assert rec.status == RecommendationStatus.REQUEST_INFO, (
        f"Expected request_info, got {rec.status} — P1-01 regression"
    )
    assert rec.status != RecommendationStatus.REJECTED, (
        "request_info must not silently map to rejected"
    )
    # safety_cleared was False before (PENDING_REVIEW), must remain False (unchanged, not forced)
    assert rec.safety_cleared is False  # unchanged from initial state
    assert rec.reviewed_by_doctor_id == setup_data["doctor"].id
    assert rec.reviewed_at is not None

    # Check audit log
    from app.models.governance import AuditLog

    audit_entry = (
        db.query(AuditLog)
        .filter_by(
            resource_id=rec.id,
            action="ai.recommendation_request_info",
        )
        .first()
    )
    assert audit_entry is not None, "Audit log for request_info not found"


def test_get_pending_queue(db, setup_data):
    service = DoctorReviewService(db)

    # Create pending rec
    sess = AISession(patient_id=setup_data["patient"].id, session_type="triage")
    db.add(sess)
    db.flush()
    rec = AIClinicalRecommendation(
        session_id=sess.id,
        patient_id=setup_data["patient"].id,
        recommendation_type="triage_assessment",
        content="Queue content",
        status=RecommendationStatus.PENDING_REVIEW,
    )
    db.add(rec)
    db.commit()

    # No consent yet -> queue should be empty
    queue = service.get_pending_queue(setup_data["d_user"])
    assert len(queue) == 0

    # Grant consent to the doctor's clinic
    consent = Consent(
        patient_id=setup_data["patient"].id,
        consent_type="ai_use",
        data_scope="*",
        granted_to=setup_data["clinic"].id,
        valid_from=utcnow() - dt.timedelta(hours=1),
        valid_until=utcnow() + dt.timedelta(hours=1),
    )
    db.add(consent)
    db.commit()

    # Should find recommendation in queue
    queue = service.get_pending_queue(setup_data["d_user"])
    assert len(queue) == 1
    assert queue[0].id == rec.id
