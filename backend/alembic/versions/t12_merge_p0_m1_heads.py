"""t12 merge: unify the two alembic heads t12_p0 (#89) and t12_m1 (#88)

Both ``t12_p0_doctor_review_decisions`` (PR #89, doctor-portal review store) and
``t12_m1_meto_conv_review`` (PR #88, Meto conversation review) branch from
``t11_m1_health_metric_original``. Once both PRs land on ``main`` the revision
graph has TWO heads, so ``alembic upgrade head`` (the deploy job) fails with
"Multiple head revisions are present".

This is a MERGE revision only: it unifies the two heads into one. It performs NO
schema change (upgrade/downgrade are no-ops).

IMPORTANT — merge order: this revision's parents must already exist, so it can
only be merged to ``main`` AFTER both #88 and #89 have landed.

Revision ID: t12_merge_p0_m1_heads
Revises: t12_p0_doctor_review_decisions, t12_m1_meto_conv_review
Create Date: 2026-07-07
"""

from __future__ import annotations

# revision identifiers, used by Alembic.
revision = "t12_merge_p0_m1_heads"
down_revision = ("t12_p0_doctor_review_decisions", "t12_m1_meto_conv_review")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op: this revision only unifies the two heads in the graph."""


def downgrade() -> None:
    """No-op: splitting back into two heads requires no schema change."""
