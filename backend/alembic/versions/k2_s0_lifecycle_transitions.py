"""K2 Slice 0: create `knowledge_lifecycle_transitions` (append-only
lifecycle transition history).

Authorization history: this table predates an explicit citation in
docs/medication-management/
MEDICATION_KNOWLEDGE_SLICE0_ORIGIN_PROVENANCE_FLAGS_IMPLEMENTATION_PLAN.md
(§B3 there names only three migrations) — flagged at the 2026-07-27
final-checkpoint review, then explicitly authorized by PTH the same day
as the fourth Slice 0 migration, per the binding PTH implementation
instruction requiring lifecycle transition history with actor/reviewer
identity, timestamp, reason code, and PHI-free rationale. See
docs/medication-management/adrs/ADR-13-KNOWLEDGE-CONTENT-LIFECYCLE.md,
Amendment 1 (2026-07-27), and the plan doc's own §0.3 item 5, for the
authorizing record. Not reverted; keep as-is per that decision.

Mirrors `app/models/drug_knowledge_lifecycle_transition.py`'s
`KnowledgeLifecycleTransition` model exactly. Polymorphic association — no
physical FK to any of the 5 knowledge tables, same shape as
`knowledge_reference_links`/`knowledge_review_specialties`/
`knowledge_ai_generations`.

No clinical content is authored by this migration — the table is created
empty. Every write into it goes through `knowledge_repository.py`'s
`_record_transition()`, called from inside the same transaction as the
status transition it records (`submit_for_review`, `approve_row`,
`reject_row`, `retire_row`, and the automatic `_deprecate_superseded`).

Downgrade safety: refuses if the table is non-empty — any row in it is
real transition history, never a reconstructable default.

Revision ID: k2_s0_lifecycle_transitions
Revises: k2_s0_ai_generation_history
Create Date: 2026-07-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "k2_s0_lifecycle_transitions"
down_revision: str | None = "k2_s0_ai_generation_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KNOWLEDGE_TABLES = (
    "drug_usage",
    "drug_patient_education",
    "drug_side_effects",
    "drug_monitoring",
    "drug_contraindications",
)

# Must match app/models/drug_knowledge_content.py's STATUS_VALUES exactly
# (migrations cannot import app code — see e.g. k2_s0_add_rejected_status.py
# for the same convention). Both from_status and to_status are NOT NULL —
# no row has ever recorded a null "creation" transition (create_draft
# never calls _record_transition) — so both are constrained
# unconditionally to one of these 6 values, never allowing null.
_STATUS_VALUES = ("draft", "clinical_review", "approved", "rejected", "deprecated", "retired")


def upgrade() -> None:
    knowledge_table_values = ",".join(f"'{t}'" for t in _KNOWLEDGE_TABLES)
    status_values = ",".join(f"'{s}'" for s in _STATUS_VALUES)

    op.create_table(
        "knowledge_lifecycle_transitions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("knowledge_table", sa.String(32), nullable=False),
        sa.Column("knowledge_row_id", sa.String(36), nullable=False),
        sa.Column("from_status", sa.String(16), nullable=False),
        sa.Column("to_status", sa.String(16), nullable=False),
        sa.Column("actor_id", sa.String(255), nullable=False),
        sa.Column("actor_role", sa.String(64), nullable=True),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("transitioned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint(
            f"knowledge_table IN ({knowledge_table_values})",
            name="ck_knowledge_lifecycle_transitions_table",
        ),
        sa.CheckConstraint(
            f"from_status IN ({status_values})",
            name="ck_knowledge_lifecycle_transitions_from_status",
        ),
        sa.CheckConstraint(
            f"to_status IN ({status_values})",
            name="ck_knowledge_lifecycle_transitions_to_status",
        ),
    )
    op.create_index(
        "ix_knowledge_lifecycle_transitions_row",
        "knowledge_lifecycle_transitions",
        ["knowledge_table", "knowledge_row_id"],
    )


def downgrade() -> None:
    """Refuses to drop the table if it holds any row — this is the
    non-negotiable "existing lifecycle history must never be overwritten"
    requirement applied at the schema level: a downgrade that silently
    dropped real transition history would violate it just as much as an
    UPDATE would."""
    bind = op.get_bind()
    count = bind.execute(sa.text("SELECT COUNT(*) FROM knowledge_lifecycle_transitions")).scalar()
    if count:
        raise RuntimeError(
            f"Refusing to downgrade: knowledge_lifecycle_transitions has {count} "
            "row(s). This table is append-only lifecycle history — dropping it "
            "would destroy an audit trail that cannot be reconstructed. Remediate "
            "(export/archive the data first) before downgrading past this revision."
        )
    op.drop_index("ix_knowledge_lifecycle_transitions_row", table_name="knowledge_lifecycle_transitions")
    op.drop_table("knowledge_lifecycle_transitions")
