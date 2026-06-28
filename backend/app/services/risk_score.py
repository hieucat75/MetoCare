"""Risk score service — persist and retrieve metabolic score history.

T13: Save metabolic score results for PATIENT callers and expose a paginated
history endpoint with trend analysis.

Pure service functions; no HTTP concerns here.
"""

from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.metabolic_score import MetabolicScoreResult
from app.models.clinical import RiskScore

# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------


def save_score(
    db: Session,
    *,
    patient_id: str,
    result: MetabolicScoreResult,
) -> RiskScore:
    """Persist a MetabolicScoreResult for *patient_id*.

    Extracts the top 3 factors (by points, descending) and stores them as a
    JSON string in ``top_risks``.  The raw score and band are stored verbatim.

    Returns the newly committed RiskScore ORM instance.
    """
    # Top-3 factors sorted by points descending; factors with 0 points omitted.
    top_factors = sorted(
        [f for f in result.factors if f.points > 0],
        key=lambda f: f.points,
        reverse=True,
    )[:3]
    top_risks_json = json.dumps(
        [{"name": f.name, "points": f.points, "detail": f.detail} for f in top_factors],
        ensure_ascii=False,
    )

    record = RiskScore(
        patient_id=patient_id,
        metabolic_score=result.score,
        band=result.band.value,
        top_risks=top_risks_json,
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
) -> tuple[int, list[RiskScore]]:
    """Return *(total, items)* for the patient's metabolic score history.

    Items are ordered newest-first (``created_at DESC``).
    *limit* is clamped to 100.
    """
    limit = min(limit, 100)

    total: int = db.execute(
        select(func.count()).select_from(RiskScore).where(RiskScore.patient_id == patient_id)
    ).scalar_one()

    rows = list(
        db.execute(
            select(RiskScore)
            .where(RiskScore.patient_id == patient_id)
            .order_by(RiskScore.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).scalars()
    )

    return total, rows


def compute_trend(scores: list[RiskScore]) -> str:
    """Compute a simple directional trend from the two most-recent scores.

    Scores must be ordered newest-first (as returned by ``get_history``).

    Returns one of:
    - ``"insufficient_data"``  — fewer than 2 records
    - ``"worsening"``          — most-recent score > previous by > 5 points
    - ``"improving"``          — most-recent score < previous by > 5 points
    - ``"stable"``             — delta ≤ 5 in either direction
    """
    if len(scores) < 2:
        return "insufficient_data"

    last = scores[0].metabolic_score
    previous = scores[1].metabolic_score
    delta = last - previous

    if delta > 5:
        return "worsening"
    if delta < -5:
        return "improving"
    return "stable"
