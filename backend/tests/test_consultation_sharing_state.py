"""Explicit sharing state, and the first grant on a pre-feature consultation.

The property under test: no surface ever has to infer WHY sharing is
unavailable, and no surface ever reports an action the patient did not take.
"Revoked" and "never granted" are different facts about a person's decision, and
collapsing them into a 403 made the doctor UI assert the wrong one.

Synthetic fixtures only; no production data.
"""

from __future__ import annotations

import pytest
from app.domain import consultation_consent_policy as policy
from app.domain.consultation_sharing_state import SharingState
from app.models.consultation import ConsultationStatus
from app.models.consultation_consent import ConsultationDataConsent
from app.models.governance import AuditLog
from app.services import consultation as consult_svc
from app.services import consultation_payment
from sqlalchemy import select

from tests.consultation_factories import (
    CONSENT_ALL_CATEGORIES,
    create_doctor,
    create_patient,
    headers,
    restore_payload,
)

API = "/api/v1"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _booked(db, *, categories=None, pay=True):
    doctor = create_doctor(db)
    user, profile = create_patient(db)
    consultation = consult_svc.create_consultation(
        db,
        patient_id=profile.id,
        doctor_id=doctor.id,
        data_consent_accepted=True,
        consent_categories=categories if categories is not None else CONSENT_ALL_CATEGORIES,
        consent_source="web",
    )
    if pay:
        consultation_payment.pay_mock(db, consultation, patient_profile_id=profile.id)
    return doctor, user, profile, consultation


def _make_legacy(db, consultation_id) -> None:
    """Turn a booked consultation into a pre-feature one by removing its consent.

    This is how a consultation booked before the migration actually looks: the
    consultation and its payment exist, and there is no consent row anywhere.
    Deleting the row reproduces that exactly, rather than inserting a fabricated
    "legacy" record — which is the thing the whole feature refuses to do.
    """
    db.execute(
        ConsultationDataConsent.__table__.delete().where(
            ConsultationDataConsent.consultation_id == consultation_id
        )
    )
    db.commit()


def _state(client, user, consultation_id):
    return client.get(
        f"{API}/consultations/{consultation_id}/data-sharing-consent",
        headers=headers(user.id, "patient"),
    )


def _doctor_view(client, doctor, consultation_id):
    return client.get(
        f"{API}/consultations/{consultation_id}",
        headers=headers(doctor.user_id, "doctor"),
    )


def _summary(client, doctor, consultation_id):
    return client.get(
        f"{API}/consultations/{consultation_id}/patient-summary",
        headers=headers(doctor.user_id, "doctor"),
    )


# ---------------------------------------------------------------------------
# The state model itself
# ---------------------------------------------------------------------------


def test_never_granted_is_not_revoked(client, db):
    """The distinction this whole change exists for."""
    _doctor, user, _profile, consultation = _booked(db)
    _make_legacy(db, consultation.id)

    body = _state(client, user, consultation.id).json()
    assert body["state"] == SharingState.NEVER_GRANTED
    assert body["consent"] is None

    # And the same consultation, once actually granted then withdrawn, is REVOKED.
    _doctor2, user2, _p2, consultation2 = _booked(db)
    client.delete(
        f"{API}/consultations/{consultation2.id}/data-sharing-consent",
        headers=headers(user2.id, "patient"),
    )
    assert _state(client, user2, consultation2.id).json()["state"] == SharingState.REVOKED


def test_stale_consent_version_is_needs_reconsent_not_revoked(client, db):
    """A CONSENT_VERSION bump is not a patient withdrawing.

    Without its own state this lands in the same bucket as REVOKED and the
    doctor is told the patient withdrew — when the patient did nothing at all
    and it was us who moved the terms.
    """
    _doctor, user, _profile, consultation = _booked(db)
    row = db.execute(
        select(ConsultationDataConsent).where(
            ConsultationDataConsent.consultation_id == consultation.id
        )
    ).scalar_one()
    row.consent_version = "0.9"
    db.commit()

    body = _state(client, user, consultation.id).json()
    assert body["state"] == SharingState.NEEDS_RECONSENT
    assert body["consent"]["revoked_at"] is None


@pytest.mark.parametrize(
    ("status", "can_share"),
    [
        (ConsultationStatus.PAID, True),
        (ConsultationStatus.IN_PROGRESS, True),
        (ConsultationStatus.COMPLETED, False),
        (ConsultationStatus.CANCELLED, False),
    ],
)
def test_can_share_follows_the_lifecycle(client, db, status, can_share):
    _doctor, user, _profile, consultation = _booked(db)
    consultation.status = status
    db.commit()
    assert _state(client, user, consultation.id).json()["can_share"] is can_share


# ---------------------------------------------------------------------------
# Doctor-facing state
# ---------------------------------------------------------------------------


def test_doctor_sees_never_granted_on_a_legacy_consultation(client, db):
    doctor, _user, _profile, consultation = _booked(db)
    _make_legacy(db, consultation.id)

    resp = _doctor_view(client, doctor, consultation.id)
    assert resp.status_code == 200
    assert resp.json()["sharing_state"] == SharingState.NEVER_GRANTED
    # Still fail-closed on the PHI surface itself.
    assert _summary(client, doctor, consultation.id).status_code == 403


def test_doctor_sees_revoked_after_the_patient_withdraws(client, db):
    doctor, user, _profile, consultation = _booked(db)
    assert _doctor_view(client, doctor, consultation.id).json()["sharing_state"] == (
        SharingState.ACTIVE
    )

    client.delete(
        f"{API}/consultations/{consultation.id}/data-sharing-consent",
        headers=headers(user.id, "patient"),
    )
    resp = _doctor_view(client, doctor, consultation.id)
    assert resp.json()["sharing_state"] == SharingState.REVOKED
    assert _summary(client, doctor, consultation.id).status_code == 403


def test_doctor_state_does_not_leak_categories(client, db):
    """The doctor learns THAT sharing is off, never what was withheld."""
    doctor, user, _profile, consultation = _booked(db, categories=[policy.CATEGORY_MEDICATIONS])
    client.delete(
        f"{API}/consultations/{consultation.id}/data-sharing-consent",
        headers=headers(user.id, "patient"),
    )
    body = _doctor_view(client, doctor, consultation.id).json()
    assert body["sharing_state"] == SharingState.REVOKED
    assert "categories" not in body
    assert "consent" not in body


def test_doctor_cannot_read_the_patient_consent_endpoint(client, db):
    doctor, _user, _profile, consultation = _booked(db)
    resp = client.get(
        f"{API}/consultations/{consultation.id}/data-sharing-consent",
        headers=headers(doctor.user_id, "doctor"),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Legacy patient view
# ---------------------------------------------------------------------------


def test_legacy_patient_gets_a_state_not_a_404(client, db):
    """The old contract answered 404 and the card rendered nothing at all."""
    _doctor, user, _profile, consultation = _booked(db)
    _make_legacy(db, consultation.id)

    resp = _state(client, user, consultation.id)
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == SharingState.NEVER_GRANTED
    assert body["can_share"] is True
    assert body["consultation_status"] == ConsultationStatus.PAID


def test_another_patients_consultation_is_still_404(client, db):
    """Ownership, not row existence, is the gate — and it must stay opaque."""
    _doctor, _user, _profile, consultation = _booked(db)
    _make_legacy(db, consultation.id)
    intruder, _intruder_profile = create_patient(db)

    assert _state(client, intruder, consultation.id).status_code == 404
    assert (
        client.get(
            f"{API}/consultations/00000000-0000-0000-0000-000000000000/data-sharing-consent",
            headers=headers(intruder.id, "patient"),
        ).status_code
        == 404
    )


def test_revoking_a_never_granted_consultation_states_the_truth(client, db):
    """Reporting "revoked" would claim the patient withdrew something they never gave."""
    _doctor, user, _profile, consultation = _booked(db)
    _make_legacy(db, consultation.id)

    resp = client.delete(
        f"{API}/consultations/{consultation.id}/data-sharing-consent",
        headers=headers(user.id, "patient"),
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "not_granted"
    # And nothing was written to make it look like there had been a grant.
    assert (
        db.execute(
            select(ConsultationDataConsent).where(
                ConsultationDataConsent.consultation_id == consultation.id
            )
        ).scalar_one_or_none()
        is None
    )


# ---------------------------------------------------------------------------
# First grant on a pre-feature consultation
# ---------------------------------------------------------------------------


def test_patient_can_explicitly_grant_first_consent(client, db):
    doctor, user, _profile, consultation = _booked(db)
    _make_legacy(db, consultation.id)
    assert _summary(client, doctor, consultation.id).status_code == 403

    resp = client.post(
        f"{API}/consultations/{consultation.id}/data-sharing-consent",
        json=restore_payload(CONSENT_ALL_CATEGORIES, source="web"),
        headers=headers(user.id, "patient"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == SharingState.ACTIVE
    assert sorted(body["consent"]["categories"]) == sorted(CONSENT_ALL_CATEGORIES)
    # Stamped with TODAY's terms, and with the time they actually consented —
    # never backdated to the booking.
    assert body["consent"]["consent_version"] == policy.CONSENT_VERSION
    assert body["consent"]["policy_version"] == policy.POLICY_VERSION

    # Access is genuinely restored, care relationship reopened.
    assert _summary(client, doctor, consultation.id).status_code == 200


def test_first_grant_restores_only_the_disclosed_categories(client, db):
    doctor, user, _profile, consultation = _booked(db)
    _make_legacy(db, consultation.id)

    client.post(
        f"{API}/consultations/{consultation.id}/data-sharing-consent",
        json=restore_payload([policy.CATEGORY_MEDICATIONS]),
        headers=headers(user.id, "patient"),
    )
    body = _summary(client, doctor, consultation.id).json()
    assert body["shared_categories"] == [policy.CATEGORY_MEDICATIONS]
    assert policy.CATEGORY_LAB_RESULTS in body["withheld_categories"]
    assert policy.CATEGORY_HEALTH_RECORDS in body["withheld_categories"]


def test_first_grant_requires_explicit_categories(client, db):
    """No previous set to intersect with, so a default would mean "everything"."""
    _doctor, user, _profile, consultation = _booked(db)
    _make_legacy(db, consultation.id)

    resp = client.post(
        f"{API}/consultations/{consultation.id}/data-sharing-consent",
        json=restore_payload(),  # no categories
        headers=headers(user.id, "patient"),
    )
    assert resp.status_code == 422


def test_first_grant_drops_never_shareable_categories(client, db):
    """AI chat history has no key here, so no client can grant it."""
    _doctor, user, _profile, consultation = _booked(db)
    _make_legacy(db, consultation.id)

    resp = client.post(
        f"{API}/consultations/{consultation.id}/data-sharing-consent",
        json=restore_payload(
            [policy.CATEGORY_MEDICATIONS, "ai_chat_history", "meto_conversations"]
        ),
        headers=headers(user.id, "patient"),
    )
    assert resp.status_code == 200
    assert resp.json()["consent"]["categories"] == [policy.CATEGORY_MEDICATIONS]


@pytest.mark.parametrize("bad", [{"consent_version": "0.9"}, {"policy_version": "0.1"}])
def test_first_grant_fails_closed_on_a_stale_version(client, db, bad):
    _doctor, user, _profile, consultation = _booked(db)
    _make_legacy(db, consultation.id)

    resp = client.post(
        f"{API}/consultations/{consultation.id}/data-sharing-consent",
        json=restore_payload(CONSENT_ALL_CATEGORIES, **bad),
        headers=headers(user.id, "patient"),
    )
    assert resp.status_code == 409
    assert (
        db.execute(
            select(ConsultationDataConsent).where(
                ConsultationDataConsent.consultation_id == consultation.id
            )
        ).scalar_one_or_none()
        is None
    )


def test_first_grant_requires_explicit_acceptance(client, db):
    _doctor, user, _profile, consultation = _booked(db)
    _make_legacy(db, consultation.id)

    resp = client.post(
        f"{API}/consultations/{consultation.id}/data-sharing-consent",
        json=restore_payload(CONSENT_ALL_CATEGORIES, accepted=False),
        headers=headers(user.id, "patient"),
    )
    assert resp.status_code == 422


@pytest.mark.parametrize("status", [ConsultationStatus.COMPLETED, ConsultationStatus.CANCELLED])
def test_an_ineligible_consultation_cannot_be_shared(client, db, status):
    """Its access grants are already closed, so consent would grant nothing."""
    _doctor, user, _profile, consultation = _booked(db)
    _make_legacy(db, consultation.id)
    consultation.status = status
    db.commit()

    resp = client.post(
        f"{API}/consultations/{consultation.id}/data-sharing-consent",
        json=restore_payload(CONSENT_ALL_CATEGORIES),
        headers=headers(user.id, "patient"),
    )
    assert resp.status_code == 409
    assert _state(client, user, consultation.id).json()["can_share"] is False


def test_a_wrong_patient_cannot_create_consent(client, db):
    doctor, _user, _profile, consultation = _booked(db)
    _make_legacy(db, consultation.id)
    intruder, _intruder_profile = create_patient(db)

    resp = client.post(
        f"{API}/consultations/{consultation.id}/data-sharing-consent",
        json=restore_payload(CONSENT_ALL_CATEGORIES),
        headers=headers(intruder.id, "patient"),
    )
    assert resp.status_code == 404
    assert _summary(client, doctor, consultation.id).status_code == 403


def test_first_grant_preserves_consultation_payment_and_notes(client, db):
    doctor, user, _profile, consultation = _booked(db)
    note = client.post(
        f"{API}/consultations/{consultation.id}/notes",
        json={"content": "Ghi chú tổng hợp"},
        headers=headers(doctor.user_id, "doctor"),
    )
    assert note.status_code == 201
    _make_legacy(db, consultation.id)

    client.post(
        f"{API}/consultations/{consultation.id}/data-sharing-consent",
        json=restore_payload(CONSENT_ALL_CATEGORIES),
        headers=headers(user.id, "patient"),
    )

    detail = client.get(
        f"{API}/consultations/{consultation.id}", headers=headers(user.id, "patient")
    ).json()
    assert detail["status"] == ConsultationStatus.PAID
    assert detail["paid_at"] is not None
    notes = client.get(
        f"{API}/consultations/{consultation.id}/notes",
        headers=headers(doctor.user_id, "doctor"),
    ).json()
    assert len(notes) == 1


def test_the_full_legacy_journey_grant_revoke_reshare(client, db):
    """NEVER_GRANTED → ACTIVE → REVOKED → ACTIVE, each state stated explicitly."""
    doctor, user, _profile, consultation = _booked(db)
    _make_legacy(db, consultation.id)
    url = f"{API}/consultations/{consultation.id}/data-sharing-consent"
    patient = headers(user.id, "patient")

    assert _state(client, user, consultation.id).json()["state"] == SharingState.NEVER_GRANTED

    granted = client.post(url, json=restore_payload(CONSENT_ALL_CATEGORIES), headers=patient)
    assert granted.json()["state"] == SharingState.ACTIVE
    assert _summary(client, doctor, consultation.id).status_code == 200

    client.delete(url, headers=patient)
    assert _state(client, user, consultation.id).json()["state"] == SharingState.REVOKED
    assert _doctor_view(client, doctor, consultation.id).json()["sharing_state"] == (
        SharingState.REVOKED
    )
    assert _summary(client, doctor, consultation.id).status_code == 403

    # Re-share still intersects with the grant that now exists — narrowing only.
    reshared = client.post(
        url, json=restore_payload([policy.CATEGORY_LAB_RESULTS]), headers=patient
    )
    assert reshared.json()["state"] == SharingState.ACTIVE
    assert reshared.json()["consent"]["categories"] == [policy.CATEGORY_LAB_RESULTS]
    body = _summary(client, doctor, consultation.id).json()
    assert body["shared_categories"] == [policy.CATEGORY_LAB_RESULTS]


def test_first_grant_is_audited_without_phi(client, db):
    _doctor, user, profile, consultation = _booked(db)
    _make_legacy(db, consultation.id)
    client.post(
        f"{API}/consultations/{consultation.id}/data-sharing-consent",
        json=restore_payload(CONSENT_ALL_CATEGORIES),
        headers=headers(user.id, "patient"),
    )

    rows = list(
        db.execute(
            select(AuditLog).where(AuditLog.action == "consultation_consent_granted")
        ).scalars()
    )
    assert rows, "the first grant must be audited like any other consent decision"
    for row in rows:
        blob = f"{row.details}"
        # Category KEYS are fine — they name kinds of data, never data.
        assert profile.full_name not in blob
        assert "Metformin" not in blob
