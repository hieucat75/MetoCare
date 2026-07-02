"""T10 — Doctor verification tests (approve/reject/suspend, PENDING hidden, audit)."""

from __future__ import annotations

from app.models.consultation import DoctorVerificationStatus
from app.models.governance import AuditLog
from app.models.user import User, UserRole
from app.services import doctor_verification
from sqlalchemy import select

from tests.consultation_factories import create_doctor, headers


def _admin(db):
    import os

    user = User(
        email=f"adm-{os.urandom(4).hex()}@meto.vn",
        password_hash="x",
        role=UserRole.SUPER_ADMIN,
        full_name="Admin",
        is_active=True,
        mfa_enabled=True,
    )
    db.add(user)
    db.commit()
    return user


def test_approve_sets_verified_and_mirrors_flag(db):
    doctor = create_doctor(db, verification_status=DoctorVerificationStatus.PENDING_VERIFICATION)
    admin = _admin(db)
    result = doctor_verification.approve(db, doctor.id, actor_id=admin.id)
    assert result.verification_status == DoctorVerificationStatus.VERIFIED
    assert result.is_verified is True


def test_reject_and_suspend_clear_flag(db):
    admin = _admin(db)
    d1 = create_doctor(db, verification_status=DoctorVerificationStatus.PENDING_VERIFICATION)
    d2 = create_doctor(db, verification_status=DoctorVerificationStatus.VERIFIED)
    r1 = doctor_verification.reject(db, d1.id, actor_id=admin.id)
    r2 = doctor_verification.suspend(db, d2.id, actor_id=admin.id)
    assert r1.verification_status == DoctorVerificationStatus.REJECTED and r1.is_verified is False
    assert r2.verification_status == DoctorVerificationStatus.SUSPENDED and r2.is_verified is False


def test_list_pending_only(db):
    p = create_doctor(db, verification_status=DoctorVerificationStatus.PENDING_VERIFICATION)
    create_doctor(db, verification_status=DoctorVerificationStatus.VERIFIED)
    pending = doctor_verification.list_pending(db)
    assert p.id in {d.id for d in pending}
    assert all(
        d.verification_status == DoctorVerificationStatus.PENDING_VERIFICATION for d in pending
    )


def test_approval_is_audited(db):
    doctor = create_doctor(db, verification_status=DoctorVerificationStatus.PENDING_VERIFICATION)
    admin = _admin(db)
    doctor_verification.approve(db, doctor.id, actor_id=admin.id)
    rows = db.execute(
        select(AuditLog).where(
            AuditLog.action == "doctor_profile_approval",
            AuditLog.resource_id == doctor.id,
        )
    ).scalars().all()
    assert len(rows) >= 1


def test_admin_endpoints_rbac_and_flow(db, client):
    admin = _admin(db)
    doctor = create_doctor(db, verification_status=DoctorVerificationStatus.PENDING_VERIFICATION)
    adm_headers = headers(admin.id, "super_admin")

    # List filtered by status
    resp = client.get("/api/v1/admin/doctors?status=PENDING_VERIFICATION", headers=adm_headers)
    assert resp.status_code == 200
    assert any(d["id"] == doctor.id for d in resp.json())

    # Verify
    v = client.post(f"/api/v1/admin/doctors/{doctor.id}/verify", headers=adm_headers)
    assert v.status_code == 200
    assert v.json()["verification_status"] == "VERIFIED"

    # A patient token is rejected (RBAC).
    denied = client.post(
        f"/api/v1/admin/doctors/{doctor.id}/suspend",
        headers=headers("someone", "patient"),
    )
    assert denied.status_code == 403
