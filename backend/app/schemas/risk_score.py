"""Schemas for the metabolic score history API (T13).

Separate from ``clinical.py`` to keep T13 additions isolated and avoid touching
the existing ``RiskScoreOut`` in ``clinical.py`` (which is exported for other
consumers).
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from pydantic import BaseModel, field_validator

# ---------------------------------------------------------------------------
# RiskScoreOut — individual history item
# ---------------------------------------------------------------------------


class RiskScoreOut(BaseModel):
    """Serialised view of a single RiskScore row for the history endpoint.

    ``top_risks`` is stored as a JSON string in the DB; here it is exposed as a
    parsed list so API consumers don't have to re-parse it themselves.
    """

    id: str
    metabolic_score: int
    band: str
    top_risks: list[Any]
    created_at: dt.datetime

    model_config = {"from_attributes": True}

    @field_validator("top_risks", mode="before")
    @classmethod
    def parse_top_risks(cls, v: Any) -> list[Any]:
        """Accept a JSON string (from ORM) or an already-parsed list."""
        if v is None:
            return []
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, list) else []
            except (json.JSONDecodeError, ValueError):
                return []
        if isinstance(v, list):
            return v
        return []


# ---------------------------------------------------------------------------
# RiskScoreHistoryResponse — paginated history + trend
# ---------------------------------------------------------------------------


class RiskScoreHistoryResponse(BaseModel):
    """Response envelope for ``GET /patients/{patient_id}/metabolic-scores``."""

    patient_id: str
    total: int
    items: list[RiskScoreOut]
    trend: str  # "improving" | "worsening" | "stable" | "insufficient_data"


# ---------------------------------------------------------------------------
# LiveScoreFactor / LiveScoreOut — on-demand score computed from metrics
# ---------------------------------------------------------------------------


class LiveScoreFactor(BaseModel):
    """A single contributing factor of the live metabolic score (explainable)."""

    name: str
    points: int
    detail: str


class LiveScoreOut(BaseModel):
    """Response for ``GET /patients/{patient_id}/metabolic-score/live``.

    ``available=False`` (with ``score=None``) means the patient has no metric
    readings usable for scoring — a *genuine* empty state, distinct from the old
    bug where a stored-but-empty table produced a false empty.
    """

    patient_id: str
    available: bool
    score: int | None = None
    band: str | None = None  # good | fair | elevated | high_concern
    factors: list[LiveScoreFactor] = []
    explanation: str | None = None
