"""Triage log service — persist and retrieve triage history.

T19: Save triage results for PATIENT callers and expose a paginated
history endpoint.

Pure service functions; no HTTP concerns here.
"""

from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.triage import TriageResult
from app.models.triage_log import TriageLog


def save_triage(
    db: Session,
    *,
    patient_id: str,
    symptom_text: str,
    result: TriageResult,
) -> TriageLog:
    """Persist a TriageResult for *patient_id*.

    Stores red_flags as a JSON string. Returns the newly committed TriageLog
    ORM instance.
    """
    red_flags_json = json.dumps(result.red_flags, ensure_ascii=False) if result.red_flags else None

    record = TriageLog(
        patient_id=patient_id,
        symptom_text=symptom_text,
        risk_level=result.risk_level.value,
        action=result.action.value,
        red_flags=red_flags_json,
        message=result.message,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_history(
    db: Session,
    *,
    patient_id: str,
    limit: int = 20,
    offset: int = 0,
) -> tuple[int, list[TriageLog]]:
    """Return *(total, items)* for the patient's triage history.

    Items are ordered newest-first (``created_at DESC``).
    *limit* is clamped to 100.
    """
    limit = min(limit, 100)

    total: int = db.execute(
        select(func.count()).select_from(TriageLog).where(TriageLog.patient_id == patient_id)
    ).scalar_one()

    rows = list(
        db.execute(
            select(TriageLog)
            .where(TriageLog.patient_id == patient_id)
            .order_by(TriageLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).scalars()
    )

    return total, rows
