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

from app.core.clock import utcnow
from app.models.clinical import Medication


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
