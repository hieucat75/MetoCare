"""Terms/Privacy consent recorded atomically at registration.

Covers the extended POST /auth/register consent block:
- consent accepted → a terms_consents row is written with the full metadata
- no consent block → registration still succeeds, no row (non-breaking)
- idempotent per (user_id, terms_version) → same version recorded once
"""
from __future__ import annotations

import os

from app.models.consent import TermsConsent
from app.models.user import User
from app.services import auth


def _phone() -> str:
    # Valid-looking VN mobile: "09" + 8 numeric digits.
    return "09" + str(int.from_bytes(os.urandom(4), "big")).zfill(8)[:8]


def test_register_with_consent_writes_row(client, db):
    phone = _phone()
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "phone": phone,
            "password": "supersecret1",
            "full_name": "Nguyễn Văn Test",
            "consent": {
                "accepted": True,
                "terms_version": "1.0",
                "privacy_version": "1.0",
                "app_version": "1.0.0",
                "locale": "vi-VN",
                "timezone": "Asia/Ho_Chi_Minh",
                "device_platform": "web",
            },
        },
    )
    assert resp.status_code == 201, resp.text
    user_id = resp.json()["user_id"]

    row = db.query(TermsConsent).filter(TermsConsent.user_id == user_id).one()
    assert row.terms_version == "1.0"
    assert row.privacy_version == "1.0"
    assert row.app_version == "1.0.0"
    assert row.locale == "vi-VN"
    assert row.timezone == "Asia/Ho_Chi_Minh"
    assert row.device_platform == "web"
    assert row.accepted_at is not None
    # ip captured server-side (TestClient → testclient/local host)
    assert row.ip is not None


def test_register_records_accepted_source_and_language(client, db):
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "phone": _phone(),
            "password": "supersecret1",
            "consent": {
                "accepted": True,
                "terms_version": "1.0",
                "privacy_version": "1.0",
                "accepted_source": "registration",
                "accepted_language": "vi-VN",
            },
        },
    )
    assert resp.status_code == 201, resp.text
    row = db.query(TermsConsent).filter(
        TermsConsent.user_id == resp.json()["user_id"]
    ).one()
    assert row.accepted_source == "registration"
    assert row.accepted_language == "vi-VN"
    assert row.revoked_at is None


def test_me_exposes_accepted_terms_version(client):
    """/auth/me reports the accepted version — drives the login/version gate."""
    token = client.post(
        "/api/v1/auth/register",
        json={
            "phone": _phone(),
            "password": "supersecret1",
            "consent": {"accepted": True, "terms_version": "1.0", "privacy_version": "1.0"},
        },
    ).json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, me.text
    assert me.json()["accepted_terms_version"] == "1.0"


def test_accept_terms_endpoint_records_for_logged_in_user(client):
    """A user who registered WITHOUT consent can accept later via the gate."""
    reg = client.post(
        "/api/v1/auth/register",
        json={"phone": _phone(), "password": "supersecret1"},
    ).json()
    token = reg["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Before: no accepted version → gate would trigger.
    assert client.get("/api/v1/auth/me", headers=headers).json()["accepted_terms_version"] is None

    resp = client.post(
        "/api/v1/auth/accept-terms",
        headers=headers,
        json={
            "accepted": True,
            "terms_version": "1.0",
            "privacy_version": "1.0",
            "accepted_source": "reconsent",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["accepted_terms_version"] == "1.0"


def test_register_without_consent_is_non_breaking(client, db):
    phone = _phone()
    resp = client.post(
        "/api/v1/auth/register",
        json={"phone": phone, "password": "supersecret1", "full_name": "No Consent"},
    )
    assert resp.status_code == 201, resp.text
    user_id = resp.json()["user_id"]
    assert db.query(TermsConsent).filter(TermsConsent.user_id == user_id).count() == 0


def test_consent_recorded_once_per_terms_version(db):
    """Re-recording the same terms version for a user is a no-op."""
    user = auth.register(
        db,
        phone="+84900000001",
        password="supersecret1",
        full_name="Idem",
        consent=auth.TermsConsentData(
            accepted=True, terms_version="1.0", privacy_version="1.0"
        ),
    )
    try:
        # Second acceptance of the SAME version → still exactly one row.
        auth._record_terms_consent(
            db,
            user_id=user.id,
            consent=auth.TermsConsentData(
                accepted=True, terms_version="1.0", privacy_version="1.0"
            ),
        )
        db.commit()
        assert db.query(TermsConsent).filter(TermsConsent.user_id == user.id).count() == 1

        # A NEW terms version → a second row.
        auth._record_terms_consent(
            db,
            user_id=user.id,
            consent=auth.TermsConsentData(
                accepted=True, terms_version="2.0", privacy_version="1.0"
            ),
        )
        db.commit()
        assert db.query(TermsConsent).filter(TermsConsent.user_id == user.id).count() == 2
    finally:
        db.query(TermsConsent).filter(TermsConsent.user_id == user.id).delete()
        db.query(User).filter(User.id == user.id).delete()
        db.commit()
