"""API tests for doctor review workflow endpoints."""

from __future__ import annotations

import datetime as dt
import os
from unittest.mock import patch

import pytest
from app.core.clock import utcnow
from app.core.security import create_access_token
from app.models.ai import AIClinicalRecommendation, AISession, RecommendationStatus
from app.models.care import Clinic, Doctor, DoctorClinic
from app.models.governance import Consent
from app.models.patient import PatientProfile
from app.models.user import User, UserRole


@pytest.fixture
def setup_api_data(db):
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
        email=f"ai-service-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=UserRole.AI_SERVICE,
        full_name="AI Service",
    )
    db.add(ai_user)

    db.commit()

    doctor_token = create_access_token(subject=d_user.id, role="doctor", mfa=True)
    patient_token = create_access_token(subject=p_user.id, role="patient")
    ai_token = create_access_token(subject=ai_user.id, role="ai_service", mfa=False)

    return {
        "patient": patient,
        "clinic": clinic,
        "doctor": doctor,
        "d_user": d_user,
        "ai_user": ai_user,
        "p_user": p_user,
        "doctor_headers": {"Authorization": f"Bearer {doctor_token}"},
        "patient_headers": {"Authorization": f"Bearer {patient_token}"},
        "ai_headers": {"Authorization": f"Bearer {ai_token}"},
    }


def test_doctor_gets_pending_queue(client, db, setup_api_data):
    """DOCTOR -> 200, list of recommendations."""
    # Create session and rec
    session = AISession(patient_id=setup_api_data["patient"].id, session_type="triage")
    db.add(session)
    db.flush()
    rec = AIClinicalRecommendation(
        session_id=session.id,
        patient_id=setup_api_data["patient"].id,
        recommendation_type="triage_assessment",
        status=RecommendationStatus.PENDING_REVIEW,
    )
    db.add(rec)

    # Grant consent to the doctor's clinic so it shows in queue
    consent = Consent(
        patient_id=setup_api_data["patient"].id,
        consent_type="ai_use",
        data_scope="*",
        granted_to=setup_api_data["clinic"].id,
        valid_from=utcnow() - dt.timedelta(hours=1),
        valid_until=utcnow() + dt.timedelta(hours=1),
    )
    db.add(consent)
    db.commit()

    with patch("app.services.doctor_review.is_enabled", return_value=True):
        r = client.get(
            "/api/v1/doctor/review/queue",
            headers=setup_api_data["doctor_headers"],
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["id"] == rec.id


def test_non_doctor_cannot_get_queue(client, setup_api_data):
    """PATIENT -> 403."""
    r = client.get(
        "/api/v1/doctor/review/queue",
        headers=setup_api_data["patient_headers"],
    )
    assert r.status_code == 403, r.text


def test_ai_service_submits_rec_for_review(client, db, setup_api_data):
    """AI_SERVICE -> 201."""
    session = AISession(patient_id=setup_api_data["patient"].id, session_type="triage")
    db.add(session)
    db.flush()
    rec = AIClinicalRecommendation(
        session_id=session.id,
        patient_id=setup_api_data["patient"].id,
        recommendation_type="triage_assessment",
        status=RecommendationStatus.PENDING_REVIEW,
    )
    db.add(rec)
    db.commit()

    with patch("app.services.doctor_review.is_enabled", return_value=True):
        r = client.post(
            f"/api/v1/doctor/review/{rec.id}/submit",
            headers=setup_api_data["ai_headers"],
        )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == RecommendationStatus.PENDING_REVIEW


def test_patient_cannot_submit_for_review(client, db, setup_api_data):
    """PATIENT -> 403."""
    session = AISession(patient_id=setup_api_data["patient"].id, session_type="triage")
    db.add(session)
    db.flush()
    rec = AIClinicalRecommendation(
        session_id=session.id,
        patient_id=setup_api_data["patient"].id,
        recommendation_type="triage_assessment",
        status=RecommendationStatus.PENDING_REVIEW,
    )
    db.add(rec)
    db.commit()

    r = client.post(
        f"/api/v1/doctor/review/{rec.id}/submit",
        headers=setup_api_data["patient_headers"],
    )
    assert r.status_code == 403, r.text


def test_doctor_accepts_recommendation(client, db, setup_api_data):
    """DOCTOR + valid rec -> 200, status=accepted."""
    session = AISession(patient_id=setup_api_data["patient"].id, session_type="triage")
    db.add(session)
    db.flush()
    rec = AIClinicalRecommendation(
        session_id=session.id,
        patient_id=setup_api_data["patient"].id,
        recommendation_type="triage_assessment",
        status=RecommendationStatus.PENDING_REVIEW,
    )
    db.add(rec)
    db.commit()

    with patch("app.services.doctor_review.is_enabled", return_value=True):
        r = client.post(
            f"/api/v1/doctor/review/{rec.id}/review",
            headers=setup_api_data["doctor_headers"],
            json={"verdict": "accepted", "notes": "Approved for metabolic plan"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "accepted"
    assert body["safety_cleared"] is True
    assert body["reviewed_by_doctor_id"] == setup_api_data["doctor"].id


def test_doctor_rejects_recommendation(client, db, setup_api_data):
    """DOCTOR + valid rec -> 200, status=rejected."""
    session = AISession(patient_id=setup_api_data["patient"].id, session_type="triage")
    db.add(session)
    db.flush()
    rec = AIClinicalRecommendation(
        session_id=session.id,
        patient_id=setup_api_data["patient"].id,
        recommendation_type="triage_assessment",
        status=RecommendationStatus.PENDING_REVIEW,
    )
    db.add(rec)
    db.commit()

    with patch("app.services.doctor_review.is_enabled", return_value=True):
        r = client.post(
            f"/api/v1/doctor/review/{rec.id}/review",
            headers=setup_api_data["doctor_headers"],
            json={"verdict": "rejected", "notes": "Not safe"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "rejected"
    assert body["safety_cleared"] is False
    assert body["reviewed_by_doctor_id"] == setup_api_data["doctor"].id


def test_non_doctor_cannot_review_recommendation(client, db, setup_api_data):
    """PATIENT -> 403."""
    session = AISession(patient_id=setup_api_data["patient"].id, session_type="triage")
    db.add(session)
    db.flush()
    rec = AIClinicalRecommendation(
        session_id=session.id,
        patient_id=setup_api_data["patient"].id,
        recommendation_type="triage_assessment",
        status=RecommendationStatus.PENDING_REVIEW,
    )
    db.add(rec)
    db.commit()

    r = client.post(
        f"/api/v1/doctor/review/{rec.id}/review",
        headers=setup_api_data["patient_headers"],
        json={"verdict": "accepted"},
    )
    assert r.status_code == 403, r.text


def test_unauthenticated_cannot_access_queue(client):
    """no token -> 401."""
    r = client.get("/api/v1/doctor/review/queue")
    assert r.status_code == 401, r.text


def test_doctor_request_info_verdict(client, db, setup_api_data):
    """P1-01: verdict=request_info -> status=request_info, NOT rejected."""
    session = AISession(patient_id=setup_api_data["patient"].id, session_type="triage")
    db.add(session)
    db.flush()
    rec = AIClinicalRecommendation(
        session_id=session.id,
        patient_id=setup_api_data["patient"].id,
        recommendation_type="triage_assessment",
        status=RecommendationStatus.PENDING_REVIEW,
    )
    db.add(rec)
    db.commit()

    with patch("app.services.doctor_review.is_enabled", return_value=True):
        r = client.post(
            f"/api/v1/doctor/review/{rec.id}/review",
            headers=setup_api_data["doctor_headers"],
            json={"verdict": "request_info", "notes": "Need more tests"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    # P1-01: must be request_info, NOT rejected
    assert body["status"] == "request_info", (
        f"Expected 'request_info', got '{body['status']}' — P1-01 regression"
    )
    assert body["status"] != "rejected", "request_info must not silently map to rejected"


def test_doctor_request_info_safety_cleared_unchanged(client, db, setup_api_data):
    """P1-01: request_info must NOT set safety_cleared=False (must not behave as rejection)."""
    session = AISession(patient_id=setup_api_data["patient"].id, session_type="triage")
    db.add(session)
    db.flush()
    rec = AIClinicalRecommendation(
        session_id=session.id,
        patient_id=setup_api_data["patient"].id,
        recommendation_type="triage_assessment",
        status=RecommendationStatus.PENDING_REVIEW,
    )
    db.add(rec)
    db.commit()
    original_safety_cleared = rec.safety_cleared  # False at pending_review

    with patch("app.services.doctor_review.is_enabled", return_value=True):
        r = client.post(
            f"/api/v1/doctor/review/{rec.id}/review",
            headers=setup_api_data["doctor_headers"],
            json={"verdict": "request_info", "notes": "Missing lab data"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    # safety_cleared must remain unchanged (not forcibly set to False like rejection)
    assert body["safety_cleared"] == original_safety_cleared, (
        "request_info must not change safety_cleared — it is not a rejection"
    )


def test_doctor_accepts_still_works_after_p1_fix(client, db, setup_api_data):
    """Regression: accepted verdict still works correctly after P1-01 fix."""
    session = AISession(patient_id=setup_api_data["patient"].id, session_type="triage")
    db.add(session)
    db.flush()
    rec = AIClinicalRecommendation(
        session_id=session.id,
        patient_id=setup_api_data["patient"].id,
        recommendation_type="triage_assessment",
        status=RecommendationStatus.PENDING_REVIEW,
    )
    db.add(rec)
    db.commit()

    with patch("app.services.doctor_review.is_enabled", return_value=True):
        r = client.post(
            f"/api/v1/doctor/review/{rec.id}/review",
            headers=setup_api_data["doctor_headers"],
            json={"verdict": "accepted"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "accepted"
    assert body["safety_cleared"] is True


def test_doctor_rejects_still_works_after_p1_fix(client, db, setup_api_data):
    """Regression: rejected verdict still works correctly after P1-01 fix."""
    session = AISession(patient_id=setup_api_data["patient"].id, session_type="triage")
    db.add(session)
    db.flush()
    rec = AIClinicalRecommendation(
        session_id=session.id,
        patient_id=setup_api_data["patient"].id,
        recommendation_type="triage_assessment",
        status=RecommendationStatus.PENDING_REVIEW,
    )
    db.add(rec)
    db.commit()

    with patch("app.services.doctor_review.is_enabled", return_value=True):
        r = client.post(
            f"/api/v1/doctor/review/{rec.id}/review",
            headers=setup_api_data["doctor_headers"],
            json={"verdict": "rejected", "notes": "Not appropriate"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "rejected"
    assert body["safety_cleared"] is False


def test_request_info_audit_action(db, setup_api_data):
    """P1-01: audit action for request_info must be 'ai.recommendation_request_info'."""
    from unittest.mock import patch

    from app.models.governance import AuditLog
    from app.services.doctor_review import DoctorReviewService

    session = AISession(patient_id=setup_api_data["patient"].id, session_type="triage")
    db.add(session)
    db.flush()
    rec = AIClinicalRecommendation(
        session_id=session.id,
        patient_id=setup_api_data["patient"].id,
        recommendation_type="triage_assessment",
        status=RecommendationStatus.PENDING_REVIEW,
    )
    db.add(rec)
    db.commit()

    with patch("app.services.doctor_review.is_enabled", return_value=True):
        DoctorReviewService(db).review(
            recommendation_id=rec.id,
            action="request_info",
            doctor=setup_api_data["d_user"],
            notes="Need imaging",
        )
    db.commit()

    audit_entry = db.query(AuditLog).filter_by(
        resource_id=rec.id,
        action="ai.recommendation_request_info",
    ).first()
    assert audit_entry is not None, "Audit log for request_info action not found"
