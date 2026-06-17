import os

import pytest
from app.core.clock import utcnow
from app.models.care import Encounter
from app.models.patient import PatientProfile
from app.models.user import User, UserRole
from sqlalchemy import select


@pytest.fixture
def setup_encounter(db):
    user = User(
        email=f"patient-soft-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Soft Patient"
    )
    admin = User(
        email=f"admin-soft-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.SUPER_ADMIN,
        full_name="Soft Admin"
    )
    db.add_all([user, admin])
    db.flush()
    
    profile = PatientProfile(user_id=user.id, full_name="Soft Patient")
    db.add(profile)
    db.flush()

    encounter = Encounter(
        patient_id=profile.id,
        encounter_type="routine",
        status="pending_review",
        chief_complaint="Checkup",
        encounter_date=utcnow()
    )
    db.add(encounter)
    db.commit()

    return {
        "encounter": encounter,
        "admin": admin,
        "profile": profile
    }

def test_soft_delete_lifecycle(db, setup_encounter):
    enc = setup_encounter["encounter"]
    admin = setup_encounter["admin"]

    # Initially not deleted
    assert enc.deleted_at is None
    assert enc.deleted_by is None

    # Perform soft delete
    now = utcnow()
    enc.deleted_at = now
    enc.deleted_by = admin.id
    db.commit()

    # Refresh and assert fields
    db.refresh(enc)
    assert enc.deleted_at == now
    assert enc.deleted_by == admin.id

    # Query excluding deleted (application default)
    stmt = select(Encounter).where(
        Encounter.patient_id == setup_encounter["profile"].id,
        Encounter.deleted_at.is_(None)
    )
    active_encs = db.execute(stmt).scalars().all()
    assert len(active_encs) == 0

    # Query including deleted (for medical reviewers / admins)
    stmt_all = select(Encounter).where(
        Encounter.patient_id == setup_encounter["profile"].id
    )
    all_encs = db.execute(stmt_all).scalars().all()
    assert len(all_encs) == 1
    assert all_encs[0].id == enc.id
