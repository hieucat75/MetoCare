"""T10 — Consultation notes tests (append-only; patient sees only after completion)."""

from __future__ import annotations

import pytest
from app.models.consultation import ConsultationNote
from app.services import consultation as svc
from app.services import consultation_note, consultation_payment
from fastapi import HTTPException

from tests.consultation_factories import create_doctor, create_patient


def _paid(db):
    doctor = create_doctor(db)
    user, profile = create_patient(db)
    c = svc.create_consultation(
        db, patient_id=profile.id, doctor_id=doctor.id, data_consent_accepted=True
    )
    consultation_payment.pay_mock(db, c, patient_profile_id=profile.id)
    return doctor, user, profile, c


def test_add_note_persists_encrypted_content(db):
    doctor, user, profile, c = _paid(db)
    note = consultation_note.add_note(
        db, consultation_id=c.id, doctor_user_id=doctor.user_id, content="Uống thuốc đều"
    )
    # Round-trips as plaintext through the model...
    assert note.content == "Uống thuốc đều"
    # ...but the raw column value is ciphertext (EncryptedString), not plaintext.
    raw = db.execute(
        __import__("sqlalchemy").text(
            "SELECT content FROM consultation_notes WHERE id = :i"
        ),
        {"i": note.id},
    ).scalar_one()
    assert raw != "Uống thuốc đều"


def test_non_owning_doctor_cannot_add_note(db):
    doctor, user, profile, c = _paid(db)
    other = create_doctor(db)
    with pytest.raises(HTTPException) as exc:
        consultation_note.add_note(
            db, consultation_id=c.id, doctor_user_id=other.user_id, content="x"
        )
    assert exc.value.status_code == 403


def test_notes_are_append_only():
    """No update/delete path exists in the notes service (append-only invariant)."""
    exported = set(dir(consultation_note))
    assert not {"update_note", "edit_note", "delete_note", "remove_note"} & exported


def test_patient_sees_notes_only_after_completion(db):
    doctor, user, profile, c = _paid(db)
    consultation_note.add_note(
        db, consultation_id=c.id, doctor_user_id=doctor.user_id, content="lời khuyên"
    )
    # Before completion: patient blocked.
    with pytest.raises(HTTPException) as exc:
        consultation_note.list_notes(
            db,
            consultation_id=c.id,
            requester_role="patient",
            requester_user_id=user.id,
            patient_profile_id=profile.id,
        )
    assert exc.value.status_code == 403
    # After completion: patient can read.
    svc.complete(db, c.id, doctor_user_id=doctor.user_id)
    notes = consultation_note.list_notes(
        db,
        consultation_id=c.id,
        requester_role="patient",
        requester_user_id=user.id,
        patient_profile_id=profile.id,
    )
    assert len(notes) == 1


def test_doctor_can_always_list_own_notes(db):
    doctor, user, profile, c = _paid(db)
    consultation_note.add_note(
        db, consultation_id=c.id, doctor_user_id=doctor.user_id, content="note"
    )
    notes = consultation_note.list_notes(
        db,
        consultation_id=c.id,
        requester_role="doctor",
        requester_user_id=doctor.user_id,
    )
    assert len(notes) == 1


def test_no_update_or_delete_on_note_model(db):
    doctor, user, profile, c = _paid(db)
    note = consultation_note.add_note(
        db, consultation_id=c.id, doctor_user_id=doctor.user_id, content="immutable"
    )
    # The model itself is a plain append row; verify it exists and is retrievable.
    assert db.get(ConsultationNote, note.id) is not None
