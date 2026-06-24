"""Medication service — add, list, and soft-delete Medication records (T15).

Pure service functions; all HTTP concerns live in the route layer.
RBAC and consent checks are performed by the caller (route) before
invoking these functions.

SAFETY NOTE: AI must NEVER add or modify medication records.  This constraint
is enforced at the API/RBAC layer; this service layer trusts the caller has
already validated access.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import datetime as dt

from app.core.clock import as_naive_utc, utcnow
from app.models.clinical import Medication, MedicationAdherence


def add_medication(
    db: Session,
    *,
    patient_id: str,
    data: dict,
) -> Medication:
    """Persist a new Medication record for *patient_id*.

    ``data`` must contain at least ``name``.  Optional keys:
    ``dose`` and ``note``.

    Returns the committed Medication instance.
    """
    record = Medication(
        patient_id=patient_id,
        name=data["name"],
        dose=data.get("dose"),
        frequency=data.get("frequency"),
        note=data.get("note"),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def update_medication(
    db: Session,
    *,
    patient_id: str,
    med_id: str,
    data: dict,
) -> Medication:
    """Apply a partial update to a Medication record (PR-D).

    Only keys present in *data* are written (caller passes ``exclude_unset``).
    Raises 404 if the record does not exist, is soft-deleted, or belongs to a
    different patient.
    """
    record = db.get(Medication, med_id)

    if record is None or record.patient_id != patient_id or record.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medication not found.",
        )

    for field, value in data.items():
        setattr(record, field, value)

    db.commit()
    db.refresh(record)
    return record


def list_medications(
    db: Session,
    *,
    patient_id: str,
    limit: int = 20,
    offset: int = 0,
) -> tuple[int, list[Medication]]:
    """Return *(total, items)* for the patient's active medication records.

    Only non-deleted records (``deleted_at IS NULL``) are included.
    Items are ordered oldest-first (``created_at ASC``).
    *limit* is clamped to 100.
    """
    limit = min(limit, 100)

    base_filter = (
        Medication.patient_id == patient_id,
        Medication.deleted_at.is_(None),
    )

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
) -> None:
    """Soft-delete a Medication record.

    Sets ``deleted_at`` to now.  Raises 404 if the record does not exist or
    already belongs to a different patient.  Does NOT raise on an already-deleted
    record — it is idempotent on repeated calls.

    Raises:
        404 — record not found or not owned by *patient_id*.
    """
    record = db.get(Medication, med_id)

    if record is None or record.patient_id != patient_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medication not found.",
        )

    if record.deleted_at is None:
        record.deleted_at = utcnow()
        db.commit()


# --------------------------------------------------------------------------- #
# Adherence (Phase 2)
# --------------------------------------------------------------------------- #

def log_adherence(
    db: Session,
    *,
    medication_id: str,
    patient_id: str,
    data: dict,
) -> MedicationAdherence:
    """Record a dose event (taken or skipped) for a medication.

    Raises 404 if the medication does not belong to the patient or is deleted.
    """
    med = db.get(Medication, medication_id)
    if med is None or med.patient_id != patient_id or med.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medication not found.",
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
    db.commit()
    db.refresh(record)
    return record


def get_adherence(
    db: Session,
    *,
    medication_id: str,
    patient_id: str,
    limit: int = 30,
) -> list[MedicationAdherence]:
    """Return the most recent adherence records for one medication, newest first."""
    med = db.get(Medication, medication_id)
    if med is None or med.patient_id != patient_id or med.deleted_at is not None:
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

    all_records = list(
        db.execute(
            select(MedicationAdherence)
            .where(MedicationAdherence.patient_id == patient_id)
        ).scalars()
    )

    total = len(all_records)
    taken = sum(1 for r in all_records if r.taken_at is not None)
    skipped = sum(1 for r in all_records if r.skipped)
    adherence_rate = round(taken / total, 4) if total > 0 else 0.0

    _, active_meds = list_medications(db, patient_id=patient_id, limit=100)

    today_medications: list[TodayMedicationOut] = []
    for med in active_meds:
        today_records = [
            r for r in all_records
            if r.medication_id == med.id
            and as_naive_utc(r.created_at) >= today_start
            and as_naive_utc(r.created_at) < today_end
        ]
        taken_today = any(r.taken_at is not None for r in today_records)
        skipped_today = any(r.skipped for r in today_records)
        med_records = [r for r in all_records if r.medication_id == med.id and r.taken_at]
        last_taken = max((r.taken_at for r in med_records), default=None)
        today_medications.append(TodayMedicationOut(
            medication_id=med.id,
            name=med.name,
            dose=med.dose,
            frequency=med.frequency,
            taken_today=taken_today,
            skipped_today=skipped_today,
            last_taken_at=last_taken,
        ))

    return {
        "total_doses_logged": total,
        "taken": taken,
        "skipped": skipped,
        "adherence_rate": adherence_rate,
        "today_medications": today_medications,
    }
