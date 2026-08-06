"""P1-3 — `GET /reminders/due` must gate the ROWS IT RETURNS, not just its counter.

A `DoseOccurrence` is a materialised row. Nothing about the row says whether the
schedule that produced it, or the drug behind that schedule, is still in force.
Four conditions have to hold before it may be shown: the schedule is active, the
schedule is the current version, the medication is not soft-deleted, and the
medication is still lifecycle-active.

`deliver_due_reminders` and the dashboard each restated all four by hand. The
`/reminders/due` endpoint restated NONE of them on its `items` payload — it
called `deliver_due_reminders` for the `delivered` counter (correctly gated) and
then ran its own bare `DoseOccurrence` query for the list. So the counter said
zero while the response still listed, by name, doses for paused schedules and
for medications the patient or their doctor had discontinued. The reminder list
is the one surface whose entire job is to tell a patient what to take now.

The fix is one shared `due_doses_query()` that all three paths call, because a
four-part safety predicate restated per call site is a predicate that will be
restated incompletely again. This suite asserts the endpoint payload for every
way a dose can fall out of force, and asserts the three paths agree.
"""

from __future__ import annotations

import datetime as dt

import pytest
from app.main import app
from app.services import medication as medication_svc
from app.services import medication_schedule as sched
from app.services import patient_dashboard
from fastapi.testclient import TestClient

# The endpoint sweeps overdue doses to MISSED before it reads, so a dose must be
# recently due — not due in a fixed past month — or it legitimately drops out.
NOW = dt.datetime.now(dt.UTC)
TODAY = NOW.date()
DUE_STATES = ("pending", "notified")


def _seed_due(db, patient, name: str):
    """An active medication + schedule with one already-due materialised dose."""
    med = medication_svc.add_medication(
        db, patient_id=patient["patient_id"], data={"name": name}, commit=True
    )
    s = sched.create_schedule(
        db,
        patient_id=patient["patient_id"],
        medication_id=med.id,
        schedule_type="fixed_daily",
        # A minute ago, in UTC, so the dose is due but not yet sweepable.
        local_dose_times=[(NOW - dt.timedelta(minutes=1)).strftime("%H:%M")],
        patient_timezone="UTC",
        start_date=TODAY,
        end_date=TODAY,
    )
    db.commit()
    sched.materialize_due(db, s, now=NOW)
    db.commit()
    return med, s


def _visible(db, patient) -> list[str]:
    """Dose ids the shared predicate considers showable."""
    return [
        d.id
        for d in db.execute(
            sched.due_doses_query(
                patient_id=patient["patient_id"], now=NOW, states=DUE_STATES
            )
        ).scalars()
    ]


def _endpoint_items(patient) -> list[dict]:
    with TestClient(app) as client:
        r = client.get(
            f"/api/v1/patients/{patient['patient_id']}/reminders/due",
            headers=patient["headers"],
        )
    assert r.status_code == 200, r.text
    return r.json()["items"]


# ── 1. A dose in force IS returned (the suite would pass vacuously otherwise) ──


def test_an_in_force_dose_is_returned(db, patient):
    _med, s = _seed_due(db, patient, "Metformin-live")
    assert _visible(db, patient), "an active, due dose was not visible at all"
    assert any(i["schedule_id"] == s.id for i in _endpoint_items(patient))


# ── 2. Every way a dose falls out of force ───────────────────────────────────


def test_paused_schedule_is_not_returned(db, patient):
    _med, s = _seed_due(db, patient, "Enalapril-paused")
    sched.pause_schedule(db, patient_id=patient["patient_id"], schedule_id=s.id)
    db.commit()

    assert _visible(db, patient) == []
    assert _endpoint_items(patient) == []


def test_stopped_schedule_is_not_returned(db, patient):
    _med, s = _seed_due(db, patient, "Enalapril-stopped")
    sched.stop_schedule(db, patient_id=patient["patient_id"], schedule_id=s.id)
    db.commit()

    assert _visible(db, patient) == []
    assert _endpoint_items(patient) == []


def test_superseded_schedules_doses_are_not_returned(db, patient):
    """An edit creates a new version; the OLD version's already-materialised
    doses outlive it and must not be shown against the superseded row."""
    _med, s = _seed_due(db, patient, "Gliclazide-edit")
    sched.edit_schedule(
        db, patient_id=patient["patient_id"], schedule_id=s.id,
        local_dose_times=["09:30"],
    )
    db.commit()

    assert s.id not in [
        i["schedule_id"] for i in _endpoint_items(patient)
    ], "a superseded schedule's dose was returned"


@pytest.mark.parametrize(
    "target,role",
    [
        ("discontinued", "patient"),
        ("on_hold", "doctor"),  # ADR-11: on_hold is reserved to the prescriber
        ("entered_in_error", "patient"),
    ],
)
def test_lifecycle_exit_removes_the_dose_from_the_payload(db, patient, target, role):
    med, _s = _seed_due(db, patient, f"Lifecycle-{target}")
    medication_svc.update_medication(
        db,
        patient_id=patient["patient_id"],
        med_id=med.id,
        data={"lifecycle_status": target, "status_reason": "test"},
        actor_user_id=patient["user_id"],
        actor_role=role,
    )
    db.commit()

    assert _visible(db, patient) == []
    assert _endpoint_items(patient) == []


def test_soft_deleted_medication_is_not_returned(db, patient):
    med, _s = _seed_due(db, patient, "Deleted-med")
    medication_svc.delete_medication(
        db,
        patient_id=patient["patient_id"],
        med_id=med.id,
        actor_user_id=patient["user_id"],
        actor_role="patient",
    )
    db.commit()

    assert _visible(db, patient) == []
    assert _endpoint_items(patient) == []


# ── 3. LEGACY rows — the cases the write-path cancel does NOT cover ──────────
#
# Every test above goes through a write path (pause / stop / edit / lifecycle
# exit) that ALSO cancels the schedule's open doses, so the row is gone before
# any read runs and the ungated query could not have leaked it. Those tests
# characterise the behaviour; they do not discriminate the fix.
#
# These do. They mutate the row directly, exactly as a row written before those
# cancel paths existed already looks in the database — the same legacy-row
# argument that `reconcile_schedules_with_medication_state` exists for. Against
# the ungated query these FAIL: the endpoint returns a dose for a paused or
# superseded schedule. This is the actual residual exposure P1-3 closes.


def test_legacy_paused_schedule_with_uncancelled_doses_is_not_returned(db, patient):
    _med, s = _seed_due(db, patient, "Legacy-paused")
    s.status = "paused"  # as a pre-cancel-path row already looks on disk
    db.commit()

    assert _visible(db, patient) == []
    assert _endpoint_items(patient) == [], "ungated read returned a paused dose"


def test_legacy_superseded_schedule_with_uncancelled_doses_is_not_returned(db, patient):
    _med, s = _seed_due(db, patient, "Legacy-superseded")
    other_med, other_s = _seed_due(db, patient, "Legacy-successor")
    s.superseded_by = other_s.id  # superseded but still status=active
    db.commit()

    returned = {i["schedule_id"] for i in _endpoint_items(patient)}
    assert s.id not in returned, "ungated read returned a superseded schedule's dose"
    assert other_s.id in returned, "the current version stopped being visible"
    assert other_med is not None


def test_legacy_row_for_a_retired_medication_is_not_returned(db, patient):
    """`reconcile` repairs this one before the read — pinned so that the repair
    and the read predicate cannot disagree about what "retired" means."""
    med, _s = _seed_due(db, patient, "Legacy-retired")
    med.lifecycle_status = "discontinued"
    db.commit()

    assert _visible(db, patient) == []
    assert _endpoint_items(patient) == []


# ── 4. The three read paths must agree ───────────────────────────────────────


def test_endpoint_dashboard_and_predicate_agree(db, patient):
    """The class property. These three drifted apart once already — the endpoint
    was the one that had lost every gate."""
    _live_med, live_s = _seed_due(db, patient, "Agree-live")
    _dead_med, dead_s = _seed_due(db, patient, "Agree-paused")
    sched.pause_schedule(db, patient_id=patient["patient_id"], schedule_id=dead_s.id)
    db.commit()

    predicate = set(_visible(db, patient))
    items = _endpoint_items(patient)
    endpoint = {i["id"] for i in items}
    dash = patient_dashboard.build_dashboard(db, patient_id=patient["patient_id"])
    dashboard = {d["dose_id"] for d in dash["doses_due"]}

    assert predicate == endpoint == dashboard, (
        f"paths disagree: predicate={predicate} endpoint={endpoint} dash={dashboard}"
    )
    assert any(i["schedule_id"] == live_s.id for i in items)
    assert dead_s.id not in {i["schedule_id"] for i in items}
