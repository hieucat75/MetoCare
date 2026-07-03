"""Admin consultation monitoring tests.

Covers RBAC (non-admin → 403), MFA enforcement (admin without MFA → 403),
list filters, and stats counts + mock revenue.
"""

from __future__ import annotations

import os

from app.models.user import User, UserRole
from app.services import consultation as consult_svc
from app.services import consultation_payment

from tests.consultation_factories import create_doctor, create_patient, headers


def _admin(db) -> User:
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


def _seed_consult(db, *, fee=200000.0, paid=False):
    doctor = create_doctor(db, fee=fee)
    _u, profile = create_patient(db)
    c = consult_svc.create_consultation(
        db, patient_id=profile.id, doctor_id=doctor.id, data_consent_accepted=True
    )
    if paid:
        consultation_payment.pay_mock(db, c, patient_profile_id=profile.id)
    return doctor, profile, c


# ---------------------------------------------------------------------------
# RBAC + MFA
# ---------------------------------------------------------------------------


def test_non_admin_forbidden(db, client):
    _seed_consult(db)
    resp = client.get(
        "/api/v1/admin/consultations",
        headers=headers("someone", "patient"),
    )
    assert resp.status_code == 403


def test_admin_without_mfa_forbidden(db, client):
    admin = _admin(db)
    resp = client.get(
        "/api/v1/admin/consultations",
        headers=headers(admin.id, "super_admin", mfa=False),
    )
    assert resp.status_code == 403


def test_stats_non_admin_forbidden(db, client):
    resp = client.get(
        "/api/v1/admin/consultations/stats",
        headers=headers("someone", "doctor"),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Listing + filters
# ---------------------------------------------------------------------------


def test_list_returns_joined_names(db, client):
    admin = _admin(db)
    doctor, profile, c = _seed_consult(db)
    resp = client.get(
        "/api/v1/admin/consultations",
        headers=headers(admin.id, "super_admin"),
    )
    assert resp.status_code == 200
    row = next(r for r in resp.json() if r["id"] == c.id)
    assert row["doctor_name"] == doctor.full_name
    assert row["patient_name"] == profile.full_name
    assert row["status"] == "REQUESTED"
    assert row["payment_status"] == "UNPAID"


def test_filter_by_status(db, client):
    admin = _admin(db)
    _d1, _p1, unpaid = _seed_consult(db)
    _d2, _p2, paid = _seed_consult(db, paid=True)
    resp = client.get(
        "/api/v1/admin/consultations?status=PAID",
        headers=headers(admin.id, "super_admin"),
    )
    assert resp.status_code == 200
    ids = {r["id"] for r in resp.json()}
    assert paid.id in ids
    assert unpaid.id not in ids


def test_filter_by_doctor_and_patient(db, client):
    admin = _admin(db)
    doctor, profile, c = _seed_consult(db)
    _other = _seed_consult(db)
    adm = headers(admin.id, "super_admin")

    by_doctor = client.get(f"/api/v1/admin/consultations?doctor_id={doctor.id}", headers=adm)
    assert by_doctor.status_code == 200
    assert {r["id"] for r in by_doctor.json()} == {c.id}

    by_patient = client.get(f"/api/v1/admin/consultations?patient_id={profile.id}", headers=adm)
    assert by_patient.status_code == 200
    assert {r["id"] for r in by_patient.json()} == {c.id}


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


def test_stats_counts_and_mock_revenue(db, client):
    # The test DB is shared across the session, so assert on deltas against a
    # baseline captured before seeding this test's rows.
    admin = _admin(db)
    adm = headers(admin.id, "super_admin")

    base = client.get("/api/v1/admin/consultations/stats", headers=adm).json()

    _seed_consult(db, fee=100000.0)  # REQUESTED, unpaid
    _seed_consult(db, fee=200000.0, paid=True)  # PAID
    _seed_consult(db, fee=300000.0, paid=True)  # PAID

    resp = client.get("/api/v1/admin/consultations/stats", headers=adm)
    assert resp.status_code == 200
    body = resp.json()

    # All six statuses present (zero-filled).
    for key in (
        "REQUESTED",
        "CONFIRMED",
        "PAID",
        "IN_PROGRESS",
        "COMPLETED",
        "CANCELLED",
    ):
        assert key in body["by_status"]

    assert body["total"] - base["total"] == 3
    assert body["by_status"]["REQUESTED"] - base["by_status"]["REQUESTED"] == 1
    assert body["by_status"]["PAID"] - base["by_status"]["PAID"] == 2
    assert body["paid_count"] - base["paid_count"] == 2
    assert body["mock_revenue"] - base["mock_revenue"] == 500000.0
