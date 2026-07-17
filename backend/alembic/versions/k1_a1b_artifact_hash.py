"""K1-A1B: add artifact_hash column to the 5 knowledge tables.

Persistence piece required for the A1b orchestrator's idempotency design
(MEDICATION_PHASE_A1B_ORCHESTRATOR_IMPLEMENTATION_PLAN.md §3). `versioning.py`'s
known_versions_for() needs a comparable hash per row across importer
invocations; several of the hashed inputs (specialty_codes, ai_generated,
disclaimer.acknowledged) have no other persistence path in this schema, so
the computed hash itself must be stored.

Nullable, not NOT NULL (PTH round-8 review of the plan) — this migration
does NOT and cannot backfill a real hash for any pre-existing row: several
hashed inputs are simply not recoverable from persisted state. A NOT NULL
column would force a fabricated value (empty string, partial-data hash, or
a sentinel) that could later be compared as if it were real, misclassifying
an artifact that never existed. Immutability for any legacy NULL-hash row
is enforced at the application layer instead (versioning.py's
known_versions_for fails the whole batch closed with
LEGACY_ARTIFACT_HASH_UNAVAILABLE on a non-retired NULL-hash row), not at
the schema level.

Tightening this column to NOT NULL, if ever done, is a separate, later
migration gated on a documented remediation process confirming zero
remaining NULL-hash non-retired rows — not authorized by this migration.

No clinical content is authored by this migration. No API route, no
frontend, no AI wiring touches any of this — same dormancy discipline as
every other K1/A1b migration.

Revision ID: k1_a1b_artifact_hash
Revises: k1_a1b_f2_specialty_seed
Create Date: 2026-07-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "k1_a1b_artifact_hash"
down_revision: str | None = "k1_a1b_f2_specialty_seed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KNOWLEDGE_TABLES = (
    "drug_usage",
    "drug_patient_education",
    "drug_side_effects",
    "drug_monitoring",
    "drug_contraindications",
)


def upgrade() -> None:
    for table in _KNOWLEDGE_TABLES:
        op.add_column(
            table,
            sa.Column("artifact_hash", sa.String(64), nullable=True),
        )


def downgrade() -> None:
    """Drops exactly the 5 columns this migration added, nothing else. Any
    hash values written since upgrade are lost — an accepted cost of
    dropping the column itself, not a separate data-loss risk requiring a
    fail-closed guard (unlike F1's downgrade, which guards against losing
    real clinical/reference data in tables this migration does not touch)."""
    for table in _KNOWLEDGE_TABLES:
        op.drop_column(table, "artifact_hash")
