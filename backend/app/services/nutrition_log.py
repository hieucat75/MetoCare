"""Nutrition log service — create and list NutritionLog records (T18).

Pure service functions; all HTTP concerns live in the route layer.
RBAC and consent checks are performed by the caller (route) before
invoking these functions.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import as_naive_utc, utcnow
from app.models.nutrition import NutritionLog


def create_log(
    db: Session,
    *,
    patient_id: str,
    data: dict,
) -> NutritionLog:
    """Persist a new NutritionLog for *patient_id*.

    ``data`` must contain at least ``description``.  Optional keys:
    ``meal_type`` (str), ``calories_kcal`` (int), and
    ``logged_at`` (datetime, defaults to now).

    Returns the committed NutritionLog instance.
    """
    logged_at: dt.datetime = as_naive_utc(data.get("logged_at")) or utcnow()

    record = NutritionLog(
        patient_id=patient_id,
        description=data["description"],
        meal_type=data.get("meal_type"),
        calories_kcal=data.get("calories_kcal"),
        logged_at=logged_at,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_logs(
    db: Session,
    *,
    patient_id: str,
    limit: int = 20,
    offset: int = 0,
) -> tuple[int, list[NutritionLog]]:
    """Return *(total, items)* for the patient's nutrition logs.

    Items are ordered newest-first (``logged_at DESC``).
    *limit* is clamped to 100.
    """
    limit = min(limit, 100)

    total: int = db.execute(
        select(func.count()).select_from(NutritionLog).where(NutritionLog.patient_id == patient_id)
    ).scalar_one()

    rows = list(
        db.execute(
            select(NutritionLog)
            .where(NutritionLog.patient_id == patient_id)
            .order_by(NutritionLog.logged_at.desc())
            .limit(limit)
            .offset(offset)
        ).scalars()
    )

    return total, rows
