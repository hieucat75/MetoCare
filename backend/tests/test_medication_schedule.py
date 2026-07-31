"""J3/M6 tests: medication schedule + idempotent materialization + reminder
delivery + adherence (Master Plan §1.8, BRD §G)."""

from __future__ import annotations

import datetime as dt

import pytest
from app.main import app
from app.models.medication_schedule import DoseOccurrence
from app.services import medication as medication_svc
from app.services import medication_schedule as sched
from app.services import notifications
from fastapi.testclient import TestClient
from sqlalchemy import select


def _seed_med(db, patient_id: str, name: str = "Metformin"):
    return medication_svc.add_medication(
        db, patient_id=patient_id, data={"name": name}, commit=True
    )


def _first_dose(db, schedule_id: str) -> DoseOccurrence | None:
    return db.execute(
        select(DoseOccurrence).where(DoseOccurrence.schedule_id == schedule_id)
    ).scalars().first()


# ── service: materialization ─────────────────────────────────────────────────
def test_materialize_is_idempotent(db, patient):
    med = _seed_med(db, patient["patient_id"])
    s = sched.create_schedule(
        db,
        patient_id=patient["patient_id"],
        medication_id=med.id,
        schedule_type="fixed_daily",
        local_dose_times=["08:00", "20:00"],
        patient_timezone="UTC",
    )
    db.commit()
    n1 = sched.materialize_due(db, s)
    db.commit()
    n2 = sched.materialize_due(db, s)
    db.commit()
    assert n1 > 0
    assert n2 == 0  # a second run creates no duplicate doses


def test_prn_materializes_no_doses(db, patient):
    med = _seed_med(db, patient["patient_id"], "Paracetamol")
    s = sched.create_schedule(
        db, patient_id=patient["patient_id"], medication_id=med.id, schedule_type="prn"
    )
    db.commit()
    assert sched.materialize_due(db, s) == 0


def test_confirmed_only_rejects_terminal_medication(db, patient):
    med = _seed_med(db, patient["patient_id"], "OldMed")
    med.lifecycle_status = "entered_in_error"
    db.commit()
    with pytest.raises(sched.InvalidSchedule):
        sched.create_schedule(
            db,
            patient_id=patient["patient_id"],
            medication_id=med.id,
            schedule_type="fixed_daily",
            local_dose_times=["08:00"],
        )


def test_reminder_delivered_and_dose_marked_notified(db, patient):
    med = _seed_med(db, patient["patient_id"], "Amlodipine")
    s = sched.create_schedule(
        db,
        patient_id=patient["patient_id"],
        medication_id=med.id,
        schedule_type="fixed_daily",
        local_dose_times=["08:00"],
        patient_timezone="UTC",
        start_date=dt.date(2026, 6, 1),
    )
    db.commit()
    now = dt.datetime(2026, 6, 1, 8, 3, tzinfo=dt.UTC)  # 3 min after the 08:00 dose
    sched.materialize_due(db, s, now=now)
    db.commit()
    notifications.reset()
    delivered = sched.deliver_due_reminders(
        db, patient_id=patient["patient_id"], user_id=patient["user_id"], now=now
    )
    db.commit()
    assert delivered == 1
    events = [n.event for n in notifications.recent(patient["user_id"])]
    assert "medication_reminder" in events  # deterministic transport recorded it
    assert _first_dose(db, s.id).state == "notified"


def test_mark_taken_and_adherence(db, patient):
    med = _seed_med(db, patient["patient_id"], "Simvastatin")
    s = sched.create_schedule(
        db,
        patient_id=patient["patient_id"],
        medication_id=med.id,
        schedule_type="fixed_daily",
        local_dose_times=["09:00"],
        patient_timezone="UTC",
        start_date=dt.date(2026, 6, 1),
        end_date=dt.date(2026, 6, 1),  # single day → exactly one dose
    )
    db.commit()
    now = dt.datetime(2026, 6, 1, 9, 1, tzinfo=dt.UTC)
    sched.materialize_due(db, s, now=now)
    db.commit()
    d = _first_dose(db, s.id)
    sched.mark_dose(db, patient_id=patient["patient_id"], dose_id=d.id, state="taken")
    db.commit()
    summary = sched.adherence_summary(db, patient_id=patient["patient_id"], schedule_id=s.id)
    assert summary["taken"] == 1
    assert summary["adherence_rate"] == 1.0


# ── API + BOLA ───────────────────────────────────────────────────────────────
def test_api_create_schedule_and_bola(db, patient, token_for):
    from app.models.patient import PatientProfile
    from app.models.user import User, UserRole

    med = _seed_med(db, patient["patient_id"], "Losartan")
    client = TestClient(app)
    r = client.post(
        f"/api/v1/patients/{patient['patient_id']}/medications/{med.id}/schedule",
        headers=patient["headers"],
        json={
            "schedule_type": "fixed_daily",
            "local_dose_times": ["08:00"],
            "patient_timezone": "UTC",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "active"

    # Another patient cannot create a schedule under this patient's id.
    other = User(email="s2@example.com", password_hash="x", role=UserRole.PATIENT, full_name="S2")
    db.add(other)
    db.flush()
    db.add(PatientProfile(user_id=other.id, full_name="S2"))
    db.commit()
    r2 = client.post(
        f"/api/v1/patients/{patient['patient_id']}/medications/{med.id}/schedule",
        headers=token_for(other.id, role="patient"),
        json={"schedule_type": "fixed_daily", "local_dose_times": ["08:00"]},
    )
    assert r2.status_code == 403


# ── review-fix regressions ───────────────────────────────────────────────────
def test_stopped_schedule_does_not_remind(db, patient):
    """P1: a due-but-unacted dose on a STOPPED schedule must not be reminded."""
    med = _seed_med(db, patient["patient_id"], "Enalapril")
    s = sched.create_schedule(
        db,
        patient_id=patient["patient_id"],
        medication_id=med.id,
        schedule_type="fixed_daily",
        local_dose_times=["08:00"],
        patient_timezone="UTC",
        start_date=dt.date(2026, 6, 1),
    )
    db.commit()
    now = dt.datetime(2026, 6, 1, 8, 3, tzinfo=dt.UTC)
    sched.materialize_due(db, s, now=now)
    db.commit()
    sched.stop_schedule(db, patient_id=patient["patient_id"], schedule_id=s.id)
    db.commit()
    notifications.reset()
    delivered = sched.deliver_due_reminders(
        db, patient_id=patient["patient_id"], user_id=patient["user_id"], now=now
    )
    db.commit()
    assert delivered == 0  # stopped → no reminder; open doses were cancelled


def test_missed_doses_counted_in_adherence(db, patient):
    """P1: an ignored dose becomes MISSED and lands in the adherence denominator."""
    med = _seed_med(db, patient["patient_id"], "Gliclazide")
    s = sched.create_schedule(
        db,
        patient_id=patient["patient_id"],
        medication_id=med.id,
        schedule_type="fixed_daily",
        local_dose_times=["08:00"],
        patient_timezone="UTC",
        start_date=dt.date(2026, 6, 1),
        end_date=dt.date(2026, 6, 1),  # single day → exactly one dose
    )
    db.commit()
    dose_time = dt.datetime(2026, 6, 1, 8, 1, tzinfo=dt.UTC)
    sched.materialize_due(db, s, now=dose_time)
    db.commit()
    later = dose_time + dt.timedelta(hours=6)  # well past the 4h grace
    swept = sched.sweep_missed(db, patient_id=patient["patient_id"], now=later)
    db.commit()
    assert swept == 1
    summary = sched.adherence_summary(db, patient_id=patient["patient_id"], schedule_id=s.id)
    assert summary["missed"] == 1
    assert summary["taken"] == 0
    assert summary["adherence_rate"] == 0.0  # not inflated to 100%


def test_edit_rejects_stopped_schedule(db, patient):
    """P2: a stopped schedule cannot be edited into a new active version."""
    med = _seed_med(db, patient["patient_id"], "Ramipril")
    s = sched.create_schedule(
        db,
        patient_id=patient["patient_id"],
        medication_id=med.id,
        schedule_type="fixed_daily",
        local_dose_times=["08:00"],
    )
    db.commit()
    sched.stop_schedule(db, patient_id=patient["patient_id"], schedule_id=s.id)
    db.commit()
    with pytest.raises(sched.InvalidSchedule):
        sched.edit_schedule(
            db, patient_id=patient["patient_id"], schedule_id=s.id, local_dose_times=["09:00"]
        )


def test_api_invalid_timezone_rejected(db, patient):
    """P2: a bad IANA timezone is rejected at the boundary (422), not stored."""
    med = _seed_med(db, patient["patient_id"], "Metoprolol")
    client = TestClient(app)
    r = client.post(
        f"/api/v1/patients/{patient['patient_id']}/medications/{med.id}/schedule",
        headers=patient["headers"],
        json={
            "schedule_type": "fixed_daily",
            "local_dose_times": ["08:00"],
            "patient_timezone": "Not/AZone",
        },
    )
    assert r.status_code == 422
