"""add unique constraint patient_profiles.user_id

Revision ID: t27_uq_patient_profile_user_id
Revises: t23_add_notifications
Create Date: 2026-06-19
"""

from alembic import op

revision = "t27_uq_patient_profile_user_id"
down_revision = "t23_add_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("patient_profiles") as batch_op:
        batch_op.create_unique_constraint(
            "uq_patient_profiles_user_id", ["user_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("patient_profiles") as batch_op:
        batch_op.drop_constraint(
            "uq_patient_profiles_user_id", type_="unique"
        )
