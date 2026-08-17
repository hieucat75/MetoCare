"""t14_m1: HealthMetric source_reference_text (Unified LabResult Contract B2 follow-up)

Adds ``source_reference_text`` to ``health_metrics`` so a confirmed LabResult's
printed/source-report reference range survives promotion into HealthMetric.
Without this, MetricOut had no printed range to pass into
`resolve_lab_semantics`, so it always fell back to CANONICAL_FALLBACK while
LabResultOut (built straight from the LabResult row) correctly showed
SOURCE_REPORT for the same confirmed result — the staging blocker this closes.

Forward-safe only, no backfill: existing HealthMetric rows keep
source_reference_text=NULL and continue resolving via CANONICAL_FALLBACK,
identical to their behaviour before this migration. A row is naturally
brought current the next time its LabResult is (re-)promoted, since
`_promote_row` is idempotent per lab_result_id.

Revision ID: t14_m1_hm_source_reference
Revises: mkt_c1_consult_consent
Create Date: 2026-08-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "t14_m1_hm_source_reference"
down_revision: str | None = "mkt_c1_consult_consent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("health_metrics") as batch:
        batch.add_column(sa.Column("source_reference_text", sa.String(length=128), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("health_metrics") as batch:
        batch.drop_column("source_reference_text")
