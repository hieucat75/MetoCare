"""patient-auth: add users.phone + make email nullable

Patients self-register/login with a VN mobile number. Adds a unique nullable
`phone` column and relaxes `email` to nullable (admin/doctor still use email;
patients have phone instead). One of email/phone is set per row.

Revision ID: pauth_user_phone
Revises: prf_notif_prefs
Create Date: 2026-06-20 06:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'pauth_user_phone'
down_revision: str | None = 'prf_notif_prefs'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('phone', sa.String(length=20), nullable=True))
        # NULLs are distinct in a UNIQUE constraint (both SQLite and Postgres),
        # so multiple email-only users (phone NULL) are allowed.
        batch_op.create_index('ix_users_phone', ['phone'], unique=True)
        batch_op.alter_column('email', existing_type=sa.String(length=255), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('email', existing_type=sa.String(length=255), nullable=False)
        batch_op.drop_index('ix_users_phone')
        batch_op.drop_column('phone')
