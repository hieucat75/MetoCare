"""merge medication P0 and clinic C1-M08 heads

Revision ID: merge_c1m08_p0med
Revises: c1_m08_queue, p0_m01_med_lifecycle
Create Date: 2026-07-12

This is a no-op merge migration. It combines two diverging heads that both
descend from c0_m9_audit_log_clinic_id:

  - c1_m08_queue      : Clinic C1 M08 Check-in & Queue (merged to main)
  - p0_m01_med_lifecycle : Medication P0 foundation (PR #103)

No schema changes are made here. All schema work is in the individual
migration files above.
"""

# revision identifiers, used by Alembic.
revision = "merge_c1m08_p0med"
down_revision = ("c1_m08_queue", "p0_m01_med_lifecycle")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
