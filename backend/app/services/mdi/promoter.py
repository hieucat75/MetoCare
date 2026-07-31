"""Promotion stage (Master Plan §1.4 Promoter / §1.5 PromotionLink).

Confirming a candidate promotes it into a canonical clinical record via the
``Promoter`` registered for its ``candidate_type``. MDI itself never writes
canonical data — each domain context registers its own promoter:
- ``medication`` → MedicationStatement→canonical path (M3, WS5)
- ``lab_result`` → LabResult/HealthMetric path (M4, WS4)
- ``diagnosis`` (M7) etc.

Until a type's promoter is registered, confirming that candidate type raises
``PromotionUnavailable`` (a clean 409) rather than fabricating a canonical id —
Charter 4: no placeholder debt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session

from app.models.medical_document import ExtractionCandidate

# Promotion actions (§1.5 PromotionLink.action).
ACTION_CREATED = "created"
ACTION_MERGED_INTO = "merged_into"


class PromotionUnavailable(Exception):
    """Raised when no promoter is registered for a candidate type yet."""


class PromotionDenied(Exception):
    """Raised when a promotion is refused for AUTHORIZATION/state reasons — e.g. a
    merge_target the caller does not own or that is terminal (→ 403)."""


class PromotionInvalid(Exception):
    """Raised when the candidate data itself is invalid for promotion — e.g. a
    correction left the medicine name empty (→ 422, a validation error)."""


@dataclass(frozen=True)
class PromotionOutcome:
    canonical_type: str
    canonical_id: str
    action: str  # created | merged_into


class Promoter(Protocol):
    def promote(
        self,
        db: Session,
        candidate: ExtractionCandidate,
        *,
        actor_user_id: str,
        merge_target_id: str | None = None,
    ) -> PromotionOutcome: ...


_REGISTRY: dict[str, Promoter] = {}


def register_promoter(candidate_type: str, promoter: Promoter) -> None:
    _REGISTRY[candidate_type] = promoter


def get_promoter(candidate_type: str) -> Promoter:
    promoter = _REGISTRY.get(candidate_type)
    if promoter is None:
        raise PromotionUnavailable(
            f"Promotion for candidate_type={candidate_type!r} is not available yet."
        )
    return promoter


def has_promoter(candidate_type: str) -> bool:
    return candidate_type in _REGISTRY


def reset_promoters() -> None:
    """Clear registered promoters (test isolation)."""
    _REGISTRY.clear()
