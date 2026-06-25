"""Medication service — add, list, and soft-delete Medication records (T15).

Pure service functions; all HTTP concerns live in the route layer.
RBAC and consent checks are performed by the caller (route) before
invoking these functions.

SAFETY NOTE: AI must NEVER add or modify medication records.  This constraint
is enforced at the API/RBAC layer; this service layer trusts the caller has
already validated access.
"""

from __future__ import annotations

import datetime as dt

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

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

    # last_taken_at: most recent taken_at across all records
    last_taken_at = max(
        (r.taken_at for r in all_records if r.taken_at is not None),
        default=None,
    )

    # weekly_rate: taken / total in last 7 days
    week_records = [
        r for r in all_records
        if as_naive_utc(r.created_at) >= week_start
    ]
    total_in_week = len(week_records)
    taken_in_week = sum(1 for r in week_records if r.taken_at is not None)
    weekly_rate = round(taken_in_week / total_in_week, 4) if total_in_week > 0 else 0.0

    # streaks: unique UTC calendar dates where a dose was taken
    taken_dates = [
        as_naive_utc(r.taken_at).date()
        for r in all_records
        if r.taken_at is not None
    ]
    current_streak, longest_streak = _compute_streaks(taken_dates)

    _, active_meds = list_medications(db, patient_id=patient_id, limit=100)

    today_medications: list[TodayMedicationOut] = []
    for med in active_meds:
        today_records = [
            r for r in all_records
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
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "weekly_rate": weekly_rate,
        "last_taken_at": last_taken_at,
    }
