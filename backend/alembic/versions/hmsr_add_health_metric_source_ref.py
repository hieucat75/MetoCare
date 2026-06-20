"""health metrics: add source_ref for lab-result promotion linkage

When a patient confirms lab results, the overlapping biomarkers are promoted into
``health_metrics`` (source='lab_result') so the dashboard + trends update. ``source``
already exists; this adds a nullable ``source_ref`` (the originating lab_result id)
so promotion is idempotent and traceable. Existing rows keep source_ref NULL.

Revision ID: hm_source_ref
Revises: pauth_user_phone
Create Date: 2026-06-20 09:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'hm_source_ref'
down_revision: str | None = 'pauth_user_phone'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('health_metrics', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source_ref', sa.String(length=64), nullable=True))
        batch_op.create_index('ix_health_metrics_source_ref', ['source_ref'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('health_metrics', schema=None) as batch_op:
        batch_op.drop_index('ix_health_metrics_source_ref')
        batch_op.drop_column('source_ref')
