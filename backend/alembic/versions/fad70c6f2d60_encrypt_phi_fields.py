"""encrypt PHI fields

Revision ID: fad70c6f2d60
Revises: 85416e7ef0e9
Create Date: 2026-06-12 20:58:25.110013

Field-level encryption is an application concern (see app/core/crypto.py); at the
database level an encrypted column is just TEXT holding base64 ciphertext. This
migration therefore only widens the affected columns to TEXT and adds the new
encrypted columns. Already-TEXT PHI columns (known_conditions, allergies,
family_history, lifestyle_profile) need no schema change — encryption is
transparent at the ORM layer.

Existing-data note: a real deployment with pre-existing plaintext rows must run a
one-off re-encryption job (see app/services/phi_migration.encrypt_existing_phi)
after upgrading. On a fresh DB there is nothing to migrate.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fad70c6f2d60"
down_revision: str | None = "85416e7ef0e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("lab_documents", schema=None) as batch_op:
        batch_op.add_column(sa.Column("raw_text", sa.Text(), nullable=True))

    with op.batch_alter_table("patient_profiles", schema=None) as batch_op:
        batch_op.add_column(sa.Column("phone", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("address", sa.Text(), nullable=True))
        batch_op.alter_column(
            "full_name", existing_type=sa.VARCHAR(length=255), type_=sa.Text(),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "dob", existing_type=sa.DATE(), type_=sa.Text(), existing_nullable=True,
        )

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column(
            "full_name", existing_type=sa.VARCHAR(length=255), type_=sa.Text(),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column(
            "full_name", existing_type=sa.Text(), type_=sa.VARCHAR(length=255),
            existing_nullable=True,
        )

    with op.batch_alter_table("patient_profiles", schema=None) as batch_op:
        batch_op.alter_column(
            "dob", existing_type=sa.Text(), type_=sa.DATE(), existing_nullable=True,
        )
        batch_op.alter_column(
            "full_name", existing_type=sa.Text(), type_=sa.VARCHAR(length=255),
            existing_nullable=True,
        )
        batch_op.drop_column("address")
        batch_op.drop_column("phone")

    with op.batch_alter_table("lab_documents", schema=None) as batch_op:
        batch_op.drop_column("raw_text")
