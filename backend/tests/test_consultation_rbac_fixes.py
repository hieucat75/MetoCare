"""T10 — RBAC/access-control regression tests (PR #78 security review).

Covers three findings:
  1. (Revised) Doctor consultation/PHI endpoints accept doctor sessions with or
     without MFA — mandatory doctor MFA was dropped for sales-led onboarding.
  2. Suspending/rejecting a doctor revokes in-flight PHI access grants and the
     defense-in-depth check denies non-VERIFIED doctors.
  3. The patient ``/pay`` response never leaks payout/platform-fee internals.
"""

from __future__ import annotations

from app.models.consultation import ConsultationAccessGrant, DoctorVerificationStatus
from app.services import consultation as svc
from app.services import consultation_payment, doctor_verification
from sqlalchemy import select

from tests.consultation_factories import (
    CONSENT_ALL_CATEGORIES,
    create_doctor,
    create_patient,
    headers,
)


def _paid_consult(db):
    doctor = create_doctor(db)
    _u, profile = create_patient(db)
    c = svc.create_consultation(
        db, patient_id=profile.id, doctor_id=doctor.id, data_consent_accepted=True,
        consent_categories=CONSENT_ALL_CATEGORIES
    )
    consultation_payment.pay_mock(db, c, patient_profile_id=profile.id)
    return doctor, profile, c


# ---------------------------------------------------------------------------
# Finding 1 (revised) — doctor consultation/PHI endpoints work with or
# without an MFA-verified session
# ---------------------------------------------------------------------------


def test_patient_summary_allows_doctor_without_mfa(db, client):
    doctor, _profile, c = _paid_consult(db)
    url = f"/api/v1/consultations/{c.id}/patient-summary"
    no_mfa = headers(doctor.user_id, "doctor", mfa=False)
    assert client.get(url, headers=no_mfa).status_code == 200
    # MFA-verified doctor also succeeds.
    assert client.get(url, headers=headers(doctor.user_id, "doctor")).status_code == 200


def test_add_note_allows_doctor_without_mfa(db, client):
    doctor, _profile, c = _paid_consult(db)
    url = f"/api/v1/consultations/{c.id}/notes"
    body = {"content": "Uống thuốc đều đặn.", "note_type": "recommendation"}
    no_mfa = headers(doctor.user_id, "doctor", mfa=False)
    assert client.post(url, json=body, headers=no_mfa).status_code == 201
    # MFA-verified doctor also succeeds.
    ok = client.post(url, json=body, headers=headers(doctor.user_id, "doctor"))
    assert ok.status_code == 201


# ---------------------------------------------------------------------------
# Finding 2 — suspend revokes in-flight grants + status is denied
# ---------------------------------------------------------------------------


def test_suspend_revokes_active_grant_and_denies_summary(db, client):
    doctor, _profile, c = _paid_consult(db)
    url = f"/api/v1/consultations/{c.id}/patient-summary"
    doc_headers = headers(doctor.user_id, "doctor")
    # Grant is active → 200 before suspension.
    assert client.get(url, headers=doc_headers).status_code == 200

    doctor_verification.suspend(db, doctor.id, actor_id="admin-x")

    # Grant now revoked in the DB.
    grant = db.execute(
        select(ConsultationAccessGrant).where(
            ConsultationAccessGrant.consultation_id == c.id
        )
    ).scalar_one()
    assert grant.revoked_at is not None
    # And the endpoint denies the suspended doctor.
    assert client.get(url, headers=doc_headers).status_code == 403
    assert doctor.verification_status == DoctorVerificationStatus.SUSPENDED


def test_reject_revokes_active_grant(db):
    doctor, _profile, c = _paid_consult(db)
    doctor_verification.reject(db, doctor.id, actor_id="admin-x")
    grant = db.execute(
        select(ConsultationAccessGrant).where(
            ConsultationAccessGrant.consultation_id == c.id
        )
    ).scalar_one()
    assert grant.revoked_at is not None


# ---------------------------------------------------------------------------
# Finding 3 — patient /pay response hides payout internals
# ---------------------------------------------------------------------------


def test_pay_response_hides_payout_internals(db, client):
    doctor = create_doctor(db)
    user, profile = create_patient(db)
    c = svc.create_consultation(
        db, patient_id=profile.id, doctor_id=doctor.id, data_consent_accepted=True,
        consent_categories=CONSENT_ALL_CATEGORIES
    )
    resp = client.post(
        f"/api/v1/consultations/{c.id}/pay",
        headers=headers(user.id, "patient"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "doctor_payout" not in body
    assert "platform_fee" not in body
    # Patient still sees what they pay.
    assert "consultation_price" in body
    assert body["payment_status"]
