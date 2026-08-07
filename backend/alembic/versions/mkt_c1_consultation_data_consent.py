"""Doctor Marketplace: consultation-specific data-sharing consent.

Adds consultation_data_consents — one row per consultation recording the
patient's explicit grant to share health data with that consultation's doctor.
Purely additive; portable SQLite/PostgreSQL (JSONB on PG for `categories`).

The unique constraint on consultation_id is the invariant that makes the access
decision unambiguous: exactly one consent row can ever exist per consultation,
so revocation flips one row and no second row can shadow it.

No backfill. Consultations created before this migration have no consent row,
which reads as "no consent" — deliberately fail-closed: a booking made under the
old checkbox never captured categories, a version, or the copy the patient read,
so it cannot be reconstructed into an explicit grant after the fact.

Revision ID: mkt_c1_consult_consent
Revises: j3_m7_sched_lifecycle
Create Date: 2026-08-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "mkt_c1_consult_consent"
down_revision: str | None = "j3_m7_sched_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOW = sa.text("CURRENT_TIMESTAMP")


def _json() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "consultation_data_consents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "consultation_id",
            sa.String(36),
            sa.ForeignKey("consultations.id"),
            nullable=False,
        ),
        sa.Column(
            "patient_id",
            sa.String(36),
            sa.ForeignKey("patient_profiles.id"),
            nullable=False,
        ),
        sa.Column("doctor_id", sa.String(36), sa.ForeignKey("doctors.id"), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("consent_version", sa.String(16), nullable=False),
        sa.Column("policy_version", sa.String(16), nullable=False),
        sa.Column("categories", _json(), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(32), nullable=True),
        sa.Column("client_app_version", sa.String(32), nullable=True),
        sa.Column("locale", sa.String(32), nullable=True),
        sa.Column("audit_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.UniqueConstraint("consultation_id", name="uq_consultation_data_consent_consultation"),
    )
    op.create_index(
        "ix_consultation_data_consents_consultation_id",
        "consultation_data_consents",
        ["consultation_id"],
    )
    op.create_index(
        "ix_consultation_data_consents_patient_id",
        "consultation_data_consents",
        ["patient_id"],
    )
    op.create_index(
        "ix_consultation_data_consents_doctor_id",
        "consultation_data_consents",
        ["doctor_id"],
    )
    op.create_index(
        "ix_consultation_data_consents_audit_id",
        "consultation_data_consents",
        ["audit_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_consultation_data_consents_audit_id", table_name="consultation_data_consents"
    )
    op.drop_index(
        "ix_consultation_data_consents_doctor_id", table_name="consultation_data_consents"
    )
    op.drop_index(
        "ix_consultation_data_consents_patient_id", table_name="consultation_data_consents"
    )
    op.drop_index(
        "ix_consultation_data_consents_consultation_id",
        table_name="consultation_data_consents",
    )
    op.drop_table("consultation_data_consents")
