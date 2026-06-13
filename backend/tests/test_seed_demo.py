"""Smoke test for the demo seed + Swagger docs gating."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from app.models.clinical import HealthMetric
from app.models.user import User, UserRole
from app.services import auth
from sqlalchemy import select

_SEED_PATH = Path(__file__).resolve().parents[1] / "scripts" / "seed_demo.py"
_spec = importlib.util.spec_from_file_location("seed_demo", _SEED_PATH)
seed_demo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_demo)


def test_seed_is_idempotent_and_creates_demo(db):
    first = seed_demo.seed(db)
    assert set(first["created_users"]) == {
        "demo.patient@example.com",
        "demo.doctor@example.com",
        "demo.admin@example.com",
    }
    assert first["metrics"] > 0
    assert first["consent"] is True

    # Three demo accounts exist with the expected roles.
    patient = db.execute(
        select(User).where(User.email == "demo.patient@example.com")
    ).scalar_one()
    doctor = db.execute(
        select(User).where(User.email == "demo.doctor@example.com")
    ).scalar_one()
    assert patient.role == UserRole.PATIENT
    assert doctor.role == UserRole.DOCTOR

    # Demo password actually authenticates.
    assert auth.authenticate(db, email="demo.patient@example.com", password="DemoPatient123!")

    # Metrics landed on the patient's profile.
    metrics = db.execute(
        select(HealthMetric).where(HealthMetric.patient_id == first["patient_id"])
    ).scalars().all()
    assert len(metrics) == first["metrics"]

    # Re-running adds nothing.
    second = seed_demo.seed(db)
    assert second["created_users"] == []
    assert second["metrics"] == 0
    assert second["consent"] is False


def test_docs_enabled_in_dev(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
