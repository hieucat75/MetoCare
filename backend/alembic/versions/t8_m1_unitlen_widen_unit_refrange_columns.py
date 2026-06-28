"""Widen unit/reference_range columns to accept OCR output without truncation.

Root cause: OCR engines (Claude Vision, Azure Doc Intel) return unit strings up
to ~40 chars (e.g. "x10³/µL (Coulter count)") and reference ranges up to ~100
chars (e.g. "Nam: 4.5-6.0 T/L; Nữ: 4.0-5.5 T/L (theo máy Sysmex)").
The previous String(24)/String(64) limits caused 422 on Save after OCR review.

Changes:
  lab_results.unit                  String(24)  → String(64)
  lab_results.reference_range       String(64)  → String(128)
  lab_results.original_unit         String(24)  → String(64)
  lab_results.original_reference_range String(64) → String(128)
  lab_results.normalized_unit_si    String(24)  → String(64)
  health_metrics.unit               String(24)  → String(64)

Pydantic schema LabResultItemIn updated in the same commit.

Revision ID: t8_m1_unitlen
Revises:     t7_m1_dquality
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "t8_m1_unitlen"
down_revision: str | None = "t7_m1_dquality"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("lab_results") as batch_op:
        batch_op.alter_column("unit",
            existing_type=sa.String(24), type_=sa.String(64), existing_nullable=True)
        batch_op.alter_column("reference_range",
            existing_type=sa.String(64), type_=sa.String(128), existing_nullable=True)
        batch_op.alter_column("original_unit",
            existing_type=sa.String(24), type_=sa.String(64), existing_nullable=True)
        batch_op.alter_column("original_reference_range",
            existing_type=sa.String(64), type_=sa.String(128), existing_nullable=True)
        batch_op.alter_column("normalized_unit_si",
            existing_type=sa.String(24), type_=sa.String(64), existing_nullable=True)

    with op.batch_alter_table("health_metrics") as batch_op:
        batch_op.alter_column("unit",
            existing_type=sa.String(24), type_=sa.String(64), existing_nullable=True)


def downgrade() -> None:
    # ⚠️  DOWNGRADE RISK: Postgres VARCHAR narrowing truncates data silently.
    # Any unit > 24 chars or reference_range > 64 chars written after t8 upgrade
    # will be truncated without error on downgrade — permanent data loss.
    # Downgrade is only safe if:
    #   1. No saves have occurred after t8 was applied, OR
    #   2. You have verified all values are within old limits first.
    # Confirmed via Postgres dress rehearsal 2026-06-28 (local PG 17, mirrors Azure PG 16 behavior).
    with op.batch_alter_table("lab_results") as batch_op:
        batch_op.alter_column("unit",
            existing_type=sa.String(64), type_=sa.String(24), existing_nullable=True)
        batch_op.alter_column("reference_range",
            existing_type=sa.String(128), type_=sa.String(64), existing_nullable=True)
        batch_op.alter_column("original_unit",
            existing_type=sa.String(64), type_=sa.String(24), existing_nullable=True)
        batch_op.alter_column("original_reference_range",
            existing_type=sa.String(128), type_=sa.String(64), existing_nullable=True)
        batch_op.alter_column("normalized_unit_si",
            existing_type=sa.String(64), type_=sa.String(24), existing_nullable=True)

    with op.batch_alter_table("health_metrics") as batch_op:
        batch_op.alter_column("unit",
            existing_type=sa.String(64), type_=sa.String(24), existing_nullable=True)
