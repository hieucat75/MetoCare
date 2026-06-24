"""Phase 4A doctor API tests.

Covers:
- GET  /doctors/me              RBAC, MFA gate, inactive doctor, no-row 404
- PATCH /doctors/me             allowed fields, blocked fields, fee validation
- GET  /doctors/me/patients     consent gate, encounter gate, cross-access isolation,
                                revoked consent, inactive patient, risk filter
- GET  /doctors/me/dashboard    zero baseline, high-risk alert, MFA gate
- POST /admin/doctors           SUPER_ADMIN+MFA only, audit, duplicate, 422
- POST /patients/{pid}/consents FK validation (AC-11)
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.care import Doctor, Encounter
from app.models.governance import AuditLog, Consent
from app.models.patient import PatientProfile
from app.models.user import User, UserRole


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def _doctor_token(user_id: str, *, mfa: bool = True) -> dict:
    token = create_access_token(subject=user_id, role="doctor", mfa=mfa)
    return {"Authorization": f"Bearer {token}"}


def _patient_token(user_id: str) -> dict:
    token = create_access_token(subject=user_id, role="patient", mfa=True)
    return {"Authorization": f"Bearer {token}"}


def _super_admin_token(user_id: str, *, mfa: bool = True) -> dict:
    token = create_access_token(subject=user_id, role="super_admin", mfa=mfa)
    return {"Authorization": f"Bearer {token}"}


def _internal_admin_token(user_id: str) -> dict:
    token = create_access_token(subject=user_id, role="internal_admin", mfa=True)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def doctor_user(db: Session):
    """Active Doctor User + Doctor row."""
    import os
    uid = os.urandom(4).hex()
    user = User(
        email=f"dr-{uid}@clinic.vn",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="BS Nguyễn Test",
        is_active=True,
        mfa_enabled=True,
    )
    db.add(user)
    db.flush()
    doc = Doctor(
        user_id=user.id,
        full_name="BS Nguyễn Test",
        specialty="Nội tiết",
        license_no="VN-0001",
        is_active=True,
    )
    db.add(doc)
    db.commit()
    return {"user": user, "doctor": doc}


@pytest.fixture
def doctor_user2(db: Session):
    """Second doctor for cross-access isolation tests."""
    import os
    uid = os.urandom(4).hex()
    user = User(
        email=f"dr2-{uid}@clinic.vn",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="BS Khác",
        is_active=True,
        mfa_enabled=True,
    )
    db.add(user)
    db.flush()
    doc = Doctor(user_id=user.id, full_name="BS Khác", specialty="Tim mạch", is_active=True)
    db.add(doc)
    db.commit()
    return {"user": user, "doctor": doc}


@pytest.fixture
def patient_user(db: Session):
    """Patient with PatientProfile (risk_segment=high)."""
    import os
    uid = os.urandom(4).hex()
    user = User(
        email=f"pt-{uid}@example.vn",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Bệnh nhân Test",
        is_active=True,
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="Bệnh nhân Test", risk_segment="high")
    db.add(profile)
    db.commit()
    return {"user": user, "profile": profile}


def _grant_consent(db: Session, patient_id: str, doctor_user_id: str) -> Consent:
    c = Consent(
        patient_id=patient_id,
        consent_type="doctor_access",
        data_scope="*",
        granted_to=doctor_user_id,
    )
    db.add(c)
    db.commit()
    return c


# ---------------------------------------------------------------------------
# GET /doctors/me
# ---------------------------------------------------------------------------

class TestGetMyProfile:
    def test_no_token_returns_401(self, client):
        assert client.get("/api/v1/doctors/me").status_code == 401

    def test_patient_token_returns_403(self, client, patient_user):
        assert client.get(
            "/api/v1/doctors/me", headers=_patient_token(patient_user["user"].id)
        ).status_code == 403

    def test_internal_admin_returns_403(self, client):
        assert client.get(
            "/api/v1/doctors/me", headers=_internal_admin_token("ia-id")
        ).status_code == 403

    def test_doctor_without_mfa_returns_403(self, client, doctor_user):
        r = client.get("/api/v1/doctors/me", headers=_doctor_token(doctor_user["user"].id, mfa=False))
        assert r.status_code == 403
        assert "MFA" in r.json()["detail"]

    def test_doctor_with_no_doctor_row_returns_404(self, client, db):
        import os
        orphan = User(email=f"orphan-{os.urandom(3).hex()}@x.com", password_hash="x", role=UserRole.DOCTOR, is_active=True)
        db.add(orphan)
        db.commit()
        assert client.get("/api/v1/doctors/me", headers=_doctor_token(orphan.id)).status_code == 404

    def test_inactive_doctor_returns_403(self, client, db):
        import os
        user = User(email=f"inact-{os.urandom(3).hex()}@x.com", password_hash="x", role=UserRole.DOCTOR, is_active=True)
        db.add(user)
        db.flush()
        db.add(Doctor(user_id=user.id, full_name="Inactive Dr", is_active=False))
        db.commit()
        assert client.get("/api/v1/doctors/me", headers=_doctor_token(user.id)).status_code == 403

    def test_returns_profile_fields(self, client, doctor_user):
        r = client.get("/api/v1/doctors/me", headers=_doctor_token(doctor_user["user"].id))
        assert r.status_code == 200
        body = r.json()
        assert body["specialty"] == "Nội tiết"
        assert body["license_no"] == "VN-0001"
        assert "password_hash" not in body
        assert "mfa_secret" not in body


# ---------------------------------------------------------------------------
# PATCH /doctors/me
# ---------------------------------------------------------------------------

class TestPatchMyProfile:
    def test_update_bio_and_specialty(self, client, doctor_user):
        r = client.patch(
            "/api/v1/doctors/me",
            json={"bio": "10 năm kinh nghiệm", "specialty": "Nội tiết - ĐTĐ"},
            headers=_doctor_token(doctor_user["user"].id),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["bio"] == "10 năm kinh nghiệm"
        assert body["specialty"] == "Nội tiết - ĐTĐ"

    def test_update_consultation_fee(self, client, doctor_user):
        r = client.patch(
            "/api/v1/doctors/me",
            json={"consultation_fee": 350000.0},
            headers=_doctor_token(doctor_user["user"].id),
        )
        assert r.status_code == 200
        assert r.json()["consultation_fee"] == 350000.0

    def test_license_no_not_changed_by_patch(self, client, db, doctor_user):
        """license_no is not in DoctorProfileUpdate schema — must remain unchanged."""
        client.patch(
            "/api/v1/doctors/me",
            json={"bio": "updated bio"},
            headers=_doctor_token(doctor_user["user"].id),
        )
        db.refresh(doctor_user["doctor"])
        assert doctor_user["doctor"].license_no == "VN-0001"

    def test_negative_fee_returns_422(self, client, doctor_user):
        r = client.patch(
            "/api/v1/doctors/me",
            json={"consultation_fee": -1},
            headers=_doctor_token(doctor_user["user"].id),
        )
        assert r.status_code == 422

    def test_no_mfa_returns_403(self, client, doctor_user):
        r = client.patch(
            "/api/v1/doctors/me",
            json={"bio": "x"},
            headers=_doctor_token(doctor_user["user"].id, mfa=False),
        )
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# GET /doctors/me/patients
# ---------------------------------------------------------------------------

class TestListMyPatients:
    def test_empty_for_new_doctor(self, client, doctor_user):
        r = client.get("/api/v1/doctors/me/patients", headers=_doctor_token(doctor_user["user"].id))
        assert r.status_code == 200
        assert r.json() == []

    def test_consented_patient_appears(self, client, db, doctor_user, patient_user):
        _grant_consent(db, patient_user["profile"].id, doctor_user["user"].id)
        r = client.get("/api/v1/doctors/me/patients", headers=_doctor_token(doctor_user["user"].id))
        assert r.status_code == 200
        assert any(p["patient_id"] == patient_user["profile"].id for p in r.json())

    def test_revoked_consent_excluded(self, client, db, doctor_user, patient_user):
        from app.core.clock import utcnow
        c = _grant_consent(db, patient_user["profile"].id, doctor_user["user"].id)
        c.revoked_at = utcnow()
        db.commit()
        r = client.get("/api/v1/doctors/me/patients", headers=_doctor_token(doctor_user["user"].id))
        assert not any(p["patient_id"] == patient_user["profile"].id for p in r.json())

    def test_encounter_assigned_patient_appears(self, client, db, doctor_user, patient_user):
        enc = Encounter(
            patient_id=patient_user["profile"].id,
            doctor_id=doctor_user["doctor"].id,
            encounter_type="outpatient",
            status="completed",
        )
        db.add(enc)
        db.commit()
        r = client.get("/api/v1/doctors/me/patients", headers=_doctor_token(doctor_user["user"].id))
        assert any(p["patient_id"] == patient_user["profile"].id for p in r.json())

    def test_no_cross_access_between_doctors(self, client, db, doctor_user, doctor_user2, patient_user):
        """Patient consented to doctor2 must NOT appear in doctor1's list."""
        _grant_consent(db, patient_user["profile"].id, doctor_user2["user"].id)
        r = client.get("/api/v1/doctors/me/patients", headers=_doctor_token(doctor_user["user"].id))
        assert not any(p["patient_id"] == patient_user["profile"].id for p in r.json())

    def test_risk_filter_high(self, client, db, doctor_user, patient_user):
        _grant_consent(db, patient_user["profile"].id, doctor_user["user"].id)
        r = client.get("/api/v1/doctors/me/patients?risk=high", headers=_doctor_token(doctor_user["user"].id))
        assert any(p["patient_id"] == patient_user["profile"].id for p in r.json())

    def test_risk_filter_low_excludes_high_patient(self, client, db, doctor_user, patient_user):
        _grant_consent(db, patient_user["profile"].id, doctor_user["user"].id)
        r = client.get("/api/v1/doctors/me/patients?risk=low", headers=_doctor_token(doctor_user["user"].id))
        assert not any(p["patient_id"] == patient_user["profile"].id for p in r.json())

    def test_inactive_patient_excluded(self, client, db, doctor_user):
        import os
        inact_user = User(email=f"inact-pt-{os.urandom(3).hex()}@x.com", password_hash="x",
                          role=UserRole.PATIENT, is_active=False)
        db.add(inact_user)
        db.flush()
        inact_profile = PatientProfile(user_id=inact_user.id, full_name="Gone")
        db.add(inact_profile)
        db.flush()
        _grant_consent(db, inact_profile.id, doctor_user["user"].id)
        r = client.get("/api/v1/doctors/me/patients", headers=_doctor_token(doctor_user["user"].id))
        assert not any(p["patient_id"] == inact_profile.id for p in r.json())

    def test_patient_token_returns_403(self, client, patient_user):
        assert client.get(
            "/api/v1/doctors/me/patients", headers=_patient_token(patient_user["user"].id)
        ).status_code == 403

    def test_no_mfa_returns_403(self, client, doctor_user):
        assert client.get(
            "/api/v1/doctors/me/patients",
            headers=_doctor_token(doctor_user["user"].id, mfa=False),
        ).status_code == 403


# ---------------------------------------------------------------------------
# GET /doctors/me/dashboard
# ---------------------------------------------------------------------------

class TestGetMyDashboard:
    def test_zero_baseline_for_new_doctor(self, client, doctor_user):
        r = client.get("/api/v1/doctors/me/dashboard", headers=_doctor_token(doctor_user["user"].id))
        assert r.status_code == 200
        body = r.json()
        assert body["appointments_today"] == 0
        assert body["pending_reviews"] == 0
        assert body["pending_approvals"] == 0
        assert body["total_patients"] == 0
        assert body["recent_alerts"] == []

    def test_total_patients_counts_consented(self, client, db, doctor_user, patient_user):
        _grant_consent(db, patient_user["profile"].id, doctor_user["user"].id)
        r = client.get("/api/v1/doctors/me/dashboard", headers=_doctor_token(doctor_user["user"].id))
        assert r.json()["total_patients"] == 1

    def test_high_risk_patient_in_alerts(self, client, db, doctor_user, patient_user):
        _grant_consent(db, patient_user["profile"].id, doctor_user["user"].id)
        r = client.get("/api/v1/doctors/me/dashboard", headers=_doctor_token(doctor_user["user"].id))
        alerts = r.json()["recent_alerts"]
        assert any(a["patient_id"] == patient_user["profile"].id for a in alerts)

    def test_no_mfa_returns_403(self, client, doctor_user):
        assert client.get(
            "/api/v1/doctors/me/dashboard",
            headers=_doctor_token(doctor_user["user"].id, mfa=False),
        ).status_code == 403

    def test_patient_token_returns_403(self, client, patient_user):
        assert client.get(
            "/api/v1/doctors/me/dashboard",
            headers=_patient_token(patient_user["user"].id),
        ).status_code == 403


# ---------------------------------------------------------------------------
# POST /admin/doctors
# ---------------------------------------------------------------------------

class TestAdminCreateDoctor:
    def _payload(self, suffix: str) -> dict:
        return {
            "email": f"new-dr-{suffix}@hospital.vn",
            "password": "SecurePass123!XYZ",
            "full_name": "BS Trần Thị Mới",
            "specialty": "Nội tiết",
            "license_no": "VN-9999",
        }

    def test_super_admin_mfa_creates_doctor(self, client):
        r = client.post(
            "/api/v1/admin/doctors",
            json=self._payload("create"),
            headers=_super_admin_token("sa-1"),
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["role"] == "doctor"
        assert body["mfa_enabled"] is False
        assert "user_id" in body
        assert "doctor_id" in body

    def test_creates_audit_log(self, client, db):
        r = client.post(
            "/api/v1/admin/doctors",
            json=self._payload("audit"),
            headers=_super_admin_token("sa-audit"),
        )
        assert r.status_code == 201
        user_id = r.json()["user_id"]
        entry = db.execute(
            select(AuditLog).where(
                AuditLog.action == "create_doctor_account",
                AuditLog.resource_id == user_id,
            )
        ).scalar_one_or_none()
        assert entry is not None
        assert entry.actor_id == "sa-audit"
        assert entry.severity == "warning"

    def test_internal_admin_returns_403(self, client):
        r = client.post(
            "/api/v1/admin/doctors",
            json=self._payload("ia"),
            headers=_internal_admin_token("ia-id"),
        )
        assert r.status_code == 403

    def test_super_admin_without_mfa_returns_403(self, client):
        r = client.post(
            "/api/v1/admin/doctors",
            json=self._payload("nomfa"),
            headers=_super_admin_token("sa-no-mfa", mfa=False),
        )
        assert r.status_code == 403

    def test_patient_token_returns_403(self, client, patient_user):
        r = client.post(
            "/api/v1/admin/doctors",
            json=self._payload("pt"),
            headers=_patient_token(patient_user["user"].id),
        )
        assert r.status_code == 403

    def test_duplicate_email_returns_409(self, client):
        payload = self._payload("dup")
        client.post("/api/v1/admin/doctors", json=payload, headers=_super_admin_token("sa-dup"))
        r2 = client.post("/api/v1/admin/doctors", json=payload, headers=_super_admin_token("sa-dup"))
        assert r2.status_code == 409

    def test_missing_required_fields_returns_422(self, client):
        r = client.post(
            "/api/v1/admin/doctors",
            json={"email": "x@x.com"},  # missing password and full_name
            headers=_super_admin_token("sa-val"),
        )
        assert r.status_code == 422

    def test_created_user_has_doctor_role(self, client, db):
        r = client.post(
            "/api/v1/admin/doctors",
            json=self._payload("rolecheck"),
            headers=_super_admin_token("sa-role"),
        )
        assert r.status_code == 201
        user_id = r.json()["user_id"]
        user = db.execute(select(User).where(User.id == user_id)).scalar_one()
        assert user.role == UserRole.DOCTOR
        assert user.is_active is True


# ---------------------------------------------------------------------------
# POST /patients/{pid}/consents — FK validation (AC-11)
# ---------------------------------------------------------------------------

class TestConsentFKValidation:
    def test_nonexistent_doctor_id_returns_400(self, client, patient_user):
        pid = patient_user["profile"].id
        r = client.post(
            f"/api/v1/patients/{pid}/consents",
            json={"granted_to": "00000000-0000-0000-0000-000000000000", "data_scope": "*"},
            headers=_patient_token(patient_user["user"].id),
        )
        assert r.status_code == 400
        assert "doctor" in r.json()["detail"].lower()

    def test_patient_user_id_as_granted_to_returns_400(self, client, patient_user):
        """Granting consent to another patient (not a doctor) must return 400."""
        pid = patient_user["profile"].id
        r = client.post(
            f"/api/v1/patients/{pid}/consents",
            json={"granted_to": patient_user["user"].id, "data_scope": "*"},
            headers=_patient_token(patient_user["user"].id),
        )
        assert r.status_code == 400

    def test_valid_doctor_user_id_succeeds(self, client, db, patient_user, doctor_user):
        pid = patient_user["profile"].id
        r = client.post(
            f"/api/v1/patients/{pid}/consents",
            json={"granted_to": doctor_user["user"].id, "data_scope": "*"},
            headers=_patient_token(patient_user["user"].id),
        )
        assert r.status_code == 201
