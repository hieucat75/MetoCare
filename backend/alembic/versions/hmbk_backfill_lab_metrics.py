"""backfill: promote existing lab_results into health_metrics

Labs saved before lab→metric sync existed (and via the interpret/async pipeline
paths) have no corresponding health_metric, so the dashboard + trends showed
nothing for them. This one-time data migration promotes every orphan lab_result
(value present, not yet linked by health_metrics.source_ref). Idempotent — already
promoted rows are skipped, so re-running is harmless.

Revision ID: hmbk_backfill
Revises: hm_source_ref
Create Date: 2026-06-20 10:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision: str = 'hmbk_backfill'
down_revision: str | None = 'hm_source_ref'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Import lazily so the migration module loads even if app import is heavy; the
    # backfill reuses the exact promotion logic (canonical mapping, idempotency).
    from app.services.lab import backfill_lab_metrics

    bind = op.get_bind()
    session = Session(bind=bind)
    written = backfill_lab_metrics(session, commit=False)
    session.flush()
    print(f"[hmbk_backfill] promoted {written} orphan lab metrics into health_metrics")


def downgrade() -> None:
    # Remove only the metrics this backfill could have created (lab-sourced).
    op.execute("DELETE FROM health_metrics WHERE source = 'lab_result'")
