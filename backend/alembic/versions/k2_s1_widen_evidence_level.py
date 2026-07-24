"""K2 Slice 1: widen evidence_level from VARCHAR(16) to VARCHAR(32).

Compatibility prerequisite discovered during K2 Slice 1's PostgreSQL
verification gate (docs/medication-management/
MEDICATION_K2_KNOWLEDGE_API_IMPLEMENTATION_PLAN.md, Revision 7) — NOT an
AI/provenance/ingestion expansion. K2 Slice 1's original "Migration: None"
claim (§2.1) was correct for K2's own read-only endpoints (they write
nothing), but incomplete for the program as a whole: it did not anticipate
that ADR-15's own locked v1 `evidence_level` vocabulary
(ADR-15-MEDICATION_KNOWLEDGE_EXTERNAL_VOCABULARY.md §D) includes two
values that do not fit the column PTH's own governance decision inherited
from K1/ADR-13 — `clinical_guideline` (18 chars) and
`peer_reviewed_literature` (24 chars), both longer than the existing
`VARCHAR(16)`. SQLite does not enforce VARCHAR length at all, so every
SQLite test (K1.5, K1.6, K2 Slice 1 — 50/50 route tests) and the first two
independent code reviews of K2 Slice 1 never observed this; only a real
PostgreSQL engine, run as K2 Slice 1's own Gate 3, caught it — see
tests/integration/test_medication_k2_slice1_postgres.py's
TestPostgresSchemaDefectEvidenceLevelColumnWidth for the reproduction.

Scope of this migration, and nothing more:
- `evidence_level` on the 5 ADR-13 knowledge tables (`drug_usage`,
  `drug_patient_education`, `drug_side_effects`, `drug_monitoring`,
  `drug_contraindications`) — the only physical columns named
  `evidence_level` anywhere in this schema. (Several unrelated Python
  dataclass fields elsewhere in the codebase — PA-11's Clinical Insight
  Engine, the separate YAML-loaded `KnowledgeCard` system — happen to
  share this field name but are plain in-memory strings, not DB columns,
  and are untouched by this migration.)
- Width: `VARCHAR(16)` -> `VARCHAR(32)`. 32 was chosen as the smallest
  round width that (a) comfortably fits every current ADR-15 §D value,
  the longest of which is 24 chars (`peer_reviewed_literature`), with 8
  chars of headroom for a plausible future addition to the same
  6-value-shaped vocabulary, and (b) matches this schema's own existing
  convention for short controlled-vocabulary code columns (e.g.
  `DrugReference.source_type VARCHAR(32)`, `Medication.source_type
  VARCHAR(32)`) rather than introducing a new width tier.
- Nothing else changes: not a rename (still `evidence_level`), not a
  vocabulary change (ADR-15 §D's 6 canonical values are unchanged, this
  migration makes them storable, it does not add/remove/redefine any of
  them), not a default-value change (still nullable, no server default,
  matching the original column exactly), not a nullability change.

No clinical content is authored by this migration. No API route,
frontend, or AI wiring is touched.

Downgrade safety: narrowing VARCHAR(32) back to VARCHAR(16) is NOT
automatically silently truncating on either dialect. Before attempting the
narrow on either dialect, this migration explicitly queries all 5 tables
for any persisted `evidence_level` value longer than 16 characters and
raises a clear `RuntimeError` naming the offending table(s)/row count if
any are found, refusing the downgrade outright — this check is written in
plain Python/SQL, not left to accidental dialect behavior (Postgres would
independently reject an unsafe narrow with its own `StringDataRight
Truncation` during `ALTER COLUMN TYPE`, but SQLite enforces no such thing
at the ALTER-operation level at all, so relying on that would be
dialect-asymmetric and undocumented). If no over-length values exist, the
narrow proceeds and is fully reversible; if any do, downgrade is refused,
not attempted-and-silently-lossy.

Revision ID: k2_s1_widen_evidence_level
Revises: k1_a1b_artifact_hash
Create Date: 2026-07-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "k2_s1_widen_evidence_level"
down_revision: str | None = "k1_a1b_artifact_hash"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KNOWLEDGE_TABLES = (
    "drug_usage",
    "drug_patient_education",
    "drug_side_effects",
    "drug_monitoring",
    "drug_contraindications",
)

_OLD_LENGTH = 16
_NEW_LENGTH = 32


def upgrade() -> None:
    """Additive-only: widening a VARCHAR never loses or alters existing
    data on either dialect — every value that fit in 16 chars still fits
    unchanged in 32. Safe to run against tables with existing rows."""
    for table in _KNOWLEDGE_TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.alter_column(
                "evidence_level",
                existing_type=sa.String(_OLD_LENGTH),
                type_=sa.String(_NEW_LENGTH),
                existing_nullable=True,
            )


def downgrade() -> None:
    """Refuses to narrow if it would truncate any existing value — see
    module docstring. Explicit, dialect-uniform pre-check, not reliance on
    either engine's own ALTER-time behavior."""
    bind = op.get_bind()
    offenders: list[str] = []
    for table in _KNOWLEDGE_TABLES:
        count = bind.execute(
            sa.text(
                f"SELECT COUNT(*) FROM {table} "
                f"WHERE evidence_level IS NOT NULL AND LENGTH(evidence_level) > :max_len"
            ),
            {"max_len": _OLD_LENGTH},
        ).scalar()
        if count:
            offenders.append(f"{table} ({count} row(s))")

    if offenders:
        raise RuntimeError(
            "Refusing to downgrade evidence_level to VARCHAR(16): the following "
            f"table(s) have values longer than {_OLD_LENGTH} characters that would "
            f"be silently truncated: {', '.join(offenders)}. This downgrade is "
            "intentionally irreversible while such values exist — remediate the "
            "data first (re-map to a <=16-char value or accept staying on "
            "VARCHAR(32)) before attempting to downgrade past this revision."
        )

    for table in _KNOWLEDGE_TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.alter_column(
                "evidence_level",
                existing_type=sa.String(_NEW_LENGTH),
                type_=sa.String(_OLD_LENGTH),
                existing_nullable=True,
            )
