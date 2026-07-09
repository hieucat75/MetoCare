"""Clinic SaaS C1 M06 — Patient Management.

Builds the consumer surface for `ClinicPatientRelationship` (roster, link,
create-with-dedup, detail, update) and exercises the mandatory security/
tenant-isolation matrix from `docs/clinic-saas/M06_IMPLEMENTATION_PLAN.md`
§6: cross-clinic BOLA, multi-clinic scoping, revoked membership, duplicate-
patient dedup (pre-check + concurrent-race safety net), paginated/capped
search, consent gate for cross-clinic reads, full role matrix (incl. field-
level filtering), feature-flag-off, audit isolation, IDOR, and the Clinical
Copilot guard (`assert_doctor_clinic_scope_for_patient`) activating once a
patient is actually linked to a clinic.
"""

from __future__ import annotations

import os

import pytest
from app.core.security import create_access_token
from app.models.clinic import ClinicMembership
from app.models.governance import Consent
from app.models.patient import PatientProfile
from app.models.user import User, UserRole

API = "/api/v1"


def _make_user(db, *, role: UserRole = UserRole.CLINIC_ADMIN) -> dict:
    user = User(
        email=f"m06-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=role,
        full_name="M06 Test User",
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
        f"{API}/clinics", json={"name": name or f"Phòng khám M06 {os.urandom(3).hex()}"},
        headers=owner["headers"],
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _add_membership(db, *, user_id: str, clinic_id: str, roles: list[str], status: str = "active"):
    m = ClinicMembership(
        user_id=user_id, clinic_id=clinic_id, roles=roles, branch_ids=[], status=status
    )
    db.add(m)
    db.commit()
    return m


def _member(db, clinic_id: str, roles: list[str], *, status: str = "active") -> dict:
    user = _make_user(db, role=UserRole.CLINIC_ADMIN)
    _add_membership(db, user_id=user["user_id"], clinic_id=clinic_id, roles=roles, status=status)
    return user


def _patient_headers(db, full_name: str = "Nguyễn Văn A", phone: str | None = None) -> dict:
    from app.core.phone import normalize_vn_phone

    raw_phone = phone or _random_phone()
    normalized_phone = normalize_vn_phone(raw_phone)
    user = User(
        phone=normalized_phone, email=None,
        password_hash="x", role=UserRole.PATIENT, full_name=full_name, is_active=True,
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name=full_name, dob="1990-01-01", gender="male")
    db.add(profile)
    db.commit()
    return {"user_id": user.id, "profile_id": profile.id, "phone": raw_phone}


def _random_phone() -> str:
    # Valid VN mobile prefix "90" (Mobifone, matches app.core.phone's
    # _NATIONAL_RE) + 7 random digits. The test DB persists across tests in
    # the same run (no per-test truncation, matching this file's/M05's own
    # convention of always using random values) — a fixed literal phone
    # collides with leftover rows from earlier tests via the real
    # User.phone unique constraint.
    return "090" + "".join(str(b % 10) for b in os.urandom(7))


def _create_payload(**overrides) -> dict:
    payload = {
        "full_name": "Trần Thị B",
        "phone": _random_phone(),
        "dob": "1985-05-05",
        "gender": "female",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Feature flag off
# ---------------------------------------------------------------------------


def test_clinic_saas_disabled_returns_503(client, owner, monkeypatch):
    clinic = _create_clinic(client, owner)
    monkeypatch.setenv("FEATURE_CLINIC_SAAS", "false")
    resp = client.get(f"{API}/clinics/{clinic['id']}/patients", headers=owner["headers"])
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Create / dedup
# ---------------------------------------------------------------------------


def test_create_patient_minimal_fields_succeeds(client, owner):
    clinic = _create_clinic(client, owner)
    resp = client.post(
        f"{API}/clinics/{clinic['id']}/patients",
        json=_create_payload(),
        headers=owner["headers"],
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["full_name"] == "Trần Thị B"
    assert body["patient_code"].startswith("BN-")
    assert body["status"] == "active"


def test_create_patient_duplicate_phone_warns_without_reason(client, owner):
    clinic = _create_clinic(client, owner)
    phone = _random_phone()
    first = client.post(
        f"{API}/clinics/{clinic['id']}/patients",
        json=_create_payload(phone=phone),
        headers=owner["headers"],
    )
    assert first.status_code == 201, first.text

    second = client.post(
        f"{API}/clinics/{clinic['id']}/patients",
        json=_create_payload(full_name="Trần Thị B2", phone=phone),
        headers=owner["headers"],
    )
    assert second.status_code == 409, second.text
    body = second.json()
    assert body["code"] == "DUPLICATE_CANDIDATE"
    assert body["candidate"]["phone"] == f"+84{phone[1:]}"


def test_create_patient_duplicate_phone_with_override_reason_succeeds(client, owner):
    clinic = _create_clinic(client, owner)
    phone = _random_phone()
    first = client.post(
        f"{API}/clinics/{clinic['id']}/patients",
        json=_create_payload(phone=phone),
        headers=owner["headers"],
    )
    assert first.status_code == 201

    second = client.post(
        f"{API}/clinics/{clinic['id']}/patients",
        json=_create_payload(
            full_name="Vợ dùng chung SĐT",
            phone=phone,
            override_dedup_reason="Vợ chồng dùng chung SĐT",
        ),
        headers=owner["headers"],
    )
    assert second.status_code == 201, second.text
    assert second.json()["patient_id"] != first.json()["patient_id"]


def test_search_candidates_exact_phone_match(client, owner):
    clinic = _create_clinic(client, owner)
    phone = _random_phone()
    created = client.post(
        f"{API}/clinics/{clinic['id']}/patients",
        json=_create_payload(phone=phone),
        headers=owner["headers"],
    )
    assert created.status_code == 201

    resp = client.get(
        f"{API}/clinics/{clinic['id']}/patients/search-candidates",
        params={"phone": phone},
        headers=owner["headers"],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["already_linked"] is True

    miss = client.get(
        f"{API}/clinics/{clinic['id']}/patients/search-candidates",
        params={"phone": _random_phone()},
        headers=owner["headers"],
    )
    assert miss.status_code == 200
    assert miss.json() is None


def test_link_existing_patient(client, owner, db):
    clinic = _create_clinic(client, owner)
    patient = _patient_headers(db)
    resp = client.post(
        f"{API}/clinics/{clinic['id']}/patients/link",
        json={"patient_id": patient["profile_id"], "phone": patient["phone"]},
        headers=owner["headers"],
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["patient_id"] == patient["profile_id"]


def test_link_same_patient_twice_rejected(client, owner, db):
    clinic = _create_clinic(client, owner)
    patient = _patient_headers(db)
    first = client.post(
        f"{API}/clinics/{clinic['id']}/patients/link",
        json={"patient_id": patient["profile_id"], "phone": patient["phone"]},
        headers=owner["headers"],
    )
    assert first.status_code == 201
    second = client.post(
        f"{API}/clinics/{clinic['id']}/patients/link",
        json={"patient_id": patient["profile_id"], "phone": patient["phone"]},
        headers=owner["headers"],
    )
    assert second.status_code == 400


def test_create_patient_concurrent_phone_race_safety_net(client, owner, db, monkeypatch):
    """Codex review P2: forces the check-then-insert TOCTOU race on
    `User.phone` (app/services/clinic_patients.py create_patient) — two
    concurrent creates with the same new phone both pass the pre-check
    before either commits. Simulated by monkeypatching `find_by_phone` to
    return None (as the loser's pre-check race would see) while a colliding
    User already exists; the DB unique constraint must still turn this into
    a controlled ClinicPatientError (400), never an unhandled 500."""
    from app.services import clinic_patients as patients_service

    clinic = _create_clinic(client, owner)
    phone = _random_phone()
    winner = client.post(
        f"{API}/clinics/{clinic['id']}/patients",
        json=_create_payload(phone=phone),
        headers=owner["headers"],
    )
    assert winner.status_code == 201, winner.text

    monkeypatch.setattr(patients_service, "find_by_phone", lambda db, phone_normalized: None)
    loser = client.post(
        f"{API}/clinics/{clinic['id']}/patients",
        json=_create_payload(full_name="Người thua cuộc đua", phone=phone),
        headers=owner["headers"],
    )
    assert loser.status_code == 400, loser.text


def test_link_wrong_phone_rejected(client, owner, db):
    """Codex review P0 regression: a bare patient_id must never be
    sufficient to link — the caller must prove real-world contact via a
    matching phone, re-verified server-side."""
    clinic = _create_clinic(client, owner)
    patient = _patient_headers(db)
    resp = client.post(
        f"{API}/clinics/{clinic['id']}/patients/link",
        json={"patient_id": patient["profile_id"], "phone": _random_phone()},
        headers=owner["headers"],
    )
    assert resp.status_code == 400, resp.text


# ---------------------------------------------------------------------------
# Tenant isolation / BOLA / multi-clinic / revoked membership
# ---------------------------------------------------------------------------


def test_cross_clinic_roster_isolated(client, owner, db):
    clinic_a = _create_clinic(client, owner)
    clinic_b = _create_clinic(client, owner)
    client.post(
        f"{API}/clinics/{clinic_a['id']}/patients",
        json=_create_payload(),
        headers={**owner["headers"], "X-Clinic-Id": clinic_a["id"]},
    )

    member_b = _member(db, clinic_b["id"], ["admin"])
    resp = client.get(
        f"{API}/clinics/{clinic_b['id']}/patients",
        headers={**member_b["headers"], "X-Clinic-Id": clinic_b["id"]},
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_cross_clinic_detail_denied_without_consent(client, owner, db):
    clinic_a = _create_clinic(client, owner)
    clinic_b = _create_clinic(client, owner)
    created = client.post(
        f"{API}/clinics/{clinic_a['id']}/patients",
        json=_create_payload(),
        headers={**owner["headers"], "X-Clinic-Id": clinic_a["id"]},
    )
    patient_id = created.json()["patient_id"]

    member_b = _member(db, clinic_b["id"], ["admin"])
    resp = client.get(
        f"{API}/clinics/{clinic_b['id']}/patients/{patient_id}",
        headers={**member_b["headers"], "X-Clinic-Id": clinic_b["id"]},
    )
    assert resp.status_code == 403


def test_cross_clinic_detail_allowed_with_active_consent(client, owner, db):
    clinic_a = _create_clinic(client, owner)
    clinic_b = _create_clinic(client, owner)
    created = client.post(
        f"{API}/clinics/{clinic_a['id']}/patients",
        json=_create_payload(),
        headers={**owner["headers"], "X-Clinic-Id": clinic_a["id"]},
    )
    patient_id = created.json()["patient_id"]

    db.add(
        Consent(
            patient_id=patient_id,
            consent_type="clinic_admin_record",
            data_scope="administrative",
            granted_to=clinic_b["id"],
        )
    )
    db.commit()

    member_b = _member(db, clinic_b["id"], ["admin"])
    resp = client.get(
        f"{API}/clinics/{clinic_b['id']}/patients/{patient_id}",
        headers={**member_b["headers"], "X-Clinic-Id": clinic_b["id"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["patient_id"] == patient_id
    assert body["patient_code"] is None  # no own-clinic relationship row


def test_multi_clinic_membership_scopes_to_active_clinic(client, owner, db):
    clinic_a = _create_clinic(client, owner)
    clinic_b = _create_clinic(client, owner)
    user = _make_user(db, role=UserRole.CLINIC_ADMIN)
    _add_membership(db, user_id=user["user_id"], clinic_id=clinic_a["id"], roles=["admin"])
    _add_membership(db, user_id=user["user_id"], clinic_id=clinic_b["id"], roles=["admin"])

    client.post(
        f"{API}/clinics/{clinic_a['id']}/patients",
        json=_create_payload(),
        headers={**user["headers"], "X-Clinic-Id": clinic_a["id"]},
    )

    resp_a = client.get(
        f"{API}/clinics/{clinic_a['id']}/patients",
        headers={**user["headers"], "X-Clinic-Id": clinic_a["id"]},
    )
    resp_b = client.get(
        f"{API}/clinics/{clinic_b['id']}/patients",
        headers={**user["headers"], "X-Clinic-Id": clinic_b["id"]},
    )
    assert resp_a.json()["total"] == 1
    assert resp_b.json()["total"] == 0


def test_revoked_membership_loses_access_immediately(client, owner, db):
    clinic = _create_clinic(client, owner)
    member = _member(db, clinic["id"], ["admin"])
    ok = client.get(
        f"{API}/clinics/{clinic['id']}/patients",
        headers={**member["headers"], "X-Clinic-Id": clinic["id"]},
    )
    assert ok.status_code == 200

    row = db.query(ClinicMembership).filter_by(
        user_id=member["user_id"], clinic_id=clinic["id"]
    ).one()
    row.status = "removed"
    db.commit()

    denied = client.get(
        f"{API}/clinics/{clinic['id']}/patients",
        headers={**member["headers"], "X-Clinic-Id": clinic["id"]},
    )
    assert denied.status_code == 403


def test_idor_clinic_id_path_mismatch_rejected(client, owner, db):
    clinic_a = _create_clinic(client, owner)
    clinic_b = _create_clinic(client, owner)
    member_a = _member(db, clinic_a["id"], ["admin"])
    resp = client.get(
        f"{API}/clinics/{clinic_b['id']}/patients",
        headers={**member_a["headers"], "X-Clinic-Id": clinic_a["id"]},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Role matrix / field-level filtering
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("roles", [["owner"], ["admin"], ["doctor"], ["nurse"], ["receptionist"]])
def test_full_access_roles_see_admin_fields(client, owner, db, roles):
    clinic = _create_clinic(client, owner)
    client.post(
        f"{API}/clinics/{clinic['id']}/patients", json=_create_payload(), headers=owner["headers"]
    )
    member = _member(db, clinic["id"], roles)
    resp = client.get(
        f"{API}/clinics/{clinic['id']}/patients",
        headers={**member["headers"], "X-Clinic-Id": clinic["id"]},
    )
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert "dob" in item and "address" in item and "internal_notes" in item


def test_care_coordinator_sees_narrow_shape_only(client, owner, db):
    clinic = _create_clinic(client, owner)
    client.post(
        f"{API}/clinics/{clinic['id']}/patients", json=_create_payload(), headers=owner["headers"]
    )
    member = _member(db, clinic["id"], ["care_coordinator"])
    resp = client.get(
        f"{API}/clinics/{clinic['id']}/patients",
        headers={**member["headers"], "X-Clinic-Id": clinic["id"]},
    )
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert "dob" not in item
    assert "address" not in item
    assert "internal_notes" not in item
    assert item["full_name"] == "Trần Thị B"


def test_accountant_denied_roster_access(client, owner, db):
    clinic = _create_clinic(client, owner)
    member = _member(db, clinic["id"], ["accountant"])
    resp = client.get(
        f"{API}/clinics/{clinic['id']}/patients",
        headers={**member["headers"], "X-Clinic-Id": clinic["id"]},
    )
    assert resp.status_code == 403


def test_receptionist_can_create_and_patch(client, owner, db):
    """RBAC_MATRIX.md's Patient admin record row + BRD §6.2 ("Receptionist:
    Tạo/sửa hồ sơ hành chính") both grant Receptionist full read+write here
    (Codex review P1 fix — status/internal_notes PATCH was incorrectly
    Owner/Admin-only)."""
    clinic = _create_clinic(client, owner)
    reception = _member(db, clinic["id"], ["receptionist"])
    created = client.post(
        f"{API}/clinics/{clinic['id']}/patients",
        json=_create_payload(),
        headers={**reception["headers"], "X-Clinic-Id": clinic["id"]},
    )
    assert created.status_code == 201, created.text

    patch = client.patch(
        f"{API}/clinics/{clinic['id']}/patients/{created.json()['patient_id']}",
        json={"internal_notes": "note"},
        headers={**reception["headers"], "X-Clinic-Id": clinic["id"]},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["internal_notes"] == "note"


def test_accountant_denied_patch(client, owner, db):
    clinic = _create_clinic(client, owner)
    created = client.post(
        f"{API}/clinics/{clinic['id']}/patients", json=_create_payload(), headers=owner["headers"]
    )
    accountant = _member(db, clinic["id"], ["accountant"])
    patch = client.patch(
        f"{API}/clinics/{clinic['id']}/patients/{created.json()['patient_id']}",
        json={"internal_notes": "note"},
        headers={**accountant["headers"], "X-Clinic-Id": clinic["id"]},
    )
    assert patch.status_code == 403


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


def test_owner_can_update_status_and_notes(client, owner):
    clinic = _create_clinic(client, owner)
    created = client.post(
        f"{API}/clinics/{clinic['id']}/patients", json=_create_payload(), headers=owner["headers"]
    )
    patient_id = created.json()["patient_id"]
    resp = client.patch(
        f"{API}/clinics/{clinic['id']}/patients/{patient_id}",
        json={"status": "inactive", "internal_notes": "Ngưng khám"},
        headers=owner["headers"],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "inactive"
    assert resp.json()["internal_notes"] == "Ngưng khám"


def test_update_invalid_status_rejected(client, owner):
    clinic = _create_clinic(client, owner)
    created = client.post(
        f"{API}/clinics/{clinic['id']}/patients", json=_create_payload(), headers=owner["headers"]
    )
    resp = client.patch(
        f"{API}/clinics/{clinic['id']}/patients/{created.json()['patient_id']}",
        json={"status": "bogus"},
        headers=owner["headers"],
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Pagination / audit isolation
# ---------------------------------------------------------------------------


def test_roster_pagination_bounded(client, owner):
    clinic = _create_clinic(client, owner)
    for i in range(3):
        client.post(
            f"{API}/clinics/{clinic['id']}/patients",
            json=_create_payload(full_name=f"BN {i}", phone=_random_phone()),
            headers=owner["headers"],
        )
    resp = client.get(
        f"{API}/clinics/{clinic['id']}/patients", params={"limit": 2}, headers=owner["headers"]
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2


def test_audit_rows_tenant_isolated(client, owner, db):
    from app.models.governance import AuditLog

    clinic_a = _create_clinic(client, owner)
    clinic_b = _create_clinic(client, owner)
    created = client.post(
        f"{API}/clinics/{clinic_a['id']}/patients",
        json=_create_payload(),
        headers={**owner["headers"], "X-Clinic-Id": clinic_a["id"]},
    )
    relationship_id = created.json()["id"]
    # Filter by this specific relationship's resource_id, not a global count —
    # the test DB persists across the whole run (no per-test truncation, same
    # convention as the rest of this file), so other tests' audit rows for the
    # same action are also present.
    rows = (
        db.query(AuditLog)
        .filter_by(action="clinic_patient_create", resource_id=relationship_id)
        .all()
    )
    assert len(rows) == 1
    assert rows[0].clinic_id == clinic_a["id"]
    assert rows[0].clinic_id != clinic_b["id"]


# ---------------------------------------------------------------------------
# Clinical Copilot guard activation (assert_doctor_clinic_scope_for_patient)
# ---------------------------------------------------------------------------


class _StubProvider:
    provider_name = "claude"
    model_name = "stub-1.0"
    max_context_tokens = 32_000
    supports_streaming = False
    supports_tool_use = False

    async def chat(self, *args, **kwargs):
        from app.ai.providers.base import ChatResponse

        return ChatResponse(
            content="{}", tool_calls=None, input_tokens=1, output_tokens=1,
            model_used=self.model_name, finish_reason="stop", latency_ms=1,
            provider=self.provider_name,
        )

    async def chat_stream(self, *args, **kwargs):
        raise NotImplementedError
        yield  # pragma: no cover

    async def cancel(self, request_id: str) -> bool:
        return True

    async def estimate_tokens(self, text: str) -> int:
        return 1

    def health_check(self):
        from app.ai.providers.base import ProviderHealthStatus

        return ProviderHealthStatus(provider=self.provider_name, is_alive=True)


def _doctor_with_membership(db, clinic_id: str) -> dict:
    doctor = _make_user(db, role=UserRole.DOCTOR)
    _add_membership(db, user_id=doctor["user_id"], clinic_id=clinic_id, roles=["doctor"])
    token = create_access_token(subject=doctor["user_id"], role="doctor", mfa=True)
    doctor["headers"] = {"Authorization": f"Bearer {token}"}
    return doctor


def test_clinical_copilot_guard_activates_on_linked_patient(client, owner, db, monkeypatch):
    from app.ai.registry import ProviderRegistry

    monkeypatch.setenv("FEATURE_CLINICAL_COPILOT", "true")
    registry = ProviderRegistry()
    registry.register(_StubProvider())
    monkeypatch.setattr("app.services.clinical_copilot.get_registry", lambda: registry)

    clinic_a = _create_clinic(client, owner)
    clinic_b = _create_clinic(client, owner)
    created = client.post(
        f"{API}/clinics/{clinic_a['id']}/patients",
        json=_create_payload(),
        headers={**owner["headers"], "X-Clinic-Id": clinic_a["id"]},
    )
    patient_id = created.json()["patient_id"]

    doctor_a = _doctor_with_membership(db, clinic_a["id"])
    doctor_b = _doctor_with_membership(db, clinic_b["id"])
    db.add(
        Consent(
            patient_id=patient_id, consent_type="doctor_access", data_scope="profile",
            granted_to=doctor_a["user_id"],
        )
    )
    db.add(
        Consent(
            patient_id=patient_id, consent_type="ai_use", data_scope="clinical_copilot",
            granted_to=doctor_a["user_id"],
        )
    )
    db.add(
        Consent(
            patient_id=patient_id, consent_type="doctor_access", data_scope="profile",
            granted_to=doctor_b["user_id"],
        )
    )
    db.add(
        Consent(
            patient_id=patient_id, consent_type="ai_use", data_scope="clinical_copilot",
            granted_to=doctor_b["user_id"],
        )
    )
    db.commit()

    denied = client.post(
        f"{API}/doctor/patients/{patient_id}/ai-summary", json={}, headers=doctor_b["headers"]
    )
    assert denied.status_code == 403, denied.text

    allowed = client.post(
        f"{API}/doctor/patients/{patient_id}/ai-summary", json={}, headers=doctor_a["headers"]
    )
    assert allowed.status_code in (200, 201), allowed.text
