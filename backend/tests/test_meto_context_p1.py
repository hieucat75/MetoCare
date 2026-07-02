"""P1 regression: Meto AI must load the care plan and upcoming appointments.

Continuation of the P0 fix (efb57cc). Clinical/scheduling data is keyed by
``patient_profiles.id`` (NOT ``user.id``), and ``profile.id != user.id``. The
ContextBuilder historically filtered ``care_plans`` and ``appointments`` by
``user.id``, so:

- ``_build_care_plan`` never matched a real plan (wrong key + it also compared
  ``status = 'active'`` while the enum stores ``"ACTIVE"``).
- ``_build_today_context`` never returned appointments (wrong key + it selected
  columns — title/appointment_time/provider_name/location — that don't exist,
  so the query threw and was silently swallowed).

These tests seed a real patient whose ``profile.id != user.id``, seed an ACTIVE
care plan and a future appointment under ``profile.id`` (as the app stores them),
and assert the assembled context exposes both. They FAIL against the pre-fix
builder and PASS after it.
"""
from __future__ import annotations

import datetime as dt

from app.ai.context.builder import ContextBuilder
from app.ai.context.schemas import ScreenContext
from app.models.care import Appointment, CarePlan, Doctor


def _seed_active_care_plan(db, profile_id: str, title: str) -> str:
    """Seed an ACTIVE care plan keyed by profile_id (as the app stores them)."""
    plan = CarePlan(
        patient_id=profile_id,
        title=title,
        ai_generated=False,  # set before status so the C2 @validates guard passes
        status="ACTIVE",
    )
    db.add(plan)
    db.commit()
    return plan.id


def _seed_future_appointment(db, profile_id: str) -> tuple[str, str]:
    """Seed a doctor + a future appointment keyed by profile_id. Returns (appt_id, doctor_id)."""
    doctor = Doctor(full_name="BS. Trần Văn Khám")
    db.add(doctor)
    db.flush()

    appt = Appointment(
        patient_id=profile_id,
        doctor_id=doctor.id,
        scheduled_at=dt.datetime.combine(
            dt.date.today() + dt.timedelta(days=1), dt.time(9, 0)
        ),
        mode="offline",
        status="requested",
    )
    db.add(appt)
    db.commit()
    return appt.id, doctor.id


def test_profile_id_differs_from_user_id(patient):
    """Guard: the fixture must exercise the real bug (profile.id != user.id)."""
    assert patient["patient_id"] != patient["user_id"], (
        "test is meaningless unless profile.id != user.id"
    )


def test_context_includes_active_care_plan(db, patient):
    """Seed an ACTIVE care plan under profile.id → context must expose it."""
    user_id = patient["user_id"]
    profile_id = patient["patient_id"]
    title = "Kế hoạch kiểm soát đường huyết"

    plan_id = None
    try:
        plan_id = _seed_active_care_plan(db, profile_id, title)

        ctx = ContextBuilder().build(db, user_id, ScreenContext(screen_id="dashboard"))

        assert ctx.care_plan is not None, (
            "P1 REGRESSION: care_plan is None although an ACTIVE plan exists for "
            "this patient (keyed by profile.id)"
        )
        assert ctx.care_plan["plan_name"] == title
        assert "care_plan" in ctx.included_blocks
    finally:
        if plan_id is not None:
            db.query(CarePlan).filter(CarePlan.id == plan_id).delete()
            db.commit()


def test_context_includes_upcoming_appointment(db, patient):
    """Seed a future appointment under profile.id → today_context must expose it."""
    user_id = patient["user_id"]
    profile_id = patient["patient_id"]

    appt_id = doctor_id = None
    try:
        appt_id, doctor_id = _seed_future_appointment(db, profile_id)

        ctx = ContextBuilder().build(db, user_id, ScreenContext(screen_id="dashboard"))

        appts = ctx.today_context.get("upcoming_appointments", [])
        assert len(appts) == 1, (
            f"P1 REGRESSION: expected 1 upcoming appointment, got {len(appts)} "
            "(query keyed by user.id and/or selected non-existent columns)"
        )
        appt = appts[0]
        assert appt["datetime"] is not None
        assert appt["mode"] == "offline"
        assert appt["status"] == "requested"
        assert "today_context" in ctx.included_blocks
    finally:
        if appt_id is not None:
            db.query(Appointment).filter(Appointment.id == appt_id).delete()
        if doctor_id is not None:
            db.query(Doctor).filter(Doctor.id == doctor_id).delete()
        db.commit()


def test_care_plan_isolated_by_profile(db, patient):
    """A care plan seeded under ANOTHER patient's profile must NOT leak into this context."""
    from app.models.patient import PatientProfile
    from app.models.user import User

    user_id = patient["user_id"]

    other_user = other_profile = plan_id = None
    try:
        other_user = User(
            email=f"other-{dt.datetime.now().timestamp()}@example.com",
            password_hash="x",
            role="patient",
            full_name="Người khác",
        )
        db.add(other_user)
        db.flush()
        other_profile = PatientProfile(user_id=other_user.id, full_name="Người khác")
        db.add(other_profile)
        db.flush()
        plan_id = _seed_active_care_plan(db, other_profile.id, "Kế hoạch của người khác")

        ctx = ContextBuilder().build(db, user_id, ScreenContext(screen_id="dashboard"))

        assert ctx.care_plan is None, (
            "ISOLATION LEAK: this user's context picked up another patient's care plan"
        )
    finally:
        if plan_id is not None:
            db.query(CarePlan).filter(CarePlan.id == plan_id).delete()
        if other_profile is not None:
            db.query(PatientProfile).filter(PatientProfile.id == other_profile.id).delete()
        if other_user is not None:
            db.query(User).filter(User.id == other_user.id).delete()
        db.commit()
