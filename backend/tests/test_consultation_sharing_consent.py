"""Consultation-specific doctor data-sharing consent.

The property under test throughout: a doctor reads patient data only when the
patient explicitly said so, for THIS consultation, in a form we recorded — and
only the categories they said yes to. Every other path fails closed.

Synthetic fixtures only; no production data.
"""

from __future__ import annotations

import datetime as dt

import pytest
from app.domain import consultation_consent_policy as policy
from app.models.clinical import HealthMetric, LabDocument, Medication
from app.models.consultation import ConsultationAccessGrant, ConsultationStatus
from app.models.consultation_consent import ConsultationDataConsent
from app.models.governance import AuditLog
from app.services import consultation as consult_svc
from app.services import consultation_payment
from sqlalchemy import select

from tests.consultation_factories import (
    CONSENT_ALL_CATEGORIES,
    consent_payload,
    create_doctor,
    create_patient,
    headers,
)

API = "/api/v1"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _booked(db, *, categories=None):
    """A paid consultation with an active grant + consent. The happy path."""
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
    consultation_payment.pay_mock(db, consultation, patient_profile_id=profile.id)
    return doctor, user, profile, consultation


def _consent_row(db, consultation_id) -> ConsultationDataConsent:
    return db.execute(
        select(ConsultationDataConsent).where(
            ConsultationDataConsent.consultation_id == consultation_id
        )
    ).scalar_one()


def _summary(client, doctor, consultation_id):
    return client.get(
        f"{API}/consultations/{consultation_id}/patient-summary",
        headers=headers(doctor.user_id, "doctor"),
    )


def _seed_all_categories(db, patient_id: str) -> None:
    """One row in every category the summary can surface."""
    db.add(
        HealthMetric(
            patient_id=patient_id,
            metric_type="glucose_fasting",
            value=5.5,
            unit="mmol/L",
            measured_at=dt.datetime(2026, 3, 1, 8, 0),
            source="self_report",
            status="normal",
        )
    )
    db.add(
        Medication(
            patient_id=patient_id,
            name="Metformin",
            dose="500mg",
            lifecycle_status="active",
        )
    )
    db.add(
        LabDocument(
            patient_id=patient_id,
            storage_key="synthetic/lab-1.pdf",
            file_type="pdf",
            lab_name="Phòng xét nghiệm Test",
            ocr_status="done",
        )
    )
    db.commit()


# ---------------------------------------------------------------------------
# Booking requires explicit consent
# ---------------------------------------------------------------------------


def test_booking_without_consent_block_is_rejected(client, db):
    """No consent block at all → 422. The field is required, not optional."""
    doctor = create_doctor(db)
    user, _profile = create_patient(db)
    resp = client.post(
        f"{API}/consultations",
        json={"doctor_id": doctor.id, "data_consent_accepted": True},
        headers=headers(user.id, "patient"),
    )
    assert resp.status_code == 422


def test_booking_with_accepted_false_is_rejected(client, db):
    """`accepted: false` is not a value the schema permits — a declined modal
    must never be able to reach the server as a booking at all."""
    doctor = create_doctor(db)
    user, _profile = create_patient(db)
    resp = client.post(
        f"{API}/consultations",
        json={
            "doctor_id": doctor.id,
            "data_consent_accepted": True,
            "data_sharing_consent": consent_payload(accepted=False),
        },
        headers=headers(user.id, "patient"),
    )
    assert resp.status_code == 422


def test_booking_with_empty_categories_is_rejected(client, db):
    doctor = create_doctor(db)
    user, _profile = create_patient(db)
    resp = client.post(
        f"{API}/consultations",
        json={
            "doctor_id": doctor.id,
            "data_consent_accepted": True,
            "data_sharing_consent": consent_payload(categories=[]),
        },
        headers=headers(user.id, "patient"),
    )
    assert resp.status_code == 422


def test_booking_with_only_unknown_categories_is_rejected(client, db):
    """A client cannot manufacture consent out of category keys we don't know."""
    doctor = create_doctor(db)
    user, _profile = create_patient(db)
    resp = client.post(
        f"{API}/consultations",
        json={
            "doctor_id": doctor.id,
            "data_consent_accepted": True,
            "data_sharing_consent": consent_payload(categories=["ai_chat_history"]),
        },
        headers=headers(user.id, "patient"),
    )
    assert resp.status_code == 400


def test_explicit_consent_books_and_records_the_grant(client, db):
    doctor = create_doctor(db)
    user, profile = create_patient(db)
    resp = client.post(
        f"{API}/consultations",
        json={
            "doctor_id": doctor.id,
            "data_consent_accepted": True,
            "data_sharing_consent": consent_payload(
                consent_version=policy.CONSENT_VERSION,
                policy_version=policy.POLICY_VERSION,
                source="web",
                client_app_version="1.4.0",
                locale="vi-VN",
            ),
        },
        headers=headers(user.id, "patient"),
    )
    assert resp.status_code == 201
    consultation_id = resp.json()["id"]

    record = _consent_row(db, consultation_id)
    assert record.patient_id == profile.id
    assert record.doctor_id == doctor.id
    assert record.purpose == policy.PURPOSE_DOCTOR_CONSULTATION
    assert record.consent_version == policy.CONSENT_VERSION
    assert record.policy_version == policy.POLICY_VERSION
    assert set(record.granted_categories()) == set(CONSENT_ALL_CATEGORIES)
    assert record.granted_at is not None
    assert record.revoked_at is None
    assert record.source == "web"
    assert record.client_app_version == "1.4.0"
    assert record.locale == "vi-VN"
    assert record.audit_id is not None


def test_stale_client_consent_version_is_rejected_at_booking(client, db):
    """A client rendering old terms showed the patient something else. 409."""
    doctor = create_doctor(db)
    user, _profile = create_patient(db)
    resp = client.post(
        f"{API}/consultations",
        json={
            "doctor_id": doctor.id,
            "data_consent_accepted": True,
            "data_sharing_consent": consent_payload(consent_version="0.9"),
        },
        headers=headers(user.id, "patient"),
    )
    assert resp.status_code == 409


def test_a_rejected_booking_leaves_no_consultation_and_no_consent(client, db):
    """The two rows are written in one transaction — neither survives alone."""
    doctor = create_doctor(db)
    user, profile = create_patient(db)
    before = len(consult_svc.list_patient_consultations(db, profile.id))
    resp = client.post(
        f"{API}/consultations",
        json={
            "doctor_id": doctor.id,
            "data_consent_accepted": True,
            "data_sharing_consent": consent_payload(categories=["nonsense"]),
        },
        headers=headers(user.id, "patient"),
    )
    assert resp.status_code == 400
    assert len(consult_svc.list_patient_consultations(db, profile.id)) == before
    assert (
        db.execute(
            select(ConsultationDataConsent).where(
                ConsultationDataConsent.patient_id == profile.id
            )
        )
        .scalars()
        .all()
        == []
    )


# ---------------------------------------------------------------------------
# Doctor PHI access needs BOTH conditions
# ---------------------------------------------------------------------------


def test_doctor_with_consent_and_grant_can_read(client, db):
    doctor, _user, profile, consultation = _booked(db)
    _seed_all_categories(db, profile.id)
    resp = _summary(client, doctor, consultation.id)
    assert resp.status_code == 200
    assert resp.json()["patient_id"] == profile.id


def test_doctor_without_care_relationship_is_denied_even_with_consent(client, db):
    """Consent alone is not access — an unpaid consultation has no grant."""
    doctor = create_doctor(db)
    _user, profile = create_patient(db)
    consultation = consult_svc.create_consultation(
        db,
        patient_id=profile.id,
        doctor_id=doctor.id,
        data_consent_accepted=True,
        consent_categories=CONSENT_ALL_CATEGORIES,
    )
    assert _consent_row(db, consultation.id) is not None  # consent exists
    assert _summary(client, doctor, consultation.id).status_code == 403


def test_care_relationship_without_consent_is_denied(client, db):
    """The mirror case: a live grant, but the consent row is gone.

    This is the pre-migration consultation — booked under the old checkbox,
    which recorded no categories and no version. It must read as no consent.
    """
    doctor, _user, _profile, consultation = _booked(db)
    db.delete(_consent_row(db, consultation.id))
    db.commit()

    grant = db.execute(
        select(ConsultationAccessGrant).where(
            ConsultationAccessGrant.consultation_id == consultation.id,
            ConsultationAccessGrant.revoked_at.is_(None),
        )
    ).scalar_one()
    assert grant is not None  # the care relationship is intact...
    assert _summary(client, doctor, consultation.id).status_code == 403  # ...and denied


def test_consent_for_a_different_doctor_is_rejected(client, db):
    doctor, _user, _profile, consultation = _booked(db)
    other_doctor = create_doctor(db)
    record = _consent_row(db, consultation.id)
    record.doctor_id = other_doctor.id
    db.commit()
    assert _summary(client, doctor, consultation.id).status_code == 403


def test_consent_for_a_different_patient_is_rejected(client, db):
    doctor, _user, _profile, consultation = _booked(db)
    _other_user, other_profile = create_patient(db)
    record = _consent_row(db, consultation.id)
    record.patient_id = other_profile.id
    db.commit()
    assert _summary(client, doctor, consultation.id).status_code == 403


def test_consent_belonging_to_another_consultation_is_rejected(client, db):
    """A consent row is bound to one consultation and authorises no other."""
    doctor, _user, profile, first = _booked(db)
    second = consult_svc.create_consultation(
        db,
        patient_id=profile.id,
        doctor_id=doctor.id,
        data_consent_accepted=True,
        consent_categories=CONSENT_ALL_CATEGORIES,
    )
    consultation_payment.pay_mock(db, second, patient_profile_id=profile.id)

    # Remove the second consultation's own consent; the first one's must not
    # stand in for it, even though doctor and patient match.
    db.delete(_consent_row(db, second.id))
    db.commit()

    assert _summary(client, doctor, first.id).status_code == 200
    assert _summary(client, doctor, second.id).status_code == 403


def test_stale_stored_consent_version_fails_closed(client, db):
    """A grant recorded against older terms is not consent to the current ones."""
    doctor, _user, _profile, consultation = _booked(db)
    assert _summary(client, doctor, consultation.id).status_code == 200

    record = _consent_row(db, consultation.id)
    record.consent_version = "0.9"
    db.commit()
    assert _summary(client, doctor, consultation.id).status_code == 403


def test_wrong_purpose_fails_closed(client, db):
    doctor, _user, _profile, consultation = _booked(db)
    record = _consent_row(db, consultation.id)
    record.purpose = "marketing"
    db.commit()
    assert _summary(client, doctor, consultation.id).status_code == 403


def test_completed_consultation_denies_access(client, db):
    doctor, _user, _profile, consultation = _booked(db)
    consult_svc.complete(db, consultation.id, doctor_user_id=doctor.user_id)
    assert _summary(client, doctor, consultation.id).status_code == 403


def test_cross_patient_bola_on_the_summary(client, db):
    """A doctor cannot reach patient B's data through patient A's consultation."""
    _doctor_a, _u, _p, consultation_a = _booked(db)
    doctor_b = create_doctor(db)
    resp = client.get(
        f"{API}/consultations/{consultation_a.id}/patient-summary",
        headers=headers(doctor_b.user_id, "doctor"),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Revocation
# ---------------------------------------------------------------------------


def test_revocation_denies_future_reads(client, db):
    doctor, user, _profile, consultation = _booked(db)
    assert _summary(client, doctor, consultation.id).status_code == 200

    resp = client.delete(
        f"{API}/consultations/{consultation.id}/data-sharing-consent",
        headers=headers(user.id, "patient"),
    )
    assert resp.status_code == 200
    assert _summary(client, doctor, consultation.id).status_code == 403


def test_revocation_also_closes_the_care_relationship_grant(client, db):
    """An already-issued session must not keep reading PHI after revocation."""
    _doctor, user, _profile, consultation = _booked(db)
    client.delete(
        f"{API}/consultations/{consultation.id}/data-sharing-consent",
        headers=headers(user.id, "patient"),
    )
    active = (
        db.execute(
            select(ConsultationAccessGrant).where(
                ConsultationAccessGrant.consultation_id == consultation.id,
                ConsultationAccessGrant.revoked_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    assert active == []


def test_revocation_keeps_the_consultation_and_its_records(client, db):
    """Withdrawing sharing is not a deletion request, and not a cancellation."""
    doctor, user, _profile, consultation = _booked(db)
    consult_svc.start(db, consultation.id, doctor_user_id=doctor.user_id)

    client.delete(
        f"{API}/consultations/{consultation.id}/data-sharing-consent",
        headers=headers(user.id, "patient"),
    )
    db.refresh(consultation)
    assert consultation.status == ConsultationStatus.IN_PROGRESS
    assert consultation.cancelled_at is None
    # The consent row survives, marked revoked — the record of what was agreed
    # and when it was withdrawn is itself the audit evidence.
    record = _consent_row(db, consultation.id)
    assert record.revoked_at is not None
    assert set(record.granted_categories()) == set(CONSENT_ALL_CATEGORIES)


def test_revocation_is_idempotent(client, db):
    _doctor, user, _profile, consultation = _booked(db)
    url = f"{API}/consultations/{consultation.id}/data-sharing-consent"
    assert client.delete(url, headers=headers(user.id, "patient")).status_code == 200
    assert client.delete(url, headers=headers(user.id, "patient")).status_code == 200


def test_another_patient_cannot_read_or_revoke_a_consent(client, db):
    """Cross-patient probing is answered 404 — not 403, which would confirm the
    consultation exists."""
    _doctor, _user, _profile, consultation = _booked(db)
    intruder, _intruder_profile = create_patient(db)
    url = f"{API}/consultations/{consultation.id}/data-sharing-consent"
    assert client.get(url, headers=headers(intruder.id, "patient")).status_code == 404
    assert client.delete(url, headers=headers(intruder.id, "patient")).status_code == 404


def test_a_doctor_cannot_read_the_consent_record(client, db):
    """Doctors receive permitted data or a 403 — never a map of what was shared."""
    doctor, _user, _profile, consultation = _booked(db)
    resp = client.get(
        f"{API}/consultations/{consultation.id}/data-sharing-consent",
        headers=headers(doctor.user_id, "doctor"),
    )
    assert resp.status_code == 403


def test_patient_can_read_their_own_consent(client, db):
    _doctor, user, _profile, consultation = _booked(db)
    resp = client.get(
        f"{API}/consultations/{consultation.id}/data-sharing-consent",
        headers=headers(user.id, "patient"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_active"] is True
    assert body["purpose"] == policy.PURPOSE_DOCTOR_CONSULTATION
    assert sorted(body["categories"]) == sorted(CONSENT_ALL_CATEGORIES)


# ---------------------------------------------------------------------------
# Minimum data — only the granted categories
# ---------------------------------------------------------------------------


def test_partial_consent_returns_only_the_granted_categories(client, db):
    doctor, _user, profile, consultation = _booked(db, categories=[policy.CATEGORY_MEDICATIONS])
    _seed_all_categories(db, profile.id)

    body = _summary(client, doctor, consultation.id).json()
    assert [m["name"] for m in body["medications"]] == ["Metformin"]
    # Everything the patient did not grant is absent, not merely empty-ish.
    assert body["vitals"]["latest"] == []
    assert body["lab_documents"] == []
    assert body["symptoms"] == []
    assert body["nutrition"] == []
    assert body["active_care_plans"] == []
    assert body["metabolic_score"]["latest_score"] is None


def test_health_records_grant_does_not_leak_lab_derived_metrics(client, db):
    """A metric promoted from a lab report is lab data, and rides lab_results."""
    doctor, _user, profile, consultation = _booked(
        db, categories=[policy.CATEGORY_HEALTH_RECORDS]
    )
    db.add(
        HealthMetric(
            patient_id=profile.id,
            metric_type="hba1c",
            value=7.2,
            unit="%",
            measured_at=dt.datetime(2026, 3, 2, 8, 0),
            source="lab_result",
            source_ref="synthetic-lab-row",
            status="high",
        )
    )
    db.add(
        HealthMetric(
            patient_id=profile.id,
            metric_type="weight",
            value=70.0,
            unit="kg",
            measured_at=dt.datetime(2026, 3, 3, 8, 0),
            source="self_report",
            status="normal",
        )
    )
    db.commit()

    body = _summary(client, doctor, consultation.id).json()
    kinds = {row["metric_type"] for row in body["vitals"]["latest"]}
    assert kinds == {"weight"}


def test_lab_results_grant_returns_lab_derived_metrics_only(client, db):
    doctor, _user, profile, consultation = _booked(db, categories=[policy.CATEGORY_LAB_RESULTS])
    db.add(
        HealthMetric(
            patient_id=profile.id,
            metric_type="hba1c",
            value=7.2,
            unit="%",
            measured_at=dt.datetime(2026, 3, 2, 8, 0),
            source="lab_result",
            source_ref="synthetic-lab-row",
            status="high",
        )
    )
    db.add(
        HealthMetric(
            patient_id=profile.id,
            metric_type="weight",
            value=70.0,
            unit="kg",
            measured_at=dt.datetime(2026, 3, 3, 8, 0),
            source="self_report",
            status="normal",
        )
    )
    db.commit()

    body = _summary(client, doctor, consultation.id).json()
    kinds = {row["metric_type"] for row in body["vitals"]["latest"]}
    assert kinds == {"hba1c"}


def test_legacy_null_source_metrics_ride_health_records(client, db):
    """`source IS NULL` is legacy self-entered data — it must not disappear for
    a patient who granted health_records."""
    doctor, _user, profile, consultation = _booked(
        db, categories=[policy.CATEGORY_HEALTH_RECORDS]
    )
    db.add(
        HealthMetric(
            patient_id=profile.id,
            metric_type="weight",
            value=71.0,
            unit="kg",
            measured_at=dt.datetime(2026, 3, 4, 8, 0),
            source=None,
        )
    )
    db.commit()
    body = _summary(client, doctor, consultation.id).json()
    assert [r["metric_type"] for r in body["vitals"]["latest"]] == ["weight"]


def test_the_narrowest_grant_still_returns_a_wellformed_summary(client, db):
    doctor, _user, profile, consultation = _booked(
        db, categories=[policy.CATEGORY_PATIENT_PROFILE]
    )
    _seed_all_categories(db, profile.id)
    resp = _summary(client, doctor, consultation.id)
    assert resp.status_code == 200
    body = resp.json()
    assert body["medications"] == []
    assert body["vitals"]["latest"] == []
    assert body["vitals"]["trend"] == "insufficient_data"


# ---------------------------------------------------------------------------
# Never-shareable data
# ---------------------------------------------------------------------------


def test_unconfirmed_ocr_candidates_are_never_exposed(client, db):
    """An extracted-but-unconfirmed candidate is a machine guess, not a record."""
    from app.models.medical_document import (
        CAND_STATUS_NEEDS_REVIEW,
        DocumentExtraction,
        ExtractionCandidate,
        MedicalDocument,
    )

    doctor, _user, profile, consultation = _booked(db)
    document = MedicalDocument(
        patient_id=profile.id,
        quarantine_key="synthetic/quarantine/doc-1",
        doc_type="prescription",
        status="needs_review",
    )
    db.add(document)
    db.flush()
    extraction = DocumentExtraction(
        document_id=document.id,
        schema_version="1",
        provider="mock",
        extraction_run_id="synthetic-run-1",
    )
    db.add(extraction)
    db.flush()
    db.add(
        ExtractionCandidate(
            extraction_id=extraction.id,
            document_id=document.id,
            patient_id=profile.id,
            candidate_type="medication",
            fields_json={"name": "UNCONFIRMED_OCR_DRUG", "dose": "999mg"},
            dedupe_key="synthetic-1",
            status=CAND_STATUS_NEEDS_REVIEW,
        )
    )
    db.commit()

    raw = _summary(client, doctor, consultation.id).text
    assert "UNCONFIRMED_OCR_DRUG" not in raw
    assert "999mg" not in raw


def test_ai_chat_history_is_not_a_grantable_category(db):
    """There is no key a client could send to share Meto conversations."""
    for key in policy.NEVER_SHAREABLE:
        assert key not in policy.CATEGORY_SET
        assert policy.normalize_categories([key]) == ()


def test_unknown_categories_are_dropped_not_stored(client, db):
    doctor = create_doctor(db)
    user, _profile = create_patient(db)
    resp = client.post(
        f"{API}/consultations",
        json={
            "doctor_id": doctor.id,
            "data_consent_accepted": True,
            "data_sharing_consent": consent_payload(
                categories=[policy.CATEGORY_MEDICATIONS, "ai_chat_history", "everything"]
            ),
        },
        headers=headers(user.id, "patient"),
    )
    assert resp.status_code == 201
    record = _consent_row(db, resp.json()["id"])
    assert set(record.granted_categories()) == {policy.CATEGORY_MEDICATIONS}


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def _audit_rows(db, action: str, *, consultation_id: str | None = None) -> list[AuditLog]:
    """Audit rows for *action*, optionally narrowed to one consultation.

    The test database is shared across the module, so an unscoped count would
    pick up rows other tests wrote.
    """
    rows = list(db.execute(select(AuditLog).where(AuditLog.action == action)).scalars())
    if consultation_id is None:
        return rows
    return [r for r in rows if (r.details or {}).get("consultation_id") == consultation_id]


def test_grant_and_revoke_are_audited_without_phi(client, db):
    doctor, user, profile, consultation = _booked(db)
    _seed_all_categories(db, profile.id)
    client.delete(
        f"{API}/consultations/{consultation.id}/data-sharing-consent",
        headers=headers(user.id, "patient"),
    )

    granted = _audit_rows(db, "consultation_consent_granted", consultation_id=consultation.id)
    revoked = _audit_rows(db, "consultation_consent_revoked", consultation_id=consultation.id)
    assert len(granted) == 1
    assert len(revoked) == 1

    for row in granted + revoked:
        blob = f"{row.details}"
        # Identifiers, category keys and versions only — never clinical content.
        assert "Metformin" not in blob
        assert "glucose" not in blob
        assert "Phòng xét nghiệm" not in blob
    assert granted[0].details["consultation_id"] == consultation.id
    assert granted[0].details["doctor_id"] == doctor.id
    assert revoked[0].details["consultation_id"] == consultation.id


def test_a_denied_read_is_audited(client, db):
    doctor, user, _profile, consultation = _booked(db)
    client.delete(
        f"{API}/consultations/{consultation.id}/data-sharing-consent",
        headers=headers(user.id, "patient"),
    )
    _summary(client, doctor, consultation.id)

    denied = [
        r
        for r in _audit_rows(db, "doctor_view_patient_data")
        if r.outcome == "denied" and r.actor_id == doctor.id
    ]
    assert denied, "a refused PHI read must leave a trace"


# ---------------------------------------------------------------------------
# Policy endpoint
# ---------------------------------------------------------------------------


def test_policy_endpoint_serves_the_copy_clients_must_render(client, db):
    user, _profile = create_patient(db)
    resp = client.get(
        f"{API}/consultations/data-sharing-policy",
        headers=headers(user.id, "patient"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Chia sẻ thông tin sức khỏe với bác sĩ?"
    assert body["accept_label"] == "Đồng ý và tiếp tục"
    assert body["decline_label"] == "Không chia sẻ"
    assert body["consent_version"] == policy.CONSENT_VERSION
    assert [c["key"] for c in body["categories"]] == list(policy.CATEGORIES)
    # Proves the literal route is not swallowed by /{consultation_id}.
    assert body["purpose"] == policy.PURPOSE_DOCTOR_CONSULTATION


@pytest.mark.parametrize("role", ["doctor", "internal_admin"])
def test_policy_endpoint_is_patient_only(client, db, role):
    doctor = create_doctor(db)
    resp = client.get(
        f"{API}/consultations/data-sharing-policy",
        headers=headers(doctor.user_id, role),
    )
    assert resp.status_code == 403
