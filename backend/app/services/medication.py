"""Medication service — add, list, and soft-delete Medication records (T15).

Pure service functions; all HTTP concerns live in the route layer.
RBAC and consent checks are performed by the caller (route) before
invoking these functions.

SAFETY NOTE: AI must NEVER add or modify medication records.  This constraint
is enforced at the API/RBAC layer; this service layer trusts the caller has
already validated access.

ADR-04 invariant (P0 service phase): every create/edit of a canonical
``medications`` row goes through ``medication_statements`` first, and every
state change writes a ``medication_audit_log`` row in the SAME transaction.
No write path may bypass the statement table.
"""

from __future__ import annotations

import datetime as dt

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.clock import as_naive_utc, utcnow
from app.models.clinical import (
    Medication,
    MedicationAdherence,
    MedicationAuditLog,
    MedicationStatement,
)

DELETED_LIFECYCLE_STATUS = "entered_in_error"

# Plan §6.1 — closed value set (mirrors the DB CHECK constraint) and the
# subset a PATIENT may set via the API. on_hold is doctor-only in BOTH
# directions; expired is reserved for the (future) system job.
LIFECYCLE_STATUSES = {
    "active",
    "paused",
    "on_hold",
    "completed",
    "discontinued",
    "expired",
    "entered_in_error",
}
PATIENT_SETTABLE_STATUSES = {
    "active",
    "paused",
    "completed",
    "discontinued",
    "entered_in_error",
}
# Default list visibility (Plan §5.5).
DEFAULT_VISIBLE_STATUSES = ["active", "paused", "on_hold"]
COMPLETED_VISIBLE_STATUSES = ["completed", "discontinued"]

# ADR-11 'From states' — the ONLY legal source→target pairs, for every
# role (role overlays like on_hold-doctor-only apply on top). target
# entered_in_error is additionally allowed from any non-terminal source.
ALLOWED_TRANSITIONS = {
    ("paused", "active"),
    ("on_hold", "active"),
    ("active", "paused"),
    ("active", "on_hold"),
    ("active", "completed"),
    ("active", "discontinued"),
    ("paused", "discontinued"),
    ("on_hold", "discontinued"),
}
ADMIN_ROLES = {"internal_admin", "super_admin"}
# Roles that may perform ANY lifecycle transition at all (Plan §6.1 names
# only these; everything else — e.g. medical_reviewer — is read-only).
LIFECYCLE_ROLES = {"patient", "doctor"} | ADMIN_ROLES
# ADR-11 §Transition reasons — these transitions REQUIRE a status_reason;
# any → entered_in_error also requires one (handled separately).
REASON_REQUIRED_TRANSITIONS = {
    ("active", "discontinued"),
    ("active", "on_hold"),
    ("on_hold", "active"),
}


def _validate_lifecycle_transition(
    record: Medication,
    target: str,
    actor_role: str | None,
    reason: str | None,
) -> None:
    """Enforce Plan §6.1 RBAC + ADR-11 reason rules for a transition (4xx)."""
    current = record.lifecycle_status
    if target == current:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"lifecycle_status đã là '{target}' — không có transition.",
        )
    role = (actor_role or "").lower()
    # Explicit lifecycle-role allowlist: unlisted roles (e.g.
    # medical_reviewer) must never change clinical state (Codex R14).
    if role not in LIFECYCLE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vai trò này không được phép thay đổi lifecycle_status.",
        )
    # ADR-11: entered_in_error is TERMINAL ("record should not exist") —
    # no outgoing transition for any role. Re-create the medication instead.
    if current == "entered_in_error":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="entered_in_error là trạng thái cuối — tạo hồ sơ thuốc mới thay vì khôi phục.",
        )
    if target == "expired":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="expired chỉ được set bởi hệ thống.",
        )
    if target == "on_hold" and role != "doctor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="on_hold chỉ được set bởi bác sĩ.",
        )
    # ADR-11 'From states': completed is a planned course end — only an
    # ACTIVE medication can complete, for every role.
    if target == "completed" and current != "active":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"completed chỉ hợp lệ từ 'active' (hiện tại: '{current}').",
        )
    # ADR-11 role matrix: entered_in_error is reserved to PATIENT (own
    # record) and ADMIN — a doctor cannot remove a record from clinical
    # processing this way.
    if target == "entered_in_error" and role not in ({"patient"} | ADMIN_ROLES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="entered_in_error chỉ dành cho bệnh nhân (hồ sơ của mình) hoặc admin.",
        )
    # ADR-11: any → entered_in_error is permitted from every source state
    # (including on_hold) — it flags a mistaken record, not a clinical change.
    if target != "entered_in_error":
        if current == "on_hold" and role != "doctor":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Chỉ bác sĩ có thể thay đổi trạng thái on_hold.",
            )
        # Universal state machine — doctors are NOT exempt (Codex R12: a
        # completed/discontinued drug must never be reactivated in place).
        if (current, target) not in ALLOWED_TRANSITIONS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Transition '{current}' → '{target}' không hợp lệ (ADR-11).",
            )
    if (
        (current, target) in REASON_REQUIRED_TRANSITIONS or target == "entered_in_error"
    ) and not reason:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Transition '{current}' → '{target}' bắt buộc phải có status_reason (ADR-11).",
        )


def _snapshot(record: Medication) -> dict:
    """JSON-safe snapshot of the full canonical medication state."""
    return {
        "id": record.id,
        "patient_id": record.patient_id,
        "name": record.name,
        "dose": record.dose,
        "frequency": record.frequency,
        "note": record.note,
        "lifecycle_status": record.lifecycle_status,
        "verification_status": record.verification_status,
        "source_type": record.source_type,
        "medication_category": record.medication_category,
        "status_reason": record.status_reason,
        "drug_product_id": record.drug_product_id,
        "generic_name": record.generic_name,
        "deleted_at": record.deleted_at.isoformat() if record.deleted_at else None,
        "deleted_by": record.deleted_by,
    }


def _write_audit(
    db: Session,
    *,
    record: Medication,
    event_type: str,
    field_changed: str | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
    transition_reason: str | None = None,
    event_data: dict | None = None,
    before: dict | None = None,
    after: dict | None = None,
    actor_user_id: str | None = None,
    actor_role: str | None = None,
) -> None:
    """Append one medication_audit_log row (no commit — caller owns the txn)."""
    db.add(
        MedicationAuditLog(
            medication_id=record.id,
            patient_id=record.patient_id,
            event_type=event_type,
            field_changed=field_changed,
            old_value=old_value,
            new_value=new_value,
            transition_reason=transition_reason,
            event_data=event_data,
            before_snapshot=before,
            after_snapshot=after,
            created_by_user_id=actor_user_id,
            created_by_role=actor_role,
        )
    )


def add_medication(
    db: Session,
    *,
    patient_id: str,
    data: dict,
    actor_user_id: str | None = None,
    actor_role: str | None = None,
    source_type: str = "patient_manual",
    commit: bool = True,
) -> Medication:
    """Persist a new Medication record for *patient_id* (statement-first).

    ``data`` must contain at least ``name``.  Optional keys:
    ``dose``, ``frequency`` and ``note``.

    ``source_type`` provenance stamps both the statement and the canonical row
    (must be a value allowed by the ``chk_source_type`` CHECK on ``medications``,
    e.g. ``patient_manual`` (default) or ``ocr_confirmed`` for a confirmed
    prescription-OCR promotion). Used by the MDI medication promoter (§1.5).

    Flow (Implementation Plan §5.2, single transaction):
      statement(pending) → canonical row → statement accepted+merged → audit.

    Returns the committed Medication instance.
    """
    statement = MedicationStatement(
        patient_id=patient_id,
        source_type=source_type,
        assertion_type="new_entry",
        raw_drug_name=data["name"],
        raw_dose=data.get("dose"),
        raw_frequency=data.get("frequency"),
        statement_status="pending",
    )
    db.add(statement)
    # Flush the statement BEFORE the canonical write — SQLAlchemy otherwise
    # orders INSERTs by FK dependency (medications first), which would invert
    # the ADR-04 statement-first sequence inside the transaction.
    db.flush()

    record = Medication(
        patient_id=patient_id,
        name=data["name"],
        dose=data.get("dose"),
        frequency=data.get("frequency"),
        note=data.get("note"),
        source_type=source_type,
    )
    db.add(record)
    db.flush()

    statement.statement_status = "accepted"
    statement.merged_into_medication_id = record.id

    _write_audit(
        db,
        record=record,
        event_type="create",
        after=_snapshot(record),
        actor_user_id=actor_user_id,
        actor_role=actor_role,
    )

    # commit=False lets transaction-owning callers (seed script savepoints)
    # keep the statement+row+audit trio inside their own atomic scope.
    if commit:
        db.commit()
        db.refresh(record)
    else:
        db.flush()
    return record


def update_medication(
    db: Session,
    *,
    patient_id: str,
    med_id: str,
    data: dict,
    actor_user_id: str | None = None,
    actor_role: str | None = None,
) -> Medication:
    """Apply a partial update to a Medication record (PR-D).

    Only keys present in *data* are written (caller passes ``exclude_unset``).
    An empty *data* is a true no-op: no statement, no audit row.
    Raises 404 if the record does not exist, is soft-deleted, or belongs to a
    different patient.
    """
    # Row lock (no-op on SQLite) serializes against concurrent delete/update,
    # so the deleted_at check and the before-snapshot reflect committed state.
    record = db.execute(
        select(Medication).where(Medication.id == med_id).with_for_update()
    ).scalar_one_or_none()

    if record is None or record.patient_id != patient_id or record.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medication not found.",
        )

    if not data:
        return record

    # entered_in_error is terminal AND excluded from all clinical
    # processing — no edit of any kind (Codex R12 P2).
    if record.lifecycle_status == "entered_in_error":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Hồ sơ entered_in_error là trạng thái cuối — không thể chỉnh sửa.",
        )

    # on_hold is a doctor-controlled state: NO edit of any kind by others
    # while it holds (Codex R1 P1 — non-lifecycle PATCH must not bypass it).
    # Sole exception (ADR-11: any → entered_in_error): a PURE
    # entered-in-error transition may still flag a mistaken record.
    _is_pure_error_flag = data.get("lifecycle_status") == "entered_in_error" and set(
        data
    ) <= {"lifecycle_status", "status_reason"}
    if (
        record.lifecycle_status == "on_hold"
        and (actor_role or "").lower() != "doctor"
        and not _is_pure_error_flag
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ bác sĩ có thể thay đổi hồ sơ thuốc đang on_hold.",
        )

    lifecycle_target = data.get("lifecycle_status")
    if lifecycle_target is None and "status_reason" in data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="status_reason chỉ được gửi kèm một lifecycle transition.",
        )
    if "lifecycle_status" in data and lifecycle_target is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="lifecycle_status không được là null.",
        )
    if lifecycle_target is not None:
        if lifecycle_target not in LIFECYCLE_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid lifecycle_status '{lifecycle_target}'.",
            )
        # Set-or-clear on every transition so a stale reason never survives
        # a later transition that omits it.
        data = {**data, "status_reason": data.get("status_reason")}

        # Q-OQ-1 (Plan §6.3): a patient re-asserting an expired medication
        # does NOT directly reactivate it — a pending continued_use statement
        # is created for review instead, and the canonical row is untouched.
        # Checked BEFORE the transition table (this path is deliberately not
        # a transition).
        if (
            record.lifecycle_status == "expired"
            and lifecycle_target == "active"
            and (actor_role or "").lower() == "patient"
        ):
            extra_fields = set(data) - {"lifecycle_status", "status_reason"}
            if extra_fields:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "Re-assert thuốc expired phải gửi riêng — không kèm "
                        f"chỉnh sửa khác ({', '.join(sorted(extra_fields))})."
                    ),
                )
            db.add(
                MedicationStatement(
                    patient_id=patient_id,
                    source_type="patient_manual",
                    assertion_type="continued_use",
                    related_medication_id=record.id,
                    payload_snapshot=_snapshot(record),
                    raw_drug_name=record.name,
                    raw_dose=record.dose,
                    raw_frequency=record.frequency,
                    # Case A/B/C gap reconciliation needs the re-assert date.
                    effective_from=utcnow().date(),
                    # Plan §6.3 Case D: doctor-prescribed expired records go
                    # to the clinician queue; patient-resolvable otherwise.
                    statement_status=(
                        "awaiting_clinician"
                        if record.source_type == "doctor_prescribed"
                        else "pending"
                    ),
                )
            )
            db.commit()
            db.refresh(record)
            return record

        _validate_lifecycle_transition(
            record, lifecycle_target, actor_role, data.get("status_reason")
        )

    before = _snapshot(record)

    # Statement-first (ADR-04): an edit is a corrected assertion about the
    # same medication — recorded before the canonical row changes.
    statement = MedicationStatement(
        patient_id=patient_id,
        source_type="patient_manual",
        assertion_type="new_entry",
        related_medication_id=record.id,
        payload_snapshot=before,
        raw_drug_name=data.get("name", record.name),
        raw_dose=data.get("dose", record.dose),
        raw_frequency=data.get("frequency", record.frequency),
        statement_status="accepted",
        merged_into_medication_id=record.id,
    )
    db.add(statement)
    # Statement INSERT precedes the canonical UPDATE (ADR-04 ordering).
    db.flush()

    for field, value in data.items():
        setattr(record, field, value)
    db.flush()

    after = _snapshot(record)
    changed = sorted(f for f in data if before.get(f) != after.get(f))
    if lifecycle_target is not None and "lifecycle_status" in changed:
        # T-04: lifecycle transitions are first-class audit events, with
        # status_reason preserved as transition_reason.
        _write_audit(
            db,
            record=record,
            event_type="lifecycle_change",
            field_changed="lifecycle_status",
            old_value=before["lifecycle_status"],
            new_value=after["lifecycle_status"],
            transition_reason=data.get("status_reason"),
            event_data={"fields": changed},
            before=before,
            after=after,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
        )
    else:
        single = changed[0] if len(changed) == 1 else None
        _write_audit(
            db,
            record=record,
            event_type="update",
            field_changed=single,
            old_value=str(before[single]) if single else None,
            new_value=str(after[single]) if single else None,
            event_data={"fields": changed},
            before=before,
            after=after,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
        )

    db.commit()
    db.refresh(record)
    return record


def list_medications(
    db: Session,
    *,
    patient_id: str,
    limit: int = 20,
    offset: int = 0,
    lifecycle_filter: str | None = None,
    include_completed: bool = False,
) -> tuple[int, list[Medication]]:
    """Return *(total, items)* for the patient's active medication records.

    Only non-deleted records (``deleted_at IS NULL``) are included.
    Default visibility (Plan §5.5): active/paused/on_hold. ``include_completed``
    adds completed+discontinued. ``lifecycle_filter`` overrides: a specific
    state, or ``"all"`` (caller must have enforced admin RBAC).
    Items are ordered oldest-first (``created_at ASC``).
    *limit* is clamped to 100.
    """
    limit = min(limit, 100)

    filters = [
        Medication.patient_id == patient_id,
        Medication.deleted_at.is_(None),
    ]
    if lifecycle_filter == "all":
        pass  # no lifecycle restriction (admin-only, enforced by the route)
    elif lifecycle_filter is not None:
        filters.append(Medication.lifecycle_status == lifecycle_filter)
    else:
        visible = list(DEFAULT_VISIBLE_STATUSES)
        if include_completed:
            visible += COMPLETED_VISIBLE_STATUSES
        filters.append(Medication.lifecycle_status.in_(visible))
    base_filter = tuple(filters)

    total: int = db.execute(
        select(func.count()).select_from(Medication).where(*base_filter)
    ).scalar_one()

    rows = list(
        db.execute(
            select(Medication)
            .where(*base_filter)
            .order_by(Medication.created_at.asc())
            .limit(limit)
            .offset(offset)
        ).scalars()
    )

    return total, rows


def delete_medication(
    db: Session,
    *,
    patient_id: str,
    med_id: str,
    actor_user_id: str | None = None,
    actor_role: str | None = None,
) -> bool:
    """Soft-delete a Medication record as a lifecycle transition.

    Sets ``deleted_at`` AND ``lifecycle_status='entered_in_error'`` (the
    invariant migration p0_m01 established: soft-deleted ⇒ entered_in_error),
    and writes the audit row in the same transaction.  Raises 404 if the
    record does not exist or belongs to a different patient.  Does NOT raise
    on an already-deleted record — it is idempotent on repeated calls.

    Returns True when THIS call performed the transition (callers gate their
    own success auditing on it); False for already-deleted/no-op calls.

    Raises:
        404 — record not found or not owned by *patient_id*.
    """
    record = db.execute(
        select(Medication).where(Medication.id == med_id).with_for_update()
    ).scalar_one_or_none()

    if record is None or record.patient_id != patient_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medication not found.",
        )

    if record.deleted_at is None and record.lifecycle_status == "entered_in_error":
        # Already terminal and excluded from processing — deleting again would
        # write a bogus same-state transition. No-op.
        return False

    if record.deleted_at is None:
        # Deletion IS a lifecycle exit. on_hold records cannot be deleted via
        # this API by ANYONE: patients/admins lack on_hold authority, and the
        # route blocks doctors from deleting medications entirely (clinical
        # safety). The doctor must clear on_hold first.
        if record.lifecycle_status == "on_hold":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Hồ sơ thuốc đang on_hold — bác sĩ phải gỡ on_hold trước khi xoá.",
            )

        before = _snapshot(record)
        previous_status = record.lifecycle_status

        # Statement-first (ADR-04): the deletion assertion is recorded before
        # the canonical row changes, inside the same transaction — a lost
        # race below rolls it back together with everything else.
        db.add(
            MedicationStatement(
                patient_id=patient_id,
                source_type="patient_manual",
                assertion_type="new_entry",
                related_medication_id=record.id,
                payload_snapshot=before,
                raw_drug_name=record.name,
                raw_dose=record.dose,
                raw_frequency=record.frequency,
                statement_status="accepted",
                merged_into_medication_id=record.id,
            )
        )
        db.flush()

        # Conditional UPDATE guards against concurrent deletes: only the
        # request that wins the WHERE deleted_at IS NULL race performs the
        # transition and writes the audit row.
        result = db.execute(
            update(Medication)
            .where(Medication.id == med_id, Medication.deleted_at.is_(None))
            .values(
                deleted_at=utcnow(),
                deleted_by=actor_user_id,
                lifecycle_status=DELETED_LIFECYCLE_STATUS,
            )
        )
        if result.rowcount != 1:
            db.rollback()  # lost the race — the other request owns the audit
            return False
        db.refresh(record)

        _write_audit(
            db,
            record=record,
            event_type="lifecycle_change",
            field_changed="lifecycle_status",
            old_value=previous_status,
            new_value=DELETED_LIFECYCLE_STATUS,
            transition_reason="patient_deleted_record",
            before=before,
            after=_snapshot(record),
            actor_user_id=actor_user_id,
            actor_role=actor_role,
        )
        db.commit()
        return True

    return False


# --------------------------------------------------------------------------- #
# Adherence (Phase 2)
# --------------------------------------------------------------------------- #


def log_adherence(
    db: Session,
    *,
    medication_id: str,
    patient_id: str,
    data: dict,
    actor_user_id: str | None = None,
    actor_role: str | None = None,
) -> MedicationAdherence:
    """Record a dose event (taken or skipped) for a medication.

    A skipped dose additionally writes an observational
    ``patient_reported_non_adherence`` audit event (T-04: NULL snapshots —
    observational events never carry state).  No lifecycle change.

    Raises 404 if the medication does not belong to the patient or is deleted.
    """
    med = db.get(Medication, medication_id)
    if med is None or med.patient_id != patient_id or med.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medication not found.",
        )
    if med.lifecycle_status != "active":
        # Dose events belong to actively-taken regimens; paused/on_hold
        # concerns go through report-non-adherence (observational channel).
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Chỉ ghi nhận liều cho thuốc đang active.",
        )
    record = MedicationAdherence(
        medication_id=medication_id,
        patient_id=patient_id,
        scheduled_time=data.get("scheduled_time"),
        taken_at=data.get("taken_at"),
        skipped=data.get("skipped", False),
        note=data.get("note"),
    )
    db.add(record)
    db.flush()

    if record.skipped:
        _write_audit(
            db,
            record=med,
            event_type="patient_reported_non_adherence",
            event_data={"adherence_id": record.id, "note": data.get("note")},
            actor_user_id=actor_user_id,
            actor_role=actor_role,
        )

    db.commit()
    db.refresh(record)
    return record


def verify_medication(
    db: Session,
    *,
    medication_id: str,
    patient_id: str,
    actor_user_id: str | None = None,
    actor_role: str | None = None,
) -> Medication:
    """Clinician verification (ADR-11 §API): set verification_status to
    'clinician_confirmed' with a verification_change audit event.

    Doctor-only. Idempotent: verifying an already-confirmed record is a
    no-op (no duplicate audit row). No MedicationStatement is created —
    verification is a clinician attestation ABOUT the record, not a new
    assertion of medication use (ADR-04 statements model usage assertions).

    Raises 403 for non-doctors, 404 if not found/deleted/not owned.
    """
    if (actor_role or "").lower() != "doctor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ bác sĩ có thể xác nhận thuốc.",
        )
    record = db.execute(
        select(Medication).where(Medication.id == medication_id).with_for_update()
    ).scalar_one_or_none()
    if record is None or record.patient_id != patient_id or record.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medication not found.",
        )
    if record.lifecycle_status == "entered_in_error":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Không thể xác nhận hồ sơ entered_in_error (trạng thái cuối).",
        )
    if record.verification_status == "clinician_confirmed":
        return record

    before = _snapshot(record)
    previous = record.verification_status
    record.verification_status = "clinician_confirmed"
    db.flush()
    _write_audit(
        db,
        record=record,
        event_type="verification_change",
        field_changed="verification_status",
        old_value=previous,
        new_value="clinician_confirmed",
        before=before,
        after=_snapshot(record),
        actor_user_id=actor_user_id,
        actor_role=actor_role,
    )
    db.commit()
    db.refresh(record)
    return record


def report_non_adherence(
    db: Session,
    *,
    medication_id: str,
    patient_id: str,
    note: str | None = None,
    actor_user_id: str | None = None,
    actor_role: str | None = None,
) -> None:
    """Record a patient non-adherence report (Plan §5.4, gate T-05).

    Pure observational event: one medication_audit_log row with NULL
    before/after snapshots. Does NOT change lifecycle_status.

    Raises 404 if the medication does not belong to the patient or is deleted.
    """
    med = db.get(Medication, medication_id)
    if med is None or med.patient_id != patient_id or med.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medication not found.",
        )
    if med.lifecycle_status == "entered_in_error":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Hồ sơ entered_in_error không nhận báo cáo non-adherence.",
        )
    _write_audit(
        db,
        record=med,
        event_type="patient_reported_non_adherence",
        event_data={"note": note},
        actor_user_id=actor_user_id,
        actor_role=actor_role,
    )
    db.commit()


def get_adherence(
    db: Session,
    *,
    medication_id: str,
    patient_id: str,
    limit: int = 30,
) -> list[MedicationAdherence]:
    """Return the most recent adherence records for one medication, newest first."""
    med = db.get(Medication, medication_id)
    if (
        med is None
        or med.patient_id != patient_id
        or med.deleted_at is not None
        or med.lifecycle_status == "entered_in_error"
    ):
        # entered_in_error is excluded from all display incl. dose history.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medication not found.",
        )
    rows = list(
        db.execute(
            select(MedicationAdherence)
            .where(
                MedicationAdherence.medication_id == medication_id,
                MedicationAdherence.patient_id == patient_id,
            )
            .order_by(MedicationAdherence.created_at.desc())
            .limit(min(limit, 100))
        ).scalars()
    )
    return rows


def _compute_streaks(taken_dates: list[dt.date]) -> tuple[int, int]:
    """Return *(current_streak, longest_streak)* from a list of unique UTC dates.

    Args:
        taken_dates: Sorted list of unique calendar dates where patient took at
            least one dose.  May be unsorted — this function sorts internally.

    Returns:
        A tuple ``(current_streak, longest_streak)`` where:
        - *current_streak* counts consecutive days ending at today or yesterday
          (UTC).  If the most recent taken date is before yesterday the streak
          is 0.
        - *longest_streak* is the maximum run of consecutive calendar days
          anywhere in the history.
    """
    if not taken_dates:
        return 0, 0

    unique_sorted = sorted(set(taken_dates))
    today = utcnow().date()
    yesterday = today - dt.timedelta(days=1)

    # Longest streak: scan forward through sorted unique dates
    longest = 1
    run = 1
    for i in range(1, len(unique_sorted)):
        gap = (unique_sorted[i] - unique_sorted[i - 1]).days
        if gap == 1:
            run += 1
            if run > longest:
                longest = run
        else:
            run = 1

    # Current streak: walk backwards from today / yesterday
    most_recent = unique_sorted[-1]
    if most_recent < yesterday:
        return 0, longest

    # Walk backwards counting consecutive days from the anchor
    anchor = most_recent
    current = 1
    for i in range(len(unique_sorted) - 2, -1, -1):
        gap = (anchor - unique_sorted[i]).days
        if gap == 1:
            current += 1
            anchor = unique_sorted[i]
        else:
            break

    return current, longest


def adherence_summary(
    db: Session,
    *,
    patient_id: str,
) -> dict:
    """Aggregate adherence across all active medications for a patient.

    Returns a dict ready for ``AdherenceSummaryOut`` serialisation.
    """
    from app.schemas.medication import TodayMedicationOut

    today_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + dt.timedelta(days=1)
    week_start = today_start - dt.timedelta(days=7)
    year_start = today_start - dt.timedelta(days=365)

    # Rows belonging to erroneous/deleted records must not contaminate
    # adherence metrics (ADR-11: excluded from all clinical processing).
    countable_meds = select(Medication.id).where(
        Medication.patient_id == patient_id,
        Medication.deleted_at.is_(None),
        Medication.lifecycle_status != "entered_in_error",
    )
    all_records = list(
        db.execute(
            select(MedicationAdherence)
            .where(MedicationAdherence.patient_id == patient_id)
            .where(MedicationAdherence.medication_id.in_(countable_meds))
            .where(MedicationAdherence.created_at >= year_start)
            .order_by(MedicationAdherence.created_at)
        ).scalars()
    )

    total = len(all_records)
    taken = sum(1 for r in all_records if r.taken_at is not None)
    skipped = sum(1 for r in all_records if r.skipped)
    adherence_rate = round(taken / total, 4) if total > 0 else 0.0

    # last_taken_at: most recent taken_at across all records
    last_taken_at = max(
        (r.taken_at for r in all_records if r.taken_at is not None),
        default=None,
    )

    # weekly_rate: taken / total in last 7 days
    week_records = [r for r in all_records if as_naive_utc(r.created_at) >= week_start]
    total_in_week = len(week_records)
    taken_in_week = sum(1 for r in week_records if r.taken_at is not None)
    weekly_rate = round(taken_in_week / total_in_week, 4) if total_in_week > 0 else 0.0

    # streaks: unique UTC calendar dates where a dose was taken
    taken_dates = [as_naive_utc(r.taken_at).date() for r in all_records if r.taken_at is not None]
    current_streak, longest_streak = _compute_streaks(taken_dates)

    # Today-tracking targets ONLY actively-taken medications — paused/on_hold
    # must not be presented as actionable doses (Codex R8).
    _, active_meds = list_medications(
        db, patient_id=patient_id, limit=100, lifecycle_filter="active"
    )

    today_medications: list[TodayMedicationOut] = []
    for med in active_meds:
        today_records = [
            r
            for r in all_records
            if r.medication_id == med.id
            and as_naive_utc(r.created_at) >= today_start
            and as_naive_utc(r.created_at) < today_end
        ]
        # Last action wins: derive state from the most-recent record only,
        # so taken and skipped can never be simultaneously true.
        if today_records:
            latest = max(today_records, key=lambda r: as_naive_utc(r.created_at))
            taken_today = latest.taken_at is not None
            skipped_today = latest.skipped
        else:
            taken_today = False
            skipped_today = False
        med_records = [r for r in all_records if r.medication_id == med.id and r.taken_at]
        last_taken = max((r.taken_at for r in med_records), default=None)
        today_medications.append(
            TodayMedicationOut(
                medication_id=med.id,
                name=med.name,
                dose=med.dose,
                frequency=med.frequency,
                taken_today=taken_today,
                skipped_today=skipped_today,
                last_taken_at=last_taken,
            )
        )

    return {
        "total_doses_logged": total,
        "taken": taken,
        "skipped": skipped,
        "adherence_rate": adherence_rate,
        "today_medications": today_medications,
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "weekly_rate": weekly_rate,
        "last_taken_at": last_taken_at,
    }
