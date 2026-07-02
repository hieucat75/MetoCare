"""T10 — Marketplace browse tests (VERIFIED-only; SUSPENDED excluded; filters)."""

from __future__ import annotations

import pytest
from app.models.consultation import DoctorVerificationStatus
from app.services import consultation as svc
from app.services import doctor_marketplace
from fastapi import HTTPException

from tests.consultation_factories import create_doctor, create_patient, headers


def test_browse_returns_only_verified(db):
    verified = create_doctor(db, verification_status=DoctorVerificationStatus.VERIFIED)
    create_doctor(db, verification_status=DoctorVerificationStatus.PENDING_VERIFICATION)
    create_doctor(db, verification_status=DoctorVerificationStatus.SUSPENDED)
    create_doctor(db, verification_status=DoctorVerificationStatus.REJECTED)
    ids = {d.id for d in doctor_marketplace.browse_doctors(db)}
    assert verified.id in ids
    # None of the non-verified doctors leak into the marketplace.
    all_rows = doctor_marketplace.browse_doctors(db)
    assert all(
        d.verification_status == DoctorVerificationStatus.VERIFIED for d in all_rows
    )


def test_suspended_excluded_and_cannot_receive_booking(db):
    suspended = create_doctor(db, verification_status=DoctorVerificationStatus.SUSPENDED)
    ids = {d.id for d in doctor_marketplace.browse_doctors(db)}
    assert suspended.id not in ids
    # Booking against a suspended doctor is refused.
    _u, profile = create_patient(db)
    with pytest.raises(HTTPException) as exc:
        svc.create_consultation(
            db, patient_id=profile.id, doctor_id=suspended.id, data_consent_accepted=True
        )
    assert exc.value.status_code == 403


def test_price_filter(db):
    cheap = create_doctor(db, fee=100000.0)
    pricey = create_doctor(db, fee=500000.0)
    rows = doctor_marketplace.browse_doctors(db, max_price=200000.0)
    ids = {d.id for d in rows}
    assert cheap.id in ids
    assert pricey.id not in ids


def test_method_filter(db):
    chat_only = create_doctor(db, methods="chat")
    video_doc = create_doctor(db, methods="chat,video")
    rows = doctor_marketplace.browse_doctors(db, method="video")
    ids = {d.id for d in rows}
    assert video_doc.id in ids
    assert chat_only.id not in ids


def test_detail_rejects_unverified(db):
    pending = create_doctor(db, verification_status=DoctorVerificationStatus.PENDING_VERIFICATION)
    with pytest.raises(HTTPException) as exc:
        doctor_marketplace.get_doctor_detail(db, pending.id)
    assert exc.value.status_code == 404


def test_browse_endpoint_and_disclaimer(db, client):
    doctor = create_doctor(db)
    _u, profile = create_patient(db)
    pt_user_id = profile.user_id
    resp = client.get("/api/v1/marketplace/doctors", headers=headers(pt_user_id, "patient"))
    assert resp.status_code == 200
    assert any(d["id"] == doctor.id for d in resp.json())
    detail = client.get(
        f"/api/v1/marketplace/doctors/{doctor.id}", headers=headers(pt_user_id, "patient")
    )
    assert detail.status_code == 200
    body = detail.json()
    assert "không thay thế cấp cứu" in (body.get("disclaimer") or "")
