"""P1-3 — the adherence denominator must not depend on app-open frequency.

Dose rows only ever came into existence when a request handler ran
`materialize_due`, and `compute_occurrences` clamps to `max(start, today_local)`
with a 7-day horizon. So the persisted row set was a record of when the patient
opened the app, and `adherence_summary` counted exactly that set.

Measured before the fix: a twice-daily schedule running 2026-07-01..2026-08-05
prescribes 70 doses. A patient last active on 2026-07-06 had 14 rows, covering
07-06..07-13. Fifty-six doses — 80% of the therapy — were invisible to the rate.

The clinical inversion this produces: a patient who disengages entirely accrues
almost no rows, so almost nothing can be counted against them, while a patient
who engages daily and misses a few scores worse. A clinician reading those two
numbers before deciding whether to escalate therapy would rank them backwards.

The fix reconciles every expected occurrence in the requested window into
existence first, then counts. These tests assert EXACT counts, because "roughly
right" is what the old behaviour looked like too.
"""

from __future__ import annotations

import datetime as dt

import pytest
from app.models.medication_schedule import DoseOccurrence
from app.services import medication as medication_svc
from app.services import medication_schedule as sched
from sqlalchemy import select

TZ = "Asia/Ho_Chi_Minh"
# Fixed clock: every expectation below is a hand-computed calendar count.
NOW = dt.datetime(2026, 8, 5, 6, 0, tzinfo=dt.UTC)
TODAY = dt.date(2026, 8, 5)


def _med(db, patient, name):
    return medication_svc.add_medication(
        db, patient_id=patient["patient_id"], data={"name": name}, commit=True
    )


def _make(db, patient, name, **kw):
    med = _med(db, patient, name)
    kw.setdefault("patient_timezone", TZ)
    s = sched.create_schedule(
        db, patient_id=patient["patient_id"], medication_id=med.id, **kw
    )
    db.commit()
    return med, s


def _summary(db, patient, s, **kw):
    kw.setdefault("now", NOW)
    out = sched.adherence_summary(
        db, patient_id=patient["patient_id"], schedule_id=s.id, **kw
    )
    db.commit()
    return out


def _rows(db, s):
    return db.execute(
        select(DoseOccurrence).where(DoseOccurrence.schedule_id == s.id)
    ).scalars().all()


# ── 1. Dormancy: the defect itself ──────────────────────────────────────────


@pytest.mark.parametrize("dormant_days", [0, 7, 30])
def test_denominator_is_identical_regardless_of_dormancy(db, patient, dormant_days):
    """The property in one assertion. A patient who last opened the app N days
    ago must get the same expected count as one who opened it this morning."""
    _m, s = _make(
        db, patient, f"Dormant{dormant_days}",
        schedule_type="fixed_daily", local_dose_times=["08:00", "20:00"],
        start_date=dt.date(2026, 7, 1),
    )
    # Simulate the app being opened `dormant_days` ago and not since: that is the
    # ONLY materialization that ever ran.
    last_open = NOW - dt.timedelta(days=dormant_days)
    sched.materialize_due(db, s, now=last_open)
    db.commit()

    summary = _summary(
        db, patient, s, period_start=dt.date(2026, 7, 1), period_end=dt.date(2026, 8, 4)
    )
    # 2026-07-01..2026-08-04 inclusive = 35 days x 2 doses.
    assert summary["expected_count"] == 70, (
        f"dormant {dormant_days}d: expected 70 prescribed doses, "
        f"got {summary['expected_count']} — the denominator still tracks app usage"
    )


def test_thirty_day_dormancy_counts_every_missed_dose(db, patient):
    """The headline case. Nothing was taken, so all 70 must be missed and the
    rate must be 0.0 — not the flattering 'no data' the old code produced."""
    _m, s = _make(
        db, patient, "Dormant30Missed",
        schedule_type="fixed_daily", local_dose_times=["08:00", "20:00"],
        start_date=dt.date(2026, 7, 1),
    )
    sched.materialize_due(db, s, now=NOW - dt.timedelta(days=30))
    db.commit()

    summary = _summary(
        db, patient, s, period_start=dt.date(2026, 7, 1), period_end=dt.date(2026, 8, 4)
    )
    assert summary["expected_count"] == 70
    assert summary["missed_count"] == 70
    assert summary["taken_count"] == 0
    assert summary["adherence_rate"] == 0.0


def test_a_disengaged_patient_does_not_outscore_an_engaged_one(db, patient):
    """The clinical inversion, asserted directly."""
    _m, engaged = _make(
        db, patient, "Engaged",
        schedule_type="fixed_daily", local_dose_times=["08:00"],
        start_date=dt.date(2026, 7, 20),
    )
    sched.reconcile_period(
        db, engaged, period_start=dt.date(2026, 7, 20), period_end=dt.date(2026, 8, 4),
        now=NOW,
    )
    db.commit()
    for dose in _rows(db, engaged)[:14]:   # took 14 of 16
        sched.mark_dose(db, patient_id=patient["patient_id"], dose_id=dose.id, state="taken")
    db.commit()

    _m2, disengaged = _make(
        db, patient, "Disengaged",
        schedule_type="fixed_daily", local_dose_times=["08:00"],
        start_date=dt.date(2026, 7, 20),
    )
    # Never opened the app after day one.
    sched.materialize_due(db, disengaged, now=dt.datetime(2026, 7, 20, 6, tzinfo=dt.UTC))
    db.commit()

    a = _summary(db, patient, engaged,
                 period_start=dt.date(2026, 7, 20), period_end=dt.date(2026, 8, 4))
    b = _summary(db, patient, disengaged,
                 period_start=dt.date(2026, 7, 20), period_end=dt.date(2026, 8, 4))
    assert a["adherence_rate"] > b["adherence_rate"], (
        f"the disengaged patient scored {b['adherence_rate']} vs the engaged "
        f"patient's {a['adherence_rate']} — the ranking is inverted"
    )


# ── 2. Schedule shapes, exact counts ────────────────────────────────────────


@pytest.mark.parametrize(
    "kind,times,recurrence,start,expected",
    [
        # 2026-07-01..2026-08-04 = 35 days.
        ("fixed_daily", ["08:00"], None, dt.date(2026, 7, 1), 35),
        ("fixed_daily", ["08:00", "20:00"], None, dt.date(2026, 7, 1), 70),
        # Alternate-day from 07-01: 07-01,03,05,... within 35 days -> 18.
        ("interval", ["08:00"], {"interval_days": 2}, dt.date(2026, 7, 1), 18),
        # Every 3 days: 07-01,04,07,... -> 12.
        ("interval", ["08:00"], {"interval_days": 3}, dt.date(2026, 7, 1), 12),
        # 21-on/7-off from 07-01: on 07-01..07-21 (21) + 07-29..08-04 (7) = 28.
        ("cyclic", ["08:00"], {"on_days": 21, "off_days": 7}, dt.date(2026, 7, 1), 28),
    ],
)
def test_expected_count_matches_the_prescription(
    db, patient, kind, times, recurrence, start, expected
):
    _m, s = _make(
        db, patient, f"Shape-{kind}-{expected}",
        schedule_type=kind, local_dose_times=times, recurrence=recurrence,
        start_date=start,
    )
    summary = _summary(
        db, patient, s, period_start=dt.date(2026, 7, 1), period_end=dt.date(2026, 8, 4)
    )
    assert summary["expected_count"] == expected


def test_days_of_week_counts_only_its_weekdays(db, patient):
    _m, s = _make(
        db, patient, "MonThuAdherence",
        schedule_type="days_of_week", local_dose_times=["08:00"],
        recurrence={"days": [0, 3]}, start_date=dt.date(2026, 7, 1),
    )
    summary = _summary(
        db, patient, s, period_start=dt.date(2026, 7, 1), period_end=dt.date(2026, 8, 4)
    )
    mondays_thursdays = sum(
        1
        for i in range((dt.date(2026, 8, 4) - dt.date(2026, 7, 1)).days + 1)
        if (dt.date(2026, 7, 1) + dt.timedelta(days=i)).weekday() in (0, 3)
    )
    assert summary["expected_count"] == mondays_thursdays


# ── 3. Period boundaries ────────────────────────────────────────────────────


def test_a_period_entirely_before_the_schedule_start_is_empty(db, patient):
    _m, s = _make(
        db, patient, "BeforeStart", schedule_type="fixed_daily",
        local_dose_times=["08:00"], start_date=dt.date(2026, 7, 1),
    )
    summary = _summary(
        db, patient, s, period_start=dt.date(2026, 6, 1), period_end=dt.date(2026, 6, 30)
    )
    assert summary["expected_count"] == 0
    assert summary["adherence_rate"] is None, "a percentage from an empty period"


def test_a_period_partially_before_the_start_counts_only_the_overlap(db, patient):
    _m, s = _make(
        db, patient, "PartialOverlap", schedule_type="fixed_daily",
        local_dose_times=["08:00"], start_date=dt.date(2026, 7, 20),
    )
    summary = _summary(
        db, patient, s, period_start=dt.date(2026, 7, 1), period_end=dt.date(2026, 8, 4)
    )
    assert summary["expected_count"] == 16  # 07-20..08-04


def test_a_period_after_the_end_date_is_empty(db, patient):
    _m, s = _make(
        db, patient, "AfterEnd", schedule_type="fixed_daily",
        local_dose_times=["08:00"], start_date=dt.date(2026, 7, 1),
        end_date=dt.date(2026, 7, 10),
    )
    summary = _summary(
        db, patient, s, period_start=dt.date(2026, 7, 20), period_end=dt.date(2026, 8, 4)
    )
    assert summary["expected_count"] == 0


def test_an_empty_single_day_period_is_valid(db, patient):
    _m, s = _make(
        db, patient, "OneDay", schedule_type="fixed_daily",
        local_dose_times=["08:00"], start_date=dt.date(2026, 7, 1),
    )
    summary = _summary(
        db, patient, s, period_start=dt.date(2026, 8, 1), period_end=dt.date(2026, 8, 1)
    )
    assert summary["expected_count"] == 1


def test_an_inverted_period_is_rejected(db, patient):
    _m, s = _make(
        db, patient, "Inverted", schedule_type="fixed_daily",
        local_dose_times=["08:00"], start_date=dt.date(2026, 7, 1),
    )
    with pytest.raises(sched.InvalidSchedule):
        _summary(db, patient, s,
                 period_start=dt.date(2026, 8, 4), period_end=dt.date(2026, 7, 1))


def test_an_unbounded_period_is_rejected(db, patient):
    """A request must not be able to walk an arbitrary calendar and materialize
    an arbitrary number of rows."""
    _m, s = _make(
        db, patient, "Unbounded", schedule_type="fixed_daily",
        local_dose_times=["08:00"], start_date=dt.date(2020, 1, 1),
    )
    with pytest.raises(sched.InvalidSchedule):
        _summary(db, patient, s,
                 period_start=dt.date(2020, 1, 1), period_end=dt.date(2026, 8, 4))


def test_future_doses_are_excluded_from_the_rate(db, patient):
    """A dose that has not come around cannot have been missed."""
    _m, s = _make(
        db, patient, "FutureExcluded", schedule_type="fixed_daily",
        local_dose_times=["08:00"], start_date=dt.date(2026, 8, 1),
    )
    summary = _summary(
        db, patient, s, period_start=dt.date(2026, 8, 1), period_end=dt.date(2026, 8, 10)
    )
    assert summary["future_count"] > 0
    assert summary["expected_count"] == 10
    assert summary["missed_count"] + summary["future_count"] == 10


# ── 4. Lifecycle: pause / resume / stop / edit ──────────────────────────────


def test_a_paused_schedule_does_not_accrue_new_missed_doses(db, patient):
    """Pausing means the patient is legitimately not taking the drug. Inventing
    missed doses for that period is the same fabrication as deleting real ones,
    in reverse."""
    _m, s = _make(
        db, patient, "PausedNoAccrual", schedule_type="fixed_daily",
        local_dose_times=["08:00"], start_date=dt.date(2026, 7, 1),
    )
    sched.pause_schedule(db, patient_id=patient["patient_id"], schedule_id=s.id)
    db.commit()

    summary = _summary(
        db, patient, s, period_start=dt.date(2026, 7, 1), period_end=dt.date(2026, 8, 4)
    )
    assert summary["reconciled"] is False, "a paused period was backfilled"
    assert summary["expected_count"] == 0


def test_resuming_restores_reconciliation(db, patient):
    _m, s = _make(
        db, patient, "ResumeReconciles", schedule_type="fixed_daily",
        local_dose_times=["08:00"], start_date=dt.date(2026, 7, 1),
    )
    sched.pause_schedule(db, patient_id=patient["patient_id"], schedule_id=s.id)
    db.commit()
    sched.resume_schedule(db, patient_id=patient["patient_id"], schedule_id=s.id)
    db.commit()

    summary = _summary(
        db, patient, s, period_start=dt.date(2026, 7, 1), period_end=dt.date(2026, 8, 4)
    )
    assert summary["reconciled"] is True
    assert summary["expected_count"] == 35


def test_a_stopped_schedule_does_not_accrue(db, patient):
    _m, s = _make(
        db, patient, "StoppedNoAccrual", schedule_type="fixed_daily",
        local_dose_times=["08:00"], start_date=dt.date(2026, 7, 1),
    )
    sched.stop_schedule(db, patient_id=patient["patient_id"], schedule_id=s.id)
    db.commit()
    summary = _summary(
        db, patient, s, period_start=dt.date(2026, 7, 1), period_end=dt.date(2026, 8, 4)
    )
    assert summary["expected_count"] == 0


def test_history_recorded_before_dormancy_survives_reconciliation(db, patient):
    """Reconciliation must ADD the missing rows, never rewrite acted ones."""
    _m, s = _make(
        db, patient, "HistorySurvives", schedule_type="fixed_daily",
        local_dose_times=["08:00"], start_date=dt.date(2026, 7, 1),
    )
    sched.reconcile_period(
        db, s, period_start=dt.date(2026, 7, 1), period_end=dt.date(2026, 7, 5), now=NOW
    )
    db.commit()
    taken_ids = [d.id for d in _rows(db, s)[:3]]
    for did in taken_ids:
        sched.mark_dose(db, patient_id=patient["patient_id"], dose_id=did, state="taken")
    db.commit()

    summary = _summary(
        db, patient, s, period_start=dt.date(2026, 7, 1), period_end=dt.date(2026, 8, 4)
    )
    assert summary["taken_count"] == 3, "reconciliation overwrote recorded history"
    assert summary["expected_count"] == 35


def test_skipped_is_counted_separately_but_stays_in_the_denominator(db, patient):
    """A patient who skips half their doses is not adherent, however deliberate
    each skip was — but a skip is not a miss and must not be reported as one."""
    _m, s = _make(
        db, patient, "SkippedSemantics", schedule_type="fixed_daily",
        local_dose_times=["08:00"], start_date=dt.date(2026, 7, 1),
    )
    sched.reconcile_period(
        db, s, period_start=dt.date(2026, 7, 1), period_end=dt.date(2026, 7, 4), now=NOW
    )
    db.commit()
    rows = _rows(db, s)
    sched.mark_dose(db, patient_id=patient["patient_id"], dose_id=rows[0].id, state="taken")
    sched.mark_dose(db, patient_id=patient["patient_id"], dose_id=rows[1].id, state="skipped")
    db.commit()

    summary = _summary(
        db, patient, s, period_start=dt.date(2026, 7, 1), period_end=dt.date(2026, 7, 4)
    )
    assert summary["taken_count"] == 1
    assert summary["skipped_count"] == 1
    assert summary["missed_count"] == 2
    assert summary["adherence_rate"] == pytest.approx(0.25)


# ── 5. Idempotency and concurrency ──────────────────────────────────────────


def test_repeated_summary_calls_are_idempotent(db, patient):
    _m, s = _make(
        db, patient, "RepeatIdempotent", schedule_type="fixed_daily",
        local_dose_times=["08:00", "20:00"], start_date=dt.date(2026, 7, 1),
    )
    first = _summary(db, patient, s,
                     period_start=dt.date(2026, 7, 1), period_end=dt.date(2026, 8, 4))
    count_after_first = len(_rows(db, s))
    for _ in range(4):
        again = _summary(db, patient, s,
                         period_start=dt.date(2026, 7, 1), period_end=dt.date(2026, 8, 4))
        assert again["expected_count"] == first["expected_count"]
    assert len(_rows(db, s)) == count_after_first, "repeat calls created rows"


def test_reconciliation_never_duplicates_occurrences(db, patient):
    _m, s = _make(
        db, patient, "NoDupes", schedule_type="fixed_daily",
        local_dose_times=["08:00"], start_date=dt.date(2026, 7, 1),
    )
    for _ in range(3):
        sched.reconcile_period(
            db, s, period_start=dt.date(2026, 7, 1), period_end=dt.date(2026, 8, 4),
            now=NOW,
        )
        db.commit()
    rows = _rows(db, s)
    assert len({r.idempotency_key for r in rows}) == len(rows)
    assert len(rows) == 35


def test_overlapping_windows_converge(db, patient):
    """Two requests for different but overlapping periods must not double-count
    the overlap."""
    _m, s = _make(
        db, patient, "Overlap", schedule_type="fixed_daily",
        local_dose_times=["08:00"], start_date=dt.date(2026, 7, 1),
    )
    _summary(db, patient, s,
             period_start=dt.date(2026, 7, 1), period_end=dt.date(2026, 7, 20))
    _summary(db, patient, s,
             period_start=dt.date(2026, 7, 10), period_end=dt.date(2026, 8, 4))
    rows = _rows(db, s)
    assert len({r.idempotency_key for r in rows}) == len(rows)
    final = _summary(db, patient, s,
                     period_start=dt.date(2026, 7, 1), period_end=dt.date(2026, 8, 4))
    assert final["expected_count"] == 35


# ── 6. Timezone and DST ─────────────────────────────────────────────────────


def test_the_period_is_evaluated_in_the_patient_timezone(db, patient):
    """A local calendar day is the unit, not a UTC day: at UTC+7 an 08:00 local
    dose is 01:00 UTC, so a UTC-based window would slice days apart."""
    _m, s = _make(
        db, patient, "TzBoundary", schedule_type="fixed_daily",
        local_dose_times=["08:00"], start_date=dt.date(2026, 7, 1),
    )
    summary = _summary(
        db, patient, s, period_start=dt.date(2026, 7, 1), period_end=dt.date(2026, 7, 31)
    )
    assert summary["expected_count"] == 31
    assert summary["timezone"] == TZ


def test_a_dst_transition_neither_adds_nor_drops_a_day(db, patient):
    """Europe/London falls back on 2026-10-25. October has 31 days and the
    schedule is daily, so it must be exactly 31 — a UTC-hour-based count would
    produce 30 or 32."""
    med = _med(db, patient, "DstAdherence")
    s = sched.create_schedule(
        db, patient_id=patient["patient_id"], medication_id=med.id,
        schedule_type="fixed_daily", local_dose_times=["08:00"],
        patient_timezone="Europe/London", start_date=dt.date(2026, 10, 1),
    )
    db.commit()
    occ = sched.expected_occurrences_in_window(
        s, window_start=dt.date(2026, 10, 1), window_end=dt.date(2026, 10, 31)
    )
    assert len(occ) == 31
    tz = sched._tz("Europe/London")
    assert {u.astimezone(tz).strftime("%H:%M") for u, _ in occ} == {"08:00"}


# ── 7. The contract itself ──────────────────────────────────────────────────


def test_the_summary_reports_its_period_and_calculation_version(db, patient):
    _m, s = _make(
        db, patient, "Contract", schedule_type="fixed_daily",
        local_dose_times=["08:00"], start_date=dt.date(2026, 7, 1),
    )
    summary = _summary(
        db, patient, s, period_start=dt.date(2026, 7, 1), period_end=dt.date(2026, 8, 4)
    )
    assert summary["period_start"] == dt.date(2026, 7, 1)
    assert summary["period_end"] == dt.date(2026, 8, 4)
    assert summary["calculation_version"] == sched.ADHERENCE_CALCULATION_VERSION
    for key in ("expected_count", "taken_count", "skipped_count", "missed_count",
                "future_count", "excluded_cancelled_count", "reconciled"):
        assert key in summary


def test_a_prn_schedule_reports_unreconciled_rather_than_a_percentage(db, patient):
    """PRN has no prescribed schedule — there is nothing to be adherent TO, so a
    percentage would be meaningless rather than merely imprecise."""
    med = _med(db, patient, "PrnAdherence")
    s = sched.create_schedule(
        db, patient_id=patient["patient_id"], medication_id=med.id,
        schedule_type="prn", patient_timezone=TZ,
    )
    db.commit()
    summary = _summary(
        db, patient, s, period_start=dt.date(2026, 7, 1), period_end=dt.date(2026, 8, 4)
    )
    assert summary["reconciled"] is False
    assert summary["adherence_rate"] is None
