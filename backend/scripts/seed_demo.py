"""Seed deterministic DEMO data for manual testing via Swagger UI.

Creates three demo accounts (patient / doctor / admin), a window of synthetic
health metrics for the patient, and an active consent letting the demo doctor
read the patient's metrics. Idempotent: re-running does not duplicate anything.

ALL data here is fake — no real names, emails, or PHI. Do NOT run against prod.

Run from the backend directory:
    python scripts/seed_demo.py
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

# Make `app` importable when run as a script from the backend dir.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.clock import utcnow  # noqa: E402
from app.core.database import SessionLocal, create_all  # noqa: E402
from app.models.clinical import HealthMetric  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.services import auth, consent, health_metrics  # noqa: E402
from sqlalchemy import select  # noqa: E402

# (email, password, role, full_name) — fake credentials, demo only.
DEMO_USERS = [
    ("demo.patient@example.com", "DemoPatient123!", UserRole.PATIENT, "Demo Patient"),
    ("demo.doctor@example.com", "DemoDoctor123!", UserRole.DOCTOR, "Demo Doctor"),
    ("demo.admin@example.com", "DemoAdmin123!", UserRole.INTERNAL_ADMIN, "Demo Admin"),
]

# Synthetic metric series (all within normal ranges; NOT real measurements).
# metric_type, unit, base value, per-day delta, normal_min, normal_max
DEMO_METRICS = [
    ("blood_pressure_systolic", "mmHg", 118.0, 0.2, 90.0, 130.0),
    ("blood_pressure_diastolic", "mmHg", 76.0, 0.1, 60.0, 85.0),
    ("fasting_glucose", "mg/dL", 92.0, 0.15, 70.0, 99.0),
    ("weight_kg", "kg", 68.0, 0.02, None, None),
]


def _get_or_create_user(db, email, password, role, full_name) -> tuple[User, bool]:
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing is not None:
        return existing, False
    user = auth.register(db, email=email, password=password, full_name=full_name, role=role)
    return user, True


def _patient_profile_id(db, user: User) -> str:
    from app.models.patient import PatientProfile

    profile = db.execute(
        select(PatientProfile).where(PatientProfile.user_id == user.id)
    ).scalar_one()
    return profile.id


def seed(db) -> dict:
    summary: dict = {"created_users": [], "metrics": 0, "consent": False}

    users: dict[str, User] = {}
    for email, password, role, full_name in DEMO_USERS:
        user, created = _get_or_create_user(db, email, password, role, full_name)
        users[role.value if role != UserRole.INTERNAL_ADMIN else "admin"] = user
        if created:
            summary["created_users"].append(email)

    patient = users["patient"]
    doctor = users["doctor"]
    patient_id = _patient_profile_id(db, patient)

    # Seed 30 days of metrics — but only if none exist yet (idempotent).
    existing_metrics = db.execute(
        select(HealthMetric).where(HealthMetric.patient_id == patient_id).limit(1)
    ).scalar_one_or_none()
    if existing_metrics is None:
        now = utcnow()
        for day in range(30, -1, -2):  # every 2 days for the last month
            measured_at = now - dt.timedelta(days=day)
            for metric_type, unit, base, delta, nmin, nmax in DEMO_METRICS:
                health_metrics.create_metric(
                    db,
                    patient_id=patient_id,
                    requester_id=patient.id,  # patient owns their own data
                    metric_type=metric_type,
                    value=round(base + delta * (30 - day), 1),
                    unit=unit,
                    measured_at=measured_at,
                    source="seed_demo",
                    normal_range_min=nmin,
                    normal_range_max=nmax,
                )
                summary["metrics"] += 1

    # Active consent: demo doctor may read the patient's health metrics.
    already = consent.has_access(
        db, patient_id=patient_id, requester_id=doctor.id, scope="health_metric"
    )
    if not already:
        consent.grant(
            db,
            patient_id=patient_id,
            consent_type="data_sharing",
            data_scope="health_metric",
            granted_to=doctor.id,
        )
        db.commit()
        summary["consent"] = True

    summary["patient_id"] = patient_id
    summary["patient_user_id"] = patient.id
    summary["doctor_user_id"] = doctor.id
    return summary


def main() -> None:
    create_all()  # SQLite dev convenience; Postgres uses Alembic migrations.
    db = SessionLocal()
    try:
        result = seed(db)
    finally:
        db.close()

    print("Demo seed complete.")
    print(f"  New users:     {result['created_users'] or '(already existed)'}")
    print(f"  Metrics added: {result['metrics']}")
    print(f"  Consent added: {result['consent']}")
    print(f"  patient_id (profile) = {result['patient_id']}")
    print("\nLogin (POST /api/v1/auth/login):")
    for email, password, role, _ in DEMO_USERS:
        print(f"  {role.value:15} {email:22} {password}")
    print("\nOpen Swagger UI: http://localhost:8000/docs")


if __name__ == "__main__":
    main()
