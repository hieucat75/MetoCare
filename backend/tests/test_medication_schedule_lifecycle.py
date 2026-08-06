"""P0-1 — a doctor-instructed pause must not become fabricated non-adherence.

Reproduced before the fix, on the exact scenario a clinician described:

    fixed_daily 08:00 + 20:00, running from 2026-07-01.
    Doctor instructs a 10-day hold. Patient pauses 07-10, resumes 07-20.
    Adherence requested for 07-01..08-04.

    expected_count=70  missed_count=70  adherence_rate=0.0  reconciled=True

`MedicationSchedule` carried only a CURRENT `status`, and `reconcile_period`
gated on it, so zero-accrual held ONLY while the schedule was still paused. The
moment the patient resumed — i.e. the moment they did exactly what they were
told — the whole hold backfilled as MISSED. Twenty doses of fabricated
non-adherence on a patient who followed instructions, stamped `reconciled=True`.

The consequence is not "a slightly wrong number": a clinician facing an
uncontrolled result plus "50% adherent" concludes the patient is not taking the
drug, and does not escalate therapy that needs escalating.

These tests assert EXACT counts. "Roughly right" is what the old behaviour looked
like too.
"""

from __future__ import annotations

import datetime as dt

import pytest
from app.models.medication_schedule import (
    LIFECYCLE_ACTIVATED,
    LIFECYCLE_PAUSED,
    LIFECYCLE_RESUMED,
    DoseOccurrence,
)
from app.services import medication as medication_svc
from app.services import medication_schedule as sched
from sqlalchemy import select

TZ = "Asia/Ho_Chi_Minh"
# Fixed clock. Every expectation below is a hand-computed calendar count.
NOW = dt.datetime(2026, 8, 5, 6, 0, tzinfo=dt.UTC)
TRACKING_START = dt.datetime(2026, 7, 1, 0, 0, tzinfo=dt.UTC)


def _utc(y: int, m: int, d: int, hh: int = 0, mm: int = 0) -> dt.datetime:
    return dt.datetime(y, m, d, hh, mm, tzinfo=dt.UTC)


def _now_plus(**kw) -> dt.datetime:
    return dt.datetime.now(dt.UTC) + dt.timedelta(**kw)


def _make(db, patient, name, **kw):
    """A schedule that has been under observation since TRACKING_START.

    `tracking_start_at` is the retrospective-tracking OPT-IN (P1-4). Passing it
    here is what makes a historical window countable at all; without it the floor
    is creation time and these windows would legitimately be empty.
    """
    med = medication_svc.add_medication(
        db, patient_id=patient["patient_id"], data={"name": name}, commit=True
    )
    kw.setdefault("patient_timezone", TZ)
    kw.setdefault("tracking_start_at", TRACKING_START)
    kw.setdefault("now", TRACKING_START)
    s = sched.create_schedule(
        db, patient_id=patient["patient_id"], medication_id=med.id, **kw
    )
    db.commit()
    return med, s


def _summary(db, patient, s, **kw):
    kw.setdefault("now", NOW)
    kw.setdefault("period_start", dt.date(2026, 7, 1))
    kw.setdefault("period_end", dt.date(2026, 8, 4))
    out = sched.adherence_summary(
        db, patient_id=patient["patient_id"], schedule_id=s.id, **kw
    )
    db.commit()
    return out


def _daily(db, patient, name, times=("08:00",)):
    return _make(
        db, patient, name, schedule_type="fixed_daily",
        local_dose_times=list(times), start_date=dt.date(2026, 7, 1),
    )


def _hold(db, patient, s, pause_at, resume_at=None):
    sched.pause_schedule(
        db, patient_id=patient["patient_id"], schedule_id=s.id,
        effective_at=pause_at, reason_code="doctor_instructed",
    )
    db.commit()
    if resume_at is not None:
        sched.resume_schedule(
            db, patient_id=patient["patient_id"], schedule_id=s.id,
            effective_at=resume_at,
        )
        db.commit()


# ── 1. The P0 itself ────────────────────────────────────────────────────────


def test_a_doctor_instructed_hold_contributes_zero_expected_doses(db, patient):
    """THE headline case, in the numbers the clinician reported.

    07-01..08-04 is 35 days x 2 doses = 70 if nothing was ever held. The hold
    covers 07-10..07-19 inclusive = 10 days = 20 doses the patient was
    INSTRUCTED not to take. 50 remain, and none of the 20 may be MISSED.
    """
    _m, s = _daily(db, patient, "InstructedHold", times=("08:00", "20:00"))
    _hold(db, patient, s, _utc(2026, 7, 9, 17, 0), _utc(2026, 7, 19, 17, 0))

    summary = _summary(db, patient, s)
    assert summary["expected_count"] == 50, (
        "the hold is still in the denominator — a pause has been retroactively "
        f"converted into missed doses (got {summary['expected_count']})"
    )
    assert summary["excluded_paused_count"] == 20
    assert summary["missed_count"] == 50   # genuinely untouched outside the hold
    assert summary["reconciled"] is True


def test_the_hold_is_not_reintroduced_by_asking_again(db, patient):
    """Reconciliation is idempotent: asking twice must not re-materialize."""
    _m, s = _daily(db, patient, "AskTwice", times=("08:00", "20:00"))
    _hold(db, patient, s, _utc(2026, 7, 9, 17, 0), _utc(2026, 7, 19, 17, 0))
    first = _summary(db, patient, s)
    second = _summary(db, patient, s)
    assert first["expected_count"] == second["expected_count"] == 50
    assert first["excluded_paused_count"] == second["excluded_paused_count"] == 20


def test_removing_the_interval_filter_reintroduces_the_defect(db, patient):
    """Discriminating check: the filter, not some accident, is doing the work."""
    _m, s = _daily(db, patient, "Discriminate", times=("08:00", "20:00"))
    _hold(db, patient, s, _utc(2026, 7, 9, 17, 0), _utc(2026, 7, 19, 17, 0))
    unfiltered = sched.expected_occurrences_in_window(
        s, window_start=dt.date(2026, 7, 1), window_end=dt.date(2026, 8, 4)
    )
    filtered = sched.expected_occurrences_in_window(
        s, window_start=dt.date(2026, 7, 1), window_end=dt.date(2026, 8, 4),
        intervals=sched.active_intervals(db, s), floor=sched.tracking_floor(s),
    )
    assert len(unfiltered) == 70
    assert len(filtered) == 50


# ── 2. Boundary semantics ───────────────────────────────────────────────────


def test_pause_effective_at_is_inclusive_of_the_hold(db, patient):
    """A dose at exactly the pause instant is INSIDE the hold: the patient told
    to stop "from 08:00" has not been asked to take the 08:00 dose."""
    _m, s = _daily(db, patient, "PauseInclusive")
    # 08:00 Asia/Ho_Chi_Minh == 01:00 UTC.
    _hold(db, patient, s, _utc(2026, 7, 10, 1, 0), _utc(2026, 7, 12, 1, 0))
    summary = _summary(db, patient, s)
    # 35 days; 07-10 and 07-11 held (07-12's 08:00 is the resume instant).
    assert summary["expected_count"] == 33
    assert summary["excluded_paused_count"] == 2


def test_resume_effective_at_begins_the_next_active_interval(db, patient):
    """Half-open ``[resume, next_pause)``: no dose is lost between two events."""
    _m, s = _daily(db, patient, "ResumeExclusive")
    _hold(db, patient, s, _utc(2026, 7, 10, 1, 0), _utc(2026, 7, 12, 1, 0))
    kept = {
        utc for utc, _ in sched.expected_occurrences_in_window(
            s, window_start=dt.date(2026, 7, 9), window_end=dt.date(2026, 7, 13),
            intervals=sched.active_intervals(db, s), floor=sched.tracking_floor(s),
        )
    }
    assert _utc(2026, 7, 12, 1, 0) in kept, "the resume-instant dose was dropped"
    assert _utc(2026, 7, 10, 1, 0) not in kept, "the pause-instant dose was kept"


def test_pause_before_the_first_daily_dose_holds_the_whole_day(db, patient):
    _m, s = _daily(db, patient, "PauseBeforeDose")
    _hold(db, patient, s, _utc(2026, 7, 10, 0, 30), _utc(2026, 7, 11, 0, 30))
    kept = {
        utc for utc, _ in sched.expected_occurrences_in_window(
            s, window_start=dt.date(2026, 7, 10), window_end=dt.date(2026, 7, 10),
            intervals=sched.active_intervals(db, s), floor=sched.tracking_floor(s),
        )
    }
    assert kept == set()


def test_pause_between_two_daily_doses(db, patient):
    """Held at midday: the morning dose stands, the evening one does not."""
    _m, s = _daily(db, patient, "MiddayPause", times=("08:00", "20:00"))
    # 12:00 local 07-10 == 05:00 UTC; 08:00 local = 01:00 UTC, 20:00 = 13:00 UTC.
    _hold(db, patient, s, _utc(2026, 7, 10, 5, 0))
    kept = {
        utc for utc, _ in sched.expected_occurrences_in_window(
            s, window_start=dt.date(2026, 7, 10), window_end=dt.date(2026, 7, 10),
            intervals=sched.active_intervals(db, s), floor=sched.tracking_floor(s),
        )
    }
    assert kept == {_utc(2026, 7, 10, 1, 0)}


def test_multiple_pause_resume_cycles_each_subtract(db, patient):
    _m, s = _daily(db, patient, "TwoCycles")
    _hold(db, patient, s, _utc(2026, 7, 4, 17), _utc(2026, 7, 7, 17))    # 3 days
    _hold(db, patient, s, _utc(2026, 7, 19, 17), _utc(2026, 7, 24, 17))  # 5 days
    summary = _summary(db, patient, s)
    assert summary["expected_count"] == 35 - 8
    assert summary["excluded_paused_count"] == 8


def test_a_pause_spanning_a_dst_boundary_subtracts_whole_local_days(db, patient):
    """The hold was expressed in local days, so a DST transition inside it must
    not silently add or drop one."""
    med = medication_svc.add_medication(
        db, patient_id=patient["patient_id"], data={"name": "DstHold"}, commit=True
    )
    s = sched.create_schedule(
        db, patient_id=patient["patient_id"], medication_id=med.id,
        schedule_type="fixed_daily", local_dose_times=["08:00"],
        start_date=dt.date(2026, 3, 1), patient_timezone="Europe/London",
        tracking_start_at=_utc(2026, 3, 1), now=_utc(2026, 3, 1),
    )
    db.commit()
    # UK clocks go forward 2026-03-29. Hold from 03-25 08:00 local (08:00 UTC,
    # GMT) to 04-02 08:00 local (07:00 UTC, BST): 8 local dosing days.
    _hold(db, patient, s, _utc(2026, 3, 25, 8, 0), _utc(2026, 4, 2, 7, 0))
    kept = sched.expected_occurrences_in_window(
        s, window_start=dt.date(2026, 3, 1), window_end=dt.date(2026, 4, 10),
        intervals=sched.active_intervals(db, s), floor=sched.tracking_floor(s),
    )
    assert len(kept) == 41 - 8


# ── 3. Backdated, future-dated, and illegal commands ────────────────────────


def test_a_backdated_pause_never_deletes_recorded_history(db, patient):
    """The patient recorded doses; the doctor's hold is entered afterwards and
    backdated over them. Those assertions are the patient's, not ours to erase."""
    _m, s = _daily(db, patient, "Backdated")
    sched.reconcile_period(
        db, s, period_start=dt.date(2026, 7, 1), period_end=dt.date(2026, 7, 10), now=NOW
    )
    db.commit()
    rows = list(db.execute(
        select(DoseOccurrence).where(DoseOccurrence.schedule_id == s.id)
        .order_by(DoseOccurrence.scheduled_utc)
    ).scalars())
    for dose in rows[4:7]:      # 07-05, 07-06, 07-07 taken
        sched.mark_dose(db, patient_id=patient["patient_id"], dose_id=dose.id, state="taken")
    db.commit()

    _hold(db, patient, s, _utc(2026, 7, 4, 17), _utc(2026, 7, 7, 17))

    survivors = list(db.execute(
        select(DoseOccurrence).where(
            DoseOccurrence.schedule_id == s.id, DoseOccurrence.state == "taken"
        )
    ).scalars())
    assert len(survivors) == 3, "a backdated pause destroyed recorded history"

    summary = _summary(db, patient, s)
    # Held doses leave the denominator entirely — including ones the patient
    # recorded, which cannot be adherence to a prescription that was withdrawn.
    assert summary["taken_count"] == 0
    assert summary["excluded_paused_count"] == 3
    assert summary["expected_count"] == 35 - 3


def test_a_future_dated_pause_leaves_the_schedule_running_until_it_takes_effect(db, patient):
    _m, s = _daily(db, patient, "FuturePause")
    future = _now_plus(days=30)
    sched.pause_schedule(
        db, patient_id=patient["patient_id"], schedule_id=s.id, effective_at=future,
        reason_code="pre_procedure_hold",
    )
    db.commit()
    assert s.status == "active", "a future-dated hold stopped the schedule today"
    intervals = sched.active_intervals(db, s)
    assert intervals and intervals[-1][1] == future


def test_pausing_an_already_paused_schedule_is_refused(db, patient):
    _m, s = _daily(db, patient, "DoublePause")
    _hold(db, patient, s, _utc(2026, 7, 10))
    with pytest.raises(sched.LifecycleConflict):
        sched.pause_schedule(
            db, patient_id=patient["patient_id"], schedule_id=s.id,
            effective_at=_utc(2026, 7, 15),
        )
    db.rollback()


def test_an_identical_repeated_pause_is_idempotent_not_an_error(db, patient):
    """A double-tapped button records ONE hold, not two overlapping intervals.

    This is the concurrency case in its observable form: two requests carrying
    the same effective instant converge on one event via the unique
    `idempotency_key`, so neither ordering produces a different denominator.
    """
    _m, s = _daily(db, patient, "DoubleTap")
    when = _utc(2026, 7, 10)
    _hold(db, patient, s, when)
    sched.pause_schedule(
        db, patient_id=patient["patient_id"], schedule_id=s.id, effective_at=when
    )
    db.commit()
    events = sched.lifecycle_events(db, s.id)
    assert [e.event_type for e in events].count(LIFECYCLE_PAUSED) == 1


def test_resuming_a_running_schedule_adds_no_interval(db, patient):
    _m, s = _daily(db, patient, "ResumeRunning")
    sched.resume_schedule(db, patient_id=patient["patient_id"], schedule_id=s.id)
    db.commit()
    assert [e.event_type for e in sched.lifecycle_events(db, s.id)] == [LIFECYCLE_ACTIVATED]


def test_nothing_may_follow_a_stop(db, patient):
    _m, s = _daily(db, patient, "StopTerminal")
    sched.stop_schedule(
        db, patient_id=patient["patient_id"], schedule_id=s.id,
        effective_at=_utc(2026, 7, 10),
    )
    db.commit()
    with pytest.raises(sched.ScheduleError):
        sched.resume_schedule(db, patient_id=patient["patient_id"], schedule_id=s.id)
    db.rollback()


def test_stopping_while_paused_closes_the_timeline_once(db, patient):
    """A stop after a pause must not reopen and re-close the interval — that
    would resurrect the held days into the denominator."""
    _m, s = _daily(db, patient, "StopWhilePaused")
    _hold(db, patient, s, _utc(2026, 7, 10))
    sched.stop_schedule(
        db, patient_id=patient["patient_id"], schedule_id=s.id,
        effective_at=_utc(2026, 7, 15),
    )
    db.commit()
    intervals = sched.fold_intervals(sched.lifecycle_events(db, s.id))
    assert len(intervals) == 1
    assert intervals[0][1] == _utc(2026, 7, 10)


def test_editing_while_paused_does_not_resurrect_the_held_days(db, patient):
    """Edit supersedes the old version and activates the new one; the hold in
    between belongs to neither and must stay out of the denominator."""
    _m, s = _daily(db, patient, "EditWhilePaused")
    _hold(db, patient, s, _utc(2026, 7, 9, 17))
    new = sched.edit_schedule(
        db, patient_id=patient["patient_id"], schedule_id=s.id,
        local_dose_times=["09:00"],
    )
    db.commit()
    summary = _summary(db, patient, new)
    assert summary["excluded_paused_count"] > 0
    assert summary["expected_count"] < 35


def test_the_timeline_is_append_only(db, patient):
    """Correcting a mistake appends the correcting event; it never rewrites."""
    _m, s = _daily(db, patient, "AppendOnly")
    _hold(db, patient, s, _utc(2026, 7, 10), _utc(2026, 7, 20))
    types = [e.event_type for e in sched.lifecycle_events(db, s.id)]
    assert types == [LIFECYCLE_ACTIVATED, LIFECYCLE_PAUSED, LIFECYCLE_RESUMED]


def test_lifecycle_events_carry_no_clinical_free_text(db, patient):
    """A lifecycle trail that leaks WHY a drug was held is its own disclosure."""
    _m, s = _daily(db, patient, "PhiSafe")
    _hold(db, patient, s, _utc(2026, 7, 10))
    for event in sched.lifecycle_events(db, s.id):
        assert len(event.reason_code) <= 48
        assert " " not in event.reason_code, "reason_code must be a closed vocabulary"
        assert event.note_ref is None or len(event.note_ref) <= 64
