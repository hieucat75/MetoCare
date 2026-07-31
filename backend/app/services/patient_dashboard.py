"""Action-first patient dashboard aggregator (BRD §I).

Surfaces what the patient should DO today — the decision-first view. The top
priorities are the net-new Journey-2/3 signals: today's medication doses and
pending OCR confirmations. Trends / metabolic score / appointments / Meto are
composed by the client from their existing dedicated endpoints; this endpoint
owns the action feed + the counts that drive it. Read-only (no delivery/mutation).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.clinical import Medication
from app.models.medical_document import (
    CAND_STATUS_CONFIRMED,
    CAND_STATUS_EXTRACTED,
    CAND_STATUS_MERGED,
    CAND_STATUS_NEEDS_REVIEW,
    ExtractionCandidate,
)
from app.models.medication_schedule import (
    SCHED_STATUS_ACTIVE,
    DoseOccurrence,
    MedicationSchedule,
)
from app.services import medication_schedule as sched

_DUE_STATES = ("pending", "notified")
_OPEN_CANDIDATE_STATES = (CAND_STATUS_EXTRACTED, CAND_STATUS_NEEDS_REVIEW)
_RECENT_DAYS = 7


def build_dashboard(db: Session, *, patient_id: str, now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(dt.UTC)

    # Materialize newly-due doses + sweep overdue → missed BEFORE reading, exactly
    # like GET /reminders/due — otherwise a patient who only opens the dashboard
    # never sees today's dose and stale doses count as "due" forever (review P1).
    # Caller commits (this mutates).
    sched.sweep_missed(db, patient_id=patient_id, now=now)
    for _s in db.execute(
        select(MedicationSchedule).where(
            MedicationSchedule.patient_id == patient_id,
            MedicationSchedule.status == SCHED_STATUS_ACTIVE,
        )
    ).scalars():
        sched.materialize_due(db, _s, now=now)

    # 1. Today's medication doses due (pending/notified whose time has arrived).
    due_doses = list(
        db.execute(
            select(DoseOccurrence)
            .where(
                DoseOccurrence.patient_id == patient_id,
                DoseOccurrence.state.in_(_DUE_STATES),
                DoseOccurrence.scheduled_utc <= now,
            )
            .order_by(DoseOccurrence.scheduled_utc)
        ).scalars()
    )
    doses_due = [
        {
            "dose_id": d.id,
            "schedule_id": d.schedule_id,
            "scheduled_utc": d.scheduled_utc,
            "local_render": d.local_render,
            "state": d.state,
        }
        for d in due_doses
    ]

    # 2. Pending OCR confirmations (candidates still awaiting the patient).
    pending_reviews = (
        db.execute(
            select(func.count(ExtractionCandidate.id)).where(
                ExtractionCandidate.patient_id == patient_id,
                ExtractionCandidate.status.in_(_OPEN_CANDIDATE_STATES),
            )
        ).scalar()
        or 0
    )

    # 3. Active medications count.
    active_meds = (
        db.execute(
            select(func.count(Medication.id)).where(
                Medication.patient_id == patient_id,
                Medication.deleted_at.is_(None),
                Medication.lifecycle_status == "active",
            )
        ).scalar()
        or 0
    )

    # 4. Recently confirmed items (last 7d) — "newly added to your record".
    since = now - dt.timedelta(days=_RECENT_DAYS)
    recently_confirmed = (
        db.execute(
            select(func.count(ExtractionCandidate.id)).where(
                ExtractionCandidate.patient_id == patient_id,
                ExtractionCandidate.status.in_((CAND_STATUS_CONFIRMED, CAND_STATUS_MERGED)),
                ExtractionCandidate.reviewed_at.isnot(None),
                ExtractionCandidate.reviewed_at >= since,
            )
        ).scalar()
        or 0
    )

    # ── action feed (decision-first) ─────────────────────────────────────────
    actions: list[dict] = []
    if doses_due:
        actions.append(
            {
                "type": "medication_dose",
                "title_vi": f"Có {len(doses_due)} liều thuốc cần uống",
                "count": len(doses_due),
                "route": "/reminders",
            }
        )
    if pending_reviews:
        actions.append(
            {
                "type": "confirm_document",
                "title_vi": f"Có {pending_reviews} mục tài liệu cần xác nhận",
                "count": pending_reviews,
                "route": "/documents/review",
            }
        )

    empty_state = not (doses_due or pending_reviews or active_meds or recently_confirmed)
    if empty_state:
        actions.append(
            {
                "type": "add_document",
                "title_vi": "Bắt đầu bằng cách thêm một tài liệu y tế",
                "count": 0,
                "route": "/add-document",
            }
        )

    return {
        "patient_id": patient_id,
        "generated_at": now,
        "doses_due": doses_due,
        "doses_due_count": len(doses_due),
        "pending_document_reviews": pending_reviews,
        "active_medications": active_meds,
        "recently_confirmed": recently_confirmed,
        "actions": actions,
        "empty_state": empty_state,
    }
