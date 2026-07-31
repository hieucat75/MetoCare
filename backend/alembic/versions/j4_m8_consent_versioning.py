"""Journey 4 M8: per-category Meto consent versioning (§J).

Adds meto_consents.policy_version (the consent-policy version a grant was made
against — a grant is only honored while it matches the current version, forcing
re-consent on a policy bump) and a uniqueness constraint on (user_id,
context_type) so grant/revoke upserts a single row per category. Additive on a
previously-dormant table; portable SQLite/PostgreSQL via batch_alter_table.

Revision ID: j4_m8_consent_versioning
Revises: j3_m5_medication_schedule
Create Date: 2026-08-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "j4_m8_consent_versioning"
down_revision: str | None = "j3_m5_medication_schedule"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("meto_consents", schema=None) as batch:
        batch.add_column(sa.Column("policy_version", sa.String(length=16), nullable=True))
        batch.create_unique_constraint(
            "uq_meto_consent_user_category", ["user_id", "context_type"]
        )


def downgrade() -> None:
    with op.batch_alter_table("meto_consents", schema=None) as batch:
        batch.drop_constraint("uq_meto_consent_user_category", type_="unique")
        batch.drop_column("policy_version")
