"""T10 — Consultation review tests (post-completion, one per, 1–5, aggregation)."""

from __future__ import annotations

import pytest
from app.services import consultation as svc
from app.services import consultation_payment, consultation_review
from fastapi import HTTPException

from tests.consultation_factories import create_doctor, create_patient


def _completed(db):
    doctor = create_doctor(db)
    user, profile = create_patient(db)
    c = svc.create_consultation(
        db, patient_id=profile.id, doctor_id=doctor.id, data_consent_accepted=True
    )
    consultation_payment.pay_mock(db, c, patient_profile_id=profile.id)
    svc.complete(db, c.id, doctor_user_id=doctor.user_id)
    return doctor, user, profile, c


def test_review_requires_completed(db):
    doctor = create_doctor(db)
    _u, profile = create_patient(db)
    c = svc.create_consultation(
        db, patient_id=profile.id, doctor_id=doctor.id, data_consent_accepted=True
    )
    with pytest.raises(HTTPException) as exc:
        consultation_review.create_review(
            db, consultation_id=c.id, patient_profile_id=profile.id, rating=5
        )
    assert exc.value.status_code == 409


def test_review_only_owner(db):
    doctor, user, profile, c = _completed(db)
    _u2, other = create_patient(db)
    with pytest.raises(HTTPException) as exc:
        consultation_review.create_review(
            db, consultation_id=c.id, patient_profile_id=other.id, rating=4
        )
    assert exc.value.status_code == 403


def test_review_rating_bounds(db):
    doctor, user, profile, c = _completed(db)
    with pytest.raises(HTTPException) as exc:
        consultation_review.create_review(
            db, consultation_id=c.id, patient_profile_id=profile.id, rating=6
        )
    assert exc.value.status_code == 422


def test_one_review_per_consultation(db):
    doctor, user, profile, c = _completed(db)
    consultation_review.create_review(
        db, consultation_id=c.id, patient_profile_id=profile.id, rating=5
    )
    with pytest.raises(HTTPException) as exc:
        consultation_review.create_review(
            db, consultation_id=c.id, patient_profile_id=profile.id, rating=3
        )
    assert exc.value.status_code == 409


def test_rating_aggregation_updates_doctor(db):
    doctor = create_doctor(db)
    ratings = [5, 3]
    for r in ratings:
        _u, profile = create_patient(db)
        c = svc.create_consultation(
            db, patient_id=profile.id, doctor_id=doctor.id, data_consent_accepted=True
        )
        consultation_payment.pay_mock(db, c, patient_profile_id=profile.id)
        svc.complete(db, c.id, doctor_user_id=doctor.user_id)
        consultation_review.create_review(
            db, consultation_id=c.id, patient_profile_id=profile.id, rating=r
        )
    db.refresh(doctor)
    assert doctor.rating_count == 2
    assert doctor.rating_avg == 4.0
