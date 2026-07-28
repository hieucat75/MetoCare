"""Lifecycle transition history (Medication Knowledge Slice 0).

Authorized by the binding PTH implementation instruction of 2026-07-27
(Slice 0 final checkpoint), requiring lifecycle transition history with
actor/reviewer identity, timestamp, reason code, and PHI-free rationale —
see docs/medication-management/adrs/ADR-13-KNOWLEDGE-CONTENT-LIFECYCLE.md,
Amendment 1, for the full authorizing record and design rationale, and
docs/medication-management/
MEDICATION_KNOWLEDGE_SLICE0_ORIGIN_PROVENANCE_FLAGS_IMPLEMENTATION_PLAN.md
§B3 Migration 3 for the schema-level documentation.

Polymorphic association, same shape as `KnowledgeReferenceLink`/
`KnowledgeReviewSpecialty`/`KnowledgeAIGeneration` — metadata-about-history,
never joined for clinical content itself.

Append-only, no exceptions: every call in `knowledge_repository.py` that
transitions a row's `status` (`submit_for_review`, `approve_row`,
`reject_row`, `retire_row`, and the automatic `_deprecate_superseded`)
inserts exactly one row here, inside that same transaction. No update or
delete path exists anywhere in this codebase for this table — existing
history rows are never overwritten, matching ADR-13's append-only
discipline for the knowledge content itself.

`reason_code`/`rationale` are PHI-free by construction: they describe a
workflow/status fact ("why this transition happened"), never patient
content — same discipline `app/services/audit.py`'s `details` field
already follows.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.core.database import Base

from ._mixins import TimestampMixin, UUIDPrimaryKey
from .drug_knowledge_content import STATUS_VALUES
from .drug_knowledge_governance import KNOWLEDGE_TABLES


class KnowledgeLifecycleTransition(UUIDPrimaryKey, TimestampMixin, Base):
    """One recorded status transition for one knowledge row."""

    __tablename__ = "knowledge_lifecycle_transitions"

    knowledge_table: Mapped[str] = mapped_column(String(32), nullable=False)
    # Polymorphic reference resolved by knowledge_table, not a physical FK
    # — same convention as every other polymorphic association in this
    # domain (KnowledgeReferenceLink, KnowledgeReviewSpecialty,
    # KnowledgeAIGeneration).
    knowledge_row_id: Mapped[str] = mapped_column(String(36), nullable=False)

    from_status: Mapped[str] = mapped_column(String(16), nullable=False)
    to_status: Mapped[str] = mapped_column(String(16), nullable=False)

    # Always the real identity responsible for the transition. For every
    # transition a human directly requests, the real human `actor_user_id`
    # — never a fabricated system identity. The one *automatically
    # triggered* transition (`_deprecate_superseded`, fired when approving
    # a newer row deprecates an older one for the same business key) also
    # records the real human approver's `actor_user_id`, since their
    # approval is what caused it — not a reserved SystemActor string (ADR-
    # 13 Amendment 1 §3). Reserved `SystemActor` identities
    # (app/core/system_actors.py) are for a future automated process
    # (ingestion/normalization/AI synthesis) that writes here on its own
    # initiative with no human in the loop — none exists yet, so none has
    # ever been written to this column.
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_role: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Short controlled code (e.g. "standard_transition",
    # "auto_deprecated_superseded", or a reviewer-supplied rejection
    # reason) — never free text alone; rationale below carries the
    # human-readable detail.
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)

    transitioned_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "knowledge_table IN (" + ",".join(f"'{t}'" for t in KNOWLEDGE_TABLES) + ")",
            name="ck_knowledge_lifecycle_transitions_table",
        ),
        # 2026-07-27 final-checkpoint addition: from_status/to_status were
        # previously unconstrained at the DB level (every other enum-like
        # column in this domain — status, origin, generation_status,
        # review_status — already gets one). Both columns are NOT NULL
        # (see above) — no row has ever recorded a null "creation"
        # transition (create_draft never calls _record_transition; only
        # submit_for_review/approve_row/reject_row/retire_row/
        # _deprecate_superseded do, and each always supplies a real
        # `from_status`), so both constraints require one of the 6
        # canonical STATUS_VALUES unconditionally, never allowing null.
        CheckConstraint(
            "from_status IN (" + ",".join(f"'{s}'" for s in STATUS_VALUES) + ")",
            name="ck_knowledge_lifecycle_transitions_from_status",
        ),
        CheckConstraint(
            "to_status IN (" + ",".join(f"'{s}'" for s in STATUS_VALUES) + ")",
            name="ck_knowledge_lifecycle_transitions_to_status",
        ),
        Index(
            "ix_knowledge_lifecycle_transitions_row",
            "knowledge_table",
            "knowledge_row_id",
        ),
    )

    @validates("from_status", "to_status")
    def _validate_status_value(self, key: str, value: str) -> str:
        """ORM-level mirror of the DB CHECK constraints above — fails
        exactly as clearly (a raised exception, not a silent write) when
        constructed via the ORM with an out-of-vocabulary value, before
        the row ever reaches the database."""
        if value not in STATUS_VALUES:
            raise ValueError(
                f"{key}={value!r} is not one of the 6 canonical lifecycle "
                f"values {STATUS_VALUES}."
            )
        return value
