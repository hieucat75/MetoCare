"""Seed a pilot patient account (User + PatientProfile) in a single transaction.

The public API POST /auth/register creates PATIENT accounts but does not
populate PatientProfile fields beyond full_name. This script seeds a complete
patient record for pilot onboarding, including demographics needed for the
metabolic scoring engine.

Idempotent: if the email already exists the script prints a SKIPPED notice and
exits cleanly, printing the existing user_id and patient_profile_id.

Usage (from backend/ directory):
    python scripts/seed_patient.py \\
        --email patient@example.com \\
        --password "PatientPass!2026" \\
        --full-name "Nguyen Van A" \\
        --dob 1985-06-15 \\
        --gender male \\
        --height-cm 172 \\
        --weight-kg 70

    # PostgreSQL
    MCP_DATABASE_URL=postgresql+psycopg2://mcp:pass@localhost:5432/mcp \\
    python scripts/seed_patient.py ...
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

# Make `app` importable when run as a script from the backend dir.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal, create_all  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.patient import PatientProfile  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from sqlalchemy import select  # noqa: E402

_PASSWORD_MIN_LEN = 12
_PASSWORD_PATTERN = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?`~]).{12,}$"
)
_VALID_GENDERS = frozenset({"male", "female", "other"})


def _validate_password(password: str) -> None:
    if len(password) < _PASSWORD_MIN_LEN:
        raise ValueError(
            f"Password must be at least {_PASSWORD_MIN_LEN} characters long "
            f"(got {len(password)})."
        )
    if not _PASSWORD_PATTERN.match(password):
        raise ValueError(
            "Password must contain at least one uppercase letter, one lowercase "
            "letter, one digit, and one special character."
        )


def _validate_dob(dob: str) -> str:
    """Validate ISO date string (YYYY-MM-DD) and return it normalised."""
    try:
        parsed = datetime.date.fromisoformat(dob)
    except ValueError as exc:
        raise ValueError(f"--dob must be in YYYY-MM-DD format, got: '{dob}'.") from exc
    if parsed >= datetime.date.today():
        raise ValueError("--dob must be in the past.")
    if parsed.year < 1900:
        raise ValueError("--dob year must be >= 1900.")
    return parsed.isoformat()


def _validate_gender(gender: str) -> str:
    g = gender.strip().lower()
    if g not in _VALID_GENDERS:
        raise ValueError(
            f"--gender must be one of {sorted(_VALID_GENDERS)}, got: '{gender}'."
        )
    return g


def _validate_measurement(value: float | None, flag: str, min_val: float, max_val: float) -> None:
    if value is None:
        return
    if not (min_val <= value <= max_val):
        raise ValueError(
            f"--{flag} must be between {min_val} and {max_val}, got: {value}."
        )


def seed_patient(
    *,
    email: str,
    password: str,
    full_name: str,
    dob: str | None = None,
    gender: str | None = None,
    height_cm: float | None = None,
    weight_kg: float | None = None,
) -> dict:
    """Create a patient User + PatientProfile atomically.

    Returns a dict with keys:
        action             : "created" | "skipped"
        email              : str
        user_id            : str
        patient_profile_id : str
    """
    # --- input validation ---
    email = email.strip().lower()
    if not email or "@" not in email:
        raise ValueError(f"Invalid email address: '{email}'.")

    _validate_password(password)

    normalised_dob: str | None = None
    if dob:
        normalised_dob = _validate_dob(dob)

    normalised_gender: str | None = None
    if gender:
        normalised_gender = _validate_gender(gender)

    if height_cm is not None:
        _validate_measurement(height_cm, "height-cm", 50.0, 250.0)
    if weight_kg is not None:
        _validate_measurement(weight_kg, "weight-kg", 10.0, 500.0)

    create_all()  # SQLite dev: create tables if missing; Postgres: no-op (Alembic)

    db = SessionLocal()
    try:
        existing_user = db.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()

        if existing_user is not None:
            # Fetch the existing profile (created by auth.register at PATIENT registration).
            existing_profile = db.execute(
                select(PatientProfile).where(PatientProfile.user_id == existing_user.id)
            ).scalar_one_or_none()
            return {
                "action": "skipped",
                "email": email,
                "user_id": str(existing_user.id),
                "patient_profile_id": str(existing_profile.id) if existing_profile else "(none)",
            }

        # Create user.
        user = User(
            email=email,
            password_hash=hash_password(password),
            role=UserRole.PATIENT,
            full_name=full_name or None,
            is_active=True,
        )
        db.add(user)
        db.flush()  # populate user.id before creating profile

        # Create linked PatientProfile.
        profile = PatientProfile(
            user_id=user.id,
            full_name=full_name or None,
            dob=normalised_dob,
            gender=normalised_gender,
            height_cm=height_cm,
            weight_kg=weight_kg,
        )
        db.add(profile)
        db.commit()
        db.refresh(user)
        db.refresh(profile)

        return {
            "action": "created",
            "email": email,
            "user_id": str(user.id),
            "patient_profile_id": str(profile.id),
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Seed a pilot patient account (User + PatientProfile) into the "
            "MetoCare database. Idempotent: skips if email already exists."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Environment variables:\n"
            "  MCP_DATABASE_URL   Override the database URL (PostgreSQL in prod).\n\n"
            "Example:\n"
            "  python scripts/seed_patient.py \\\n"
            "      --email patient@example.com \\\n"
            "      --password 'PatientPass!2026' \\\n"
            "      --full-name 'Nguyen Van A' \\\n"
            "      --dob 1985-06-15 \\\n"
            "      --gender male \\\n"
            "      --height-cm 172 \\\n"
            "      --weight-kg 70"
        ),
    )
    parser.add_argument("--email", required=True, help="Patient email address.")
    parser.add_argument(
        "--password", required=True,
        help="Password (min 12 chars, upper+lower+digit+special).",
    )
    parser.add_argument("--full-name", required=True, help="Patient full name.")
    parser.add_argument(
        "--dob", default=None,
        help="Date of birth in YYYY-MM-DD format (optional).",
    )
    parser.add_argument(
        "--gender", default=None,
        choices=sorted(_VALID_GENDERS),
        help="Biological sex / gender identity (optional).",
    )
    parser.add_argument(
        "--height-cm", type=float, default=None,
        help="Height in centimetres (optional, range 50–250).",
    )
    parser.add_argument(
        "--weight-kg", type=float, default=None,
        help="Weight in kilograms (optional, range 10–500).",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        result = seed_patient(
            email=args.email,
            password=args.password,
            full_name=args.full_name,
            dob=args.dob,
            gender=args.gender,
            height_cm=args.height_cm,
            weight_kg=args.weight_kg,
        )
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    action = result["action"]
    if action == "created":
        print("[OK] Created patient account.")
        print(f"  email              : {result['email']}")
        print(f"  user_id            : {result['user_id']}")
        print(f"  patient_profile_id : {result['patient_profile_id']}")
        print()
        print("Save these IDs — you will need them for API calls.")
    elif action == "skipped":
        print("[SKIP] Account already exists — no changes made.")
        print(f"  email              : {result['email']}")
        print(f"  user_id            : {result['user_id']}")
        print(f"  patient_profile_id : {result['patient_profile_id']}")


if __name__ == "__main__":
    main()
