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
        data={"lifecycle_status": "active", "status_reason": "Đã có kết quả — tiếp tục dùng"},
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
        _patch(
            client, patient, stopped["id"],
            {"lifecycle_status": "discontinued", "status_reason": "patient_preference"},
        ).status_code
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


# --------------------------------------------------------------------------- #
# Codex R1 hardening — on_hold protection + delete statement + status_reason
# --------------------------------------------------------------------------- #


def test_patient_cannot_edit_on_hold_record_at_all(client, patient, db):
    med = _create_med(client, patient)
    _force_lifecycle(db, med["id"], "on_hold")
    r = _patch(client, patient, med["id"], {"note": "thử sửa"})
    assert r.status_code == 403


def test_patient_cannot_delete_on_hold_record(client, patient, db):
    med = _create_med(client, patient)
    _force_lifecycle(db, med["id"], "on_hold")
    r = client.delete(
        f"/api/v1/patients/{patient['patient_id']}/medications/{med['id']}",
        headers=patient["headers"],
    )
    assert r.status_code == 403


def test_delete_records_a_statement(client, patient, db):
    med = _create_med(client, patient)
    r = client.delete(
        f"/api/v1/patients/{patient['patient_id']}/medications/{med['id']}",
        headers=patient["headers"],
    )
    assert r.status_code == 204
    stmts = list(
        db.execute(
            select(MedicationStatement).where(
                MedicationStatement.merged_into_medication_id == med["id"]
            )
        ).scalars()
    )
    assert len(stmts) == 2  # create + deletion assertion
    deletion = [s for s in stmts if s.related_medication_id == med["id"]]
    assert len(deletion) == 1
    assert deletion[0].payload_snapshot["lifecycle_status"] == "active"


def test_status_reason_requires_transition(client, patient):
    med = _create_med(client, patient)
    r = _patch(client, patient, med["id"], {"status_reason": "lý do mồ côi"})
    assert r.status_code == 422


def test_transition_without_reason_clears_stale_reason(client, patient):
    med = _create_med(client, patient)
    assert (
        _patch(
            client, patient, med["id"],
            {"lifecycle_status": "paused", "status_reason": "Dừng tạm"},
        ).status_code
        == 200
    )
    r = _patch(client, patient, med["id"], {"lifecycle_status": "active"})
    assert r.status_code == 200
    assert r.json()["status_reason"] is None


# --------------------------------------------------------------------------- #
# Codex R2 hardening — transition table + mandatory reasons + null guard
# --------------------------------------------------------------------------- #


def test_same_state_transition_rejected(client, patient):
    med = _create_med(client, patient)
    r = _patch(client, patient, med["id"], {"lifecycle_status": "active"})
    assert r.status_code == 422


def test_orphan_reason_via_same_state_transition_rejected(client, patient):
    med = _create_med(client, patient)
    r = _patch(
        client, patient, med["id"],
        {"lifecycle_status": "active", "status_reason": "lý do lậu"},
    )
    assert r.status_code == 422


def test_patient_cannot_reactivate_completed(client, patient):
    med = _create_med(client, patient)
    assert (
        _patch(client, patient, med["id"], {"lifecycle_status": "completed"}).status_code == 200
    )
    r = _patch(client, patient, med["id"], {"lifecycle_status": "active"})
    assert r.status_code == 403


def test_discontinue_requires_reason(client, patient):
    med = _create_med(client, patient)
    r = _patch(client, patient, med["id"], {"lifecycle_status": "discontinued"})
    assert r.status_code == 422
    r = _patch(
        client, patient, med["id"],
        {"lifecycle_status": "discontinued", "status_reason": "adverse_effect"},
    )
    assert r.status_code == 200


def test_entered_in_error_requires_reason(client, patient):
    med = _create_med(client, patient)
    r = _patch(client, patient, med["id"], {"lifecycle_status": "entered_in_error"})
    assert r.status_code == 422


def test_null_lifecycle_status_rejected(client, patient):
    med = _create_med(client, patient)
    r = _patch(client, patient, med["id"], {"lifecycle_status": None})
    assert r.status_code == 422


def test_delete_of_on_hold_blocked_for_everyone(client, patient, db):
    med = _create_med(client, patient)
    _force_lifecycle(db, med["id"], "on_hold")
    # Service-level doctor call is also refused — doctors cannot delete at
    # the route layer either (clinical safety), so the state is consistent.
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        medication_svc.delete_medication(
            db, patient_id=patient["patient_id"], med_id=med["id"], actor_role="doctor"
        )
    assert exc.value.status_code == 403


# --------------------------------------------------------------------------- #
# Codex R3 hardening
# --------------------------------------------------------------------------- #


def test_patient_can_flag_on_hold_record_entered_in_error(client, patient, db):
    med = _create_med(client, patient)
    _force_lifecycle(db, med["id"], "on_hold")
    r = _patch(
        client, patient, med["id"],
        {"lifecycle_status": "entered_in_error", "status_reason": "Nhập nhầm thuốc"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["lifecycle_status"] == "entered_in_error"


def test_on_hold_error_flag_with_extra_fields_still_blocked(client, patient, db):
    med = _create_med(client, patient)
    _force_lifecycle(db, med["id"], "on_hold")
    r = _patch(
        client, patient, med["id"],
        {"lifecycle_status": "entered_in_error", "status_reason": "x", "note": "sửa lén"},
    )
    assert r.status_code == 403


def test_expired_re_review_doctor_prescribed_goes_to_clinician(client, patient, db):
    med = _create_med(client, patient)
    db.execute(
        update(Medication)
        .where(Medication.id == med["id"])
        .values(lifecycle_status="expired", source_type="doctor_prescribed")
    )
    db.commit()
    r = _patch(client, patient, med["id"], {"lifecycle_status": "active"})
    assert r.status_code == 200
    stmt = db.execute(
        select(MedicationStatement).where(
            MedicationStatement.related_medication_id == med["id"],
            MedicationStatement.assertion_type == "continued_use",
        )
    ).scalar_one()
    assert stmt.statement_status == "awaiting_clinician"


def test_expired_re_review_rejects_mixed_payload(client, patient, db):
    med = _create_med(client, patient)
    _force_lifecycle(db, med["id"], "expired")
    r = _patch(
        client, patient, med["id"],
        {"lifecycle_status": "active", "dose": "1000mg"},
    )
    assert r.status_code == 422


def test_entered_in_error_filter_admin_only(client, patient):
    r = _list(client, patient, lifecycle_status="entered_in_error")
    assert r.status_code == 403


def test_re_review_statement_has_effective_from(client, patient, db):
    med = _create_med(client, patient)
    _force_lifecycle(db, med["id"], "expired")
    assert _patch(client, patient, med["id"], {"lifecycle_status": "active"}).status_code == 200
    stmt = db.execute(
        select(MedicationStatement).where(
            MedicationStatement.related_medication_id == med["id"],
            MedicationStatement.assertion_type == "continued_use",
        )
    ).scalar_one()
    assert stmt.effective_from is not None


# --------------------------------------------------------------------------- #
# Codex R5 hardening — verify endpoint + entered_in_error roles + report RBAC
# --------------------------------------------------------------------------- #


def test_doctor_cannot_set_entered_in_error(client, patient, db):
    med = _create_med(client, patient)
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        medication_svc.update_medication(
            db,
            patient_id=patient["patient_id"],
            med_id=med["id"],
            data={"lifecycle_status": "entered_in_error", "status_reason": "x"},
            actor_role="doctor",
        )
    assert exc.value.status_code == 403


def test_admin_can_set_entered_in_error(client, patient, db):
    med = _create_med(client, patient)
    record = medication_svc.update_medication(
        db,
        patient_id=patient["patient_id"],
        med_id=med["id"],
        data={"lifecycle_status": "entered_in_error", "status_reason": "data fix"},
        actor_role="internal_admin",
    )
    assert record.lifecycle_status == "entered_in_error"


def test_verify_medication_doctor_only(client, patient, db):
    med = _create_med(client, patient)
    # Patient via route → 403
    r = client.post(
        f"/api/v1/patients/{patient['patient_id']}/medications/{med['id']}/verify",
        headers=patient["headers"],
    )
    assert r.status_code == 403

    # Doctor via service → confirmed + verification_change audit; idempotent.
    record = medication_svc.verify_medication(
        db,
        medication_id=med["id"],
        patient_id=patient["patient_id"],
        actor_role="doctor",
    )
    assert record.verification_status == "clinician_confirmed"
    record = medication_svc.verify_medication(
        db,
        medication_id=med["id"],
        patient_id=patient["patient_id"],
        actor_role="doctor",
    )
    assert record.verification_status == "clinician_confirmed"

    rows = [x for x in _audit_rows(db, med["id"]) if x.event_type == "verification_change"]
    assert len(rows) == 1
    assert rows[0].old_value == "patient_reported"
    assert rows[0].new_value == "clinician_confirmed"
    assert rows[0].before_snapshot["verification_status"] == "patient_reported"
    assert rows[0].after_snapshot["verification_status"] == "clinician_confirmed"


def test_doctor_cannot_complete_from_paused(client, patient, db):
    med = _create_med(client, patient)
    assert _patch(client, patient, med["id"], {"lifecycle_status": "paused"}).status_code == 200
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        medication_svc.update_medication(
            db,
            patient_id=patient["patient_id"],
            med_id=med["id"],
            data={"lifecycle_status": "completed"},
            actor_role="doctor",
        )
    assert exc.value.status_code == 422


def test_adherence_log_rejected_for_paused(client, patient):
    med = _create_med(client, patient)
    assert _patch(client, patient, med["id"], {"lifecycle_status": "paused"}).status_code == 200
    r = client.post(
        f"/api/v1/patients/{patient['patient_id']}/medications/{med['id']}/adherence",
        json={"skipped": True},
        headers=patient["headers"],
    )
    assert r.status_code == 422


def test_adherence_summary_excludes_paused_from_today(client, patient):
    active = _create_med(client, patient, name="Metformin")
    paused = _create_med(client, patient, name="Crestor")
    assert _patch(client, patient, paused["id"], {"lifecycle_status": "paused"}).status_code == 200
    r = client.get(
        f"/api/v1/patients/{patient['patient_id']}/medications/adherence-summary",
        headers=patient["headers"],
    )
    assert r.status_code == 200, r.text
    names = [m["name"] for m in r.json()["today_medications"]]
    assert "Metformin" in names
    assert "Crestor" not in names
    assert active["id"]
