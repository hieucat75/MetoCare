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


# ── CLIN PS-5: medication lifecycle → schedule cascade ───────────────────────
def _active_schedule_with_due_dose(db, patient, name: str):
    """Seed an active medication + fixed-daily schedule with one materialized,
    already-due dose. Returns (med, schedule, now)."""
    med = _seed_med(db, patient["patient_id"], name)
    s = sched.create_schedule(
        db,
        patient_id=patient["patient_id"],
        medication_id=med.id,
        schedule_type="fixed_daily",
        local_dose_times=["08:00"],
        patient_timezone="UTC",
        start_date=dt.date(2026, 6, 1),
        end_date=dt.date(2026, 6, 1),
    )
    db.commit()
    now = dt.datetime(2026, 6, 1, 8, 3, tzinfo=dt.UTC)
    sched.materialize_due(db, s, now=now)
    db.commit()
    return med, s, now


def test_deleted_medication_does_not_generate_reminders(db, patient):
    """CLIN PS-5: deleting the drug must stop its reminders — the app must never
    tell a patient by name to take a medication they removed."""
    med, s, now = _active_schedule_with_due_dose(db, patient, "Enalapril-del")
    assert _first_dose(db, s.id) is not None
    medication_svc.delete_medication(
        db,
        patient_id=patient["patient_id"],
        med_id=med.id,
        actor_user_id=patient["user_id"],
        actor_role="patient",
    )
    notifications.reset()
    delivered = sched.deliver_due_reminders(
        db, patient_id=patient["patient_id"], user_id=patient["user_id"], now=now
    )
    db.commit()
    assert delivered == 0
    db.refresh(s)
    assert s.status == "stopped"  # cascade stopped the schedule
    assert _first_dose(db, s.id) is None  # open doses cancelled


def test_stopped_medication_does_not_generate_reminders(db, patient):
    """CLIN PS-5: a lifecycle exit (active → discontinued) cascades to the
    schedule, so a drug the patient/doctor stopped never reminds again."""
    med, s, now = _active_schedule_with_due_dose(db, patient, "Gliclazide-stop")
    medication_svc.update_medication(
        db,
        patient_id=patient["patient_id"],
        med_id=med.id,
        data={"lifecycle_status": "discontinued", "status_reason": "bác sĩ cho ngừng"},
        actor_user_id=patient["user_id"],
        actor_role="patient",
    )
    notifications.reset()
    delivered = sched.deliver_due_reminders(
        db, patient_id=patient["patient_id"], user_id=patient["user_id"], now=now
    )
    db.commit()
    assert delivered == 0
    db.refresh(s)
    assert s.status == "stopped"


def test_legacy_inactive_medication_dose_is_never_reminded(db, patient):
    """CLIN PS-5 (query-side guard): rows broken BEFORE the cascade existed —
    an inactive medication whose schedule is still 'active' — must not remind."""
    med, s, now = _active_schedule_with_due_dose(db, patient, "Legacy-med")
    # Simulate the pre-fix state: medication retired without any cascade.
    med.lifecycle_status = "discontinued"
    db.commit()
    assert s.status == "active"
    notifications.reset()
    delivered = sched.deliver_due_reminders(
        db, patient_id=patient["patient_id"], user_id=patient["user_id"], now=now
    )
    db.commit()
    assert delivered == 0


# ── P1-A (integration review): a malformed recurrence must be REJECTED, never
# degraded. The old code fell through to "every day applies", so a cyclical
# regimen reminded the patient to dose on rest days.

import pytest as _pytest  # noqa: E402
from app.services import medication_schedule as _sched  # noqa: E402


def _mk(db, patient, **kw):
    from app.services import medication as medication_svc

    med = medication_svc.add_medication(
        db, patient_id=patient["patient_id"], data={"name": "Prednisolone"}, commit=True
    )
    return _sched.create_schedule(
        db, patient_id=patient["patient_id"], medication_id=med.id, **kw
    )


@_pytest.mark.parametrize(
    "kind,rec",
    [
        ("cyclic", {}),
        ("cyclic", {"off_days": 7}),
        ("cyclic", {"on_days": 0, "off_days": 7}),
        ("cyclic", {"on_days": "x", "off_days": 7}),
        ("cyclic", {"on_days": 3, "off_days": -1}),
        ("interval", {}),
        ("interval", {"interval_days": 0}),
        ("interval", {"interval_days": "weekly"}),
        ("days_of_week", {}),
        ("days_of_week", {"days": []}),
        ("days_of_week", {"days": [7]}),
        ("days_of_week", {"days": ["mon"]}),
    ],
)
def test_malformed_recurrence_is_rejected(db, patient, kind, rec):
    with _pytest.raises(_sched.InvalidSchedule):
        _mk(db, patient, schedule_type=kind, local_dose_times=["08:00"], recurrence=rec)


@_pytest.mark.parametrize("bad", [["8am"], ["25:00"], ["08:60"], [""], ["08:00", "nope"]])
def test_unparseable_dose_times_are_rejected(db, patient, bad):
    """An ACTIVE schedule that can never remind is worse than a refused one."""
    with _pytest.raises(_sched.InvalidSchedule):
        _mk(db, patient, schedule_type="fixed_daily", local_dose_times=bad)


def test_valid_recurrences_still_accepted(db, patient):
    for kind, rec in (
        ("cyclic", {"on_days": 5, "off_days": 2}),
        ("interval", {"interval_days": 3}),
        ("days_of_week", {"days": [0, 2, 4]}),
        ("fixed_daily", None),
    ):
        # interval/cyclic are phase-dependent and now REQUIRE a persisted anchor.
        anchor = {"start_date": dt.date(2026, 8, 5)} if kind in ("interval", "cyclic") else {}
        s = _mk(
            db, patient, schedule_type=kind, local_dose_times=["08:00"],
            recurrence=rec, **anchor,
        )
        assert s.status == "active"


def test_malformed_cyclic_never_degrades_to_daily():
    """Defence in depth for legacy rows already stored malformed."""
    import datetime as dt

    from app.models.medication_schedule import MedicationSchedule

    s = MedicationSchedule(
        medication_id="m", patient_id="p", schedule_type="cyclic",
        recurrence={"off_days": 7}, patient_timezone="UTC", status="active",
    )
    start = dt.date(2026, 8, 1)
    assert not any(
        _sched._day_applies(s, start + dt.timedelta(days=i), start) for i in range(14)
    )


def test_malformed_interval_never_degrades_to_daily():
    import datetime as dt

    from app.models.medication_schedule import MedicationSchedule

    s = MedicationSchedule(
        medication_id="m", patient_id="p", schedule_type="interval",
        recurrence={}, patient_timezone="UTC", status="active",
    )
    start = dt.date(2026, 8, 1)
    assert not any(
        _sched._day_applies(s, start + dt.timedelta(days=i), start) for i in range(14)
    )


# ── P1-B (integration review): editing a schedule must NOT rewrite history.
# _cancel_open_doses deleted every open dose, including ones already past due but
# not yet swept to MISSED — so a patient who missed doses and then changed their
# reminder time had that non-adherence ERASED and the denominator restarted.


def test_editing_a_schedule_preserves_missed_history(db, patient):
    import datetime as dt

    from app.services import medication as medication_svc

    pid = patient["patient_id"]
    med = medication_svc.add_medication(
        db, patient_id=pid, data={"name": "Metformin"}, commit=True
    )
    s = _sched.create_schedule(
        db, patient_id=pid, medication_id=med.id, schedule_type="fixed_daily",
        local_dose_times=["08:00"], patient_timezone="UTC",
        start_date=dt.date(2026, 6, 1), end_date=dt.date(2026, 6, 3),
    )
    db.commit()

    # Materialize from BEFORE the first dose time so all three days are created
    # (compute_occurrences only materializes forward of `now`), then let them all
    # go overdue — edit_schedule sweeps against the real clock.
    _sched.materialize_due(db, s, now=dt.datetime(2026, 6, 1, 7, tzinfo=dt.UTC))
    db.commit()
    opened = db.query(_sched.DoseOccurrence).filter_by(schedule_id=s.id).count()
    assert opened >= 3

    # The patient now edits their reminder time.
    new = _sched.edit_schedule(
        db, patient_id=pid, schedule_id=s.id, local_dose_times=["09:00"]
    )
    db.commit()

    adherence = _sched.adherence_summary(db, patient_id=pid, schedule_id=s.id)
    # The property this test protects: the overdue doses were swept to MISSED and
    # KEPT, not deleted. That still holds.
    assert adherence["missed"] >= 3, adherence
    # The RATE is now withheld, and that is deliberate. This schedule has been
    # superseded, so `reconcile_period` declines it and the counts are whatever
    # happened to be materialized before the edit — i.e. a function of when the
    # patient last opened the app, not of their therapy. Publishing 0.0 from that
    # set would be the engagement-derived number this work removes; a superseded
    # version cannot answer "how adherent were you" and must say so.
    assert adherence["reconciled"] is False
    assert adherence["adherence_rate"] is None, adherence
    assert new.id != s.id and new.version == s.version + 1


def test_editing_a_schedule_still_drops_future_doses(db, patient):
    """The superseded version must not keep reminding for doses that never came."""
    import datetime as dt

    from app.services import medication as medication_svc

    pid = patient["patient_id"]
    med = medication_svc.add_medication(
        db, patient_id=pid, data={"name": "Metformin"}, commit=True
    )
    s = _sched.create_schedule(
        db, patient_id=pid, medication_id=med.id, schedule_type="fixed_daily",
        local_dose_times=["08:00"], patient_timezone="UTC",
        start_date=dt.date(2026, 6, 1),
    )
    db.commit()
    _sched.materialize_due(db, s, now=dt.datetime(2026, 6, 1, 7, tzinfo=dt.UTC))
    db.commit()

    _sched.edit_schedule(db, patient_id=pid, schedule_id=s.id, local_dose_times=["09:00"])
    db.commit()

    future_open = (
        db.query(_sched.DoseOccurrence)
        .filter(
            _sched.DoseOccurrence.schedule_id == s.id,
            _sched.DoseOccurrence.state.in_(("pending", "notified")),
            _sched.DoseOccurrence.scheduled_utc > dt.datetime.now(dt.UTC),
        )
        .count()
    )
    assert future_open == 0
