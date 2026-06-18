"""Symptom log service — create and list SymptomLog records (T15).

Pure service functions; all HTTP concerns live in the route layer.
RBAC and consent checks are performed by the caller (route) before
invoking these functions.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.models.clinical import SymptomLog


def create_symptom(
    db: Session,
    *,
    patient_id: str,
    data: dict,
) -> SymptomLog:
    """Persist a new SymptomLog for *patient_id*.

    ``data`` must contain at least ``description``.  Optional keys:
    ``severity`` (0–10) and ``reported_at`` (datetime, defaults to now).

    Returns the committed SymptomLog instance.
    """
    reported_at: dt.datetime = data.get("reported_at") or utcnow()

    record = SymptomLog(
        patient_id=patient_id,
        description=data["description"],
        severity=data.get("severity"),
        reported_at=reported_at,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_symptoms(
    db: Session,
    *,
    patient_id: str,
    limit: int = 20,
    offset: int = 0,
) -> tuple[int, list[SymptomLog]]:
    """Return *(total, items)* for the patient's symptom logs.

    Items are ordered newest-first (``reported_at DESC``).
    *limit* is clamped to 100.
    """
    limit = min(limit, 100)

    total: int = db.execute(
        select(func.count()).select_from(SymptomLog).where(
            SymptomLog.patient_id == patient_id
        )
    ).scalar_one()

    rows = list(
        db.execute(
            select(SymptomLog)
            .where(SymptomLog.patient_id == patient_id)
            .order_by(SymptomLog.reported_at.desc())
            .limit(limit)
            .offset(offset)
        ).scalars()
    )

    return total, rows
