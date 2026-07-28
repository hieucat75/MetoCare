"""AI generation history (Medication Knowledge Slice 0, docs/medication-
management/MEDICATION_KNOWLEDGE_SLICE0_ORIGIN_PROVENANCE_FLAGS_IMPLEMENTATION_
PLAN.md §B2.4).

Polymorphic association, same shape and rationale as
`KnowledgeReferenceLink`/`KnowledgeReviewSpecialty`
(drug_knowledge_references.py / drug_knowledge_governance.py):
metadata-about-provenance, never joined for clinical content itself.

Append-only in practice, with two narrow, explicitly-justified mutable
fields: every column describing *what was generated* is set once at insert
and never changes; `review_status` and `superseded_by_generation_id`
describe the generation's *current disposition* and may each be updated
exactly once, by exactly one sanctioned caller (Slice 3's own
promotion/supersession service function — not built in Slice 0). Nothing
in this table is ever deleted or content-mutated. A retry after a
transient failure, or a regeneration producing a materially different
output, is always a NEW row — never an UPDATE of an existing one.

No clinical content is authored by this migration — the table starts and
stays empty through Slice 0 (no AI provider calls, no synthesis code, no
caller that would ever insert a row here yet).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.sqlite import JSON as SQLITE_JSON
from sqlalchemy.orm import Mapped, mapped_column, validates
from sqlalchemy.types import JSON

from app.core.database import Base

from ._mixins import TimestampMixin, UUIDPrimaryKey
from .drug_knowledge_content import ORIGIN_VALUES
from .drug_knowledge_governance import KNOWLEDGE_TABLES

_JSON_TYPE = JSON().with_variant(SQLITE_JSON(), "sqlite")

GENERATION_STATUS_VALUES = ("succeeded", "failed")
REVIEW_STATUS_VALUES = ("pending", "promoted", "rejected", "superseded")


class KnowledgeAIGeneration(UUIDPrimaryKey, TimestampMixin, Base):
    """One AI generation attempt targeting (or intended to target) one
    knowledge row. Many generations may legitimately target the same row
    (retries, regenerations) — there is no uniqueness constraint on
    `(knowledge_table, target_row_id)`."""

    __tablename__ = "knowledge_ai_generations"

    # 2026-07-27 final-checkpoint fix: overrides TimestampMixin's own
    # `created_at` (server_default=CURRENT_TIMESTAMP) for THIS model only
    # — never touches the shared mixin, which many unrelated models also
    # use. `_assert_ai_provenance_complete` (knowledge_repository.py)
    # orders qualifying generations by `created_at DESC` to deterministically
    # pick the most recent attempt when several exist; two independent
    # final-checkpoint reviews (architecture + security) both found that
    # `CURRENT_TIMESTAMP` alone is not a safe tiebreaker for that query:
    # on PostgreSQL it is TRANSACTION-start time (every row inserted in
    # the same transaction — e.g. a retry loop — ties exactly); on SQLite
    # it is second-resolution text (rows inserted within the same wall-
    # clock second tie exactly). `default=` (Python-side, computed fresh
    # per row at flush time, microsecond resolution on both dialects)
    # fixes both failure modes without a schema/migration change or a new
    # tiebreaker column. `server_default` is kept as a fallback default
    # for any raw-SQL insert path that bypasses the ORM.
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        default=lambda: dt.datetime.now(dt.UTC),
        nullable=False,
    )

    knowledge_table: Mapped[str] = mapped_column(String(32), nullable=False)
    # Polymorphic reference resolved by knowledge_table, not a physical FK
    # — same convention as KnowledgeReferenceLink/KnowledgeReviewSpecialty.
    # Nullable: a failed generation may have no draft row to point at yet.
    target_row_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Matches MetoMessage's provider+model naming/width convention
    # (app/models/meto.py) — the established "what produced this" shape
    # elsewhere in this codebase, not a new pattern.
    model_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model_identifier: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version_snapshot: Mapped[str | None] = mapped_column(String(128), nullable=True)

    prompt_template_id: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_template_version: Mapped[str] = mapped_column(String(32), nullable=False)
    normalization_pipeline_version: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # DrugReference ids and/or other knowledge_row ids this generation
    # consumed as input (e.g. a source_extracted draft row it synthesized
    # from). List of opaque id strings, never resolved-content.
    input_source_ids: Mapped[list] = mapped_column(_JSON_TYPE, nullable=False, default=list)
    # sha256 hex, full-payload hash — same discipline as
    # medication_knowledge_import/versioning.py's artifact_hash(): hashes
    # the full authored/generated artifact, not just identity fields.
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generation_params: Mapped[dict | None] = mapped_column(_JSON_TYPE, nullable=True)

    generation_status: Mapped[str] = mapped_column(String(16), nullable=False)
    # PHI-free, structured failure detail only — never a raw provider
    # error blob, never any patient- or medication-identifying free text.
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Why `origin` exists here AND on the 5 knowledge tables, with
    # different semantics (2026-07-27 final-checkpoint documentation):
    # `KnowledgeLifecycleMixin.origin` (drug_knowledge_content.py) answers
    # "how was THIS PERSISTED KNOWLEDGE ROW produced" — one fact about one
    # row, set once at construction, checked by `approve_row`'s provenance
    # guard. This column instead answers "what KIND OF GENERATION PROCESS
    # produced THIS GENERATION RECORD" — always 'ai_synthesized' in Slice
    # 0's scope (the only kind of generation process that exists), stored
    # explicitly rather than hardcoded so a future origin-producing
    # generation kind (e.g. `rule_derived` from an automated pipeline) is
    # representable without a schema change. The two columns are not
    # redundant: a `KnowledgeAIGeneration` row's own `origin` describes the
    # generation attempt itself, independent of whether the knowledge row
    # it targets ever adopts a matching `origin` (it always does today,
    # since `_assert_ai_provenance_complete` only ever fires for
    # `origin='ai_synthesized'` knowledge rows, but the two are set by
    # different code paths and are not enforced to be identical at the DB
    # level).
    origin: Mapped[str] = mapped_column(String(24), nullable=False, default="ai_synthesized")

    # Mutable, exactly once each, by exactly one sanctioned caller
    # (Slice 3's own promotion/supersession function — not built here).
    review_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    superseded_by_generation_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_ai_generations.id", ondelete="RESTRICT"), nullable=True
    )

    # Reserved system-actor identity (app/core/system_actors.py) — never a
    # real human user_id, never attributed to a real admin account.
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "knowledge_table IN (" + ",".join(f"'{t}'" for t in KNOWLEDGE_TABLES) + ")",
            name="ck_knowledge_ai_generations_table",
        ),
        CheckConstraint(
            "generation_status IN ("
            + ",".join(f"'{v}'" for v in GENERATION_STATUS_VALUES)
            + ")",
            name="ck_knowledge_ai_generations_status",
        ),
        CheckConstraint(
            "review_status IN (" + ",".join(f"'{v}'" for v in REVIEW_STATUS_VALUES) + ")",
            name="ck_knowledge_ai_generations_review_status",
        ),
        # 2026-07-27 final-checkpoint addition: `origin` was previously an
        # unrestricted VARCHAR(24) — every other enum-like column on this
        # table already gets a CHECK. Uses the same governed vocabulary as
        # the 5 knowledge tables' own `origin` column (see the docstring
        # above for how the two columns' semantics differ).
        CheckConstraint(
            "origin IN (" + ",".join(f"'{v}'" for v in ORIGIN_VALUES) + ")",
            name="ck_knowledge_ai_generations_origin",
        ),
        Index("ix_knowledge_ai_generations_row", "knowledge_table", "target_row_id"),
        Index("ix_knowledge_ai_generations_review_status", "review_status"),
    )

    @validates("origin")
    def _validate_origin(self, key: str, value: str) -> str:
        """ORM-level mirror of the DB CHECK constraint above."""
        if value not in ORIGIN_VALUES:
            raise ValueError(f"origin={value!r} is not one of {ORIGIN_VALUES}.")
        return value
