"""PR-S1 behavioral tests — statement-first writes + audit writer (T-04 subset).

ADR-04 invariant under test: every create/edit of a canonical ``medications``
row produces a ``medication_statements`` row in the same transaction, and
every state change appends a ``medication_audit_log`` row.

Uses the existing ``client``/``patient``/``db`` conftest fixtures (SQLite).
"""

from __future__ import annotations

from app.models.clinical import Medication, MedicationAuditLog, MedicationStatement
from sqlalchemy import select


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


def _statements(db, med_id):
    return list(
        db.execute(
            select(MedicationStatement).where(
                MedicationStatement.merged_into_medication_id == med_id
            )
        ).scalars()
    )


def _audit_rows(db, med_id):
    return list(
        db.execute(
            select(MedicationAuditLog)
            .where(MedicationAuditLog.medication_id == med_id)
            .order_by(MedicationAuditLog.created_at)
        ).scalars()
    )


# --------------------------------------------------------------------------- #
# Create: statement-first
# --------------------------------------------------------------------------- #


def test_create_produces_accepted_statement(client, patient, db):
    med = _create_med(client, patient)

    stmts = _statements(db, med["id"])
    assert len(stmts) == 1
    s = stmts[0]
    assert s.patient_id == patient["patient_id"]
    assert s.source_type == "patient_manual"
    assert s.assertion_type == "new_entry"
    assert s.statement_status == "accepted"
    assert s.raw_drug_name == "Metformin"
    assert s.raw_dose == "850mg"
    assert s.raw_frequency == "2 lần/ngày"


def test_create_writes_audit_row_with_after_snapshot_only(client, patient, db):
    med = _create_med(client, patient, name="Crestor", dose="10mg")

    rows = _audit_rows(db, med["id"])
    assert len(rows) == 1
    row = rows[0]
    assert row.event_type == "create"
    assert row.before_snapshot is None
    assert row.after_snapshot is not None
    assert row.after_snapshot["name"] == "Crestor"
    assert row.after_snapshot["dose"] == "10mg"
    assert row.after_snapshot["lifecycle_status"] == "active"
    assert row.created_by_role == "patient"  # CurrentUser.role is lowercase
    assert row.created_by_user_id is not None


def test_created_medication_has_p0_defaults(client, patient, db):
    med = _create_med(client, patient)
    record = db.get(Medication, med["id"])
    assert record.lifecycle_status == "active"
    assert record.verification_status == "patient_reported"
    assert record.source_type == "patient_manual"
    assert record.medication_category == "conventional_drug"


# --------------------------------------------------------------------------- #
# Update: statement-first + before/after audit
# --------------------------------------------------------------------------- #


def test_update_produces_statement_and_audit(client, patient, db):
    med = _create_med(client, patient)
    r = client.patch(
        f"/api/v1/patients/{patient['patient_id']}/medications/{med['id']}",
        json={"dose": "1000mg"},
        headers=patient["headers"],
    )
    assert r.status_code == 200, r.text

    stmts = _statements(db, med["id"])
    assert len(stmts) == 2  # create + update
    update_stmt = [s for s in stmts if s.related_medication_id == med["id"]]
    assert len(update_stmt) == 1
    assert update_stmt[0].payload_snapshot["dose"] == "850mg"  # pre-change state
    assert update_stmt[0].raw_dose == "1000mg"

    rows = _audit_rows(db, med["id"])
    assert [r.event_type for r in rows] == ["create", "update"]
    upd = rows[1]
    assert upd.field_changed == "dose"
    assert upd.old_value == "850mg"
    assert upd.new_value == "1000mg"
    assert upd.before_snapshot["dose"] == "850mg"
    assert upd.after_snapshot["dose"] == "1000mg"
    assert upd.event_data == {"fields": ["dose"]}


# --------------------------------------------------------------------------- #
# Delete: lifecycle transition + audit (C1 fix)
# --------------------------------------------------------------------------- #


def test_delete_sets_entered_in_error_and_audits(client, patient, db):
    med = _create_med(client, patient)
    r = client.delete(
        f"/api/v1/patients/{patient['patient_id']}/medications/{med['id']}",
        headers=patient["headers"],
    )
    assert r.status_code == 204, r.text

    record = db.get(Medication, med["id"])
    db.refresh(record)
    assert record.deleted_at is not None
    assert record.lifecycle_status == "entered_in_error"
    assert record.deleted_by is not None

    rows = _audit_rows(db, med["id"])
    assert [r.event_type for r in rows] == ["create", "lifecycle_change"]
    change = rows[1]
    assert change.field_changed == "lifecycle_status"
    assert change.old_value == "active"
    assert change.new_value == "entered_in_error"
    assert change.before_snapshot["lifecycle_status"] == "active"
    assert change.before_snapshot["deleted_at"] is None
    assert change.after_snapshot["lifecycle_status"] == "entered_in_error"
    assert change.after_snapshot["deleted_at"] is not None


def test_delete_is_idempotent_single_audit_row(client, patient, db):
    med = _create_med(client, patient)
    url = f"/api/v1/patients/{patient['patient_id']}/medications/{med['id']}"
    assert client.delete(url, headers=patient["headers"]).status_code == 204
    assert client.delete(url, headers=patient["headers"]).status_code == 204

    rows = _audit_rows(db, med["id"])
    assert len([r for r in rows if r.event_type == "lifecycle_change"]) == 1


# --------------------------------------------------------------------------- #
# Adherence: observational audit event (NULL snapshots)
# --------------------------------------------------------------------------- #


def test_skipped_dose_writes_observational_event(client, patient, db):
    med = _create_med(client, patient)
    r = client.post(
        f"/api/v1/patients/{patient['patient_id']}/medications/{med['id']}/adherence",
        json={"skipped": True, "note": "Quên uống"},
        headers=patient["headers"],
    )
    assert r.status_code == 201, r.text

    rows = [
        row
        for row in _audit_rows(db, med["id"])
        if row.event_type == "patient_reported_non_adherence"
    ]
    assert len(rows) == 1
    row = rows[0]
    assert row.before_snapshot is None
    assert row.after_snapshot is None
    assert row.event_data["note"] == "Quên uống"
    assert row.event_data["adherence_id"]


def test_taken_dose_writes_no_observational_event(client, patient, db):
    med = _create_med(client, patient)
    r = client.post(
        f"/api/v1/patients/{patient['patient_id']}/medications/{med['id']}/adherence",
        json={"taken_at": "2026-07-13T08:00:00Z", "skipped": False},
        headers=patient["headers"],
    )
    assert r.status_code == 201, r.text
    events = [row.event_type for row in _audit_rows(db, med["id"])]
    assert "patient_reported_non_adherence" not in events


# --------------------------------------------------------------------------- #
# Invariant: no canonical row without a statement
# --------------------------------------------------------------------------- #


def test_every_medication_has_a_statement(client, patient, db):
    for name in ("Metformin", "Crestor", "Levothyroxine"):
        _create_med(client, patient, name=name)

    med_ids = set(
        db.execute(
            select(Medication.id).where(Medication.patient_id == patient["patient_id"])
        ).scalars()
    )
    covered = set(
        db.execute(
            select(MedicationStatement.merged_into_medication_id).where(
                MedicationStatement.patient_id == patient["patient_id"]
            )
        ).scalars()
    )
    assert med_ids <= covered, f"medications without statements: {med_ids - covered}"


def test_api_response_shape_unchanged(client, patient):
    med = _create_med(client, patient)
    # PR-S1 must NOT expose new fields — API contract is frozen until PR-S2.
    assert set(med.keys()) == {
        "id",
        "patient_id",
        "name",
        "dose",
        "frequency",
        "note",
        "created_at",
    }


def test_empty_patch_is_true_noop(client, patient, db):
    med = _create_med(client, patient)
    r = client.patch(
        f"/api/v1/patients/{patient['patient_id']}/medications/{med['id']}",
        json={},
        headers=patient["headers"],
    )
    assert r.status_code == 200, r.text
    # No provenance/audit records for a change that changed nothing.
    assert len(_statements(db, med["id"])) == 1  # the create statement only
    assert [row.event_type for row in _audit_rows(db, med["id"])] == ["create"]
