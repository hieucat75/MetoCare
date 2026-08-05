"""P0-2 — phase-dependent schedules must have a stable, persisted anchor.

The defect class: `compute_occurrences` derived the cycle origin from
`schedule.start_date or today_local`. For `interval` and `cyclic` schedules the
origin is what defines the phase, so a NULL `start_date` made the anchor move
with the clock: `(day - anchor) % n` evaluated against *today* is 0 on every
day, and an every-2-days or 21-on/7-off regimen silently degraded to daily.

That is the most dangerous shape this module can fail into. Methotrexate is
weekly and daily dosing is a recognised fatal medication error; a 21/7 oral
contraceptive or chemotherapy cycle reminded through its rest week is a
clinically wrong instruction delivered by name. It fails silently — the patient
sees a plausible reminder every morning, and nothing in the UI says the cycle
was lost.

Three properties are pinned here, at all three layers, because fixing only one
leaves the class open:

  1. CREATE refuses an anchor-required schedule with no `start_date` (new rows).
  2. EDIT cannot reach the bad state either: it takes no `start_date` argument
     (so the anchor is structurally un-droppable), the new version inherits it,
     and a type change INTO interval/cyclic on a row that never had one is
     refused rather than silently anchored to today.
  3. `compute_occurrences` FAILS CLOSED — returns no doses — for a legacy row
     that already has NULL (the rows already in the database), rather than
     falling back to today. Producing nothing is visibly wrong; dosing every day
     is silently wrong. `needs_anchor_repair()` surfaces such rows to the UI.

Phase-INDEPENDENT types (`fixed_daily`, `days_of_week`) are deliberately exempt:
every day, or every matching weekday, qualifies regardless of when therapy
began, so for them and only for them the today fallback is correct.
"""

from __future__ import annotations

import datetime as dt

import pytest
from app.models.medication_schedule import DoseOccurrence
from app.services import medication as medication_svc
from app.services import medication_schedule as sched
from sqlalchemy import select

ANCHOR_FREE = ("fixed_daily", "days_of_week")

# A fixed clock. Every expectation below is a hand-computed calendar date, so the
# suite must not depend on the day it runs.
NOW = dt.datetime(2026, 8, 5, 6, 0, tzinfo=dt.UTC)  # Wednesday
TODAY = NOW.date()


def _med(db, patient, name: str):
    return medication_svc.add_medication(
        db, patient_id=patient["patient_id"], data={"name": name}, commit=True
    )


def _make(db, patient, name, **kw):
    med = _med(db, patient, name)
    kw.setdefault("patient_timezone", "UTC")
    s = sched.create_schedule(
        db, patient_id=patient["patient_id"], medication_id=med.id, **kw
    )
    db.commit()
    return s


def _dose_dates(schedule, *, days: int = 30) -> list[dt.date]:
    """Local calendar dates the schedule would actually remind on."""
    return sorted(
        {
            utc.astimezone(dt.UTC).date()
            for utc, _ in sched.compute_occurrences(schedule, horizon_days=days, now=NOW)
        }
    )


# ── 1. CREATE refuses a missing anchor ───────────────────────────────────────


@pytest.mark.parametrize(
    "kind,recurrence",
    [
        ("interval", {"interval_days": 2}),
        ("interval", {"interval_days": 3}),
        ("cyclic", {"on_days": 21, "off_days": 7}),
    ],
)
def test_create_rejects_anchor_required_schedule_without_start_date(
    db, patient, kind, recurrence
):
    med = _med(db, patient, f"NoAnchor-{kind}-{sorted(recurrence.items())}")
    with pytest.raises(sched.InvalidSchedule):
        sched.create_schedule(
            db,
            patient_id=patient["patient_id"],
            medication_id=med.id,
            schedule_type=kind,
            local_dose_times=["08:00"],
            recurrence=recurrence,
        )


@pytest.mark.parametrize("kind", ANCHOR_FREE)
def test_create_allows_phase_independent_schedule_without_start_date(db, patient, kind):
    """The exemption is deliberate and must not be tightened by accident."""
    rec = {"days": [0, 3]} if kind == "days_of_week" else None
    s = _make(
        db, patient, f"Anchorless-{kind}",
        schedule_type=kind, local_dose_times=["08:00"], recurrence=rec,
    )
    assert s.start_date is None
    assert s.status == "active"
    assert _dose_dates(s, days=7), "phase-independent schedule produced no doses"


# ── 2. Legacy NULL-anchor rows fail CLOSED, and are flagged ──────────────────


@pytest.mark.parametrize(
    "kind,recurrence",
    [("interval", {"interval_days": 2}), ("cyclic", {"on_days": 21, "off_days": 7})],
)
def test_legacy_null_anchor_row_produces_no_doses(db, patient, kind, recurrence):
    """The regression itself: forced to NULL behind the validator, as a row
    written before it existed would be. It must NOT degrade to daily."""
    s = _make(
        db, patient, f"Legacy-{kind}",
        schedule_type=kind, local_dose_times=["08:00"],
        recurrence=recurrence, start_date=dt.date(2026, 8, 3),
    )
    s.start_date = None  # simulate the pre-fix row
    db.commit()

    assert _dose_dates(s) == [], "NULL-anchor schedule degraded to dosing"
    assert sched.needs_anchor_repair(s) is True


@pytest.mark.parametrize("kind", ANCHOR_FREE)
def test_phase_independent_rows_are_not_flagged_for_repair(db, patient, kind):
    rec = {"days": [0, 3]} if kind == "days_of_week" else None
    s = _make(
        db, patient, f"NoRepair-{kind}",
        schedule_type=kind, local_dose_times=["08:00"], recurrence=rec,
    )
    assert sched.needs_anchor_repair(s) is False


# ── 3. The anchor actually drives the phase (hand-computed calendars) ────────


def test_every_two_days_from_a_past_anchor_keeps_its_phase(db, patient):
    """Anchor Mon 2026-08-03, today Wed 08-05 → even offsets from the anchor."""
    s = _make(
        db, patient, "Every2",
        schedule_type="interval", local_dose_times=["08:00"],
        recurrence={"interval_days": 2}, start_date=dt.date(2026, 8, 3),
    )
    # The horizon ends at NOW + 8d = 08-13 06:00 UTC, and each dose is at 08:00
    # local, so 08-13's dose falls just outside it. That boundary is deliberate
    # (`grace_start <= utc <= horizon_end`) and unrelated to the anchor.
    assert _dose_dates(s, days=8) == [
        dt.date(2026, 8, 5), dt.date(2026, 8, 7),
        dt.date(2026, 8, 9), dt.date(2026, 8, 11),
    ]


def test_every_two_days_from_the_opposite_phase(db, patient):
    """Same regimen anchored one day later must dose on the OTHER days. If the
    anchor were ignored, this and the test above would return the same dates —
    which is exactly what the bug did."""
    s = _make(
        db, patient, "Every2-odd",
        schedule_type="interval", local_dose_times=["08:00"],
        recurrence={"interval_days": 2}, start_date=dt.date(2026, 8, 4),
    )
    assert _dose_dates(s, days=8) == [
        dt.date(2026, 8, 6), dt.date(2026, 8, 8), dt.date(2026, 8, 10),
        dt.date(2026, 8, 12),
    ]


def test_every_three_days_keeps_its_phase(db, patient):
    s = _make(
        db, patient, "Every3",
        schedule_type="interval", local_dose_times=["08:00"],
        recurrence={"interval_days": 3}, start_date=dt.date(2026, 8, 3),
    )
    assert _dose_dates(s, days=10) == [
        dt.date(2026, 8, 6), dt.date(2026, 8, 9), dt.date(2026, 8, 12),
    ]


def test_weekly_interval_does_not_become_daily(db, patient):
    """Weekly dosing (methotrexate shape) — daily would be the fatal error."""
    s = _make(
        db, patient, "Weekly",
        schedule_type="interval", local_dose_times=["08:00"],
        recurrence={"interval_days": 7}, start_date=dt.date(2026, 8, 5),
    )
    assert _dose_dates(s, days=21) == [
        dt.date(2026, 8, 5), dt.date(2026, 8, 12), dt.date(2026, 8, 19),
    ]


def test_cyclic_21_on_7_off_rests_during_the_off_window(db, patient):
    """Anchor 2026-07-20 → on 07-20..08-09, off 08-10..08-16, on from 08-17."""
    s = _make(
        db, patient, "Cyclic21-7",
        schedule_type="cyclic", local_dose_times=["08:00"],
        recurrence={"on_days": 21, "off_days": 7}, start_date=dt.date(2026, 7, 20),
    )
    dates = set(_dose_dates(s, days=20))
    assert dt.date(2026, 8, 5) in dates
    assert dt.date(2026, 8, 9) in dates
    for off in range(10, 17):
        assert dt.date(2026, 8, off) not in dates, f"reminded during rest day 08-{off}"
    assert dt.date(2026, 8, 17) in dates  # next cycle resumes


def test_cyclic_5_on_2_off_rests(db, patient):
    s = _make(
        db, patient, "Cyclic5-2",
        schedule_type="cyclic", local_dose_times=["08:00"],
        recurrence={"on_days": 5, "off_days": 2}, start_date=dt.date(2026, 8, 3),
    )
    dates = set(_dose_dates(s, days=14))
    for on in (5, 6, 7):  # 08-03..08-07 is the ON block
        assert dt.date(2026, 8, on) in dates
    for off in (8, 9):
        assert dt.date(2026, 8, off) not in dates
    assert dt.date(2026, 8, 10) in dates  # next block


def test_days_of_week_only_matches_its_weekdays(db, patient):
    s = _make(
        db, patient, "MonThu",
        schedule_type="days_of_week", local_dose_times=["08:00"],
        recurrence={"days": [0, 3]},
    )
    for d in _dose_dates(s, days=21):
        assert d.weekday() in (0, 3), f"{d} is not Mon/Thu"


# ── 4. Anchor in the future / in the past ───────────────────────────────────


def test_future_anchor_does_not_dose_before_it_starts(db, patient):
    s = _make(
        db, patient, "FutureAnchor",
        schedule_type="interval", local_dose_times=["08:00"],
        recurrence={"interval_days": 2}, start_date=dt.date(2026, 8, 12),
    )
    dates = _dose_dates(s, days=20)
    assert dates and min(dates) == dt.date(2026, 8, 12)


def test_past_anchor_never_backfills_history(db, patient):
    s = _make(
        db, patient, "PastAnchor",
        schedule_type="interval", local_dose_times=["08:00"],
        recurrence={"interval_days": 2}, start_date=dt.date(2026, 1, 1),
    )
    dates = _dose_dates(s, days=10)
    assert dates and min(dates) >= TODAY, "materialized a dose in the past"


def test_end_date_bounds_the_cycle(db, patient):
    s = _make(
        db, patient, "Bounded",
        schedule_type="interval", local_dose_times=["08:00"],
        recurrence={"interval_days": 2},
        start_date=dt.date(2026, 8, 3), end_date=dt.date(2026, 8, 9),
    )
    assert max(_dose_dates(s, days=30)) <= dt.date(2026, 8, 9)


# ── 5. The anchor survives every mutation that keeps the schedule alive ──────


def test_pause_stops_dosing_but_preserves_the_anchor(db, patient):
    """Pausing must not clear the anchor: the row keeps it so the phase is intact
    if the schedule is edited back into service."""
    s = _make(
        db, patient, "PauseResume",
        schedule_type="interval", local_dose_times=["08:00"],
        recurrence={"interval_days": 2}, start_date=dt.date(2026, 8, 3),
    )
    sched.pause_schedule(db, patient_id=patient["patient_id"], schedule_id=s.id)
    db.commit()
    db.refresh(s)

    assert _dose_dates(s) == [], "paused schedule still produced doses"
    assert s.start_date == dt.date(2026, 8, 3)


def test_anchor_survives_an_edit_that_changes_only_dose_times(db, patient):
    """The edit path supersedes the row; the new version must inherit the anchor,
    or every reminder-time change would silently re-phase the cycle."""
    s = _make(
        db, patient, "EditTimes",
        schedule_type="interval", local_dose_times=["08:00"],
        recurrence={"interval_days": 2}, start_date=dt.date(2026, 8, 3),
    )
    before = _dose_dates(s, days=8)

    new = sched.edit_schedule(
        db, patient_id=patient["patient_id"], schedule_id=s.id,
        local_dose_times=["09:30"],
    )
    db.commit()
    assert new.start_date == dt.date(2026, 8, 3)
    assert _dose_dates(new, days=8) == before, "editing the time re-phased the cycle"


def test_edit_cannot_convert_an_anchorless_row_into_a_cyclic_one(db, patient):
    """A type change INTO interval/cyclic on a row that never had an anchor is the
    other way to reach the bad state, and must be refused rather than silently
    anchored to today."""
    s = _make(
        db, patient, "TypeChange",
        schedule_type="fixed_daily", local_dose_times=["08:00"],
    )
    assert s.start_date is None
    for kind, rec in (("interval", {"interval_days": 2}),
                      ("cyclic", {"on_days": 21, "off_days": 7})):
        with pytest.raises(sched.InvalidSchedule):
            sched.edit_schedule(
                db, patient_id=patient["patient_id"], schedule_id=s.id,
                schedule_type=kind, recurrence=rec,
            )
        db.rollback()


def test_stopped_schedule_produces_nothing(db, patient):
    s = _make(
        db, patient, "Stopped",
        schedule_type="cyclic", local_dose_times=["08:00"],
        recurrence={"on_days": 21, "off_days": 7}, start_date=dt.date(2026, 7, 20),
    )
    sched.stop_schedule(db, patient_id=patient["patient_id"], schedule_id=s.id)
    db.commit()
    assert _dose_dates(s) == []


# ── 6. Materialization stays idempotent for anchored schedules ──────────────


@pytest.mark.parametrize(
    "kind,recurrence",
    [("interval", {"interval_days": 2}), ("cyclic", {"on_days": 21, "off_days": 7})],
)
def test_materialization_is_idempotent_for_anchored_schedules(
    db, patient, kind, recurrence
):
    s = _make(
        db, patient, f"Idem-{kind}",
        schedule_type=kind, local_dose_times=["08:00"],
        recurrence=recurrence, start_date=dt.date(2026, 8, 3),
    )
    first = sched.materialize_due(db, s)
    db.commit()
    second = sched.materialize_due(db, s)
    db.commit()
    assert first > 0
    assert second == 0

    rows = db.execute(
        select(DoseOccurrence).where(DoseOccurrence.schedule_id == s.id)
    ).scalars().all()
    assert len({r.idempotency_key for r in rows}) == len(rows)


def test_materialization_does_not_create_doses_on_rest_days(db, patient):
    """End-to-end: the persisted DoseOccurrence rows, not just the computation."""
    s = _make(
        db, patient, "Idem-rest",
        schedule_type="cyclic", local_dose_times=["08:00"],
        recurrence={"on_days": 21, "off_days": 7}, start_date=dt.date(2026, 7, 20),
    )
    sched.materialize_due(db, s, horizon_days=20, now=NOW)
    db.commit()

    rows = db.execute(
        select(DoseOccurrence).where(DoseOccurrence.schedule_id == s.id)
    ).scalars().all()
    dates = {
        (
            r.scheduled_utc.replace(tzinfo=dt.UTC)
            if r.scheduled_utc.tzinfo is None
            else r.scheduled_utc
        ).astimezone(dt.UTC).date()
        for r in rows
    }
    assert dates, "no doses materialized at all"
    for off in range(10, 17):
        assert dt.date(2026, 8, off) not in dates, f"materialized rest-day dose 08-{off}"


def test_legacy_null_anchor_materializes_nothing(db, patient):
    s = _make(
        db, patient, "Idem-legacy",
        schedule_type="interval", local_dose_times=["08:00"],
        recurrence={"interval_days": 2}, start_date=dt.date(2026, 8, 3),
    )
    s.start_date = None
    db.commit()
    assert sched.materialize_due(db, s, now=NOW) == 0


# ── 7. DST — the anchor is a LOCAL calendar date, not a UTC instant ─────────


def test_interval_phase_is_stable_across_a_dst_transition(db, patient):
    """A timezone that observes DST must not gain or lose a dosing day when the
    offset changes: the cycle is counted in local calendar days."""
    med = _med(db, patient, "DST-interval")
    s = sched.create_schedule(
        db, patient_id=patient["patient_id"], medication_id=med.id,
        schedule_type="interval", local_dose_times=["08:00"],
        recurrence={"interval_days": 2},
        start_date=dt.date(2026, 10, 20), patient_timezone="Europe/London",
    )
    db.commit()

    # 2026-10-25 is the UK DST fallback. Span it.
    now = dt.datetime(2026, 10, 20, 6, 0, tzinfo=dt.UTC)
    occ = sched.compute_occurrences(s, horizon_days=14, now=now)
    tz = sched._tz("Europe/London")
    dates = sorted({utc.astimezone(tz).date() for utc, _ in occ})

    gaps = {(b - a).days for a, b in zip(dates, dates[1:], strict=False)}
    assert gaps == {2}, f"DST changed the cycle spacing: {dates}"
    # The local wall-clock time is 08:00 on both sides of the transition.
    local_times = {utc.astimezone(tz).strftime("%H:%M") for utc, _ in occ}
    assert local_times == {"08:00"}, local_times


# ── 8. off_days — the SAME class, reached through a different hole ──────────
#
# Found by clinical review AFTER the anchor fix. `_validate_schedule_shape` read
# `int(rec.get("off_days", 0))` and accepted 0, so `_day_applies` computed
# cycle == on and `(day - start) % on < on` was true on EVERY day: a cyclic
# schedule degraded to daily even with a perfectly good anchor. Closing only the
# anchor left the class open, which is exactly what "fix the class, not the
# instance" is meant to prevent.


@pytest.mark.parametrize("recurrence", [{"on_days": 21}, {"on_days": 21, "off_days": 0}])
def test_cyclic_without_a_rest_period_is_refused(db, patient, recurrence):
    """A cycle with no rest period is not a cycle — it is `fixed_daily`. A client
    that means daily must say so rather than describe a 21-on/0-off cycle and be
    silently agreed with."""
    med = _med(db, patient, f"NoRest-{sorted(recurrence.items())}")
    with pytest.raises(sched.InvalidSchedule):
        sched.create_schedule(
            db,
            patient_id=patient["patient_id"],
            medication_id=med.id,
            schedule_type="cyclic",
            local_dose_times=["08:00"],
            recurrence=recurrence,
            start_date=dt.date(2026, 7, 20),
        )


def test_edit_cannot_remove_the_rest_period_either(db, patient):
    s = _make(
        db, patient, "RestRemoval",
        schedule_type="cyclic", local_dose_times=["08:00"],
        recurrence={"on_days": 21, "off_days": 7}, start_date=dt.date(2026, 7, 20),
    )
    with pytest.raises(sched.InvalidSchedule):
        sched.edit_schedule(
            db, patient_id=patient["patient_id"], schedule_id=s.id,
            recurrence={"on_days": 21, "off_days": 0},
        )


def test_a_valid_cycle_still_rests(db, patient):
    """Guard against over-correcting into refusing legitimate cycles."""
    s = _make(
        db, patient, "StillRests",
        schedule_type="cyclic", local_dose_times=["08:00"],
        recurrence={"on_days": 21, "off_days": 7}, start_date=dt.date(2026, 7, 20),
    )
    dates = set(_dose_dates(s, days=20))
    assert dt.date(2026, 8, 5) in dates
    for off in range(10, 17):
        assert dt.date(2026, 8, off) not in dates


# ── 9. P1-2 — pausing must not erase real non-adherence ────────────────────
#
# Flagged by test review: the P1-2 fix (unconditional MISSED-preservation, not
# just on the edit path) shipped with NO test that discriminates it. The existing
# suite could not: `test_stopped_schedule_does_not_remind` stops the schedule
# while its dose is still within the 4h grace, so the dose is deleted either way.
#
# What was wrong: `_cancel_open_doses` hard-deleted every open dose, including
# days-old ones the sweep had not yet resolved — and the sweep only runs when the
# patient opens the app. So a patient who missed three days and then tapped
# "Tạm dừng" had that non-adherence deleted, and pause -> edit -> resume made the
# reset repeatable. A clinician reading adherence before escalating therapy would
# be acting on fabricated data.


def _overdue_dose(db, patient, name: str, hours_overdue: int = 30):
    """An active schedule with one dose materialised well past the sweep grace."""
    now = dt.datetime.now(dt.UTC)
    due = now - dt.timedelta(hours=hours_overdue)
    med = _med(db, patient, name)
    s = sched.create_schedule(
        db, patient_id=patient["patient_id"], medication_id=med.id,
        schedule_type="fixed_daily", local_dose_times=[due.strftime("%H:%M")],
        patient_timezone="UTC", start_date=due.date(), end_date=due.date(),
    )
    db.commit()
    sched.materialize_due(db, s, now=due + dt.timedelta(minutes=1))
    db.commit()
    return med, s


def _dose_states(db, schedule_id: str) -> list[str]:
    return [
        d.state
        for d in db.execute(
            select(DoseOccurrence).where(DoseOccurrence.schedule_id == schedule_id)
        ).scalars()
    ]


def test_pausing_preserves_an_overdue_dose_as_missed(db, patient):
    """The regression. Pre-fix this dose was DELETED, silently improving adherence."""
    _med, s = _overdue_dose(db, patient, "Pause-adherence")
    assert _dose_states(db, s.id), "fixture produced no dose"

    sched.pause_schedule(db, patient_id=patient["patient_id"], schedule_id=s.id)
    db.commit()

    states = _dose_states(db, s.id)
    assert states == ["missed"], f"overdue dose was not preserved as missed: {states}"


def test_stopping_preserves_an_overdue_dose_as_missed(db, patient):
    _med, s = _overdue_dose(db, patient, "Stop-adherence")
    sched.stop_schedule(db, patient_id=patient["patient_id"], schedule_id=s.id)
    db.commit()
    assert _dose_states(db, s.id) == ["missed"]


def test_a_lifecycle_exit_preserves_history_but_repudiation_purges_it(db, patient):
    """The two cases must differ. A drug the patient really stopped taking has
    real non-adherence behind it; a record marked entered_in_error does not."""
    exit_med, exit_s = _overdue_dose(db, patient, "Exit-keeps")
    medication_svc.update_medication(
        db, patient_id=patient["patient_id"], med_id=exit_med.id,
        data={"lifecycle_status": "discontinued", "status_reason": "finished course"},
        actor_user_id=patient["user_id"], actor_role="patient",
    )
    db.commit()
    assert _dose_states(db, exit_s.id) == ["missed"], "a lifecycle exit erased history"

    rep_med, rep_s = _overdue_dose(db, patient, "Repudiated-purges")
    medication_svc.update_medication(
        db, patient_id=patient["patient_id"], med_id=rep_med.id,
        data={"lifecycle_status": "entered_in_error", "status_reason": "wrong record"},
        actor_user_id=patient["user_id"], actor_role="patient",
    )
    db.commit()
    assert _dose_states(db, rep_s.id) == [], (
        "a repudiated record kept missed doses — counting non-adherence for a drug "
        "the patient was never on is as fabricated as deleting real misses"
    )


def test_a_dose_within_the_grace_window_is_not_flipped_to_missed(db, patient):
    """The other half: cancelling used cutoff=now while the sweep allows 4h, so a
    patient who took their 20:00 dose and completed the course at 20:10 had it
    marked MISSED — and, the schedule now stopped, could not correct it."""
    _med, s = _overdue_dose(db, patient, "Grace-window", hours_overdue=1)
    sched.stop_schedule(db, patient_id=patient["patient_id"], schedule_id=s.id)
    db.commit()
    assert _dose_states(db, s.id) == [], (
        "a dose still inside the 4h grace was recorded as missed"
    )
