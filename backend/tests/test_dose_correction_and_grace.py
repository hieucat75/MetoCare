"""P1-3 — a flat 4h grace, and a MISSED dose nobody could correct.

Two defects with one root: the app decided by clock alone that a dose was not
taken, and then gave the patient no way to say otherwise.

    * `_MISSED_AFTER` was 4 hours for EVERY schedule. A once-weekly GLP-1 whose
      label permits a late dose for days was marked MISSED at lunchtime on the
      day it was due, and the patient read as non-adherent for the rest of the
      week.
    * `due_doses_query` was only ever called with (pending, notified), so a
      MISSED dose appeared in no list. The client could not obtain its id, and
      the patient could not correct it. An adherence figure a patient cannot
      correct is not a measurement of the patient.

The windows here are adherence-event CLASSIFICATION windows for a tracking app.
They are not dosing advice, no clinical decision follows from the boundary, and
the correction flow records what happened while saying nothing about whether to
take a late dose.
"""

from __future__ import annotations

import datetime as dt

import pytest
from app.models.medication_schedule import DoseOccurrence
from app.services import medication as medication_svc
from app.services import medication_schedule as sched
from sqlalchemy import select

TZ = "UTC"
NOW = dt.datetime(2026, 8, 5, 12, 0, tzinfo=dt.UTC)
_OBSERVED_FROM = dt.datetime(2026, 7, 1, tzinfo=dt.UTC)


def _make(db, patient, name, **kw):
    med = medication_svc.add_medication(
        db, patient_id=patient["patient_id"], data={"name": name}, commit=True
    )
    kw.setdefault("patient_timezone", TZ)
    kw.setdefault("now", _OBSERVED_FROM)
    kw.setdefault("tracking_start_at", _OBSERVED_FROM)
    s = sched.create_schedule(
        db, patient_id=patient["patient_id"], medication_id=med.id, **kw
    )
    db.commit()
    return med, s


def _states(db, schedule_id):
    return [
        d.state
        for d in db.execute(
            select(DoseOccurrence).where(DoseOccurrence.schedule_id == schedule_id)
        ).scalars()
    ]


# ── 1. The window follows the cadence, not a constant ───────────────────────


@pytest.mark.parametrize(
    "kind,kw,hours",
    [
        ("multiple-times-daily", dict(schedule_type="fixed_daily",
                                      local_dose_times=["08:00", "20:00"]), 4),
        ("once-daily", dict(schedule_type="fixed_daily",
                            local_dose_times=["08:00"]), 12),
        ("alternate-day", dict(schedule_type="interval",
                               local_dose_times=["08:00"],
                               recurrence={"interval_days": 2},
                               start_date=dt.date(2026, 7, 1)), 24),
        ("weekly", dict(schedule_type="days_of_week",
                        local_dose_times=["08:00"],
                        recurrence={"days": [2]}), 48),
        ("cyclic", dict(schedule_type="cyclic",
                        local_dose_times=["08:00"],
                        recurrence={"on_days": 21, "off_days": 7},
                        start_date=dt.date(2026, 7, 1)), 12),
    ],
)
def test_the_grace_window_follows_the_dosing_cadence(db, patient, kind, kw, hours):
    _m, s = _make(db, patient, f"Grace-{kind}", **kw)
    assert sched.missed_after(s) == dt.timedelta(hours=hours), kind
    assert sched.grace_policy_metadata(s)["missed_after_hours"] == float(hours)


def test_a_weekly_dose_is_not_missed_four_hours_after_it_was_due(db, patient):
    """THE reproduction. Wednesday 08:00 injection, swept at 12:00 Wednesday."""
    _m, s = _make(
        db, patient, "WeeklyGLP1", schedule_type="days_of_week",
        local_dose_times=["08:00"], recurrence={"days": [2]},
        start_date=dt.date(2026, 8, 1),
    )
    sched.reconcile_period(
        db, s, period_start=dt.date(2026, 8, 5), period_end=dt.date(2026, 8, 5), now=NOW
    )
    db.commit()
    assert _states(db, s.id) == ["pending"], (
        "a weekly dose was classified MISSED four hours after its time"
    )


def test_a_weekly_dose_IS_missed_once_its_own_window_expires(db, patient):
    """The window is longer, not absent — otherwise adherence is inflated by
    doses that were simply ignored."""
    _m, s = _make(
        db, patient, "WeeklyExpires", schedule_type="days_of_week",
        local_dose_times=["08:00"], recurrence={"days": [2]},
        start_date=dt.date(2026, 8, 1),
    )
    sched.reconcile_period(
        db, s, period_start=dt.date(2026, 8, 5), period_end=dt.date(2026, 8, 5),
        now=NOW + dt.timedelta(hours=45),
    )
    db.commit()
    assert _states(db, s.id) == ["missed"]


def test_a_four_times_daily_window_never_reaches_the_next_dose(db, patient):
    """Two open doses of the same schedule cannot be told apart when one is
    finally acted on, so the window must close before the next dose is due."""
    _m, s = _make(
        db, patient, "QID", schedule_type="fixed_daily",
        local_dose_times=["06:00", "12:00", "18:00", "22:00"],
    )
    assert sched.missed_after(s) < dt.timedelta(hours=6)


def test_a_prn_schedule_can_never_be_missed(db, patient):
    _m, s = _make(db, patient, "PRN", schedule_type="prn")
    assert sched.missed_after(s) == dt.timedelta.max


def test_the_policy_is_versioned_and_surfaced(db, patient):
    """A window that changes meaning without a version is indistinguishable from
    a patient whose behaviour changed."""
    _m, s = _make(
        db, patient, "Versioned", schedule_type="fixed_daily",
        local_dose_times=["08:00"], start_date=dt.date(2026, 7, 1),
    )
    summary = sched.adherence_summary(
        db, patient_id=patient["patient_id"], schedule_id=s.id,
        period_start=dt.date(2026, 7, 1), period_end=dt.date(2026, 8, 4), now=NOW,
    )
    db.commit()
    assert summary["grace_policy"]["version"] == sched.GRACE_POLICY_VERSION
    assert summary["grace_policy"]["missed_after_hours"] == 12.0


# ── 2. Correcting a dose the clock classified ───────────────────────────────


def _one_missed(db, patient, name="Correctable"):
    _m, s = _make(
        db, patient, name, schedule_type="fixed_daily",
        local_dose_times=["08:00"], start_date=dt.date(2026, 8, 1),
        end_date=dt.date(2026, 8, 1),
    )
    sched.reconcile_period(
        db, s, period_start=dt.date(2026, 8, 1), period_end=dt.date(2026, 8, 1), now=NOW
    )
    db.commit()
    dose = db.execute(
        select(DoseOccurrence).where(DoseOccurrence.schedule_id == s.id)
    ).scalars().first()
    assert dose is not None and dose.state == "missed"
    return s, dose


def test_a_missed_dose_is_listable(db, patient):
    _s, dose = _one_missed(db, patient)
    listed = sched.list_missed_doses(db, patient_id=patient["patient_id"])
    assert [d.id for d in listed] == [dose.id]


def test_a_patient_can_record_a_dose_as_taken_late(db, patient):
    _s, dose = _one_missed(db, patient)
    corrected = sched.correct_dose(
        db, patient_id=patient["patient_id"], dose_id=dose.id, state="taken",
        reason_code="taken_late", actor_user_id="u-1", now=NOW,
    )
    db.commit()
    assert corrected.state == "taken"
    # The machine's original verdict survives beside the human's.
    assert corrected.corrected_from_state == "missed"
    assert corrected.correction_reason == "taken_late"
    assert corrected.corrected_by_actor_id == "u-1"
    assert corrected.corrected_at is not None


def test_a_correction_changes_the_adherence_figure(db, patient):
    s, dose = _one_missed(db, patient, "CorrectionCounts")
    before = sched.adherence_summary(
        db, patient_id=patient["patient_id"], schedule_id=s.id,
        period_start=dt.date(2026, 8, 1), period_end=dt.date(2026, 8, 1), now=NOW,
    )
    db.commit()
    assert before["adherence_rate"] == 0.0
    sched.correct_dose(
        db, patient_id=patient["patient_id"], dose_id=dose.id, state="taken",
        reason_code="taken_late", actor_user_id="u-1", now=NOW,
    )
    db.commit()
    after = sched.adherence_summary(
        db, patient_id=patient["patient_id"], schedule_id=s.id,
        period_start=dt.date(2026, 8, 1), period_end=dt.date(2026, 8, 1), now=NOW,
    )
    db.commit()
    assert after["adherence_rate"] == 1.0
    assert after["missed_count"] == 0


def test_a_correction_is_audited_with_actor_role_and_both_states(db, patient):
    from app.models.governance import AuditLog

    _s, dose = _one_missed(db, patient, "Audited")
    sched.correct_dose(
        db, patient_id=patient["patient_id"], dose_id=dose.id, state="skipped",
        reason_code="deliberately_skipped", actor_user_id="u-9", now=NOW,
    )
    db.commit()
    entry = db.execute(
        select(AuditLog).where(AuditLog.resource_id == dose.id)
    ).scalars().first()
    assert entry is not None, "a correction left no audit trail"
    assert entry.action == "medication_dose.correct.skipped"
    assert entry.details["from_state"] == "missed"
    assert entry.details["to_state"] == "skipped"
    assert entry.details["actor_role"] == "patient"


def test_a_second_correction_is_refused_not_silently_applied(db, patient):
    """No silent overwrite: correcting a correction would make adherence
    editable without limit."""
    _s, dose = _one_missed(db, patient, "NoDoubleCorrect")
    sched.correct_dose(
        db, patient_id=patient["patient_id"], dose_id=dose.id, state="taken",
        reason_code="taken_late", actor_user_id="u-1", now=NOW,
    )
    db.commit()
    with pytest.raises(sched.InvalidSchedule):
        sched.correct_dose(
            db, patient_id=patient["patient_id"], dose_id=dose.id, state="skipped",
            reason_code="other", actor_user_id="u-1", now=NOW,
        )
    db.rollback()


def test_only_a_missed_dose_may_be_corrected(db, patient):
    _m, s = _make(
        db, patient, "AlreadyTaken", schedule_type="fixed_daily",
        local_dose_times=["08:00"], start_date=dt.date(2026, 8, 1),
        end_date=dt.date(2026, 8, 1),
    )
    sched.reconcile_period(
        db, s, period_start=dt.date(2026, 8, 1), period_end=dt.date(2026, 8, 1),
        now=dt.datetime(2026, 8, 1, 9, tzinfo=dt.UTC),
    )
    db.commit()
    dose = db.execute(
        select(DoseOccurrence).where(DoseOccurrence.schedule_id == s.id)
    ).scalars().first()
    sched.mark_dose(db, patient_id=patient["patient_id"], dose_id=dose.id, state="taken")
    db.commit()
    with pytest.raises(sched.InvalidSchedule):
        sched.correct_dose(
            db, patient_id=patient["patient_id"], dose_id=dose.id, state="skipped",
            actor_user_id="u-1",
        )
    db.rollback()


def test_another_patient_cannot_correct_this_dose(db, patient):
    _s, dose = _one_missed(db, patient, "BolaCorrect")
    with pytest.raises(sched.ScheduleAccessDenied):
        sched.correct_dose(
            db, patient_id="someone-else", dose_id=dose.id, state="taken",
            actor_user_id="u-attacker",
        )
    db.rollback()


def test_a_role_outside_the_allow_list_is_refused(db, patient):
    """Clinician-entered correction is NOT enabled at ENG-RC. It changes a
    clinical record attributed to the patient and needs its own consent and audit
    story first; the allow-list makes widening it a deliberate, reviewable act
    rather than something that happens because a role string reached the
    service."""
    _s, dose = _one_missed(db, patient, "RoleGate")
    with pytest.raises(sched.ScheduleAccessDenied):
        sched.correct_dose(
            db, patient_id=patient["patient_id"], dose_id=dose.id, state="taken",
            actor_user_id="dr-1", actor_role="doctor",
        )
    db.rollback()


def test_an_unknown_reason_code_is_refused(db, patient):
    """The reason is a closed vocabulary. Free text here would put the patient's
    account of their own symptoms into an audit trail built to avoid PHI."""
    _s, dose = _one_missed(db, patient, "ReasonGate")
    with pytest.raises(sched.InvalidSchedule):
        sched.correct_dose(
            db, patient_id=patient["patient_id"], dose_id=dose.id, state="taken",
            reason_code="patient felt unwell and skipped it", actor_user_id="u-1",
        )
    db.rollback()


def test_a_dose_missed_under_a_stopped_schedule_is_still_correctable(db, patient):
    """The one a patient most wants to fix. `due_doses_query` excludes it by
    design — correction is a history edit, not an action list."""
    s, dose = _one_missed(db, patient, "StoppedButCorrectable")
    sched.stop_schedule(db, patient_id=patient["patient_id"], schedule_id=s.id)
    db.commit()
    listed = sched.list_missed_doses(db, patient_id=patient["patient_id"])
    assert dose.id in [d.id for d in listed]
    sched.correct_dose(
        db, patient_id=patient["patient_id"], dose_id=dose.id, state="taken",
        reason_code="taken_not_recorded", actor_user_id="u-1", now=NOW,
    )
    db.commit()
    assert db.get(DoseOccurrence, dose.id).state == "taken"


def test_a_dose_missed_before_an_edit_is_still_correctable(db, patient):
    """An edit supersedes the schedule; the dose keeps its own id and its own
    history, and the patient can still say what happened to it."""
    s, dose = _one_missed(db, patient, "EditThenCorrect")
    sched.edit_schedule(
        db, patient_id=patient["patient_id"], schedule_id=s.id,
        local_dose_times=["09:00"],
    )
    db.commit()
    sched.correct_dose(
        db, patient_id=patient["patient_id"], dose_id=dose.id, state="taken",
        reason_code="taken_late", actor_user_id="u-1", now=NOW,
    )
    db.commit()
    assert db.get(DoseOccurrence, dose.id).state == "taken"


def test_the_correction_vocabulary_carries_no_clinical_advice(db, patient):
    """Neutral by construction: the codes describe what happened, never what the
    patient should do about a late dose."""
    for code in sched._CORRECTION_REASONS:
        assert " " not in code
        for advice in ("should", "double", "skip_next", "dose_now", "take_now"):
            assert advice not in code
