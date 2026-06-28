"""Seed pilot admin accounts directly into the database.

Admin accounts cannot be created via the public API (POST /auth/register is
PATIENT-only). Use this script to bootstrap super_admin / internal_admin
accounts for pilot operations.

Idempotent: if an account with the given email already exists the script prints
a SKIPPED notice and exits cleanly.

Usage (from backend/ directory):
    # SQLite dev default
    python scripts/seed_admin.py \\
        --email admin@metocare.vn \\
        --password "SecurePass!2026" \\
        --role super_admin \\
        --full-name "MetoCare Admin"

    # PostgreSQL production
    MCP_DATABASE_URL=postgresql+psycopg2://mcp:pass@localhost:5432/mcp \\
    python scripts/seed_admin.py \\
        --email admin@metocare.vn \\
        --password "SecurePass!2026" \\
        --role super_admin \\
        --full-name "MetoCare Admin"

    # Dry-run: validate only, no DB write
    python scripts/seed_admin.py \\
        --email admin@metocare.vn \\
        --password "SecurePass!2026" \\
        --role super_admin \\
        --full-name "MetoCare Admin" \\
        --dry-run
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Make `app` importable when run as a script from the backend dir.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal, create_all  # noqa: E402  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from sqlalchemy import select  # noqa: E402

# Roles this script is authorised to create.
_ALLOWED_ROLES: frozenset[str] = frozenset(
    {UserRole.SUPER_ADMIN.value, UserRole.INTERNAL_ADMIN.value}
)

_PASSWORD_MIN_LEN = 12
_PASSWORD_PATTERN = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?`~]).{12,}$"
)


def _validate_password(password: str) -> None:
    """Raise ValueError with a descriptive message if the password is weak."""
    if len(password) < _PASSWORD_MIN_LEN:
        raise ValueError(
            f"Password must be at least {_PASSWORD_MIN_LEN} characters long (got {len(password)})."
        )
    if not _PASSWORD_PATTERN.match(password):
        raise ValueError(
            "Password must contain at least one uppercase letter, one lowercase "
            "letter, one digit, and one special character "
            "(!@#$%^&*()_+-=[]{};\\':\"|,.<>/?`~)."
        )


def _validate_role(role: str) -> UserRole:
    """Return the UserRole enum value or raise ValueError."""
    if role not in _ALLOWED_ROLES:
        allowed = ", ".join(sorted(_ALLOWED_ROLES))
        raise ValueError(
            f"Role '{role}' is not permitted by this script. Allowed roles: {allowed}."
        )
    return UserRole(role)


def seed_admin(
    *,
    email: str,
    password: str,
    role: str,
    full_name: str,
    dry_run: bool = False,
) -> dict:
    """Create a single admin account.

    Returns a dict with keys:
        action  : "created" | "skipped"
        email   : str
        role    : str
        user_id : str | None  (None when skipped or dry_run)
    """
    # --- validation (always, even in dry-run) ---
    email = email.strip().lower()
    if not email or "@" not in email:
        raise ValueError(f"Invalid email address: '{email}'.")

    user_role = _validate_role(role)
    _validate_password(password)

    if dry_run:
        print("[DRY RUN] Would create admin account:")
        print(f"  email     : {email}")
        print(f"  role      : {user_role.value}")
        print(f"  full_name : {full_name or '(not set)'}")
        print(f"  password  : {'*' * len(password)}  (length={len(password)}, strength=OK)")
        return {"action": "dry_run", "email": email, "role": user_role.value, "user_id": None}

    create_all()  # SQLite dev: create tables if missing; Postgres: no-op (Alembic)

    db = SessionLocal()
    try:
        existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()

        if existing is not None:
            return {
                "action": "skipped",
                "email": email,
                "role": existing.role.value,
                "user_id": str(existing.id),
            }

        user = User(
            email=email,
            password_hash=hash_password(password),
            role=user_role,
            full_name=full_name or None,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        return {
            "action": "created",
            "email": email,
            "role": user_role.value,
            "user_id": str(user.id),
        }
    finally:
        db.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Seed a pilot admin account directly into the MetoCare database. "
            "Idempotent: skips if email already exists."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Environment variables:\n"
            "  MCP_DATABASE_URL   Override the database URL (PostgreSQL in prod).\n\n"
            "Example:\n"
            "  MCP_DATABASE_URL=postgresql+psycopg2://mcp:pass@localhost:5432/mcp \\\n"
            "  python scripts/seed_admin.py \\\n"
            "      --email admin@metocare.vn \\\n"
            "      --password 'SecurePass!2026' \\\n"
            "      --role super_admin \\\n"
            "      --full-name 'MetoCare Admin'"
        ),
    )
    parser.add_argument("--email", required=True, help="Admin email address.")
    parser.add_argument(
        "--password",
        required=True,
        help="Password (min 12 chars, upper+lower+digit+special).",
    )
    parser.add_argument(
        "--role",
        default="super_admin",
        choices=sorted(_ALLOWED_ROLES),
        help="Admin role to assign. Default: super_admin.",
    )
    parser.add_argument("--full-name", default="", help="Display name (optional).")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs and print what would be created, but make no DB writes.",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        result = seed_admin(
            email=args.email,
            password=args.password,
            role=args.role,
            full_name=args.full_name,
            dry_run=args.dry_run,
        )
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    action = result["action"]
    if action == "created":
        print("[OK] Created admin account.")
        print(f"  email   : {result['email']}")
        print(f"  role    : {result['role']}")
        print(f"  user_id : {result['user_id']}")
    elif action == "skipped":
        print("[SKIP] Account already exists — no changes made.")
        print(f"  email   : {result['email']}")
        print(f"  role    : {result['role']}")
        print(f"  user_id : {result['user_id']}")
    # dry_run branch already printed its output above


if __name__ == "__main__":
    main()
