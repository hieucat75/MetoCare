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
    # Dedupe BEFORE adding the constraint. The docstring called this table
    # "previously-dormant", but meto_consents has been written since Meto went
    # live, and the only write path (services/meto_chat.py::update_consent) is a
    # read-then-branch with no SELECT FOR UPDATE, no ON CONFLICT, and — until this
    # very migration — no DB-level uniqueness. Two concurrent grant/revoke calls
    # for the same category (double-tap, retry-on-timeout) can both pass the
    # existence check and both INSERT.
    #
    # This was reproduced on real Postgres: with a duplicate present,
    # `ADD CONSTRAINT ... UNIQUE (user_id, context_type)` raises UniqueViolation.
    # Because Alembic runs every pending revision in ONE transaction, that failure
    # rolls back the whole deploy, not just this step.
    #
    # Keep the highest id per (user_id, context_type). ids are UUID-ish strings, so
    # "highest" is not "newest" — the tie-break only has to be deterministic, and
    # the surviving row is re-synced by the next consent write anyway.
    op.execute(
        sa.text(
            """
            DELETE FROM meto_consents
             WHERE id NOT IN (
                   SELECT keep_id FROM (
                       SELECT MAX(id) AS keep_id
                         FROM meto_consents
                        GROUP BY user_id, context_type
                   ) AS keepers
             )
            """
        )
    )

    with op.batch_alter_table("meto_consents", schema=None) as batch:
        batch.add_column(sa.Column("policy_version", sa.String(length=16), nullable=True))
        batch.create_unique_constraint(
            "uq_meto_consent_user_category", ["user_id", "context_type"]
        )


def downgrade() -> None:
    with op.batch_alter_table("meto_consents", schema=None) as batch:
        batch.drop_constraint("uq_meto_consent_user_category", type_="unique")
        batch.drop_column("policy_version")
