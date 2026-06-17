"""add ai_service to users.role CHECK constraint

Revision ID: t4_m0_role
Revises: a1b2c3d4e5f6
Create Date: 2026-06-17 14:35:00.000000

Purpose (C6 fix):
    UserRole.AI_SERVICE = "ai_service" was added to the Python enum in T4 but no migration
    updated the Postgres CHECK constraint on users.role. This migration drops the old
    CHECK constraint and recreates it with ai_service included.

    On SQLite: native_enum=False means the column is just VARCHAR with no DB-level CHECK;
    SQLite silently accepts any string. This migration is a no-op on SQLite.

    On Postgres: SQLAlchemy's Enum(native_enum=False) generates a CHECK constraint named
    "userrole" or based on the column. We drop it by name and recreate with the full list.

Constraint name discovery:
    Run on Postgres to confirm constraint name:
        SELECT conname FROM pg_constraint
        WHERE conrelid='users'::regclass AND contype='c';
    Typical name: users_role_check  (or userrole depending on SA version)
    We handle both names defensively.

Migration order:
    M0 (this) → M1 → M2 → M3 → M4 → M4b → M5 → M6 → M7 → M8 → M9
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 't4_m0_role'
down_revision: str | None = 'a1b2c3d4e5f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Full list of allowed role values (old + new)
_OLD_ROLES = ('PATIENT', 'DOCTOR', 'CLINIC_ADMIN', 'INTERNAL_ADMIN', 'MEDICAL_REVIEWER', 'SUPER_ADMIN')
_NEW_ROLES = (*_OLD_ROLES, 'AI_SERVICE')

# Postgres CHECK constraint name — SQLAlchemy ≥ 2.0 uses "userrole" as the constraint name
# because the Enum's name param is "userrole". Confirm with pg_constraint query above.
_CHECK_NAME = 'userrole'
_ALT_CHECK_NAME = 'users_role_check'


def _get_constraint_name(conn: sa.Connection) -> str | None:
    """Return the CHECK constraint name for users.role, or None if not found."""
    result = conn.execute(
        sa.text(
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid='users'::regclass AND contype='c'"
        )
    )
    names = {row[0] for row in result}
    for name in (_CHECK_NAME, _ALT_CHECK_NAME):
        if name in names:
            return name
    return None


def upgrade() -> None:
    bind = op.get_context().bind
    if bind is None or bind.dialect.name == 'sqlite':
        # SQLite: no CHECK constraint to alter
        return

    with bind.connect() as conn:
        old_name = _get_constraint_name(conn)

    with op.batch_alter_table('users', schema=None) as batch_op:
        if old_name:
            batch_op.drop_constraint(old_name, type_='check')
        batch_op.create_check_constraint(
            _CHECK_NAME,
            sa.column('role').in_(_NEW_ROLES),
        )


def downgrade() -> None:
    bind = op.get_context().bind
    if bind is None or bind.dialect.name == 'sqlite':
        return

    with bind.connect() as conn:
        current_name = _get_constraint_name(conn)

    with op.batch_alter_table('users', schema=None) as batch_op:
        if current_name:
            batch_op.drop_constraint(current_name, type_='check')
        batch_op.create_check_constraint(
            _CHECK_NAME,
            sa.column('role').in_(_OLD_ROLES),
        )
