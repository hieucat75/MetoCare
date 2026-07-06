"""t12_m1: Meto conversation admin-review columns

Adds ``reviewed_at`` + ``reviewed_by_user_id`` to ``meto_conversations`` so the
admin AI-safety console (GET/PATCH /admin/ai-sessions) can persist which
flagged conversations a human admin has already looked at.

Revision ID: t12_m1_meto_conv_review
Revises: t11_m1_health_metric_original
Create Date: 2026-07-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "t12_m1_meto_conv_review"
down_revision: str | None = "t11_m1_health_metric_original"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("meto_conversations") as batch:
        batch.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("reviewed_by_user_id", sa.String(length=36), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("meto_conversations") as batch:
        batch.drop_column("reviewed_by_user_id")
        batch.drop_column("reviewed_at")
