"""PR-S2 behavioral tests — lifecycle transitions, RBAC (§6.1), re-review
(§6.3/Q-OQ-1), list visibility (§5.5), non-adherence report (§5.4).

Completes test gates T-04 (transition_reason mapping) and T-05.
Uses the ``client``/``patient``/``db`` conftest fixtures (SQLite).
"""

from __future__ import annotations

from app.models.clinical import Medication, MedicationAuditLog, MedicationStatement
from app.services import medication as medication_svc
from sqlalchemy import select, update


def _create_med(client, patient, **overrides) -> dict:
    payload = {"name": "Metformin", "dose": "850mg", "frequency": "2 lần/ngày"}
    payload.update(overrides)
    r = client.post(
        f"/api/v1/patients/{patient['patient_id']}/medications",
        json=payload,
        headers=patient["headers"],
    )
    assert r.status_code == 201, r.text
    return r.json()


def _patch(client, patient, med_id, body):
    return client.patch(
        f"/api/v1/patients/{patient['patient_id']}/medications/{med_id}",
        json=body,
        headers=patient["headers"],
    )


def _audit_rows(db, med_id):
    return list(
        db.execute(
            select(MedicationAuditLog)
            .where(MedicationAuditLog.medication_id == med_id)
            .order_by(MedicationAuditLog.created_at)
        ).scalars()
    )


def _force_lifecycle(db, med_id, state):
    """Test-only backdoor to arrange states the API can't reach yet."""
    db.execute(update(Medication).where(Medication.id == med_id).values(lifecycle_status=state))
    db.commit()


# --------------------------------------------------------------------------- #
# §5.1 — exposure
# --------------------------------------------------------------------------- #


def test_new_fields_exposed_with_defaults(client, patient):
    med = _create_med(client, patient)
    assert med["lifecycle_status"] == "active"
    assert med["verification_status"] == "patient_reported"
    assert med["source_type"] == "patient_manual"
    assert med["medication_category"] == "conventional_drug"
    assert med["status_reason"] is None


# --------------------------------------------------------------------------- #
# §6.1 — transitions + RBAC
# --------------------------------------------------------------------------- #


def test_patient_pause_with_reason_audits_transition(client, patient, db):
    med = _create_med(client, patient)
    r = _patch(
        client, patient, med["id"],
        {"lifecycle_status": "paused", "status_reason": "Dừng trước phẫu thuật"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["lifecycle_status"] == "paused"
    assert r.json()["status_reason"] == "Dừng trước phẫu thuật"

    rows = [x for x in _audit_rows(db, med["id"]) if x.event_type == "lifecycle_change"]
    assert len(rows) == 1
    row = rows[0]
    assert row.field_changed == "lifecycle_status"
    assert row.old_value == "active"
    assert row.new_value == "paused"
    assert row.transition_reason == "Dừng trước phẫu thuật"  # T-04 item 5
    assert row.before_snapshot["lifecycle_status"] == "active"
    assert row.after_snapshot["lifecycle_status"] == "paused"


def test_patient_resume_from_paused(client, patient):
    med = _create_med(client, patient)
    assert _patch(client, patient, med["id"], {"lifecycle_status": "paused"}).status_code == 200
    r = _patch(client, patient, med["id"], {"lifecycle_status": "active"})
    assert r.status_code == 200
    assert r.json()["lifecycle_status"] == "active"


def test_patient_cannot_set_on_hold(client, patient):
    med = _create_med(client, patient)
    r = _patch(client, patient, med["id"], {"lifecycle_status": "on_hold"})
    assert r.status_code == 403


def test_patient_cannot_clear_on_hold(client, patient, db):
    med = _create_med(client, patient)
    _force_lifecycle(db, med["id"], "on_hold")
    r = _patch(client, patient, med["id"], {"lifecycle_status": "active"})
    assert r.status_code == 403


def test_doctor_can_set_and_clear_on_hold(client, patient, db):
    # Service-level check: the route's doctor path is consent-gated (separate
    # fixture machinery); the RBAC rule itself lives in the service.
    med = _create_med(client, patient)
    record = medication_svc.update_medication(
        db,
        patient_id=patient["patient_id"],
        med_id=med["id"],
        data={"lifecycle_status": "on_hold", "status_reason": "Chờ kết quả xét nghiệm"},
        actor_role="doctor",
    )
    assert record.lifecycle_status == "on_hold"
    record = medication_svc.update_medication(
        db,
        patient_id=patient["patient_id"],
        med_id=med["id"],
        data={"lifecycle_status": "active"},
        actor_role="doctor",
    )
    assert record.lifecycle_status == "active"


def test_nobody_sets_expired_via_api(client, patient):
    med = _create_med(client, patient)
    r = _patch(client, patient, med["id"], {"lifecycle_status": "expired"})
    assert r.status_code == 403


def test_invalid_lifecycle_value_rejected(client, patient):
    med = _create_med(client, patient)
    r = _patch(client, patient, med["id"], {"lifecycle_status": "stopped"})
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
# §6.3 / Q-OQ-1 — expired re-review is statement-first
# --------------------------------------------------------------------------- #


def test_expired_re_review_creates_pending_statement_not_transition(client, patient, db):
    med = _create_med(client, patient)
    _force_lifecycle(db, med["id"], "expired")

    r = _patch(client, patient, med["id"], {"lifecycle_status": "active"})
    assert r.status_code == 200, r.text
    assert r.json()["lifecycle_status"] == "expired"  # unchanged

    pending = list(
        db.execute(
            select(MedicationStatement).where(
                MedicationStatement.related_medication_id == med["id"],
                MedicationStatement.assertion_type == "continued_use",
            )
        ).scalars()
    )
    assert len(pending) == 1
    assert pending[0].statement_status == "pending"
    assert pending[0].merged_into_medication_id is None

    # No lifecycle_change audit — nothing transitioned.
    events = [x.event_type for x in _audit_rows(db, med["id"])]
    assert "lifecycle_change" not in events


# --------------------------------------------------------------------------- #
# §5.4 — non-adherence report (T-05)
# --------------------------------------------------------------------------- #


def test_report_non_adherence(client, patient, db):
    med = _create_med(client, patient)
    r = client.post(
        f"/api/v1/patients/{patient['patient_id']}/medications/{med['id']}/report-non-adherence",
        json={"note": "Quên uống 2 ngày"},
        headers=patient["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"recorded": True}

    record = db.get(Medication, med["id"])
    db.refresh(record)
    assert record.lifecycle_status == "active"  # T-05: no state change

    rows = [
        x
        for x in _audit_rows(db, med["id"])
        if x.event_type == "patient_reported_non_adherence"
    ]
    assert len(rows) == 1
    assert rows[0].before_snapshot is None
    assert rows[0].after_snapshot is None
    assert rows[0].event_data["note"] == "Quên uống 2 ngày"


# --------------------------------------------------------------------------- #
# §5.5 — list visibility
# --------------------------------------------------------------------------- #


def _list(client, patient, **params):
    return client.get(
        f"/api/v1/patients/{patient['patient_id']}/medications",
        params=params,
        headers=patient["headers"],
    )


def test_list_default_hides_discontinued(client, patient):
    _create_med(client, patient, name="Metformin")
    stopped = _create_med(client, patient, name="Crestor")
    assert (
        _patch(client, patient, stopped["id"], {"lifecycle_status": "discontinued"}).status_code
        == 200
    )

    names = [m["name"] for m in _list(client, patient).json()["items"]]
    assert "Metformin" in names
    assert "Crestor" not in names

    names = [
        m["name"] for m in _list(client, patient, include_completed=True).json()["items"]
    ]
    assert {"Metformin", "Crestor"} <= set(names)


def test_list_lifecycle_all_is_admin_only(client, patient):
    r = _list(client, patient, lifecycle_status="all")
    assert r.status_code == 403


def test_list_specific_state_filter(client, patient, db):
    med = _create_med(client, patient, name="Levothyroxine")
    _force_lifecycle(db, med["id"], "expired")
    items = _list(client, patient, lifecycle_status="expired").json()["items"]
    assert [m["name"] for m in items] == ["Levothyroxine"]


def test_list_invalid_state_filter_rejected(client, patient):
    r = _list(client, patient, lifecycle_status="bogus")
    assert r.status_code == 422
