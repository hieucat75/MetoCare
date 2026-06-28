import datetime as dt
import os

import pytest
from app.core.clock import utcnow
from app.models.governance import AuditLog, Consent
from app.models.patient import PatientProfile
from app.models.user import User, UserRole
from app.services.consent_guard import ConsentDenied, ConsentGuard


@pytest.fixture
def seeded_patient(db):
    user = User(
        email=f"test-guard-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Patient Test",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="Patient Test")
    db.add(profile)
    db.commit()
    return profile


def test_consent_guard_no_consent(db, seeded_patient):
    guard = ConsentGuard(db)
    actor_id = "some_doctor_id"

    with pytest.raises(ConsentDenied):
        guard.require(
            patient_id=seeded_patient.id,
            consent_type="ai_use",
            data_scope="*",
            actor_id=actor_id,
            actor_type="doctor",
        )

    # Assert AuditLog entry was written for deny
    audit = db.query(AuditLog).filter_by(resource_id=seeded_patient.id, outcome="denied").first()
    assert audit is not None
    assert audit.actor_id == actor_id
    assert audit.severity == "warning"


def test_consent_guard_active_consent(db, seeded_patient):
    guard = ConsentGuard(db)
    actor_id = "doctor_abc"

    # Grant active consent
    consent = Consent(
        patient_id=seeded_patient.id,
        consent_type="ai_use",
        data_scope="*",
        granted_to=actor_id,
        valid_from=utcnow() - dt.timedelta(hours=1),
        valid_until=utcnow() + dt.timedelta(hours=1),
    )
    db.add(consent)
    db.commit()

    # Should pass without raising exception
    guard.require(
        patient_id=seeded_patient.id,
        consent_type="ai_use",
        data_scope="*",
        actor_id=actor_id,
        actor_type="doctor",
    )

    # Assert AuditLog entry was written for success
    audit = (
        db.query(AuditLog)
        .filter_by(
            resource_id=seeded_patient.id, actor_id=actor_id, outcome="success", severity="info"
        )
        .first()
    )
    assert audit is not None


def test_consent_guard_expired_consent(db, seeded_patient):
    guard = ConsentGuard(db)
    actor_id = "doctor_expired"

    # Expired consent
    consent = Consent(
        patient_id=seeded_patient.id,
        consent_type="ai_use",
        data_scope="*",
        granted_to=actor_id,
        valid_from=utcnow() - dt.timedelta(hours=2),
        valid_until=utcnow() - dt.timedelta(hours=1),
    )
    db.add(consent)
    db.commit()

    with pytest.raises(ConsentDenied):
        guard.require(
            patient_id=seeded_patient.id,
            consent_type="ai_use",
            data_scope="*",
            actor_id=actor_id,
            actor_type="doctor",
        )


def test_consent_guard_revoked_consent(db, seeded_patient):
    guard = ConsentGuard(db)
    actor_id = "doctor_revoked"

    # Revoked consent
    consent = Consent(
        patient_id=seeded_patient.id,
        consent_type="ai_use",
        data_scope="*",
        granted_to=actor_id,
        valid_from=utcnow() - dt.timedelta(hours=1),
        valid_until=utcnow() + dt.timedelta(hours=1),
        revoked_at=utcnow() - dt.timedelta(minutes=30),
    )
    db.add(consent)
    db.commit()

    with pytest.raises(ConsentDenied):
        guard.require(
            patient_id=seeded_patient.id,
            consent_type="ai_use",
            data_scope="*",
            actor_id=actor_id,
            actor_type="doctor",
        )


def test_consent_guard_ai_service_same_path(db, seeded_patient):
    guard = ConsentGuard(db)
    actor_id = "ai_service"

    # Bypassing should not happen, must raise ConsentDenied
    with pytest.raises(ConsentDenied):
        guard.require(
            patient_id=seeded_patient.id,
            consent_type="ai_use",
            data_scope="*",
            actor_id=actor_id,
            actor_type="ai_service",
        )


def test_consent_guard_bypass_flag(db, seeded_patient):
    guard = ConsentGuard(db)
    actor_id = "doctor_bypassed"

    # Temporarily disable consent gate
    os.environ["FEATURE_CONSENT_GATE"] = "false"

    try:
        # Should pass even without consent
        guard.require(
            patient_id=seeded_patient.id,
            consent_type="ai_use",
            data_scope="*",
            actor_id=actor_id,
            actor_type="doctor",
        )

        # Verify bypass audit log
        audit = (
            db.query(AuditLog)
            .filter_by(
                resource_id=seeded_patient.id,
                actor_id=actor_id,
                outcome="success",
                severity="warning",
            )
            .first()
        )
        assert audit is not None
        assert "consent.bypass" in audit.action
    finally:
        if "FEATURE_CONSENT_GATE" in os.environ:
            del os.environ["FEATURE_CONSENT_GATE"]
