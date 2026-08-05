import datetime as dt
import os

import pytest
from app.core.clock import utcnow
from app.models.governance import Consent
from app.models.patient import PatientProfile
from app.models.user import User, UserRole
from app.services.consent_guard import ConsentDenied, ConsentGuard


@pytest.fixture
def integration_setup(db):
    p_user = User(
        email=f"patient-int-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Int Patient",
    )
    db.add(p_user)
    db.flush()
    patient = PatientProfile(user_id=p_user.id, full_name="Int Patient")
    db.add(patient)

    ai_user = User(
        email="ai_service@metocare.internal",
        password_hash="x",
        role="ai_service",
        full_name="AI Service",
    )
    db.add(ai_user)
    db.commit()

    return {"patient": patient, "ai_user": ai_user}


def test_consent_gate_ai_path_no_bypass(db, integration_setup):
    guard = ConsentGuard(db)
    patient_id = integration_setup["patient"].id
    ai_actor_id = integration_setup["ai_user"].id

    # 1. No consent exists, AI service tries to access -> Raises ConsentDenied
    with pytest.raises(ConsentDenied) as exc:
        guard.require(
            patient_id=patient_id,
            consent_type="ai_use",
            data_scope="*",
            actor_id=ai_actor_id,
            actor_type="ai_service",
        )
    assert "no active consent" in str(exc.value)

    # 2. Grant active consent for 'ai_use' to the AI service actor
    consent = Consent(
        patient_id=patient_id,
        consent_type="ai_use",
        data_scope="*",
        granted_to=ai_actor_id,
        valid_from=utcnow() - dt.timedelta(hours=1),
        valid_until=utcnow() + dt.timedelta(hours=1),
    )
    db.add(consent)
    db.commit()

    # 3. AI service tries to access again -> Succeeds (no exception raised)
    guard.require(
        patient_id=patient_id,
        consent_type="ai_use",
        data_scope="*",
        actor_id=ai_actor_id,
        actor_type="ai_service",
    )
