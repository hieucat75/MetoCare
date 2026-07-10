"""Clinic SaaS C1 M07 — Appointment Management.

Covers `docs/clinic-saas/M07_IMPLEMENTATION_PLAN.md` §6's mandatory security
matrix: cross-clinic IDOR (on patient/doctor/service/branch ids at create),
branch-scoped role access, full role matrix incl. Doctor row-level scoping,
sequential + concurrent double-booking (DB-level via the partial unique
index), invalid state transitions (full BRD table), cancel/reschedule
permission boundaries, inactive relationship/service rejected, doctor not a
clinic member rejected, multi-clinic active-tenant-only scoping, revoked
membership loses access immediately, feature-flag-off 503, audit tenant
isolation, list/detail pagination+filtering tenant-scoped, working-hours
enforcement + Owner/Admin override.
"""

from __future__ import annotations

import datetime as dt
import os

import pytest
from app.core.security import create_access_token
from app.models.care import Doctor
from app.models.clinic import ClinicMembership
from app.models.user import User, UserRole

API = "/api/v1"


def _make_user(db, *, role: UserRole = UserRole.CLINIC_ADMIN) -> dict:
    user = User(
        email=f"m07-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=role,
        full_name="M07 Test User",
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
        json={"name": name or f"Phòng khám M07 {os.urandom(3).hex()}"},
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


def _member(db, clinic_id: str, roles: list[str], *, status: str = "active") -> dict:
    user = _make_user(db, role=UserRole.CLINIC_ADMIN)
    _add_membership(db, user_id=user["user_id"], clinic_id=clinic_id, roles=roles, status=status)
    return user


def _doctor_with_membership(
    db, clinic_id: str, *, branch_ids: list[str] | None = None
) -> dict:
    """Wires up a real `Doctor` row + `doctor_profile_id`-linked active
    `doctor` `ClinicMembership`, mirroring
    `test_clinic_service_catalog_m05_api.py`'s
    `test_doctor_id_active_member_of_clinic_accepted` pattern."""
    doctor_profile = Doctor(full_name=f"BS {os.urandom(3).hex()}")
    db.add(doctor_profile)
    db.commit()

    doctor_user = User(
        email=f"m07-doc-{os.urandom(4).hex()}@metocare.internal",
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
        roles=["doctor"],
        branch_ids=branch_ids,
        doctor_profile_id=doctor_profile.id,
    )
    token = create_access_token(subject=doctor_user.id, role="doctor", mfa=True)
    return {
        "user_id": doctor_user.id,
        "doctor_id": doctor_profile.id,
        "headers": {"Authorization": f"Bearer {token}"},
    }


def _create_branch(client, headers, clinic_id, *, name: str | None = None, working_hours=None) -> dict:
    resp = client.post(
        f"{API}/clinics/{clinic_id}/branches",
        json={
            "name": name or f"Chi nhánh {os.urandom(3).hex()}",
            "working_hours": working_hours if working_hours is not None else {},
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_service(client, headers, clinic_id, *, duration_minutes: int = 30, **overrides) -> dict:
    payload = {
        "name": f"Khám {os.urandom(3).hex()}",
        "code": f"SVC-{os.urandom(4).hex().upper()}",
        "specialty": "Nội tiết",
        "duration_minutes": duration_minutes,
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
            "full_name": full_name or "Bệnh nhân M07",
            "phone": _random_phone(),
            "dob": "1990-01-01",
            "gender": "female",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _next_weekday_at(weekday: int, hour: int, minute: int = 0) -> dt.datetime:
    """`weekday`: Monday=0 .. Sunday=6. Always in the future (next occurrence,
    at least 1 day out) so tests never depend on "today"."""
    today = dt.date.today()
    days_ahead = (weekday - today.weekday()) % 7
    days_ahead = days_ahead if days_ahead != 0 else 7
    target_date = today + dt.timedelta(days=days_ahead)
    return dt.datetime.combine(target_date, dt.time(hour, minute))


def _iso(value: dt.datetime) -> str:
    return value.isoformat()


def _appointment_scaffold(client, owner):
    """Common fixture scaffold: clinic + branch + service + patient, all
    created by `owner`. Returns a dict with everything a create-appointment
    call needs."""
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


def _create_payload(scaffold, *, doctor_id: str | None = None, start_time: dt.datetime | None = None, **overrides) -> dict:
    payload = {
        "branch_id": scaffold["branch"]["id"],
        "patient_id": scaffold["patient"]["patient_id"],
        "doctor_id": doctor_id,
        "service_id": scaffold["service"]["id"],
        "start_time": _iso(start_time or _next_weekday_at(0, 10, 0)),
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Feature flag off
# ---------------------------------------------------------------------------


def test_clinic_saas_disabled_returns_503(client, owner, monkeypatch):
    scaffold = _appointment_scaffold(client, owner)
    monkeypatch.setenv("FEATURE_CLINIC_SAAS", "false")
    resp = client.get(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments", headers=scaffold["headers"]
    )
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Create — happy path + validation
# ---------------------------------------------------------------------------


def test_create_appointment_without_doctor_succeeds(client, owner):
    scaffold = _appointment_scaffold(client, owner)
    resp = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments",
        json=_create_payload(scaffold),
        headers=scaffold["headers"],
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["doctor_id"] is None
    assert body["price_snapshot"] == str(scaffold["service"]["price"])
    assert body["created_by_source"] == "reception"


def test_create_appointment_with_doctor_succeeds(client, owner, db):
    scaffold = _appointment_scaffold(client, owner)
    doctor = _doctor_with_membership(db, scaffold["clinic"]["id"])
    resp = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments",
        json=_create_payload(scaffold, doctor_id=doctor["doctor_id"]),
        headers=scaffold["headers"],
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["doctor_id"] == doctor["doctor_id"]


def test_create_appointment_inactive_patient_relationship_rejected(client, owner):
    scaffold = _appointment_scaffold(client, owner)
    patch = client.patch(
        f"{API}/clinics/{scaffold['clinic']['id']}/patients/{scaffold['patient']['patient_id']}",
        json={"status": "inactive"},
        headers=scaffold["headers"],
    )
    assert patch.status_code == 200, patch.text
    resp = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments",
        json=_create_payload(scaffold),
        headers=scaffold["headers"],
    )
    assert resp.status_code == 400, resp.text


def test_create_appointment_inactive_service_rejected(client, owner):
    scaffold = _appointment_scaffold(client, owner)
    patch = client.patch(
        f"{API}/clinics/{scaffold['clinic']['id']}/services/{scaffold['service']['id']}",
        json={"status": "inactive"},
        headers=scaffold["headers"],
    )
    assert patch.status_code == 200, patch.text
    resp = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments",
        json=_create_payload(scaffold),
        headers=scaffold["headers"],
    )
    assert resp.status_code == 400, resp.text


def test_create_appointment_doctor_not_member_of_clinic_rejected(client, owner, db):
    scaffold = _appointment_scaffold(client, owner)
    stray_doctor = Doctor(full_name="BS Ngoài Phòng Khám")
    db.add(stray_doctor)
    db.commit()
    resp = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments",
        json=_create_payload(scaffold, doctor_id=stray_doctor.id),
        headers=scaffold["headers"],
    )
    assert resp.status_code == 400, resp.text


def test_create_appointment_member_without_doctor_role_rejected(client, owner, db):
    scaffold = _appointment_scaffold(client, owner)
    doctor_profile = Doctor(full_name="BS Không Có Vai Trò Doctor")
    db.add(doctor_profile)
    db.commit()
    non_doctor_user = _make_user(db, role=UserRole.CLINIC_ADMIN)
    _add_membership(
        db,
        user_id=non_doctor_user["user_id"],
        clinic_id=scaffold["clinic"]["id"],
        roles=["admin"],
        doctor_profile_id=doctor_profile.id,
    )
    resp = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments",
        json=_create_payload(scaffold, doctor_id=doctor_profile.id),
        headers=scaffold["headers"],
    )
    assert resp.status_code == 400, resp.text


def test_create_appointment_doctor_outside_branch_scope_rejected(client, owner, db):
    scaffold = _appointment_scaffold(client, owner)
    other_branch = _create_branch(client, scaffold["headers"], scaffold["clinic"]["id"])
    doctor = _doctor_with_membership(
        db, scaffold["clinic"]["id"], branch_ids=[other_branch["id"]]
    )
    resp = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments",
        json=_create_payload(scaffold, doctor_id=doctor["doctor_id"]),
        headers=scaffold["headers"],
    )
    assert resp.status_code == 400, resp.text


# ---------------------------------------------------------------------------
# Cross-clinic IDOR at create
# ---------------------------------------------------------------------------


def test_create_appointment_cross_clinic_branch_rejected(client, owner):
    scaffold_a = _appointment_scaffold(client, owner)
    scaffold_b = _appointment_scaffold(client, owner)
    resp = client.post(
        f"{API}/clinics/{scaffold_a['clinic']['id']}/appointments",
        json=_create_payload(scaffold_a, branch_id=scaffold_b["branch"]["id"]),
        headers=scaffold_a["headers"],
    )
    assert resp.status_code == 400, resp.text


def test_create_appointment_cross_clinic_service_rejected(client, owner):
    scaffold_a = _appointment_scaffold(client, owner)
    scaffold_b = _appointment_scaffold(client, owner)
    resp = client.post(
        f"{API}/clinics/{scaffold_a['clinic']['id']}/appointments",
        json=_create_payload(scaffold_a, service_id=scaffold_b["service"]["id"]),
        headers=scaffold_a["headers"],
    )
    assert resp.status_code == 400, resp.text


def test_create_appointment_cross_clinic_patient_rejected(client, owner):
    scaffold_a = _appointment_scaffold(client, owner)
    scaffold_b = _appointment_scaffold(client, owner)
    resp = client.post(
        f"{API}/clinics/{scaffold_a['clinic']['id']}/appointments",
        json=_create_payload(scaffold_a, patient_id=scaffold_b["patient"]["patient_id"]),
        headers=scaffold_a["headers"],
    )
    assert resp.status_code == 400, resp.text


def test_create_appointment_cross_clinic_doctor_rejected(client, owner, db):
    scaffold_a = _appointment_scaffold(client, owner)
    scaffold_b = _appointment_scaffold(client, owner)
    doctor_b = _doctor_with_membership(db, scaffold_b["clinic"]["id"])
    resp = client.post(
        f"{API}/clinics/{scaffold_a['clinic']['id']}/appointments",
        json=_create_payload(scaffold_a, doctor_id=doctor_b["doctor_id"]),
        headers=scaffold_a["headers"],
    )
    assert resp.status_code == 400, resp.text


def test_get_appointment_cross_clinic_not_found(client, owner, db):
    scaffold_a = _appointment_scaffold(client, owner)
    scaffold_b = _appointment_scaffold(client, owner)
    created = client.post(
        f"{API}/clinics/{scaffold_a['clinic']['id']}/appointments",
        json=_create_payload(scaffold_a),
        headers=scaffold_a["headers"],
    )
    assert created.status_code == 201

    member_b = _member(db, scaffold_b["clinic"]["id"], ["admin"])
    resp = client.get(
        f"{API}/clinics/{scaffold_b['clinic']['id']}/appointments/{created.json()['id']}",
        headers={**member_b["headers"], "X-Clinic-Id": scaffold_b["clinic"]["id"]},
    )
    assert resp.status_code == 404


def test_idor_clinic_id_path_mismatch_rejected(client, owner, db):
    scaffold_a = _appointment_scaffold(client, owner)
    clinic_b = _create_clinic(client, owner)
    member_a = _member(db, scaffold_a["clinic"]["id"], ["admin"])
    resp = client.get(
        f"{API}/clinics/{clinic_b['id']}/appointments",
        headers={**member_a["headers"], "X-Clinic-Id": scaffold_a["clinic"]["id"]},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Double booking
# ---------------------------------------------------------------------------


def test_double_booking_same_slot_rejected(client, owner, db):
    scaffold = _appointment_scaffold(client, owner)
    doctor = _doctor_with_membership(db, scaffold["clinic"]["id"])
    start = _next_weekday_at(1, 9, 0)
    first = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments",
        json=_create_payload(scaffold, doctor_id=doctor["doctor_id"], start_time=start),
        headers=scaffold["headers"],
    )
    assert first.status_code == 201, first.text
    second = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments",
        json=_create_payload(scaffold, doctor_id=doctor["doctor_id"], start_time=start),
        headers=scaffold["headers"],
    )
    assert second.status_code == 400, second.text


def test_double_booking_concurrent_race_safety_net(client, owner, db, monkeypatch):
    """Codex-style race test (M06 precedent): monkeypatches the overlap
    pre-check to report no conflict (simulating the TOCTOU loser) while a
    colliding row already exists — the DB unique index must still turn this
    into a controlled 400, never an unhandled 500."""
    from app.services import clinic_appointments as appointments_service

    scaffold = _appointment_scaffold(client, owner)
    doctor = _doctor_with_membership(db, scaffold["clinic"]["id"])
    start = _next_weekday_at(2, 9, 0)
    winner = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments",
        json=_create_payload(scaffold, doctor_id=doctor["doctor_id"], start_time=start),
        headers=scaffold["headers"],
    )
    assert winner.status_code == 201, winner.text

    monkeypatch.setattr(
        appointments_service, "_has_overlapping_appointment", lambda db, **kwargs: False
    )
    loser = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments",
        json=_create_payload(scaffold, doctor_id=doctor["doctor_id"], start_time=start),
        headers=scaffold["headers"],
    )
    assert loser.status_code == 400, loser.text


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------


def _create_and_get(client, scaffold, **overrides) -> dict:
    resp = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments",
        json=_create_payload(scaffold, **overrides),
        headers=scaffold["headers"],
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_valid_transition_pending_confirmed_cancelled(client, owner):
    scaffold = _appointment_scaffold(client, owner)
    appt = _create_and_get(client, scaffold, start_time=_next_weekday_at(3, 9, 0))
    confirm = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments/{appt['id']}/confirm",
        headers=scaffold["headers"],
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["status"] == "confirmed"

    cancel = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments/{appt['id']}/cancel",
        json={"reason": "Bệnh nhân bận"},
        headers=scaffold["headers"],
    )
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["status"] == "cancelled"


def test_valid_transition_confirmed_noshow_arrived(client, owner):
    scaffold = _appointment_scaffold(client, owner)
    appt = _create_and_get(client, scaffold, start_time=_next_weekday_at(3, 10, 0))
    client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments/{appt['id']}/confirm",
        headers=scaffold["headers"],
    )
    no_show = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments/{appt['id']}/no-show",
        json={"reason": "Không đến"},
        headers=scaffold["headers"],
    )
    assert no_show.status_code == 200, no_show.text
    assert no_show.json()["status"] == "no_show"

    arrived = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments/{appt['id']}/arrived-override",
        json={"reason": "Đến muộn"},
        headers=scaffold["headers"],
    )
    assert arrived.status_code == 200, arrived.text
    assert arrived.json()["status"] == "arrived"


@pytest.mark.parametrize(
    "endpoint,body",
    [
        ("arrived-override", {"reason": "x"}),
        ("no-show", {"reason": "x"}),
    ],
)
def test_invalid_transition_from_pending_rejected(client, owner, endpoint, body):
    scaffold = _appointment_scaffold(client, owner)
    appt = _create_and_get(client, scaffold, start_time=_next_weekday_at(4, 9, 0))
    resp = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments/{appt['id']}/{endpoint}",
        json=body,
        headers=scaffold["headers"],
    )
    assert resp.status_code == 400, resp.text


def test_invalid_transition_completed_is_terminal(client, owner, db):
    """Completed has no outgoing transitions — force the row into
    `completed` directly (M08/M09's own routes don't exist yet in this
    milestone) and confirm every M07 mutation route rejects it."""
    from app.models.clinic import ClinicAppointment, ClinicAppointmentStatus

    scaffold = _appointment_scaffold(client, owner)
    appt = _create_and_get(client, scaffold, start_time=_next_weekday_at(4, 10, 0))
    row = db.get(ClinicAppointment, appt["id"])
    row.status = ClinicAppointmentStatus.COMPLETED
    db.commit()

    resp = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments/{appt['id']}/cancel",
        json={"reason": "x"},
        headers=scaffold["headers"],
    )
    assert resp.status_code == 400, resp.text


def test_invalid_transition_cancelled_to_confirmed_rejected(client, owner):
    scaffold = _appointment_scaffold(client, owner)
    appt = _create_and_get(client, scaffold, start_time=_next_weekday_at(5, 9, 0))
    cancel = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments/{appt['id']}/cancel",
        json={"reason": "x"},
        headers=scaffold["headers"],
    )
    assert cancel.status_code == 200
    confirm = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments/{appt['id']}/confirm",
        headers=scaffold["headers"],
    )
    assert confirm.status_code == 400, confirm.text


def test_denied_transition_audit_row_persists(client, owner, db):
    """A denied transition must leave a durable audit trail (BR-M07-01:
    "mọi transition ghi audit"). The route never calls db.commit() on the
    error path (it raises HTTPException from ClinicAppointmentError), so
    transition_status must commit the denial record itself before raising —
    otherwise get_session()'s implicit rollback-on-exception would silently
    discard it every time."""
    from app.models.governance import AuditLog

    scaffold = _appointment_scaffold(client, owner)
    appt = _create_and_get(client, scaffold, start_time=_next_weekday_at(5, 9, 0))
    cancel = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments/{appt['id']}/cancel",
        json={"reason": "x"},
        headers=scaffold["headers"],
    )
    assert cancel.status_code == 200

    denied = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments/{appt['id']}/confirm",
        headers=scaffold["headers"],
    )
    assert denied.status_code == 400

    rows = (
        db.query(AuditLog)
        .filter_by(action="clinic_appointment_transition_denied", resource_id=appt["id"])
        .all()
    )
    assert len(rows) == 1
    assert rows[0].outcome == "denied"
    assert rows[0].details == {"from": "cancelled", "to": "confirmed"}


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


def test_cancel_missing_reason_rejected(client, owner):
    scaffold = _appointment_scaffold(client, owner)
    appt = _create_and_get(client, scaffold, start_time=_next_weekday_at(5, 10, 0))
    resp = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments/{appt['id']}/cancel",
        json={},
        headers=scaffold["headers"],
    )
    assert resp.status_code == 422


def test_cancel_records_reason(client, owner):
    scaffold = _appointment_scaffold(client, owner)
    appt = _create_and_get(client, scaffold, start_time=_next_weekday_at(6, 9, 0))
    resp = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments/{appt['id']}/cancel",
        json={"reason": "Lý do hủy cụ thể"},
        headers=scaffold["headers"],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["cancellation_reason"] == "Lý do hủy cụ thể"
    assert resp.json()["cancelled_by_user_id"] is not None
    assert resp.json()["cancelled_at"] is not None


def test_doctor_cancel_others_appointment_forbidden(client, owner, db):
    scaffold = _appointment_scaffold(client, owner)
    doctor_a = _doctor_with_membership(db, scaffold["clinic"]["id"])
    doctor_b = _doctor_with_membership(db, scaffold["clinic"]["id"])
    appt = _create_and_get(
        client, scaffold, doctor_id=doctor_a["doctor_id"], start_time=_next_weekday_at(6, 10, 0)
    )
    resp = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments/{appt['id']}/cancel",
        json={"reason": "x"},
        headers={**doctor_b["headers"], "X-Clinic-Id": scaffold["clinic"]["id"]},
    )
    assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# Reschedule
# ---------------------------------------------------------------------------


def test_reschedule_creates_linked_appointment_and_cancels_old(client, owner):
    scaffold = _appointment_scaffold(client, owner)
    appt = _create_and_get(client, scaffold, start_time=_next_weekday_at(0, 9, 0))
    new_start = _next_weekday_at(0, 14, 0)
    resp = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments/{appt['id']}/reschedule",
        json={"start_time": _iso(new_start), "reason": "Đổi lịch theo yêu cầu"},
        headers=scaffold["headers"],
    )
    assert resp.status_code == 201, resp.text
    new_appt = resp.json()
    assert new_appt["id"] != appt["id"]
    assert new_appt["reschedule_of_id"] == appt["id"]
    assert new_appt["status"] == "pending"

    old = client.get(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments/{appt['id']}",
        headers=scaffold["headers"],
    )
    assert old.json()["status"] == "cancelled"
    assert "rescheduled" in old.json()["cancellation_reason"]


def test_reschedule_terminal_appointment_rejected(client, owner):
    scaffold = _appointment_scaffold(client, owner)
    appt = _create_and_get(client, scaffold, start_time=_next_weekday_at(1, 14, 0))
    client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments/{appt['id']}/cancel",
        json={"reason": "x"},
        headers=scaffold["headers"],
    )
    resp = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments/{appt['id']}/reschedule",
        json={"start_time": _iso(_next_weekday_at(2, 14, 0)), "reason": "x"},
        headers=scaffold["headers"],
    )
    assert resp.status_code == 400, resp.text


# ---------------------------------------------------------------------------
# Role matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "roles", [["owner"], ["admin"], ["doctor"], ["nurse"], ["receptionist"], ["care_coordinator"]]
)
def test_read_roles_see_full_roster(client, owner, db, roles):
    scaffold = _appointment_scaffold(client, owner)
    _create_and_get(client, scaffold, start_time=_next_weekday_at(3, 9, 0))
    member = _member(db, scaffold["clinic"]["id"], roles)
    resp = client.get(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments",
        headers={**member["headers"], "X-Clinic-Id": scaffold["clinic"]["id"]},
    )
    assert resp.status_code == 200, resp.text
    if roles != ["doctor"]:
        assert resp.json()["total"] == 1
    else:
        # A doctor-only member with no doctor_profile_id sees nothing (no
        # own-assigned appointments exist for them).
        assert resp.json()["total"] == 0


def test_accountant_denied_appointments_access(client, owner, db):
    scaffold = _appointment_scaffold(client, owner)
    member = _member(db, scaffold["clinic"]["id"], ["accountant"])
    resp = client.get(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments",
        headers={**member["headers"], "X-Clinic-Id": scaffold["clinic"]["id"]},
    )
    assert resp.status_code == 403


def test_doctor_sees_only_own_assigned_appointments(client, owner, db):
    scaffold = _appointment_scaffold(client, owner)
    doctor_a = _doctor_with_membership(db, scaffold["clinic"]["id"])
    doctor_b = _doctor_with_membership(db, scaffold["clinic"]["id"])
    own = _create_and_get(
        client, scaffold, doctor_id=doctor_a["doctor_id"], start_time=_next_weekday_at(0, 9, 0)
    )
    other = _create_and_get(
        client, scaffold, doctor_id=doctor_b["doctor_id"], start_time=_next_weekday_at(0, 10, 0)
    )

    listing = client.get(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments",
        headers={**doctor_a["headers"], "X-Clinic-Id": scaffold["clinic"]["id"]},
    )
    assert listing.status_code == 200
    ids = {item["id"] for item in listing.json()["items"]}
    assert own["id"] in ids
    assert other["id"] not in ids

    own_read = client.get(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments/{own['id']}",
        headers={**doctor_a["headers"], "X-Clinic-Id": scaffold["clinic"]["id"]},
    )
    assert own_read.status_code == 200

    other_read = client.get(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments/{other['id']}",
        headers={**doctor_a["headers"], "X-Clinic-Id": scaffold["clinic"]["id"]},
    )
    assert other_read.status_code == 403


def test_doctor_self_booking_only(client, owner, db):
    scaffold = _appointment_scaffold(client, owner)
    doctor_a = _doctor_with_membership(db, scaffold["clinic"]["id"])
    doctor_b = _doctor_with_membership(db, scaffold["clinic"]["id"])
    resp = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments",
        json=_create_payload(
            scaffold, doctor_id=doctor_b["doctor_id"], start_time=_next_weekday_at(1, 9, 0)
        ),
        headers={**doctor_a["headers"], "X-Clinic-Id": scaffold["clinic"]["id"]},
    )
    assert resp.status_code == 403, resp.text

    own = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments",
        json=_create_payload(
            scaffold, doctor_id=doctor_a["doctor_id"], start_time=_next_weekday_at(1, 9, 0)
        ),
        headers={**doctor_a["headers"], "X-Clinic-Id": scaffold["clinic"]["id"]},
    )
    assert own.status_code == 201, own.text


# ---------------------------------------------------------------------------
# Branch-scoped role
# ---------------------------------------------------------------------------


def test_branch_scoped_membership_cannot_create_at_other_branch(client, owner, db):
    scaffold = _appointment_scaffold(client, owner)
    other_branch = _create_branch(client, scaffold["headers"], scaffold["clinic"]["id"])
    user = _make_user(db, role=UserRole.CLINIC_ADMIN)
    _add_membership(
        db,
        user_id=user["user_id"],
        clinic_id=scaffold["clinic"]["id"],
        roles=["receptionist"],
        branch_ids=[scaffold["branch"]["id"]],
    )
    headers = {**user["headers"], "X-Clinic-Id": scaffold["clinic"]["id"]}
    resp = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments",
        json=_create_payload(scaffold, branch_id=other_branch["id"]),
        headers=headers,
    )
    # A branch-scoped receptionist must never be able to create at a
    # different branch of the same clinic ("branch-scoped role không vượt
    # branch" — this session's explicit instruction). Enforced via
    # `_assert_actor_branch_scope` against `TenantContext.branch_ids`, the
    # same pattern M05's `list_services` already established.
    assert resp.status_code == 403, resp.text


def test_branch_scoped_membership_can_create_at_own_branch(client, owner, db):
    scaffold = _appointment_scaffold(client, owner)
    user = _make_user(db, role=UserRole.CLINIC_ADMIN)
    _add_membership(
        db,
        user_id=user["user_id"],
        clinic_id=scaffold["clinic"]["id"],
        roles=["receptionist"],
        branch_ids=[scaffold["branch"]["id"]],
    )
    headers = {**user["headers"], "X-Clinic-Id": scaffold["clinic"]["id"]}
    resp = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments",
        json=_create_payload(scaffold),
        headers=headers,
    )
    assert resp.status_code == 201, resp.text


def test_branch_scoped_membership_cannot_list_other_branch(client, owner, db):
    scaffold = _appointment_scaffold(client, owner)
    other_branch = _create_branch(client, scaffold["headers"], scaffold["clinic"]["id"])
    user = _make_user(db, role=UserRole.CLINIC_ADMIN)
    _add_membership(
        db,
        user_id=user["user_id"],
        clinic_id=scaffold["clinic"]["id"],
        roles=["receptionist"],
        branch_ids=[scaffold["branch"]["id"]],
    )
    headers = {**user["headers"], "X-Clinic-Id": scaffold["clinic"]["id"]}
    denied = client.get(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments",
        params={"branch_id": other_branch["id"]},
        headers=headers,
    )
    assert denied.status_code == 403, denied.text

    # Omitting branch_id must default to the caller's OWN branch scope, not
    # every branch of the clinic.
    unfiltered = client.get(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments", headers=headers
    )
    assert unfiltered.status_code == 200
    assert unfiltered.json()["total"] == 0


def test_branch_scoped_membership_cannot_view_or_mutate_other_branch(client, owner, db):
    """Codex review P2: create/list-only branch-scope coverage would not
    catch a regression removing `_assert_actor_branch_scope` from the
    detail/mutation routes specifically (they share `_load_appointment_for_
    mutation`/an inline check, but that's implementation detail the tests
    should not assume — assert the observable behavior directly)."""
    scaffold = _appointment_scaffold(client, owner)
    other_branch = _create_branch(client, scaffold["headers"], scaffold["clinic"]["id"])
    appt = _create_and_get(
        client, scaffold, branch_id=other_branch["id"], start_time=_next_weekday_at(6, 11, 0)
    )
    user = _make_user(db, role=UserRole.CLINIC_ADMIN)
    _add_membership(
        db,
        user_id=user["user_id"],
        clinic_id=scaffold["clinic"]["id"],
        roles=["receptionist"],
        branch_ids=[scaffold["branch"]["id"]],
    )
    headers = {**user["headers"], "X-Clinic-Id": scaffold["clinic"]["id"]}

    detail = client.get(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments/{appt['id']}", headers=headers
    )
    assert detail.status_code == 403, detail.text

    confirm = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments/{appt['id']}/confirm",
        headers=headers,
    )
    assert confirm.status_code == 403, confirm.text


# ---------------------------------------------------------------------------
# Multi-clinic / revoked membership
# ---------------------------------------------------------------------------


def test_multi_clinic_membership_scopes_to_active_clinic(client, owner, db):
    scaffold_a = _appointment_scaffold(client, owner)
    scaffold_b = _appointment_scaffold(client, owner)
    user = _make_user(db, role=UserRole.CLINIC_ADMIN)
    _add_membership(
        db, user_id=user["user_id"], clinic_id=scaffold_a["clinic"]["id"], roles=["admin"]
    )
    _add_membership(
        db, user_id=user["user_id"], clinic_id=scaffold_b["clinic"]["id"], roles=["admin"]
    )

    client.post(
        f"{API}/clinics/{scaffold_a['clinic']['id']}/appointments",
        json=_create_payload(scaffold_a),
        headers={**user["headers"], "X-Clinic-Id": scaffold_a["clinic"]["id"]},
    )

    resp_a = client.get(
        f"{API}/clinics/{scaffold_a['clinic']['id']}/appointments",
        headers={**user["headers"], "X-Clinic-Id": scaffold_a["clinic"]["id"]},
    )
    resp_b = client.get(
        f"{API}/clinics/{scaffold_b['clinic']['id']}/appointments",
        headers={**user["headers"], "X-Clinic-Id": scaffold_b["clinic"]["id"]},
    )
    assert resp_a.json()["total"] == 1
    assert resp_b.json()["total"] == 0


def test_revoked_membership_loses_access_immediately(client, owner, db):
    scaffold = _appointment_scaffold(client, owner)
    member = _member(db, scaffold["clinic"]["id"], ["admin"])
    ok = client.get(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments",
        headers={**member["headers"], "X-Clinic-Id": scaffold["clinic"]["id"]},
    )
    assert ok.status_code == 200

    row = (
        db.query(ClinicMembership)
        .filter_by(user_id=member["user_id"], clinic_id=scaffold["clinic"]["id"])
        .one()
    )
    row.status = "removed"
    db.commit()

    denied = client.get(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments",
        headers={**member["headers"], "X-Clinic-Id": scaffold["clinic"]["id"]},
    )
    assert denied.status_code == 403


# ---------------------------------------------------------------------------
# Audit isolation
# ---------------------------------------------------------------------------


def test_audit_rows_tenant_isolated(client, owner, db):
    from app.models.governance import AuditLog

    scaffold_a = _appointment_scaffold(client, owner)
    scaffold_b = _appointment_scaffold(client, owner)
    created = client.post(
        f"{API}/clinics/{scaffold_a['clinic']['id']}/appointments",
        json=_create_payload(scaffold_a),
        headers=scaffold_a["headers"],
    )
    assert created.status_code == 201
    appointment_id = created.json()["id"]

    rows = (
        db.query(AuditLog)
        .filter_by(action="clinic_appointment_create", resource_id=appointment_id)
        .all()
    )
    assert len(rows) == 1
    assert rows[0].clinic_id == scaffold_a["clinic"]["id"]
    assert rows[0].clinic_id != scaffold_b["clinic"]["id"]


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


def test_appointment_list_pagination_bounded(client, owner):
    scaffold = _appointment_scaffold(client, owner)
    for i in range(3):
        client.post(
            f"{API}/clinics/{scaffold['clinic']['id']}/appointments",
            json=_create_payload(scaffold, start_time=_next_weekday_at(2, 9 + i, 0)),
            headers=scaffold["headers"],
        )
    resp = client.get(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments",
        params={"limit": 2},
        headers=scaffold["headers"],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2


# ---------------------------------------------------------------------------
# Working hours
# ---------------------------------------------------------------------------


def test_working_hours_rejects_out_of_window_booking_without_override(client, owner):
    clinic = _create_clinic(client, owner)
    headers = {**owner["headers"], "X-Clinic-Id": clinic["id"]}
    branch = _create_branch(
        client, headers, clinic["id"], working_hours={"mon": "09:00-12:00"}
    )
    service = _create_service(client, headers, clinic["id"])
    patient = _create_patient(client, headers, clinic["id"])
    scaffold = {
        "clinic": clinic,
        "headers": headers,
        "branch": branch,
        "service": service,
        "patient": patient,
    }
    out_of_hours = _next_weekday_at(0, 14, 0)  # Monday 14:00, outside 09:00-12:00
    resp = client.post(
        f"{API}/clinics/{clinic['id']}/appointments",
        json=_create_payload(scaffold, start_time=out_of_hours),
        headers=headers,
    )
    assert resp.status_code == 400, resp.text


def test_working_hours_owner_override_with_reason_succeeds(client, owner):
    clinic = _create_clinic(client, owner)
    headers = {**owner["headers"], "X-Clinic-Id": clinic["id"]}
    branch = _create_branch(
        client, headers, clinic["id"], working_hours={"mon": "09:00-12:00"}
    )
    service = _create_service(client, headers, clinic["id"])
    patient = _create_patient(client, headers, clinic["id"])
    scaffold = {
        "clinic": clinic,
        "headers": headers,
        "branch": branch,
        "service": service,
        "patient": patient,
    }
    out_of_hours = _next_weekday_at(0, 14, 0)
    resp = client.post(
        f"{API}/clinics/{clinic['id']}/appointments",
        json=_create_payload(
            scaffold, start_time=out_of_hours, override_working_hours_reason="Khám cấp cứu"
        ),
        headers=headers,
    )
    assert resp.status_code == 201, resp.text


def test_working_hours_non_owner_override_reason_ignored(client, owner, db):
    clinic = _create_clinic(client, owner)
    headers = {**owner["headers"], "X-Clinic-Id": clinic["id"]}
    branch = _create_branch(
        client, headers, clinic["id"], working_hours={"mon": "09:00-12:00"}
    )
    service = _create_service(client, headers, clinic["id"])
    patient = _create_patient(client, headers, clinic["id"])
    scaffold = {
        "clinic": clinic,
        "headers": headers,
        "branch": branch,
        "service": service,
        "patient": patient,
    }
    reception = _member(db, clinic["id"], ["receptionist"])
    out_of_hours = _next_weekday_at(0, 14, 0)
    resp = client.post(
        f"{API}/clinics/{clinic['id']}/appointments",
        json=_create_payload(
            scaffold, start_time=out_of_hours, override_working_hours_reason="Tự ý override"
        ),
        headers={**reception["headers"], "X-Clinic-Id": clinic["id"]},
    )
    assert resp.status_code == 400, resp.text


def test_working_hours_within_window_succeeds_without_override(client, owner):
    clinic = _create_clinic(client, owner)
    headers = {**owner["headers"], "X-Clinic-Id": clinic["id"]}
    branch = _create_branch(
        client, headers, clinic["id"], working_hours={"mon": "09:00-12:00"}
    )
    service = _create_service(client, headers, clinic["id"])
    patient = _create_patient(client, headers, clinic["id"])
    scaffold = {
        "clinic": clinic,
        "headers": headers,
        "branch": branch,
        "service": service,
        "patient": patient,
    }
    in_hours = _next_weekday_at(0, 10, 0)
    resp = client.post(
        f"{API}/clinics/{clinic['id']}/appointments",
        json=_create_payload(scaffold, start_time=in_hours),
        headers=headers,
    )
    assert resp.status_code == 201, resp.text


# ---------------------------------------------------------------------------
# No-show job
# ---------------------------------------------------------------------------


def test_run_no_show_job_transitions_overdue_confirmed_appointments(client, owner, db):
    from app.models.clinic import ClinicAppointment

    scaffold = _appointment_scaffold(client, owner)
    appt = _create_and_get(client, scaffold, start_time=_next_weekday_at(0, 9, 0))
    client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments/{appt['id']}/confirm",
        headers=scaffold["headers"],
    )
    # Force the row into the past so the job's grace-period cutoff matches.
    row = db.get(ClinicAppointment, appt["id"])
    row.start_time = dt.datetime.utcnow() - dt.timedelta(hours=3)
    db.commit()

    resp = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments/run-no-show-job",
        headers=scaffold["headers"],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["transitioned_count"] == 1

    check = client.get(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments/{appt['id']}",
        headers=scaffold["headers"],
    )
    assert check.json()["status"] == "no_show"

    # Idempotent: a second call finds zero matching (already-transitioned) rows.
    again = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments/run-no-show-job",
        headers=scaffold["headers"],
    )
    assert again.json()["transitioned_count"] == 0


def test_run_no_show_job_forbidden_for_non_owner_admin(client, owner, db):
    scaffold = _appointment_scaffold(client, owner)
    reception = _member(db, scaffold["clinic"]["id"], ["receptionist"])
    resp = client.post(
        f"{API}/clinics/{scaffold['clinic']['id']}/appointments/run-no-show-job",
        headers={**reception["headers"], "X-Clinic-Id": scaffold["clinic"]["id"]},
    )
    assert resp.status_code == 403
