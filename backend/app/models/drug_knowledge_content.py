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
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from ._mixins import TimestampMixin, UUIDPrimaryKey

# Shared across every knowledge table's status CHECK constraint.
STATUS_VALUES = ("draft", "clinical_review", "approved", "deprecated", "retired")


def _status_check(table: str) -> CheckConstraint:
    values = ",".join(f"'{v}'" for v in STATUS_VALUES)
    return CheckConstraint(f"status IN ({values})", name=f"ck_{table}_status")


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
    evidence_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
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


class DrugUsage(KnowledgeLifecycleMixin, UUIDPrimaryKey, TimestampMixin, Base):
    """Usage narrative per ingredient/locale/audience (ADR-13)."""

    __tablename__ = "drug_usage"

    locale: Mapped[str] = mapped_column(String(10), nullable=False, default="vi")
    audience: Mapped[str] = mapped_column(String(32), nullable=False, default="patient")
    content: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        _status_check("drug_usage"),
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
