"""t11_m1: HealthMetric original value/unit (P0 clinical-integrity)

Adds ``original_value`` + ``original_unit`` to ``health_metrics`` so every
user/AI-facing surface can display the ORIGINAL value+unit as recorded (e.g.
88 µmol/L) instead of the canonical/SI-converted number stored in
``value``/``unit`` (which is kept only for internal classification + trends).

Backfill (SQLite-compatible correlated subqueries):
  1. Lab-sourced rows copy original_value/original_unit from their source
     LabResult (matched via health_metrics.source_ref = lab_results.id).
  2. Fallback: any row still NULL (self-report metrics + labs whose original_*
     was itself NULL) copies the existing value/unit — those are already the
     as-recorded originals for self-report, and the best available for labs.

Revision ID: t11_m1_health_metric_original
Revises: t10_m1_consultation_marketplace
Create Date: 2026-07-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "t11_m1_health_metric_original"
down_revision: str | None = "t10_m1_consultation_marketplace"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("health_metrics") as batch:
        batch.add_column(sa.Column("original_value", sa.Float(), nullable=True))
        batch.add_column(sa.Column("original_unit", sa.String(length=64), nullable=True))

    # 1. Lab-sourced rows: pull the true original from the source LabResult.
    op.execute(
        """
        UPDATE health_metrics
           SET original_value = (
                   SELECT lr.original_value FROM lab_results lr
                    WHERE lr.id = health_metrics.source_ref
               ),
               original_unit = (
                   SELECT lr.original_unit FROM lab_results lr
                    WHERE lr.id = health_metrics.source_ref
               )
         WHERE source = 'lab_result'
           AND source_ref IS NOT NULL
        """
    )

    # 2. Fallback: self-report rows + labs whose original_* was NULL keep their
    #    existing value/unit (already the as-recorded original).
    op.execute(
        """
        UPDATE health_metrics
           SET original_value = value,
               original_unit = unit
         WHERE original_value IS NULL
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("health_metrics") as batch:
        batch.drop_column("original_unit")
        batch.drop_column("original_value")
