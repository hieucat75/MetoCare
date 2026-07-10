"""Clinic SaaS C1 M08 — Check-in & Queue.

Covers `docs/clinic-saas/M08_IMPLEMENTATION_PLAN.md` §7's full matrix:
cross-clinic IDOR, cross-branch scoping, full role matrix (Accountant 403,
CC read-yes/mutate-no), doctor row-scoping, duplicate sequential +
concurrent check-in (unique appointment_id), concurrent queue-number
allocation + all three reset scopes, duplicate active patient entry
(partial index), invalid appointment states, check-in window, walk-in
(happy/unlinked/inactive-service/RBAC/overlap-skip), full queue transition
matrix + missed-call cap, two-staff same-entry races (conditional-UPDATE
loser 409), priority (reason required, PHI-free audit, ordering), masked
display endpoint, revoked membership, multi-clinic scoping, feature-flag
503, audit tenant isolation + PHI-free details + denial durability.
"""

from __future__ import annotations

import datetime as dt
import json
import os

import pytest
from app.core.security import create_access_token
from app.models.care import Clinic, Doctor
from app.models.clinic import (
    ClinicAppointment,
    ClinicMembership,
    ClinicQueueCounter,
    ClinicQueueEntry,
)
from app.models.user import User, UserRole
from app.services import clinic_queue as queue_service

API = "/api/v1"


def _make_user(db, *, role: UserRole = UserRole.CLINIC_ADMIN) -> dict:
    user = User(
        email=f"m08-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=role,
        full_name="M08 Test User",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role=role.value, mfa=True)
    return {"user_id": user.id, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def owner(db):
    return _make_user(db)


def _create_clinic(client, owner, name: str | None = None) -> dict:
    resp = client.post(
        f"{API}/clinics",
        json={"name": name or f"Phòng khám M08 {os.urandom(3).hex()}"},
        headers=owner["headers"],
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _add_membership(
    db,
    *,
    user_id: str,
    clinic_id: str,
    roles: list[str],
    status: str = "active",
    branch_ids: list[str] | None = None,
    doctor_profile_id: str | None = None,
) -> ClinicMembership:
    m = ClinicMembership(
        user_id=user_id,
        clinic_id=clinic_id,
        roles=roles,
        branch_ids=branch_ids or [],
        status=status,
        doctor_profile_id=doctor_profile_id,
    )
    db.add(m)
    db.commit()
    return m


def _member(db, clinic_id: str, roles: list[str], *, branch_ids: list[str] | None = None) -> dict:
    user = _make_user(db, role=UserRole.CLINIC_ADMIN)
    _add_membership(
        db, user_id=user["user_id"], clinic_id=clinic_id, roles=roles, branch_ids=branch_ids
    )
    return user


def _doctor_with_membership(
    db,
    clinic_id: str,
    *,
    branch_ids: list[str] | None = None,
    roles: list[str] | None = None,
) -> dict:
    doctor_profile = Doctor(full_name=f"BS {os.urandom(3).hex()}")
    db.add(doctor_profile)
    db.commit()
    doctor_user = User(
        email=f"m08-doc-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="Doctor Membership User",
    )
    db.add(doctor_user)
    db.commit()
    _add_membership(
        db,
        user_id=doctor_user.id,
        clinic_id=clinic_id,
        roles=roles or ["doctor"],
        branch_ids=branch_ids,
        doctor_profile_id=doctor_profile.id,
    )
    token = create_access_token(subject=doctor_user.id, role="doctor", mfa=True)
    return {
        "user_id": doctor_user.id,
        "doctor_id": doctor_profile.id,
        "headers": {"Authorization": f"Bearer {token}"},
    }


def _create_branch(client, headers, clinic_id, *, name: str | None = None) -> dict:
    resp = client.post(
        f"{API}/clinics/{clinic_id}/branches",
        json={"name": name or f"Chi nhánh {os.urandom(3).hex()}", "working_hours": {}},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_service(client, headers, clinic_id, **overrides) -> dict:
    payload = {
        "name": f"Khám {os.urandom(3).hex()}",
        "code": f"SVC-{os.urandom(4).hex().upper()}",
        "specialty": "Nội tiết",
        "duration_minutes": 30,
        "price": 300000,
    }
    payload.update(overrides)
    resp = client.post(f"{API}/clinics/{clinic_id}/services", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _random_phone() -> str:
    return "090" + "".join(str(b % 10) for b in os.urandom(7))


def _create_patient(client, headers, clinic_id, *, full_name: str | None = None) -> dict:
    resp = client.post(
        f"{API}/clinics/{clinic_id}/patients",
        json={
            "full_name": full_name or "Bệnh nhân M08",
            "phone": _random_phone(),
            "dob": "1990-01-01",
            "gender": "female",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _soon(*, hours: int = 2, minutes: int = 0) -> dt.datetime:
    """Inside the default 12h check-in window (ADR-3); working_hours={} in
    every scaffold branch, so any wall-clock time is bookable."""
    return dt.datetime.utcnow() + dt.timedelta(hours=hours, minutes=minutes)


def _scaffold(client, owner):
    clinic = _create_clinic(client, owner)
    headers = {**owner["headers"], "X-Clinic-Id": clinic["id"]}
    branch = _create_branch(client, headers, clinic["id"])
    service = _create_service(client, headers, clinic["id"])
    patient = _create_patient(client, headers, clinic["id"])
    return {
        "clinic": clinic,
        "headers": headers,
        "branch": branch,
        "service": service,
        "patient": patient,
    }


def _create_appointment(
    client,
    scaffold,
    *,
    patient_id: str | None = None,
    doctor_id: str | None = None,
    branch_id: str | None = None,
    start_time: dt.datetime | None = None,
) -> dict:
    resp = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments",
        json={
            "branch_id": branch_id or scaffold["branch"]["id"],
            "patient_id": patient_id or scaffold["patient"]["patient_id"],
            "doctor_id": doctor_id,
            "service_id": scaffold["service"]["id"],
            "start_time": (start_time or _soon()).isoformat(),
        },
        headers=scaffold["headers"],
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _check_in(client, scaffold, appointment_id: str, *, headers=None):
    return client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments/{appointment_id}/check-in",
        headers=headers or scaffold["headers"],
    )


def _checked_in_entry(client, scaffold, **appointment_kwargs) -> dict:
    appt = _create_appointment(client, scaffold, **appointment_kwargs)
    resp = _check_in(client, scaffold, appt["id"])
    assert resp.status_code == 201, resp.text
    return resp.json()


def _entry_action(client, scaffold, entry_id: str, action: str, *, headers=None, json_body=None):
    return client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/queue/{entry_id}/{action}",
        json=json_body,
        headers=headers or scaffold["headers"],
    )


def _set_queue_config(db, clinic_id: str, config: dict) -> None:
    clinic = db.get(Clinic, clinic_id)
    clinic.queue_config = config
    db.commit()


def _appointment_status(db, appointment_id: str) -> str:
    db.expire_all()
    return db.get(ClinicAppointment, appointment_id).status


# ---------------------------------------------------------------------------
# Feature flag off (§7 item 17)
# ---------------------------------------------------------------------------


def test_clinic_saas_disabled_returns_503(client, owner, monkeypatch):
    scaffold = _scaffold(client, owner)
    appt = _create_appointment(client, scaffold)
    monkeypatch.setenv("FEATURE_CLINIC_SAAS", "false")
    assert (
        client.get(
            f"{API}/clinics/{scaffold['clinic']['id']}/queue", headers=scaffold["headers"]
        ).status_code
        == 503
    )
    assert _check_in(client, scaffold, appt["id"]).status_code == 503


# ---------------------------------------------------------------------------
# Check-in happy paths + appointment chain (items 5, 8)
# ---------------------------------------------------------------------------


def test_check_in_from_pending_creates_entry_and_chains_appointment(client, owner, db):
    scaffold = _scaffold(client, owner)
    appt = _create_appointment(client, scaffold)
    resp = _check_in(client, scaffold, appt["id"])
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "waiting"
    assert body["queue_number"] == 1
    assert body["source"] == "scheduled"
    assert body["appointment_id"] == appt["id"]
    assert body["patient_display_name"] == "Bệnh nhân M08"
    assert body["service_name"] == scaffold["service"]["name"]
    assert body["missed_call_count"] == 0
    assert body["requires_reception_action"] is False
    assert body["waiting_minutes"] >= 0
    assert _appointment_status(db, appt["id"]) == "in_queue"


def test_check_in_from_confirmed_and_from_arrived_override(client, owner, db):
    scaffold = _scaffold(client, owner)
    confirmed = _create_appointment(client, scaffold)
    assert (
        client.post(
            f"{API}/clinics/{scaffold['clinic']['id']}/appointments/{confirmed['id']}/confirm",
            headers=scaffold["headers"],
        ).status_code
        == 200
    )
    resp = _check_in(client, scaffold, confirmed["id"])
    assert resp.status_code == 201, resp.text
    # Free the active-patient slot for the second patient path below.
    assert (
        _entry_action(client, scaffold, resp.json()["id"], "leave").status_code == 200
    )

    # no_show -> arrived (M07 reception override) -> check-in from `arrived`.
    patient2 = _create_patient(client, scaffold["headers"], scaffold["clinic"]["id"])
    appt2 = _create_appointment(
        client, scaffold, patient_id=patient2["patient_id"], start_time=_soon(hours=3)
    )
    base = f"{API}/clinics/{scaffold['clinic']['id']}/appointments/{appt2['id']}"
    assert client.post(f"{base}/confirm", headers=scaffold["headers"]).status_code == 200
    assert (
        client.post(
            f"{base}/no-show", json={"reason": "Không đến"}, headers=scaffold["headers"]
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"{base}/arrived-override", json={"reason": "Đến muộn"}, headers=scaffold["headers"]
        ).status_code
        == 200
    )
    late = _check_in(client, scaffold, appt2["id"])
    assert late.status_code == 201, late.text
    assert _appointment_status(db, appt2["id"]) == "in_queue"


@pytest.mark.parametrize("forced_status", ["cancelled", "completed", "no_show", "in_consultation"])
def test_check_in_invalid_appointment_states_rejected(client, owner, db, forced_status):
    scaffold = _scaffold(client, owner)
    appt = _create_appointment(client, scaffold)
    row = db.get(ClinicAppointment, appt["id"])
    row.status = forced_status
    db.commit()
    resp = _check_in(client, scaffold, appt["id"])
    assert resp.status_code == 400, resp.text


def test_duplicate_sequential_check_in_rejected(client, owner):
    scaffold = _scaffold(client, owner)
    appt = _create_appointment(client, scaffold)
    assert _check_in(client, scaffold, appt["id"]).status_code == 201
    # Appointment is now in_queue — outside the check-in chain -> 400.
    again = _check_in(client, scaffold, appt["id"])
    assert again.status_code == 400, again.text


def test_concurrent_double_check_in_unique_appointment_409(client, owner, db, monkeypatch):
    """TOCTOU loser simulation (M07 race-test style): the loser read the
    appointment before the winner committed, so its chain check passes —
    unique(appointment_id) must turn the duplicate INSERT into a controlled
    409, and the rollback must leave the appointment NOT double-transitioned."""
    scaffold = _scaffold(client, owner)
    appt = _create_appointment(client, scaffold)
    assert _check_in(client, scaffold, appt["id"]).status_code == 201

    # Simulate the loser having passed every status validation on its stale
    # pre-commit read: the winner's `in_queue` becomes a valid no-op chain
    # entry, so this request reaches the entry INSERT — where the DB unique
    # index must be the real safety net.
    monkeypatch.setitem(queue_service._CHECKIN_CHAIN, "in_queue", ())
    loser = _check_in(client, scaffold, appt["id"])
    assert loser.status_code == 409, loser.text
    assert _appointment_status(db, appt["id"]) == "in_queue"
    assert (
        db.query(ClinicQueueEntry).filter_by(appointment_id=appt["id"]).count() == 1
    )


# ---------------------------------------------------------------------------
# Duplicate active patient entry — partial index (item 7)
# ---------------------------------------------------------------------------


def test_second_active_entry_for_same_patient_409_then_allowed_after_terminal(
    client, owner, db
):
    scaffold = _scaffold(client, owner)
    entry1 = _checked_in_entry(client, scaffold)
    appt2 = _create_appointment(client, scaffold, start_time=_soon(hours=3))

    blocked = _check_in(client, scaffold, appt2["id"])
    assert blocked.status_code == 409, blocked.text
    # The whole loser tx rolled back — appointment2 was not advanced.
    assert _appointment_status(db, appt2["id"]) == "pending"

    assert _entry_action(client, scaffold, entry1["id"], "leave").status_code == 200
    allowed = _check_in(client, scaffold, appt2["id"])
    assert allowed.status_code == 201, allowed.text


# ---------------------------------------------------------------------------
# Check-in window (item 9)
# ---------------------------------------------------------------------------


def test_check_in_window_too_early_rejected(client, owner):
    scaffold = _scaffold(client, owner)
    appt = _create_appointment(client, scaffold, start_time=_soon(hours=72))
    resp = _check_in(client, scaffold, appt["id"])
    assert resp.status_code == 400, resp.text


def test_check_in_window_too_late_rejected(client, owner, db):
    scaffold = _scaffold(client, owner)
    appt = _create_appointment(client, scaffold)
    row = db.get(ClinicAppointment, appt["id"])
    row.start_time = dt.datetime.utcnow() - dt.timedelta(hours=13)
    db.commit()
    resp = _check_in(client, scaffold, appt["id"])
    assert resp.status_code == 400, resp.text


def test_check_in_window_boundary_inside_succeeds(client, owner):
    scaffold = _scaffold(client, owner)
    appt = _create_appointment(client, scaffold, start_time=_soon(hours=11))
    resp = _check_in(client, scaffold, appt["id"])
    assert resp.status_code == 201, resp.text


def test_arrived_override_exempt_from_window(client, owner, db):
    """Regression (self-review fix): a >window late arrival that reception
    explicitly no-show -> arrived-overrode (M07, reason required) must be
    able to check in — re-applying the window from `arrived` would dead-end
    the exact late-arrival path the window error message points at."""
    scaffold = _scaffold(client, owner)
    appt = _create_appointment(client, scaffold)
    base = f"{API}/clinics/{scaffold['clinic']['id']}/appointments/{appt['id']}"
    assert client.post(f"{base}/confirm", headers=scaffold["headers"]).status_code == 200
    assert (
        client.post(
            f"{base}/no-show", json={"reason": "Không đến"}, headers=scaffold["headers"]
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"{base}/arrived-override", json={"reason": "Đến rất muộn"}, headers=scaffold["headers"]
        ).status_code
        == 200
    )
    row = db.get(ClinicAppointment, appt["id"])
    row.start_time = dt.datetime.utcnow() - dt.timedelta(hours=20)
    db.commit()
    resp = _check_in(client, scaffold, appt["id"])
    assert resp.status_code == 201, resp.text
    assert _appointment_status(db, appt["id"]) == "in_queue"


# ---------------------------------------------------------------------------
# Queue numbers + reset scopes + counter race (item 6)
# ---------------------------------------------------------------------------


def test_sequential_numbers_same_branch_day(client, owner):
    scaffold = _scaffold(client, owner)
    entry1 = _checked_in_entry(client, scaffold)
    patient2 = _create_patient(client, scaffold["headers"], scaffold["clinic"]["id"])
    entry2 = _checked_in_entry(
        client, scaffold, patient_id=patient2["patient_id"], start_time=_soon(hours=3)
    )
    assert entry1["queue_number"] == 1
    assert entry2["queue_number"] == 2


def test_branch_day_scope_resets_per_branch(client, owner):
    scaffold = _scaffold(client, owner)
    entry1 = _checked_in_entry(client, scaffold)
    branch2 = _create_branch(client, scaffold["headers"], scaffold["clinic"]["id"])
    patient2 = _create_patient(client, scaffold["headers"], scaffold["clinic"]["id"])
    entry2 = _checked_in_entry(
        client,
        scaffold,
        patient_id=patient2["patient_id"],
        branch_id=branch2["id"],
        start_time=_soon(hours=3),
    )
    assert entry1["queue_number"] == 1
    assert entry2["queue_number"] == 1  # independent per-branch counters


def test_clinic_day_scope_shares_counter_across_branches(client, owner, db):
    scaffold = _scaffold(client, owner)
    _set_queue_config(db, scaffold["clinic"]["id"], {"number_reset_scope": "clinic_day"})
    entry1 = _checked_in_entry(client, scaffold)
    branch2 = _create_branch(client, scaffold["headers"], scaffold["clinic"]["id"])
    patient2 = _create_patient(client, scaffold["headers"], scaffold["clinic"]["id"])
    entry2 = _checked_in_entry(
        client,
        scaffold,
        patient_id=patient2["patient_id"],
        branch_id=branch2["id"],
        start_time=_soon(hours=3),
    )
    assert entry1["queue_number"] == 1
    assert entry2["queue_number"] == 2  # clinic-wide continuous numbering


def test_branch_doctor_day_scope_resets_per_doctor(client, owner, db):
    scaffold = _scaffold(client, owner)
    _set_queue_config(db, scaffold["clinic"]["id"], {"number_reset_scope": "branch_doctor_day"})
    doctor_a = _doctor_with_membership(db, scaffold["clinic"]["id"])
    doctor_b = _doctor_with_membership(db, scaffold["clinic"]["id"])

    entry1 = _checked_in_entry(client, scaffold, doctor_id=doctor_a["doctor_id"])
    patient2 = _create_patient(client, scaffold["headers"], scaffold["clinic"]["id"])
    entry2 = _checked_in_entry(
        client,
        scaffold,
        patient_id=patient2["patient_id"],
        doctor_id=doctor_b["doctor_id"],
        start_time=_soon(hours=3),
    )
    patient3 = _create_patient(client, scaffold["headers"], scaffold["clinic"]["id"])
    entry3 = _checked_in_entry(
        client,
        scaffold,
        patient_id=patient3["patient_id"],
        doctor_id=doctor_a["doctor_id"],
        start_time=_soon(hours=4),
    )
    assert entry1["queue_number"] == 1
    assert entry2["queue_number"] == 1  # doctor B's own counter
    assert entry3["queue_number"] == 2  # doctor A continues


def test_counter_first_insert_race_savepoint_retry(client, owner, db, monkeypatch):
    """Simulates losing the first-insert-of-the-day race: the fake insert
    plants the counter row (the concurrent winner's) and reports failure —
    allocation must retry the UPDATE and hand out 2, never a duplicate 1
    and never a 500."""
    scaffold = _scaffold(client, owner)

    def losing_insert(db_, *, clinic_id, branch_id, scope_key, counter_date):
        db_.add(
            ClinicQueueCounter(
                clinic_id=clinic_id,
                branch_id=branch_id,
                scope_key=scope_key,
                counter_date=counter_date,
                last_number=1,
            )
        )
        db_.flush()
        return False

    monkeypatch.setattr(queue_service, "_insert_counter_row", losing_insert)
    entry = _checked_in_entry(client, scaffold)
    assert entry["queue_number"] == 2


# ---------------------------------------------------------------------------
# Walk-in (item 10)
# ---------------------------------------------------------------------------


def test_walk_in_happy_path_creates_appointment_and_entry(client, owner, db):
    scaffold = _scaffold(client, owner)
    resp = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/queue/walk-in",
        json={
            "branch_id": scaffold["branch"]["id"],
            "patient_id": scaffold["patient"]["patient_id"],
            "service_id": scaffold["service"]["id"],
        },
        headers=scaffold["headers"],
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["source"] == "walk_in"
    assert body["queue_number"] == 1
    appointment = db.get(ClinicAppointment, body["appointment_id"])
    assert appointment.created_by_source == "walk_in"
    assert appointment.status == "in_queue"


def test_walk_in_unlinked_patient_rejected(client, owner):
    scaffold_a = _scaffold(client, owner)
    scaffold_b = _scaffold(client, owner)
    resp = client.post(
        f"{API}/clinics/{scaffold_a['clinic']['id']}/queue/walk-in",
        json={
            "branch_id": scaffold_a["branch"]["id"],
            # Cross-clinic patient — no active relationship with clinic A.
            "patient_id": scaffold_b["patient"]["patient_id"],
            "service_id": scaffold_a["service"]["id"],
        },
        headers=scaffold_a["headers"],
    )
    assert resp.status_code == 400, resp.text


def test_walk_in_inactive_service_rejected(client, owner):
    scaffold = _scaffold(client, owner)
    assert (
        client.patch(
            f"{API}/clinics/{scaffold['clinic']['id']}/services/{scaffold['service']['id']}",
            json={"status": "inactive"},
            headers=scaffold["headers"],
        ).status_code
        == 200
    )
    resp = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/queue/walk-in",
        json={
            "branch_id": scaffold["branch"]["id"],
            "patient_id": scaffold["patient"]["patient_id"],
            "service_id": scaffold["service"]["id"],
        },
        headers=scaffold["headers"],
    )
    assert resp.status_code == 400, resp.text


def test_walk_in_skips_overlap_precheck(client, owner, db):
    """ADR-4: a booked slot covering "now" must not block an immediate
    walk-in arrival for the same doctor."""
    scaffold = _scaffold(client, owner)
    doctor = _doctor_with_membership(db, scaffold["clinic"]["id"])
    # Scheduled appointment spanning now for this doctor (30-min service).
    _create_appointment(
        client,
        scaffold,
        doctor_id=doctor["doctor_id"],
        start_time=dt.datetime.utcnow() - dt.timedelta(minutes=5),
    )
    patient2 = _create_patient(client, scaffold["headers"], scaffold["clinic"]["id"])
    resp = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/queue/walk-in",
        json={
            "branch_id": scaffold["branch"]["id"],
            "patient_id": patient2["patient_id"],
            "service_id": scaffold["service"]["id"],
            "doctor_id": doctor["doctor_id"],
        },
        headers=scaffold["headers"],
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.parametrize("roles,expected", [(["nurse"], 201), (["receptionist"], 201),
                                            (["care_coordinator"], 403), (["accountant"], 403)])
def test_walk_in_role_matrix(client, owner, db, roles, expected):
    scaffold = _scaffold(client, owner)
    member = _member(db, scaffold["clinic"]["id"], roles)
    resp = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/queue/walk-in",
        json={
            "branch_id": scaffold["branch"]["id"],
            "patient_id": scaffold["patient"]["patient_id"],
            "service_id": scaffold["service"]["id"],
        },
        headers={**member["headers"], "X-Clinic-Id": scaffold["clinic"]["id"]},
    )
    assert resp.status_code == expected, resp.text


def test_doctor_cannot_walk_in(client, owner, db):
    scaffold = _scaffold(client, owner)
    doctor = _doctor_with_membership(db, scaffold["clinic"]["id"])
    resp = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/queue/walk-in",
        json={
            "branch_id": scaffold["branch"]["id"],
            "patient_id": scaffold["patient"]["patient_id"],
            "service_id": scaffold["service"]["id"],
        },
        headers={**doctor["headers"], "X-Clinic-Id": scaffold["clinic"]["id"]},
    )
    assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# Queue transition matrix (item 11) + appointment sync
# ---------------------------------------------------------------------------


def test_full_valid_transition_path_with_appointment_sync(client, owner, db):
    scaffold = _scaffold(client, owner)
    entry = _checked_in_entry(client, scaffold)

    called = _entry_action(client, scaffold, entry["id"], "call")
    assert called.status_code == 200, called.text
    assert called.json()["status"] == "called"
    assert called.json()["called_at"] is not None

    started = _entry_action(client, scaffold, entry["id"], "start-consultation")
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "in_consultation"
    assert started.json()["consultation_started_at"] is not None
    assert _appointment_status(db, entry["appointment_id"]) == "in_consultation"

    completed = _entry_action(client, scaffold, entry["id"], "complete")
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"
    assert completed.json()["completed_at"] is not None
    assert _appointment_status(db, entry["appointment_id"]) == "completed"


def test_missed_call_returns_to_waiting_and_increments(client, owner, db):
    scaffold = _scaffold(client, owner)
    entry = _checked_in_entry(client, scaffold)
    assert _entry_action(client, scaffold, entry["id"], "call").status_code == 200
    missed = _entry_action(client, scaffold, entry["id"], "missed-call")
    assert missed.status_code == 200, missed.text
    body = missed.json()
    assert body["status"] == "waiting"
    assert body["missed_call_count"] == 1
    # Appointment untouched by call/missed-call (queue-only edges).
    assert _appointment_status(db, entry["appointment_id"]) == "in_queue"


def test_missed_call_cap_blocks_doctor_but_not_reception(client, owner, db):
    scaffold = _scaffold(client, owner)
    doctor = _doctor_with_membership(db, scaffold["clinic"]["id"])
    entry = _checked_in_entry(client, scaffold, doctor_id=doctor["doctor_id"])
    doctor_headers = {**doctor["headers"], "X-Clinic-Id": scaffold["clinic"]["id"]}

    for i in range(3):  # default max_missed_calls = 3
        assert (
            _entry_action(client, scaffold, entry["id"], "call", headers=doctor_headers).status_code
            == 200
        ), f"call {i}"
        missed = _entry_action(client, scaffold, entry["id"], "missed-call", headers=doctor_headers)
        assert missed.status_code == 200, missed.text
    assert missed.json()["missed_call_count"] == 3
    assert missed.json()["requires_reception_action"] is True

    # BR-M08-04: over the cap, the doctor can no longer call...
    over_cap = _entry_action(client, scaffold, entry["id"], "call", headers=doctor_headers)
    assert over_cap.status_code == 403, over_cap.text
    # ...but reception-side roles still can — their resolution paths are
    # "call again" or "leave". A further missed-call increment past the cap
    # is a hard 400 for EVERYONE (Codex M08 R1 P1: the cap was previously
    # only a doctor-call gate, so call->missed cycles could grow the count
    # unboundedly past the configured max).
    reception_call = _entry_action(client, scaffold, entry["id"], "call")
    assert reception_call.status_code == 200, reception_call.text
    capped = _entry_action(client, scaffold, entry["id"], "missed-call")
    assert capped.status_code == 400, capped.text
    assert _entry_action(client, scaffold, entry["id"], "leave").status_code == 200
    # Count never exceeded the cap.
    row = db.get(ClinicQueueEntry, entry["id"])
    db.refresh(row)
    assert row.missed_call_count == 3


def test_leave_terminal_and_appointment_untouched(client, owner, db):
    scaffold = _scaffold(client, owner)
    entry = _checked_in_entry(client, scaffold)
    left = _entry_action(client, scaffold, entry["id"], "leave")
    assert left.status_code == 200, left.text
    assert left.json()["status"] == "left"
    assert left.json()["left_at"] is not None
    # ADR-6: BRD §7.5 has no backward edge — the appointment stays in_queue.
    assert _appointment_status(db, entry["appointment_id"]) == "in_queue"
    # `left` is terminal at the entry level.
    assert _entry_action(client, scaffold, entry["id"], "call").status_code == 400


@pytest.mark.parametrize(
    "setup_actions,invalid_action",
    [
        ([], "missed-call"),  # waiting -> waiting invalid
        ([], "start-consultation"),  # waiting -> in_consultation invalid
        ([], "complete"),  # waiting -> completed invalid
        (["call"], "call"),  # called -> called invalid
        (["call"], "complete"),  # called -> completed invalid
        (["call", "start-consultation"], "call"),  # in_consultation -> called invalid
        (["call", "start-consultation"], "leave"),  # in_consultation -> left invalid
        (["call", "start-consultation"], "missed-call"),
        (["call", "start-consultation", "complete"], "call"),  # completed terminal
        (["call", "start-consultation", "complete"], "leave"),
        (["call", "start-consultation", "complete"], "complete"),
    ],
)
def test_invalid_queue_transitions_fail_closed(client, owner, setup_actions, invalid_action):
    scaffold = _scaffold(client, owner)
    entry = _checked_in_entry(client, scaffold)
    for action in setup_actions:
        assert _entry_action(client, scaffold, entry["id"], action).status_code == 200
    denied = _entry_action(client, scaffold, entry["id"], invalid_action)
    assert denied.status_code == 400, denied.text


def test_denied_checkin_audit_persists(client, owner, db):
    """Codex M08 R3 P1 regression: a rejected check-in (invalid appointment
    status / outside window) must leave a durable PHI-free audit row even
    though the route never commits on the error path."""
    from app.models.governance import AuditLog

    scaffold = _scaffold(client, owner)
    # Invalid status: cancel first, then attempt check-in.
    appt = _create_appointment(client, scaffold)
    base = f"{API}/clinics/{scaffold['clinic']['id']}/appointments/{appt['id']}"
    assert (
        client.post(
            f"{base}/cancel", json={"reason": "Đổi kế hoạch"}, headers=scaffold["headers"]
        ).status_code
        == 200
    )
    assert _check_in(client, scaffold, appt["id"]).status_code == 400

    # Outside window: fresh patient (active-entry index is untouched anyway).
    appt2 = _create_appointment(client, scaffold, start_time=_soon(hours=72))
    assert _check_in(client, scaffold, appt2["id"]).status_code == 400

    rows = (
        db.query(AuditLog)
        .filter_by(action="clinic_queue_checkin_denied", clinic_id=scaffold["clinic"]["id"])
        .all()
    )
    by_resource = {row.resource_id: row.details for row in rows}
    assert by_resource[appt["id"]]["reason"] == "invalid_status"
    assert by_resource[appt2["id"]]["reason"] == "outside_window"
    for details in by_resource.values():
        assert set(details) == {"reason", "appointment_status"}  # PHI-free codes only


def test_stale_appointment_transition_maps_409(client, owner, monkeypatch):
    """Codex M08 R3 P1 regression: the conditional-update stale loser is a
    conflict (409, client reloads), not a validation 400 — verified through
    both route modules' mapping."""
    from app.services.clinic_appointments import ClinicAppointmentConflictError

    scaffold = _scaffold(client, owner)
    appt = _create_appointment(client, scaffold)

    def stale_loser(*args, **kwargs):
        raise ClinicAppointmentConflictError("stale")

    import app.services.clinic_appointments as appointments_service

    monkeypatch.setattr(appointments_service, "transition_status", stale_loser)
    # M08 check-in route (chains through transition_status).
    resp = _check_in(client, scaffold, appt["id"])
    assert resp.status_code == 409, resp.text
    # M07 confirm route (confirm_appointment wraps transition_status).
    resp2 = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments/{appt['id']}/confirm",
        headers=scaffold["headers"],
    )
    assert resp2.status_code == 409, resp2.text


def test_skip_overlap_precheck_bound_to_walk_in_source(client, owner, db):
    """Codex M08 R3 P2 regression: skip_overlap_precheck must be inert for
    any non-walk_in source — a scheduled booking cannot bypass the guard."""
    from app.services import clinic_appointments as appointments_service
    from app.services.clinic_appointments import ClinicAppointmentError

    scaffold = _scaffold(client, owner)
    doctor = _doctor_with_membership(db, scaffold["clinic"]["id"])
    start = _soon(hours=2)
    _create_appointment(
        client, scaffold, doctor_id=doctor["doctor_id"], start_time=start
    )

    patient2 = _create_patient(client, scaffold["headers"], scaffold["clinic"]["id"])
    with pytest.raises(ClinicAppointmentError, match="trùng khung giờ"):
        appointments_service.create_appointment(
            db,
            clinic_id=scaffold["clinic"]["id"],
            actor_id=owner["user_id"],
            branch_id=scaffold["branch"]["id"],
            patient_id=patient2["patient_id"],
            doctor_id=doctor["doctor_id"],
            service_id=scaffold["service"]["id"],
            start_time=start + dt.timedelta(minutes=10),  # overlapping, different start
            created_by_source="reception",
            skip_overlap_precheck=True,  # must be ignored for non-walk_in
        )
    db.rollback()


def test_walkin_denial_never_persists_half_created_appointment(
    client, owner, db, monkeypatch
):
    """Codex M08 R4 P1 regression: _deny_checkin used to commit the whole
    session — a clock jump between walk-in's two utcnow() reads could land
    in the outside-window denial and persist the half-created walk-in
    appointment alongside the 400. Rollback-first now guarantees the denial
    audit is the ONLY row committed."""
    scaffold = _scaffold(client, owner)
    from app.models.governance import AuditLog

    base_now = dt.datetime.utcnow()
    calls = {"n": 0}

    def jumping_clock():
        calls["n"] += 1
        # 1st call = walk-in start_time; later calls = check-in's `now`,
        # jumped past the 12h window.
        return base_now if calls["n"] == 1 else base_now + dt.timedelta(hours=20)

    monkeypatch.setattr(queue_service, "utcnow", jumping_clock)
    resp = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/queue/walk-in",
        json={
            "branch_id": scaffold["branch"]["id"],
            "patient_id": scaffold["patient"]["patient_id"],
            "service_id": scaffold["service"]["id"],
        },
        headers=scaffold["headers"],
    )
    assert resp.status_code == 400, resp.text

    # The half-created walk-in appointment was rolled back, not committed.
    walkins = (
        db.query(ClinicAppointment)
        .filter_by(
            clinic_id=scaffold["clinic"]["id"],
            patient_id=scaffold["patient"]["patient_id"],
            created_by_source="walk_in",
        )
        .count()
    )
    assert walkins == 0
    # ...but the denial audit row IS durable.
    denial = (
        db.query(AuditLog)
        .filter_by(
            action="clinic_queue_checkin_denied", clinic_id=scaffold["clinic"]["id"]
        )
        .all()
    )
    assert len(denial) == 1
    assert denial[0].details["reason"] == "outside_window"


def test_cap_denials_are_audited(client, owner, db):
    """Codex M08 R4 P1 regression: the missed-call-cap 400 and the doctor
    over-cap-call 403 each leave a durable PHI-free denial audit row."""
    from app.models.governance import AuditLog

    scaffold = _scaffold(client, owner)
    doctor = _doctor_with_membership(db, scaffold["clinic"]["id"])
    entry = _checked_in_entry(client, scaffold, doctor_id=doctor["doctor_id"])
    for _ in range(3):
        assert _entry_action(client, scaffold, entry["id"], "call").status_code == 200
        assert _entry_action(client, scaffold, entry["id"], "missed-call").status_code == 200

    doctor_headers = {**doctor["headers"], "X-Clinic-Id": scaffold["clinic"]["id"]}
    assert (
        _entry_action(client, scaffold, entry["id"], "call", headers=doctor_headers).status_code
        == 403
    )
    assert _entry_action(client, scaffold, entry["id"], "call").status_code == 200
    assert _entry_action(client, scaffold, entry["id"], "missed-call").status_code == 400

    reasons = [
        row.details.get("reason")
        for row in db.query(AuditLog)
        .filter_by(
            action="clinic_queue_transition_denied",
            resource_id=entry["id"],
            outcome="denied",
        )
        .all()
    ]
    assert "over_missed_call_cap_doctor" in reasons
    assert "missed_call_cap" in reasons


def test_priority_rejected_on_terminal_entry_with_audit(client, owner, db):
    """Codex M08 R4 P2 regression: priority (and its free-text reason) can
    no longer be stamped onto a completed/left record; the rejection is
    audited and the conditional UPDATE repeats the active-status invariant."""
    from app.models.governance import AuditLog

    scaffold = _scaffold(client, owner)
    entry = _checked_in_entry(client, scaffold)
    assert _entry_action(client, scaffold, entry["id"], "leave").status_code == 200

    resp = _entry_action(
        client,
        scaffold,
        entry["id"],
        "priority",
        json_body={"is_priority": True, "reason": "Cao tuổi"},
    )
    assert resp.status_code == 400, resp.text
    row = db.get(ClinicQueueEntry, entry["id"])
    db.refresh(row)
    assert row.is_priority is False
    assert row.priority_reason is None
    denials = (
        db.query(AuditLog)
        .filter_by(action="clinic_queue_priority_denied", resource_id=entry["id"])
        .all()
    )
    assert len(denials) == 1
    assert denials[0].details == {"reason": "terminal_entry", "status": "left"}


def test_denied_transition_audit_row_persists(client, owner, db):
    """M07 denial-durability precedent applied to the queue machine: the
    route never commits on the error path, so the service must commit the
    denial audit itself before raising."""
    from app.models.governance import AuditLog

    scaffold = _scaffold(client, owner)
    entry = _checked_in_entry(client, scaffold)
    denied = _entry_action(client, scaffold, entry["id"], "start-consultation")
    assert denied.status_code == 400

    rows = (
        db.query(AuditLog)
        .filter_by(action="clinic_queue_transition_denied", resource_id=entry["id"])
        .all()
    )
    assert len(rows) == 1
    assert rows[0].outcome == "denied"
    assert rows[0].details == {"from": "waiting", "to": "in_consultation"}


# ---------------------------------------------------------------------------
# Two-staff same-entry races — conditional UPDATE loser (item 12)
# ---------------------------------------------------------------------------


def _install_racing_winner(monkeypatch, db, winner_status: str):
    """Between the route's read and the conditional UPDATE, a concurrent
    staff member flips the row — the loser must see rowcount == 0 -> 409."""
    from sqlalchemy import update as sa_update

    real_apply = queue_service._apply_transition

    def racing_apply(db_, *, entry_id, expected_status, values, **kwargs):
        db_.execute(
            sa_update(ClinicQueueEntry)
            .where(ClinicQueueEntry.id == entry_id)
            .values(status=winner_status),
            execution_options={"synchronize_session": False},
        )
        return real_apply(
            db_, entry_id=entry_id, expected_status=expected_status, values=values
        )

    monkeypatch.setattr(queue_service, "_apply_transition", racing_apply)


def test_call_race_loser_409(client, owner, db, monkeypatch):
    scaffold = _scaffold(client, owner)
    entry = _checked_in_entry(client, scaffold)
    _install_racing_winner(monkeypatch, db, "called")
    resp = _entry_action(client, scaffold, entry["id"], "call")
    assert resp.status_code == 409, resp.text


def test_start_consultation_race_loser_409_appointment_rolled_back(
    client, owner, db, monkeypatch
):
    scaffold = _scaffold(client, owner)
    entry = _checked_in_entry(client, scaffold)
    assert _entry_action(client, scaffold, entry["id"], "call").status_code == 200
    _install_racing_winner(monkeypatch, db, "in_consultation")
    resp = _entry_action(client, scaffold, entry["id"], "start-consultation")
    assert resp.status_code == 409, resp.text
    # The loser's appointment sync (flushed before the conditional UPDATE)
    # must roll back with the failed request — no partial state.
    assert _appointment_status(db, entry["appointment_id"]) == "in_queue"


def test_complete_race_loser_409(client, owner, db, monkeypatch):
    scaffold = _scaffold(client, owner)
    entry = _checked_in_entry(client, scaffold)
    assert _entry_action(client, scaffold, entry["id"], "call").status_code == 200
    assert _entry_action(client, scaffold, entry["id"], "start-consultation").status_code == 200
    _install_racing_winner(monkeypatch, db, "completed")
    resp = _entry_action(client, scaffold, entry["id"], "complete")
    assert resp.status_code == 409, resp.text
    assert _appointment_status(db, entry["appointment_id"]) == "in_consultation"


# ---------------------------------------------------------------------------
# Priority (item 13)
# ---------------------------------------------------------------------------


def test_priority_requires_reason_422(client, owner):
    scaffold = _scaffold(client, owner)
    entry = _checked_in_entry(client, scaffold)
    resp = _entry_action(
        client, scaffold, entry["id"], "priority", json_body={"is_priority": True}
    )
    assert resp.status_code == 422


def test_priority_sets_row_fields_audits_without_verbatim_reason_and_reorders(
    client, owner, db
):
    from app.models.governance import AuditLog

    scaffold = _scaffold(client, owner)
    entry1 = _checked_in_entry(client, scaffold)
    patient2 = _create_patient(client, scaffold["headers"], scaffold["clinic"]["id"])
    entry2 = _checked_in_entry(
        client, scaffold, patient_id=patient2["patient_id"], start_time=_soon(hours=3)
    )

    reason = "Bệnh nhân cao tuổi, hẹn trước bị trễ do phòng khám"
    resp = _entry_action(
        client,
        scaffold,
        entry2["id"],
        "priority",
        json_body={"is_priority": True, "reason": reason},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_priority"] is True
    assert resp.json()["priority_reason"] == reason

    audit_rows = (
        db.query(AuditLog)
        .filter_by(action="clinic_queue_priority", resource_id=entry2["id"])
        .all()
    )
    assert len(audit_rows) == 1
    assert audit_rows[0].details == {"from": False, "to": True, "reason_provided": True}
    assert reason not in json.dumps(audit_rows[0].details, ensure_ascii=False)

    # AC-M08-04/plan §4 ordering: priority first, then queue_number asc.
    listing = client.get(
        f"{API}/clinics/{scaffold['clinic']['id']}/queue", headers=scaffold["headers"]
    )
    assert listing.status_code == 200
    ids = [item["id"] for item in listing.json()["items"]]
    assert ids.index(entry2["id"]) < ids.index(entry1["id"])


def test_priority_whitespace_reason_422(client, owner):
    """Codex M08 R1 P1 regression: min_length alone accepted '   ' as a
    mandatory reason — the schema now strips before validating."""
    scaffold = _scaffold(client, owner)
    entry = _checked_in_entry(client, scaffold)
    resp = _entry_action(
        client,
        scaffold,
        entry["id"],
        "priority",
        json_body={"is_priority": True, "reason": "   "},
    )
    assert resp.status_code == 422, resp.text


def test_priority_race_loser_409(client, owner, db):
    """Codex M08 R1 P1 regression: priority was ORM read-modify-write — two
    racing staff silently last-write-won with stale audit from/to. Now a
    conditional UPDATE predicated on the loaded is_priority: the loser 409s."""
    from app.services.clinic_queue import ClinicQueueConflictError
    from sqlalchemy import update as sa_update

    scaffold = _scaffold(client, owner)
    entry_out = _checked_in_entry(client, scaffold)
    entry = db.get(ClinicQueueEntry, entry_out["id"])
    assert entry.is_priority is False  # loaded (stale-to-be) state

    # Concurrent "winner" flips the flag between our read and our write.
    db.execute(
        sa_update(ClinicQueueEntry)
        .where(ClinicQueueEntry.id == entry.id)
        .values(is_priority=True),
        execution_options={"synchronize_session": False},
    )
    with pytest.raises(ClinicQueueConflictError):
        queue_service.set_priority(
            db, entry=entry, actor_id=owner["user_id"], is_priority=True, reason="Cao tuổi"
        )


def test_doctor_with_extra_nonmanage_role_still_own_scoped(client, owner, db):
    """Codex M08 R1 P1 regression: a ['doctor', 'care_coordinator'] membership
    used to dodge own-entry scoping (the old exact-set `== {doctor}` test),
    letting it call/start any doctor's entry. Scoping now applies to every
    caller holding `doctor` without a manage role."""
    scaffold = _scaffold(client, owner)
    other_doctor = _doctor_with_membership(db, scaffold["clinic"]["id"])
    entry = _checked_in_entry(client, scaffold, doctor_id=other_doctor["doctor_id"])

    dcc = _doctor_with_membership(
        db, scaffold["clinic"]["id"], roles=["doctor", "care_coordinator"]
    )
    dcc_headers = {**dcc["headers"], "X-Clinic-Id": scaffold["clinic"]["id"]}

    for action in ("call", "start-consultation", "complete"):
        resp = _entry_action(client, scaffold, entry["id"], action, headers=dcc_headers)
        assert resp.status_code == 403, f"{action}: {resp.text}"

    # List is row-scoped to their own (empty) assignment set too.
    listing = client.get(
        f"{API}/clinics/{scaffold['clinic']['id']}/queue", headers=dcc_headers
    )
    assert listing.status_code == 200
    assert all(
        item["doctor_id"] == dcc["doctor_id"] for item in listing.json()["items"]
    )


def test_checkin_racing_cancel_stale_loser_controlled(client, owner, db):
    """Codex M08 R2 P1 regression: transition_status was ORM read-then-set —
    a check-in that loaded `confirmed` could overwrite a concurrently
    committed `cancelled` and attach an active queue entry to a cancelled
    appointment. The conditional UPDATE makes the stale loser fail
    controlled, with no entry created."""
    from app.services.clinic_appointments import ClinicAppointmentError
    from app.services.clinic_queue import ClinicQueueError
    from sqlalchemy import update as sa_update

    scaffold = _scaffold(client, owner)
    appt = _create_appointment(client, scaffold)
    base = f"{API}/clinics/{scaffold['clinic']['id']}/appointments/{appt['id']}"
    assert client.post(f"{base}/confirm", headers=scaffold["headers"]).status_code == 200

    stale = db.get(ClinicAppointment, appt["id"])
    assert stale.status == "confirmed"  # loaded, about-to-be-stale state

    # Concurrent cancel commits between our read and our write.
    db.execute(
        sa_update(ClinicAppointment)
        .where(ClinicAppointment.id == appt["id"])
        .values(status="cancelled"),
        execution_options={"synchronize_session": False},
    )

    clinic_row = db.get(Clinic, scaffold["clinic"]["id"])
    # Old behavior: the stale chain blindly ORM-overwrote cancelled ->
    # in_queue and created an entry. New behavior: the first conditional hop
    # (WHERE status='confirmed') sees rowcount 0 and raises, creating nothing.
    with pytest.raises((ClinicAppointmentError, ClinicQueueError)):
        queue_service.check_in_appointment(
            db, clinic=clinic_row, appointment=stale, actor_id=owner["user_id"]
        )
    db.rollback()  # discards the simulated concurrent write too (same session)
    assert db.query(ClinicQueueEntry).filter_by(appointment_id=appt["id"]).count() == 0
    db.expire_all()
    # The loser never wrote in_queue — pre-race state survives the rollback.
    assert _appointment_status(db, appt["id"]) == "confirmed"


def test_display_doctor_scoped_to_own_entries(client, owner, db):
    """Codex M08 R2 P1 regression: /display ignored the RBAC matrix's
    "Doctor (own)" row — a doctor-scoped caller now sees only their own
    entries there, same as the staff list."""
    scaffold = _scaffold(client, owner)
    doctor_a = _doctor_with_membership(db, scaffold["clinic"]["id"])
    doctor_b = _doctor_with_membership(db, scaffold["clinic"]["id"])
    entry_a = _checked_in_entry(client, scaffold, doctor_id=doctor_a["doctor_id"])
    patient2 = _create_patient(client, scaffold["headers"], scaffold["clinic"]["id"])
    _checked_in_entry(
        client,
        scaffold,
        doctor_id=doctor_b["doctor_id"],
        patient_id=patient2["patient_id"],
        start_time=_soon(hours=3),
    )

    resp = client.get(
        f"{API}/clinics/{scaffold['clinic']['id']}/queue/display",
        headers={**doctor_a["headers"], "X-Clinic-Id": scaffold["clinic"]["id"]},
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["queue_number"] == entry_a["queue_number"]
    # Owner (unrestricted) still sees both — the physical screen's session.
    full = client.get(
        f"{API}/clinics/{scaffold['clinic']['id']}/queue/display",
        headers=scaffold["headers"],
    )
    assert len(full.json()["items"]) == 2


def test_queue_config_non_dict_and_out_of_range_fail_safe(client, owner, db):
    """Codex M08 R2 P1 regression: a non-object queue_config (JSON string)
    must not 500, and out-of-range ints revert to the DEFAULT rather than
    clamping to an invented nearby value."""
    scaffold = _scaffold(client, owner)
    clinic_row = db.get(Clinic, scaffold["clinic"]["id"])
    clinic_row.queue_config = "not-a-dict"
    db.commit()
    appt = _create_appointment(client, scaffold)
    resp = _check_in(client, scaffold, appt["id"])
    assert resp.status_code == 201, resp.text

    # max_missed_calls=0 is out of range (min 1) -> default 3 applies, so a
    # first missed-call must still succeed instead of 400ing at "cap 0".
    clinic_row = db.get(Clinic, scaffold["clinic"]["id"])
    clinic_row.queue_config = {"max_missed_calls": 0}
    db.commit()
    entry_id = resp.json()["id"]
    assert _entry_action(client, scaffold, entry_id, "call").status_code == 200
    missed = _entry_action(client, scaffold, entry_id, "missed-call")
    assert missed.status_code == 200, missed.text
    assert missed.json()["missed_call_count"] == 1


def test_queue_config_garbage_values_fail_safe(client, owner, db):
    """Codex M08 R1 P1 regression: tenant-editable queue_config JSON with
    wrong types must degrade to defaults (fail-safe), never 500 a check-in."""
    scaffold = _scaffold(client, owner)
    clinic_row = db.get(Clinic, scaffold["clinic"]["id"])
    clinic_row.queue_config = {
        "max_missed_calls": "ba",
        "checkin_window_hours": None,
        "day_offset_minutes": [420],
        "number_reset_scope": "bogus_scope",
    }
    db.commit()

    appt = _create_appointment(client, scaffold)
    resp = _check_in(client, scaffold, appt["id"])
    assert resp.status_code == 201, resp.text
    assert resp.json()["queue_number"] == 1


def test_priority_forbidden_for_doctor(client, owner, db):
    scaffold = _scaffold(client, owner)
    doctor = _doctor_with_membership(db, scaffold["clinic"]["id"])
    entry = _checked_in_entry(client, scaffold, doctor_id=doctor["doctor_id"])
    resp = _entry_action(
        client,
        scaffold,
        entry["id"],
        "priority",
        json_body={"is_priority": True, "reason": "x"},
        headers={**doctor["headers"], "X-Clinic-Id": scaffold["clinic"]["id"]},
    )
    assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# List + display (items 3, 14)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "roles", [["owner"], ["admin"], ["nurse"], ["receptionist"], ["care_coordinator"]]
)
def test_read_roles_can_list_queue(client, owner, db, roles):
    scaffold = _scaffold(client, owner)
    _checked_in_entry(client, scaffold)
    member = _member(db, scaffold["clinic"]["id"], roles)
    resp = client.get(
        f"{API}/clinics/{scaffold['clinic']['id']}/queue",
        headers={**member["headers"], "X-Clinic-Id": scaffold["clinic"]["id"]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 1


def test_accountant_denied_queue_access(client, owner, db):
    scaffold = _scaffold(client, owner)
    member = _member(db, scaffold["clinic"]["id"], ["accountant"])
    headers = {**member["headers"], "X-Clinic-Id": scaffold["clinic"]["id"]}
    assert (
        client.get(f"{API}/clinics/{scaffold['clinic']['id']}/queue", headers=headers).status_code
        == 403
    )
    assert (
        client.get(
            f"{API}/clinics/{scaffold['clinic']['id']}/queue/display", headers=headers
        ).status_code
        == 403
    )


def test_care_coordinator_read_only_cannot_mutate(client, owner, db):
    scaffold = _scaffold(client, owner)
    entry = _checked_in_entry(client, scaffold)
    cc = _member(db, scaffold["clinic"]["id"], ["care_coordinator"])
    cc_headers = {**cc["headers"], "X-Clinic-Id": scaffold["clinic"]["id"]}
    for action, body in [
        ("call", None),
        ("leave", None),
        ("priority", {"is_priority": True, "reason": "x"}),
    ]:
        resp = _entry_action(
            client, scaffold, entry["id"], action, headers=cc_headers, json_body=body
        )
        assert resp.status_code == 403, f"{action}: {resp.text}"


def test_display_masks_initials_and_omits_phi(client, owner):
    scaffold = _scaffold(client, owner)
    patient = _create_patient(
        client, scaffold["headers"], scaffold["clinic"]["id"], full_name="Nguyễn Văn An"
    )
    _checked_in_entry(client, scaffold, patient_id=patient["patient_id"])
    resp = client.get(
        f"{API}/clinics/{scaffold['clinic']['id']}/queue/display", headers=scaffold["headers"]
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 1
    item = items[0]
    # AC-M08-03: exactly these fields — no service, no full name, no patient_id.
    assert set(item.keys()) == {"queue_number", "patient_initials", "status", "doctor_name"}
    assert item["patient_initials"] == "N.V.A"
    assert "Nguyễn Văn An" not in resp.text


def test_display_requires_auth(client, owner):
    scaffold = _scaffold(client, owner)
    resp = client.get(f"{API}/clinics/{scaffold['clinic']['id']}/queue/display")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Doctor row-scoping (item 4)
# ---------------------------------------------------------------------------


def test_doctor_sees_and_acts_only_on_own_entries(client, owner, db):
    scaffold = _scaffold(client, owner)
    doctor_a = _doctor_with_membership(db, scaffold["clinic"]["id"])
    doctor_b = _doctor_with_membership(db, scaffold["clinic"]["id"])
    own = _checked_in_entry(client, scaffold, doctor_id=doctor_a["doctor_id"])
    patient2 = _create_patient(client, scaffold["headers"], scaffold["clinic"]["id"])
    other = _checked_in_entry(
        client,
        scaffold,
        patient_id=patient2["patient_id"],
        doctor_id=doctor_b["doctor_id"],
        start_time=_soon(hours=3),
    )
    headers_a = {**doctor_a["headers"], "X-Clinic-Id": scaffold["clinic"]["id"]}

    listing = client.get(f"{API}/clinics/{scaffold['clinic']['id']}/queue", headers=headers_a)
    assert listing.status_code == 200
    ids = {item["id"] for item in listing.json()["items"]}
    assert own["id"] in ids
    assert other["id"] not in ids
    # A doctor-requested doctor_id filter cannot widen the scope.
    forced = client.get(
        f"{API}/clinics/{scaffold['clinic']['id']}/queue",
        params={"doctor_id": doctor_b["doctor_id"]},
        headers=headers_a,
    )
    assert {item["id"] for item in forced.json()["items"]} <= {own["id"]}

    assert (
        _entry_action(client, scaffold, other["id"], "call", headers=headers_a).status_code == 403
    )
    # Own-entry doctor flow: call -> start -> complete all allowed.
    assert _entry_action(client, scaffold, own["id"], "call", headers=headers_a).status_code == 200
    assert (
        _entry_action(
            client, scaffold, own["id"], "start-consultation", headers=headers_a
        ).status_code
        == 200
    )
    assert (
        _entry_action(client, scaffold, own["id"], "complete", headers=headers_a).status_code
        == 200
    )


def test_doctor_cannot_leave_entries(client, owner, db):
    scaffold = _scaffold(client, owner)
    doctor = _doctor_with_membership(db, scaffold["clinic"]["id"])
    entry = _checked_in_entry(client, scaffold, doctor_id=doctor["doctor_id"])
    resp = _entry_action(
        client,
        scaffold,
        entry["id"],
        "leave",
        headers={**doctor["headers"], "X-Clinic-Id": scaffold["clinic"]["id"]},
    )
    assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# Branch scoping (item 2)
# ---------------------------------------------------------------------------


def test_branch_scoped_receptionist_cannot_cross_branch(client, owner, db):
    scaffold = _scaffold(client, owner)
    branch2 = _create_branch(client, scaffold["headers"], scaffold["clinic"]["id"])
    patient2 = _create_patient(client, scaffold["headers"], scaffold["clinic"]["id"])
    appt_b2 = _create_appointment(
        client, scaffold, patient_id=patient2["patient_id"], branch_id=branch2["id"]
    )
    entry_b2 = None

    reception = _member(
        db, scaffold["clinic"]["id"], ["receptionist"], branch_ids=[scaffold["branch"]["id"]]
    )
    headers = {**reception["headers"], "X-Clinic-Id": scaffold["clinic"]["id"]}

    # Check-in at the other branch -> 403.
    assert _check_in(client, scaffold, appt_b2["id"], headers=headers).status_code == 403
    # Walk-in targeting the other branch -> 403.
    walk = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/queue/walk-in",
        json={
            "branch_id": branch2["id"],
            "patient_id": patient2["patient_id"],
            "service_id": scaffold["service"]["id"],
        },
        headers=headers,
    )
    assert walk.status_code == 403, walk.text
    # Explicit other-branch list -> 403; unfiltered defaults to own scope.
    assert (
        client.get(
            f"{API}/clinics/{scaffold['clinic']['id']}/queue",
            params={"branch_id": branch2["id"]},
            headers=headers,
        ).status_code
        == 403
    )

    # Owner checks the appointment in at branch2; the scoped receptionist
    # must neither see nor act on the resulting entry.
    entry_b2 = _check_in(client, scaffold, appt_b2["id"]).json()
    unfiltered = client.get(f"{API}/clinics/{scaffold['clinic']['id']}/queue", headers=headers)
    assert unfiltered.status_code == 200
    assert entry_b2["id"] not in {item["id"] for item in unfiltered.json()["items"]}
    assert (
        _entry_action(client, scaffold, entry_b2["id"], "call", headers=headers).status_code == 403
    )


# ---------------------------------------------------------------------------
# Cross-clinic IDOR (item 1)
# ---------------------------------------------------------------------------


def test_cross_clinic_ids_never_resolve(client, owner, db):
    scaffold_a = _scaffold(client, owner)
    scaffold_b = _scaffold(client, owner)
    appt_b = _create_appointment(client, scaffold_b)
    entry_b = _checked_in_entry(client, scaffold_b, start_time=_soon(hours=3))

    # Clinic A tenant + clinic A path, clinic B resource ids -> 404.
    assert _check_in(client, scaffold_a, appt_b["id"]).status_code == 404
    assert _entry_action(client, scaffold_a, entry_b["id"], "call").status_code == 404
    # Path/tenant mismatch -> 403 (tenant header pins clinic A).
    resp = client.get(
        f"{API}/clinics/{scaffold_b['clinic']['id']}/queue", headers=scaffold_a["headers"]
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Multi-clinic + revoked membership (items 15, 16)
# ---------------------------------------------------------------------------


def test_multi_clinic_membership_scopes_to_active_clinic(client, owner, db):
    scaffold_a = _scaffold(client, owner)
    scaffold_b = _scaffold(client, owner)
    _checked_in_entry(client, scaffold_a)
    user = _make_user(db, role=UserRole.CLINIC_ADMIN)
    _add_membership(db, user_id=user["user_id"], clinic_id=scaffold_a["clinic"]["id"], roles=["admin"])
    _add_membership(db, user_id=user["user_id"], clinic_id=scaffold_b["clinic"]["id"], roles=["admin"])

    resp_a = client.get(
        f"{API}/clinics/{scaffold_a['clinic']['id']}/queue",
        headers={**user["headers"], "X-Clinic-Id": scaffold_a["clinic"]["id"]},
    )
    resp_b = client.get(
        f"{API}/clinics/{scaffold_b['clinic']['id']}/queue",
        headers={**user["headers"], "X-Clinic-Id": scaffold_b["clinic"]["id"]},
    )
    assert resp_a.json()["total"] == 1
    assert resp_b.json()["total"] == 0


def test_revoked_membership_loses_access_immediately(client, owner, db):
    scaffold = _scaffold(client, owner)
    member = _member(db, scaffold["clinic"]["id"], ["admin"])
    headers = {**member["headers"], "X-Clinic-Id": scaffold["clinic"]["id"]}
    assert client.get(f"{API}/clinics/{scaffold['clinic']['id']}/queue", headers=headers).status_code == 200

    row = (
        db.query(ClinicMembership)
        .filter_by(user_id=member["user_id"], clinic_id=scaffold["clinic"]["id"])
        .one()
    )
    row.status = "removed"
    db.commit()
    assert client.get(f"{API}/clinics/{scaffold['clinic']['id']}/queue", headers=headers).status_code == 403


# ---------------------------------------------------------------------------
# Audit completeness + PHI-free details (item 18)
# ---------------------------------------------------------------------------


def test_audit_rows_tenant_isolated_and_phi_free(client, owner, db):
    from app.models.governance import AuditLog

    scaffold = _scaffold(client, owner)
    patient = _create_patient(
        client, scaffold["headers"], scaffold["clinic"]["id"], full_name="Trần Thị Bảo Ngọc"
    )
    entry = _checked_in_entry(client, scaffold, patient_id=patient["patient_id"])
    reason = "Lý do ưu tiên tuyệt mật có định danh bệnh nhân"
    assert (
        _entry_action(
            client,
            scaffold,
            entry["id"],
            "priority",
            json_body={"is_priority": True, "reason": reason},
        ).status_code
        == 200
    )
    assert _entry_action(client, scaffold, entry["id"], "call").status_code == 200
    assert _entry_action(client, scaffold, entry["id"], "missed-call").status_code == 200

    rows = db.query(AuditLog).filter(AuditLog.action.like("clinic_queue%")).all()
    checkin_rows = [r for r in rows if r.action == "clinic_queue_checkin" and r.resource_id == entry["id"]]
    assert len(checkin_rows) == 1
    assert checkin_rows[0].clinic_id == scaffold["clinic"]["id"]
    transition_rows = [
        r for r in rows if r.action == "clinic_queue_transition" and r.resource_id == entry["id"]
    ]
    assert {(r.details["from"], r.details["to"]) for r in transition_rows} == {
        ("waiting", "called"),
        ("called", "waiting"),
    }
    # PHI scan: no verbatim reason, no patient name, anywhere in any
    # clinic_queue* audit details (M07 R1 P1 discipline).
    for row in rows:
        blob = json.dumps(row.details or {}, ensure_ascii=False)
        assert reason not in blob
        assert "Trần Thị Bảo Ngọc" not in blob
        assert row.clinic_id is not None


# ---------------------------------------------------------------------------
# Unit-level helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Nguyễn Văn An", "N.V.A"),
        ("Lê Hòa", "L.H"),
        ("An", "A"),
        ("", "?"),
        (None, "?"),
    ],
)
def test_mask_initials(name, expected):
    assert queue_service.mask_initials(name) == expected
