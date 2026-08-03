"""Patient self-service data export + account deletion (GDPR / DIST-RC)."""

from __future__ import annotations

import datetime as dt

from app.core.security import create_access_token
from app.main import app
from app.models.auth_tokens import RefreshToken
from app.models.clinical import HealthMetric, LabDocument, Medication
from app.models.medical_document import DocumentPage, MedicalDocument
from app.models.meto import MetoConsent
from app.models.patient import PatientProfile
from app.models.user import User, UserRole
from app.services import account as account_svc
from fastapi.testclient import TestClient


def _seed_clinical(db, patient_id: str) -> None:
    db.add(
        HealthMetric(
            patient_id=patient_id,
            metric_type="glucose_fasting",
            value=5.5,
            unit="mmol/L",
            measured_at=dt.datetime(2026, 6, 1, 8, 0, tzinfo=dt.UTC),
            source="self_report",
        )
    )
    db.add(Medication(patient_id=patient_id, name="Metformin", dose="500mg"))
    db.commit()


def _seed_token_and_consent(db, user_id: str) -> str:
    tok = RefreshToken(
        user_id=user_id,
        jti=f"jti-{user_id}",
        expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(days=7),
        family_id="fam-1",
        generation=0,
    )
    db.add(tok)
    db.add(MetoConsent(user_id=user_id, context_type="health_data", granted=True))
    db.commit()
    return tok.id


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def test_export_returns_own_seeded_data_with_attachment_header(db, patient):
    pid = patient["patient_id"]
    _seed_clinical(db, pid)

    client = TestClient(app)
    r = client.get(f"/api/v1/patients/{pid}/export", headers=patient["headers"])
    assert r.status_code == 200, r.text

    disp = r.headers.get("content-disposition")
    assert disp is not None
    assert f"metocare-export-{pid}.json" in disp

    body = r.json()
    assert body["patient_id"] == pid
    assert "generated_at" in body
    assert body["profile"]["full_name"] == "Nguyễn Văn Test"

    metric_types = {m["metric_type"] for m in body["health_metrics"]}
    assert "glucose_fasting" in metric_types
    med_names = {m["name"] for m in body["medications"]}
    assert "Metformin" in med_names


def test_export_bola_forbids_other_patient(db, patient, token_for):
    other = User(
        email="exp-other@example.com", password_hash="x", role=UserRole.PATIENT, full_name="Other"
    )
    db.add(other)
    db.flush()
    db.add(PatientProfile(user_id=other.id, full_name="Other"))
    db.commit()

    client = TestClient(app)
    r = client.get(
        f"/api/v1/patients/{patient['patient_id']}/export",
        headers=token_for(other.id, role="patient"),
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Deletion
# ---------------------------------------------------------------------------


def test_delete_anonymizes_pii_and_revokes(db, patient):
    pid = patient["patient_id"]
    uid = patient["user_id"]
    _seed_clinical(db, pid)
    tok_id = _seed_token_and_consent(db, uid)

    original_email = db.get(User, uid).email
    original_phone = "+84900000001"
    user = db.get(User, uid)
    user.phone = original_phone
    db.commit()

    client = TestClient(app)
    r = client.request(
        "DELETE", f"/api/v1/patients/{pid}/account", headers=patient["headers"]
    )
    assert r.status_code == 200, r.text

    db.expire_all()
    user = db.get(User, uid)
    assert user.email != original_email
    assert user.phone != original_phone
    assert user.full_name is None
    assert user.is_active is False

    profile = db.get(PatientProfile, pid)
    assert profile.full_name is None

    # clinical rows soft-deleted, not removed
    metric = db.query(HealthMetric).filter(HealthMetric.patient_id == pid).first()
    assert metric is not None
    assert metric.deleted_at is not None
    med = db.query(Medication).filter(Medication.patient_id == pid).first()
    assert med.deleted_at is not None

    # refresh token revoked
    tok = db.get(RefreshToken, tok_id)
    assert tok.revoked_at is not None

    # consent revoked
    consent = (
        db.query(MetoConsent).filter(MetoConsent.user_id == uid).first()
    )
    assert consent.granted is False
    assert consent.revoked_at is not None


def test_delete_revokes_the_callers_token_immediately(db, patient):
    """SEC-F2: once the account is deleted (is_active=False), the same access
    token is rejected on the very next request — deletion takes effect against
    the already-issued token, not only after it expires. (The delete *service*
    itself remains idempotent — covered by
    test_delete_returns_object_storage_keys_for_erasure's double call.)"""
    pid = patient["patient_id"]
    client = TestClient(app)
    r1 = client.request("DELETE", f"/api/v1/patients/{pid}/account", headers=patient["headers"])
    assert r1.status_code == 200, r1.text
    # The token now belongs to a deactivated account → 401, not 200/500.
    r2 = client.request("DELETE", f"/api/v1/patients/{pid}/account", headers=patient["headers"])
    assert r2.status_code == 401, r2.text


def test_deactivated_account_token_rejected_on_protected_route(db, patient):
    """SEC-F2: an admin block (is_active=False) invalidates the account's
    already-issued access token on the next protected request — generic 401,
    same as an invalid token (no account-state enumeration)."""
    pid = patient["patient_id"]
    uid = patient["user_id"]
    client = TestClient(app)

    # token works while active
    r_ok = client.get(f"/api/v1/patients/{pid}/export", headers=patient["headers"])
    assert r_ok.status_code == 200, r_ok.text

    # simulate admin block
    db.get(User, uid).is_active = False
    db.commit()

    r_blocked = client.get(f"/api/v1/patients/{pid}/export", headers=patient["headers"])
    assert r_blocked.status_code == 401, r_blocked.text
    assert "token" in r_blocked.json()["detail"].lower()


def test_login_blocked_after_delete(db):
    from app.services import auth as auth_svc

    email = "delete-login@example.com"
    password = "secret123"
    user = auth_svc.register(db, email=email, password=password, role=UserRole.PATIENT)
    profile = (
        db.query(PatientProfile).filter(PatientProfile.user_id == user.id).first()
    )

    token = create_access_token(subject=user.id, role="patient", mfa=True)
    account_headers = {"Authorization": f"Bearer {token}"}
    client = TestClient(app)
    r = client.request(
        "DELETE", f"/api/v1/patients/{profile.id}/account", headers=account_headers
    )
    assert r.status_code == 200, r.text

    db.expire_all()
    try:
        auth_svc.authenticate(db, email=email, password=password)
        raise AssertionError("login should have failed after account deletion")
    except auth_svc.AuthError:
        pass


def test_delete_returns_object_storage_keys_for_erasure(db, patient):
    """Privacy-F2 regression: GDPR erasure must surface every backing blob key
    (medical-document quarantine/accepted, page images, lab uploads) so the
    route can delete them from object storage after the soft-delete commits."""
    pid = patient["patient_id"]
    uid = patient["user_id"]

    doc = MedicalDocument(
        patient_id=pid, quarantine_key="quar/doc1", accepted_key="acc/doc1"
    )
    db.add(doc)
    db.flush()
    db.add(DocumentPage(document_id=doc.id, page_no=1, storage_key="page/doc1-1"))
    db.add(LabDocument(patient_id=pid, storage_key="lab/upload1"))
    db.commit()

    keys = account_svc.delete_account(db, user_id=uid, patient_id=pid)

    assert set(keys) == {"quar/doc1", "acc/doc1", "page/doc1-1", "lab/upload1"}
    # Idempotent: keys still surface on a re-run so a failed prior sweep can retry.
    assert set(account_svc.delete_account(db, user_id=uid, patient_id=pid)) == set(keys)
