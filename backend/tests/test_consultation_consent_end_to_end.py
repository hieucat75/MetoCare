"""The consent journey, end to end, in the order a patient actually walks it.

    doctor detail → book → consent → agree → consultation created →
    doctor sees ONLY permitted confirmed data → patient revokes →
    subsequent doctor PHI access is denied

The per-behaviour tests live in ``test_consultation_sharing_consent.py``; this
one exists to prove the steps compose — that nothing between them re-opens a
door an earlier step closed. It is deliberately one long test: splitting it
would lose the property being checked, which is the sequence itself.

Synthetic fixtures only; no production data.
"""

from __future__ import annotations

import datetime as dt

from app.domain import consultation_consent_policy as policy
from app.models.clinical import HealthMetric, LabDocument, Medication
from app.models.consultation_consent import ConsultationDataConsent
from app.models.governance import AuditLog
from sqlalchemy import select

from tests.consultation_factories import (
    consent_payload,
    create_doctor,
    create_patient,
    headers,
    restore_payload,
)

API = "/api/v1"


def _seed_record(db, patient_id: str) -> None:
    """A patient with something in every category the doctor could see."""
    db.add(
        Medication(
            patient_id=patient_id,
            name="Warfarin",
            dose="5mg",
            lifecycle_status="active",
        )
    )
    db.add(
        HealthMetric(
            patient_id=patient_id,
            metric_type="weight",
            value=68.0,
            unit="kg",
            measured_at=dt.datetime(2026, 5, 1, 8, 0),
            source="self_report",
        )
    )
    db.add(
        LabDocument(
            patient_id=patient_id,
            storage_key="synthetic/lab.pdf",
            lab_name="Phòng xét nghiệm Test",
            ocr_status="done",
        )
    )
    db.commit()


def test_the_whole_consent_journey(client, db):
    doctor = create_doctor(db, full_name="BS Nguyễn Văn A", fee=200000.0)
    patient_user, profile = create_patient(db)
    _seed_record(db, profile.id)

    patient = headers(patient_user.id, "patient")
    doctor_headers = headers(doctor.user_id, "doctor")

    # ── 1. The consent screen, as the patient will read it ──────────────────
    shown = client.get(f"{API}/consultations/data-sharing-policy", headers=patient).json()
    assert shown["title"] == "Chia sẻ thông tin sức khỏe với bác sĩ?"
    assert shown["decline_label"] == "Không chia sẻ"
    granted_categories = [c["key"] for c in shown["categories"]]

    # ── 2. Declining books nothing ──────────────────────────────────────────
    # There is no "declined" request to send — the client simply never calls
    # create. Prove the state is untouched: no consultation at all.
    assert client.get(f"{API}/consultations", headers=patient).json() == []

    # ── 3. Agreeing creates the consultation AND the grant, together ────────
    created = client.post(
        f"{API}/consultations",
        json={
            "doctor_id": doctor.id,
            "data_consent_accepted": True,
            "data_sharing_consent": consent_payload(
                categories=granted_categories,
                consent_version=shown["consent_version"],
                policy_version=shown["policy_version"],
            ),
            "chief_complaint": "Hay chóng mặt buổi sáng",
        },
        headers=patient,
    )
    assert created.status_code == 201
    consultation_id = created.json()["id"]

    consent = db.execute(
        select(ConsultationDataConsent).where(
            ConsultationDataConsent.consultation_id == consultation_id
        )
    ).scalar_one()
    assert consent.doctor_id == doctor.id
    assert consent.patient_id == profile.id
    assert consent.revoked_at is None

    # ── 4. Before payment there is no care relationship, so no PHI ──────────
    assert (
        client.get(
            f"{API}/consultations/{consultation_id}/patient-summary", headers=doctor_headers
        ).status_code
        == 403
    ), "consent alone must not open the record"

    client.post(f"{API}/consultations/{consultation_id}/pay", headers=patient)

    # ── 5. The doctor sees the permitted, confirmed data — and only that ────
    summary = client.get(
        f"{API}/consultations/{consultation_id}/patient-summary", headers=doctor_headers
    )
    assert summary.status_code == 200
    body = summary.json()
    assert [m["name"] for m in body["medications"]] == ["Warfarin"]
    assert body["withheld_categories"] == []
    assert sorted(body["shared_categories"]) == sorted(policy.CATEGORIES)

    # ── 6. The patient withdraws sharing ────────────────────────────────────
    revoked = client.delete(
        f"{API}/consultations/{consultation_id}/data-sharing-consent", headers=patient
    )
    assert revoked.status_code == 200

    # ── 7. Every doctor PHI path is now closed ──────────────────────────────
    assert (
        client.get(
            f"{API}/consultations/{consultation_id}/patient-summary", headers=doctor_headers
        ).status_code
        == 403
    )
    # ...including the reason-for-visit text on the consultation itself, which
    # would otherwise be the obvious way around the summary being shut.
    after = client.get(f"{API}/consultations/{consultation_id}", headers=doctor_headers).json()
    assert after["chief_complaint"] is None
    assert after["patient_note"] is None

    # The consultation, the payment and the doctor's ability to write their
    # record all survive — withdrawing sharing is not a deletion request.
    assert after["status"] == "PAID"
    assert after["cancelled_at"] is None
    note = client.post(
        f"{API}/consultations/{consultation_id}/notes",
        json={"content": "Đã tư vấn qua tin nhắn."},
        headers=doctor_headers,
    )
    assert note.status_code == 201

    # The patient still sees their own words.
    own = client.get(f"{API}/consultations/{consultation_id}", headers=patient).json()
    assert own["chief_complaint"] == "Hay chóng mặt buổi sáng"

    # ── 8. The whole decision is on the audit trail, with no PHI in it ──────
    actions = {
        "consultation_consent_granted",
        "consultation_consent_revoked",
        "doctor_view_patient_data",
    }
    rows = [
        r
        for r in db.execute(select(AuditLog).where(AuditLog.action.in_(actions))).scalars()
        if (r.details or {}).get("consultation_id") == consultation_id
        or r.resource_id in (profile.id, consent.id)
    ]
    assert any(r.action == "consultation_consent_granted" for r in rows)
    assert any(r.action == "consultation_consent_revoked" for r in rows)
    assert any(
        r.action == "doctor_view_patient_data" and r.outcome == "denied" for r in rows
    ), "the refused read after revocation must be recorded"
    for row in rows:
        blob = f"{row.details}"
        assert "Warfarin" not in blob
        assert "chóng mặt" not in blob

    # ── 9. And the patient can re-share, so revoking was never a trap ───────
    restored = client.post(
        f"{API}/consultations/{consultation_id}/data-sharing-consent",
        json=restore_payload(),
        headers=patient,
    )
    assert restored.status_code == 200
    assert restored.json()["state"] == "ACTIVE"
    assert restored.json()["consent"]["is_active"] is True
    assert (
        client.get(
            f"{API}/consultations/{consultation_id}/patient-summary", headers=doctor_headers
        ).status_code
        == 200
    )
