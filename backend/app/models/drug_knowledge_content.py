"""Five of ADR-13's six typed knowledge tables (Knowledge Content Lifecycle).

`drug_interactions` is intentionally NOT included here — see the note at the
bottom of this file and MEDICATION_K1_PR1_COMPLIANCE_REVIEW.md.

Each table shares a provenance + lifecycle mixin (`KnowledgeLifecycleMixin`):
status enum, who authored/changed status and when, and the source/version/
evidence fields an approved row must carry. `status` transitions themselves
are enforced in the service layer (K1.5+), never at the DB layer — this file
only encodes the invariants ADR-13 says the *schema* must enforce:

  - `status` is one of the five lifecycle values (CHECK).
  - an `approved` row must carry reviewed_by/evidence_level/source/version/
    last_reviewed_at (conditional CHECK — "database schema enforces approval
    invariants" per ADR-13's "Production Schema Must Not Encode Test Data").
  - at most one `approved` row per table's business key (partial unique
    index, ADR-13 "Per-Table Business Key & Uniqueness Policy").

Self-approval blocking (authored_by != status_changed_by at approval) is
intentionally NOT a DB CHECK — ADR-13 requires a logged, PTH-approved
override path to exist, which a hard CHECK constraint would foreclose. That
rule is enforced in the service layer, per the ADR's own wording.

No clinical content is authored by this migration (K1 Exit Criteria EC-07/
EC-09) — these tables are created empty.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.core.database import Base
from app.core.system_actors import assert_no_forged_system_actor

from ._mixins import TimestampMixin, UUIDPrimaryKey

# Shared across every knowledge table's status CHECK constraint.
#
# 'rejected' (Medication Knowledge Slice 0, docs/medication-management/
# MEDICATION_KNOWLEDGE_SLICE0_ORIGIN_PROVENANCE_FLAGS_IMPLEMENTATION_PLAN.md
# §B2.3, PTH-approved ADR-13 amendment): closes the gap where a
# clinical_review row a reviewer declines had no modeled destination.
# clinical_review -> rejected is the only transition into this status
# (knowledge_repository._ALLOWED_TRANSITIONS); rejected is terminal — no
# transition out of it exists. A rejected row is never deleted; it stays
# for audit, just excluded from K1.6/K2 retrieval (status != 'approved'
# already excludes it, same as every other non-approved status).
STATUS_VALUES = ("draft", "clinical_review", "approved", "rejected", "deprecated", "retired")

# Row-level content origin (Slice 0 §B2.2). Every row has exactly one
# origin — a first-class fact about the row itself, not a mutable
# workflow field. `human_authored` is also this column's default: every
# row written before this migration went through create_draft, fed
# exclusively by the A1b importer's `ai_generated: Literal[False]`
# -enforced input contract (medication_knowledge_import/schema.py:171) —
# every legacy row is unambiguously human-authored, never
# 'source_extracted' (that would misclassify content no ingestion
# pipeline has ever produced).
ORIGIN_VALUES = ("source_extracted", "rule_derived", "ai_synthesized", "human_authored")

# Slice 0 §B2.2: an ai_synthesized row must be constructible only at
# status='draft' — never born reviewed/approved/deprecated/retired, and
# never born rejected either (rejection is a real reviewer decision that
# must go through submit_for_review -> reject_row, not be forged at
# construction). clinical_review is included because ai_synthesized rows
# reach clinical_review only via submit_for_review's own status-column
# UPDATE (a Core statement, not ORM attribute assignment — @validates
# does not fire there), so this set exists purely as a construction-time
# guard against direct ORM misuse, not a statement about what
# submit_for_review itself is allowed to do.
_AI_SYNTHESIZED_FORBIDDEN_STATUSES = frozenset(
    {"clinical_review", "approved", "rejected", "deprecated", "retired"}
)


def _status_check(table: str) -> CheckConstraint:
    values = ",".join(f"'{v}'" for v in STATUS_VALUES)
    return CheckConstraint(f"status IN ({values})", name=f"ck_{table}_status")


def _origin_check(table: str) -> CheckConstraint:
    values = ",".join(f"'{v}'" for v in ORIGIN_VALUES)
    return CheckConstraint(f"origin IN ({values})", name=f"ck_{table}_origin")


def _approved_invariants_check(table: str) -> CheckConstraint:
    """"database schema enforces approval invariants" (ADR-13)."""
    return CheckConstraint(
        "status <> 'approved' OR ("
        "reviewed_by IS NOT NULL AND evidence_level IS NOT NULL AND "
        "source IS NOT NULL AND version IS NOT NULL AND last_reviewed_at IS NOT NULL"
        ")",
        name=f"ck_{table}_approved_invariants",
    )


class KnowledgeLifecycleMixin:
    """Provenance mixin (ADR-01 core) + lifecycle columns (ADR-13)."""

    drug_ingredient_id: Mapped[str] = mapped_column(
        ForeignKey("drug_ingredients.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # Provenance (nullable at schema level — populated progressively through
    # the lifecycle; ADR-13's approved-invariants CHECK enforces presence
    # once a row reaches 'approved').
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Widened 16->32 chars (k2_s1_widen_evidence_level) — ADR-15 §D's locked
    # v1 vocabulary includes "clinical_guideline" (18) and
    # "peer_reviewed_literature" (24), both longer than the original 16.
    evidence_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_reviewed_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Lifecycle (ADR-13 — all four required from row creation).
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'draft'"))
    status_changed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status_changed_by: Mapped[str] = mapped_column(String(255), nullable=False)
    authored_by: Mapped[str] = mapped_column(String(255), nullable=False)

    # A1b orchestrator idempotency (MEDICATION_PHASE_A1B_ORCHESTRATOR_IMPLEMENTATION_PLAN.md
    # §3). SHA-256 hex digest over the full authoring artifact (content +
    # references + provenance) computed once at import time — nullable, not
    # NOT NULL: several hashed inputs (specialty_codes, ai_generated,
    # disclaimer.acknowledged) have no independent persistence path, so a
    # pre-existing row can never be backfilled with a real hash. Rows written
    # by the A1b importer always populate this; rows written by any other
    # caller (K1-S3's own direct tests) leave it NULL, and versioning.py's
    # known_versions_for() fails closed on a NULL hash rather than guessing.
    artifact_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Slice 0 §B2.2. NOT NULL with a server default so every pre-Slice-0
    # row backfills to 'human_authored' atomically at ADD COLUMN time (see
    # k2_s0_knowledge_origin migration) — never a separate UPDATE, and
    # never left NULL for a caller to accidentally treat as "unknown."
    origin: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=text("'human_authored'")
    )

    # ------------------------------------------------------------------ #
    # Slice 0 guard: AI content cannot be born reviewed. Mirrors
    # AIClinicalRecommendation's stricter unconditional-reject pattern
    # (app/models/ai.py), not CarePlan's looser combined-check one — see
    # plan §B2.2 for why. Defense-in-depth against direct ORM
    # construction/mutation only: the service-layer UPDATE statements
    # submit_for_review/approve_row/reject_row/retire_row already use are
    # SQLAlchemy Core statements and do not trigger these hooks. The real
    # backstop against an ai_synthesized row skipping review is
    # approve_row's own provenance guard (knowledge_repository.py), not
    # this hook alone.
    # ------------------------------------------------------------------ #

    @validates("origin")
    def _validate_origin(self, key: str, value: str) -> str:
        # 2026-07-27 final-checkpoint fix: this hook previously only
        # checked the ai_synthesized/status combination below — an
        # out-of-vocabulary value (never one of ORIGIN_VALUES at all) was
        # not rejected at the ORM layer, only by the DB CHECK constraint
        # at flush/commit time. Mirrors the DB constraint explicitly now,
        # matching this file's own `_validate_status_against_origin`
        # sibling hook and the equivalent hooks added to
        # KnowledgeLifecycleTransition/KnowledgeAIGeneration.
        if value not in ORIGIN_VALUES:
            raise ValueError(f"origin={value!r} is not one of {ORIGIN_VALUES}.")
        if value == "ai_synthesized":
            status_val = self.__dict__.get("status")
            if status_val in _AI_SYNTHESIZED_FORBIDDEN_STATUSES:
                raise ValueError(
                    "origin='ai_synthesized' may only be constructed with "
                    "status='draft'. Use the sanctioned AI draft factory; "
                    "never construct a reviewed/approved/rejected row directly."
                )
        return value

    @validates("status")
    def _validate_status_against_origin(self, key: str, value: str) -> str:
        # Same 2026-07-27 fix as _validate_origin above: general
        # vocabulary membership was previously unchecked at the ORM
        # layer, only the ai_synthesized/status combination was.
        if value not in STATUS_VALUES:
            raise ValueError(f"status={value!r} is not one of {STATUS_VALUES}.")
        if (
            self.__dict__.get("origin") == "ai_synthesized"
            and value in _AI_SYNTHESIZED_FORBIDDEN_STATUSES
        ):
            raise ValueError(
                "A row with origin='ai_synthesized' cannot be constructed "
                f"at status={value!r}. Only draft is allowed at "
                "construction; promotion happens exclusively through "
                "submit_for_review/approve_row."
            )
        return value

    @validates("authored_by")
    def _validate_authored_by(self, key: str, value: str) -> str:
        """Codex Round 2 finding (fix round 2, 2026-07-28): `authored_by`
        legitimately holds a registered `SystemActor` value for
        `origin='ai_synthesized'` rows (e.g.
        `SystemActor.MEDICATION_AI_SYNTHESIS.value`, per this codebase's
        own test convention) — so this cannot require registration
        unconditionally the way `KnowledgeAIGeneration.created_by` does.
        It only rejects a FORGED, unregistered `system:*` value, matching
        this codebase's "reserve the whole namespace, not just today's
        registered members" principle applied everywhere an actor identity
        is recorded."""
        assert_no_forged_system_actor(value)
        return value


class DrugUsage(KnowledgeLifecycleMixin, UUIDPrimaryKey, TimestampMixin, Base):
    """Usage narrative per ingredient/locale/audience (ADR-13)."""

    __tablename__ = "drug_usage"

    locale: Mapped[str] = mapped_column(String(10), nullable=False, default="vi")
    audience: Mapped[str] = mapped_column(String(32), nullable=False, default="patient")
    content: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        _status_check("drug_usage"),
        _origin_check("drug_usage"),
        _approved_invariants_check("drug_usage"),
        Index(
            "uq_drug_usage_approved_key",
            "drug_ingredient_id",
            "locale",
            "audience",
            unique=True,
            postgresql_where=text("status = 'approved'"),
            sqlite_where=text("status = 'approved'"),
        ),
    )


class DrugPatientEducation(KnowledgeLifecycleMixin, UUIDPrimaryKey, TimestampMixin, Base):
    """Patient education messages, slotted per theme (ADR-13)."""

    __tablename__ = "drug_patient_education"

    theme: Mapped[str] = mapped_column(String(64), nullable=False)
    locale: Mapped[str] = mapped_column(String(10), nullable=False, default="vi")
    audience: Mapped[str] = mapped_column(String(32), nullable=False, default="patient")
    content: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        _status_check("drug_patient_education"),
        _origin_check("drug_patient_education"),
        _approved_invariants_check("drug_patient_education"),
        Index(
            "uq_drug_patient_education_approved_key",
            "drug_ingredient_id",
            "theme",
            "locale",
            "audience",
            unique=True,
            postgresql_where=text("status = 'approved'"),
            sqlite_where=text("status = 'approved'"),
        ),
    )


class DrugSideEffect(KnowledgeLifecycleMixin, UUIDPrimaryKey, TimestampMixin, Base):
    """Side effects per ingredient (ADR-13, revised A1b-F1 per PTH's review
    of the Knowledge Template, 2026-07-16).

    The original `level` enum (common/uncommon/rare/serious) conflated two
    independent axes: how OFTEN a side effect occurs (`frequency`) and what
    the patient should DO about it (`action_level`) — a side effect can be
    simultaneously rare and urgent, which a single enum couldn't express.

    Business key is now `(drug_ingredient_id, concept_code)` alone, not
    `(..., level, concept_code)` — frequency/action_level are attributes of
    one canonical side-effect fact, not partition keys. One row per named
    side effect per ingredient.
    """

    __tablename__ = "drug_side_effects"

    # New normalized short identifier (ADR-13 round-2) distinct from the
    # free-text `description` — this is what the business-key index keys on.
    concept_code: Mapped[str] = mapped_column(String(64), nullable=False)
    # Short chip-style label for list/card UI (Companion's SideEffectsCard) —
    # distinct from the long-form `description` below.
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    frequency: Mapped[str] = mapped_column(String(16), nullable=False)
    action_level: Mapped[str] = mapped_column(String(24), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        _status_check("drug_side_effects"),
        _origin_check("drug_side_effects"),
        _approved_invariants_check("drug_side_effects"),
        CheckConstraint(
            "frequency IN ('common','uncommon','rare','unknown')",
            name="ck_drug_side_effects_frequency",
        ),
        CheckConstraint(
            "action_level IN ('self_monitor','contact_clinician','urgent_medical_help')",
            name="ck_drug_side_effects_action_level",
        ),
        Index(
            "uq_drug_side_effects_approved_key",
            "drug_ingredient_id",
            "concept_code",
            unique=True,
            postgresql_where=text("status = 'approved'"),
            sqlite_where=text("status = 'approved'"),
        ),
    )


class DrugMonitoring(KnowledgeLifecycleMixin, UUIDPrimaryKey, TimestampMixin, Base):
    """Monitoring parameter guidance per ingredient+context (ADR-13)."""

    __tablename__ = "drug_monitoring"

    parameter: Mapped[str] = mapped_column(String(128), nullable=False)
    patient_context: Mapped[str] = mapped_column(String(64), nullable=False, default="baseline")
    guidance: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        _status_check("drug_monitoring"),
        _origin_check("drug_monitoring"),
        _approved_invariants_check("drug_monitoring"),
        Index(
            "uq_drug_monitoring_approved_key",
            "drug_ingredient_id",
            "parameter",
            "patient_context",
            unique=True,
            postgresql_where=text("status = 'approved'"),
            sqlite_where=text("status = 'approved'"),
        ),
    )


class DrugContraindication(KnowledgeLifecycleMixin, UUIDPrimaryKey, TimestampMixin, Base):
    """Contraindications per ingredient+condition (ADR-13)."""

    __tablename__ = "drug_contraindications"

    condition_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # New normalized short identifier (ADR-13 round-2), e.g. "egfr_lt_30".
    condition_key: Mapped[str] = mapped_column(String(64), nullable=False)
    condition_detail: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        _status_check("drug_contraindications"),
        _origin_check("drug_contraindications"),
        _approved_invariants_check("drug_contraindications"),
        Index(
            "uq_drug_contraindications_approved_key",
            "drug_ingredient_id",
            "condition_type",
            "condition_key",
            unique=True,
            postgresql_where=text("status = 'approved'"),
            sqlite_where=text("status = 'approved'"),
        ),
    )


# drug_interactions is deliberately NOT modeled in this PR. Codex review
# flagged that a single-approved-per-canonical_pair_key design cannot
# represent ADR-02's directional/conditional interaction rules (dose/lab/
# route/condition-dependent — multiple approved rules can legitimately share
# the same subject pair). Deferred to a follow-up PR scoped to full ADR-02
# compliance.
