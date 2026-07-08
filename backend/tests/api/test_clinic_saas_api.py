"""Clinic SaaS Phase C0 — smoke tests for the new multi-tenant foundation.

Covers the surface built in this phase: feature-flag fail-closed gate,
onboarding (clinic + owner membership + trial subscription), tenant-scoped
CRUD (branches/services), the invitation lifecycle + last-owner guard,
subscription/entitlements read, cross-tenant isolation (BOLA/IDOR), and the
explicit platform-override suspend/restore path. Not the full Agent-G test
matrix — enough to prove each new primitive actually works end to end.
"""

from __future__ import annotations

import os

import pytest
from app.core.security import create_access_token
from app.models.user import User, UserRole


def _make_user(db, *, role: UserRole = UserRole.CLINIC_ADMIN) -> dict:
    user = User(
        email=f"c0-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=role,
        full_name="Clinic SaaS Test User",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role=role.value, mfa=True)
    return {"user_id": user.id, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def owner(db):
    return _make_user(db)


@pytest.fixture
def other_user(db):
    return _make_user(db)


@pytest.fixture
def super_admin(db):
    return _make_user(db, role=UserRole.SUPER_ADMIN)


def _create_clinic(client, owner, name="Phòng khám Test") -> dict:
    resp = client.post("/api/v1/clinics", json={"name": name}, headers=owner["headers"])
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Feature flag gate
# ---------------------------------------------------------------------------


def test_clinic_saas_disabled_returns_503(client, owner, monkeypatch):
    monkeypatch.setenv("FEATURE_CLINIC_SAAS", "false")
    resp = client.post("/api/v1/clinics", json={"name": "X"}, headers=owner["headers"])
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Onboarding
# ---------------------------------------------------------------------------


def test_create_clinic_onboards_owner_and_trial_subscription(client, owner):
    clinic = _create_clinic(client, owner)
    assert clinic["status"] == "trial"

    me = client.get("/api/v1/clinics/me", headers=owner["headers"])
    assert me.status_code == 200
    assert me.json()["id"] == clinic["id"]

    sub = client.get(
        f"/api/v1/clinics/{clinic['id']}/subscription", headers=owner["headers"]
    )
    assert sub.status_code == 200
    body = sub.json()
    assert body["subscription"]["status"] == "trial"
    assert body["plan"]["code"] == "trial"
    assert body["entitlements"]["max_branches"] >= 1


def test_get_clinic_requires_active_membership(client, owner, other_user):
    clinic = _create_clinic(client, owner)
    # other_user has no membership anywhere -> 403, not a silent empty result.
    resp = client.get(
        f"/api/v1/clinics/{clinic['id']}",
        headers={**other_user["headers"], "X-Clinic-Id": clinic["id"]},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Settings update (role-gated)
# ---------------------------------------------------------------------------


def test_update_clinic_settings_owner_ok(client, owner):
    clinic = _create_clinic(client, owner)
    resp = client.patch(
        f"/api/v1/clinics/{clinic['id']}",
        json={"legal_name": "Công ty TNHH Test"},
        headers=owner["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["legal_name"] == "Công ty TNHH Test"


# ---------------------------------------------------------------------------
# Branches
# ---------------------------------------------------------------------------


def test_branch_crud(client, owner):
    clinic = _create_clinic(client, owner)
    create = client.post(
        f"/api/v1/clinics/{clinic['id']}/branches",
        json={"name": "Chi nhánh 1", "working_hours": {"mon": "08:00-17:00"}},
        headers=owner["headers"],
    )
    assert create.status_code == 201, create.text
    branch = create.json()

    listed = client.get(
        f"/api/v1/clinics/{clinic['id']}/branches", headers=owner["headers"]
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    updated = client.patch(
        f"/api/v1/clinics/{clinic['id']}/branches/{branch['id']}",
        json={"phone": "0900000000"},
        headers=owner["headers"],
    )
    assert updated.status_code == 200
    assert updated.json()["phone"] == "0900000000"

    archived = client.post(
        f"/api/v1/clinics/{clinic['id']}/branches/{branch['id']}/status",
        json={"status": "archived"},
        headers=owner["headers"],
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    # Duplicate branch name within the same clinic is rejected (unique constraint).
    dup = client.post(
        f"/api/v1/clinics/{clinic['id']}/branches",
        json={"name": "Chi nhánh 1", "working_hours": {}},
        headers=owner["headers"],
    )
    assert dup.status_code >= 400


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------


def test_service_catalog_crud(client, owner):
    clinic = _create_clinic(client, owner)
    create = client.post(
        f"/api/v1/clinics/{clinic['id']}/services",
        json={"name": "Khám tổng quát", "price": 300000},
        headers=owner["headers"],
    )
    assert create.status_code == 201, create.text
    service = create.json()

    updated = client.patch(
        f"/api/v1/clinics/{clinic['id']}/services/{service['id']}",
        json={"price": 350000},
        headers=owner["headers"],
    )
    assert updated.status_code == 200
    assert updated.json()["price"] == 350000.0

    listed = client.get(
        f"/api/v1/clinics/{clinic['id']}/services", headers=owner["headers"]
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1


# ---------------------------------------------------------------------------
# Invitation lifecycle + last-owner guard
# ---------------------------------------------------------------------------


def test_invitation_accept_creates_membership(client, owner, other_user, db):
    clinic = _create_clinic(client, owner)
    invite = client.post(
        f"/api/v1/clinics/{clinic['id']}/invitations",
        json={"roles": ["nurse"], "invited_email": "nurse@example.com"},
        headers=owner["headers"],
    )
    assert invite.status_code == 201, invite.text
    raw_token = invite.json()["raw_token"]

    accept = client.post(
        "/api/v1/clinic-invitations/accept",
        json={"token": raw_token},
        headers=other_user["headers"],
    )
    assert accept.status_code == 200, accept.text
    membership = accept.json()
    assert membership["roles"] == ["nurse"]
    assert membership["status"] == "active"

    # Token is single-use — a second accept fails.
    accept_again = client.post(
        "/api/v1/clinic-invitations/accept",
        json={"token": raw_token},
        headers=other_user["headers"],
    )
    assert accept_again.status_code == 410


def test_duplicate_pending_invitation_rejected(client, owner):
    clinic = _create_clinic(client, owner)
    first = client.post(
        f"/api/v1/clinics/{clinic['id']}/invitations",
        json={"roles": ["nurse"], "invited_email": "dup@example.com"},
        headers=owner["headers"],
    )
    assert first.status_code == 201
    second = client.post(
        f"/api/v1/clinics/{clinic['id']}/invitations",
        json={"roles": ["nurse"], "invited_email": "dup@example.com"},
        headers=owner["headers"],
    )
    assert second.status_code == 409


def test_last_owner_cannot_be_demoted(client, owner):
    clinic = _create_clinic(client, owner)
    members = client.get(
        f"/api/v1/clinics/{clinic['id']}/members", headers=owner["headers"]
    ).json()
    owner_membership = next(m for m in members["items"] if "owner" in m["roles"])

    resp = client.patch(
        f"/api/v1/clinics/{clinic['id']}/members/{owner_membership['id']}",
        json={"roles": ["admin"]},
        headers=owner["headers"],
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Cross-tenant isolation
# ---------------------------------------------------------------------------


def test_cross_tenant_isolation_on_branches(client, owner, other_user):
    _create_clinic(client, owner, name="Clinic A")
    clinic_b = _create_clinic(client, other_user, name="Clinic B")

    # owner (member of clinic_a only) tries to read clinic_b's branches by
    # spoofing X-Clinic-Id — must be rejected, never return clinic_b's data.
    resp = client.get(
        f"/api/v1/clinics/{clinic_b['id']}/branches",
        headers={**owner["headers"], "X-Clinic-Id": clinic_b["id"]},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Platform override (suspend/restore)
# ---------------------------------------------------------------------------


def test_platform_override_suspend_and_restore(client, owner, super_admin):
    clinic = _create_clinic(client, owner)

    suspend = client.post(
        f"/api/v1/clinics/{clinic['id']}/suspend",
        headers={**super_admin["headers"], "X-Clinic-Id": clinic["id"]},
    )
    assert suspend.status_code == 200, suspend.text
    assert suspend.json()["status"] == "suspended"

    # A suspended clinic blocks writes for its own Owner.
    blocked = client.patch(
        f"/api/v1/clinics/{clinic['id']}",
        json={"legal_name": "Should Fail"},
        headers=owner["headers"],
    )
    assert blocked.status_code == 403

    restore = client.post(
        f"/api/v1/clinics/{clinic['id']}/restore",
        headers={**super_admin["headers"], "X-Clinic-Id": clinic["id"]},
    )
    assert restore.status_code == 200
    assert restore.json()["status"] == "active"


def test_platform_override_denied_for_non_admin(client, owner):
    clinic = _create_clinic(client, owner)
    resp = client.post(
        f"/api/v1/clinics/{clinic['id']}/suspend",
        headers={**owner["headers"], "X-Clinic-Id": clinic["id"]},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Subscription plan catalog
# ---------------------------------------------------------------------------


def test_subscription_plan_catalog_seeded(client, owner):
    resp = client.get("/api/v1/subscription-plans", headers=owner["headers"])
    assert resp.status_code == 200
    codes = {p["code"] for p in resp.json()}
    assert {"trial", "basic", "professional", "enterprise"} <= codes


# ---------------------------------------------------------------------------
# Agent G — extended test matrix (invitation lifecycle, multi-role/multi-clinic
# membership, cross-tenant isolation, path-tamper, suspend read/write split,
# branch status, pagination, controlled errors, audit/no-PHI-leak).
# ---------------------------------------------------------------------------


def _invite(client, owner_headers, clinic_id, *, roles, invited_email=None, invited_phone=None,
            branch_ids=None):
    payload = {"roles": roles}
    if invited_email:
        payload["invited_email"] = invited_email
    if invited_phone:
        payload["invited_phone"] = invited_phone
    if branch_ids is not None:
        payload["branch_ids"] = branch_ids
    resp = client.post(
        f"/api/v1/clinics/{clinic_id}/invitations", json=payload, headers=owner_headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _accept(client, user_headers, raw_token):
    return client.post(
        "/api/v1/clinic-invitations/accept", json={"token": raw_token}, headers=user_headers
    )


# --- Invitation lifecycle: revoke / expiry / duplicate-by-phone -----------


def test_revoked_pending_invitation_blocks_acceptance(client, owner, other_user):
    clinic = _create_clinic(client, owner)
    invite = _invite(client, owner["headers"], clinic["id"], roles=["nurse"],
                      invited_email="revoke-me@example.com")

    # Find the invitation id via the list endpoint (create response doesn't
    # echo the id under a separate field beyond `id` itself).
    listed = client.get(
        f"/api/v1/clinics/{clinic['id']}/invitations", headers=owner["headers"]
    ).json()
    invitation_id = next(i["id"] for i in listed["items"] if i["id"] == invite["id"])

    revoke = client.post(
        f"/api/v1/clinics/{clinic['id']}/invitations/{invitation_id}/revoke",
        headers=owner["headers"],
    )
    assert revoke.status_code == 200, revoke.text
    assert revoke.json()["status"] == "revoked"

    accept = _accept(client, other_user["headers"], invite["raw_token"])
    assert accept.status_code == 410


def test_revoking_already_revoked_invitation_is_conflict(client, owner):
    clinic = _create_clinic(client, owner)
    invite = _invite(client, owner["headers"], clinic["id"], roles=["nurse"],
                      invited_email="revoke-twice@example.com")
    first = client.post(
        f"/api/v1/clinics/{clinic['id']}/invitations/{invite['id']}/revoke",
        headers=owner["headers"],
    )
    assert first.status_code == 200
    second = client.post(
        f"/api/v1/clinics/{clinic['id']}/invitations/{invite['id']}/revoke",
        headers=owner["headers"],
    )
    assert second.status_code == 409


def test_expired_invitation_blocks_acceptance_and_flips_status(client, owner, other_user, db):
    from app.models.clinic import ClinicInvitation, ClinicInvitationStatus

    clinic = _create_clinic(client, owner)
    invite = _invite(client, owner["headers"], clinic["id"], roles=["nurse"],
                      invited_email="expired@example.com")

    row = db.get(ClinicInvitation, invite["id"])
    assert row is not None
    row.expires_at = row.expires_at.replace(year=2000)  # force into the past
    db.commit()

    accept = _accept(client, other_user["headers"], invite["raw_token"])
    assert accept.status_code == 410

    db.expire_all()
    refreshed = db.get(ClinicInvitation, invite["id"])
    assert refreshed.status == ClinicInvitationStatus.EXPIRED


def test_duplicate_pending_invitation_by_phone_rejected(client, owner):
    clinic = _create_clinic(client, owner)
    first = client.post(
        f"/api/v1/clinics/{clinic['id']}/invitations",
        json={"roles": ["nurse"], "invited_phone": "0912345678"},
        headers=owner["headers"],
    )
    assert first.status_code == 201, first.text
    second = client.post(
        f"/api/v1/clinics/{clinic['id']}/invitations",
        json={"roles": ["nurse"], "invited_phone": "0912345678"},
        headers=owner["headers"],
    )
    assert second.status_code == 409


def test_invitation_reoffered_after_revoke_is_allowed(client, owner):
    """The partial unique index only constrains *pending* rows — once the
    first is revoked, a fresh pending invite to the same email is allowed."""
    clinic = _create_clinic(client, owner)
    first = _invite(client, owner["headers"], clinic["id"], roles=["nurse"],
                     invited_email="reoffer@example.com")
    client.post(
        f"/api/v1/clinics/{clinic['id']}/invitations/{first['id']}/revoke",
        headers=owner["headers"],
    )
    second = client.post(
        f"/api/v1/clinics/{clinic['id']}/invitations",
        json={"roles": ["nurse"], "invited_email": "reoffer@example.com"},
        headers=owner["headers"],
    )
    assert second.status_code == 201, second.text


# --- Multi-role / multi-clinic membership ----------------------------------


def test_membership_holds_multiple_roles_simultaneously(client, owner, other_user):
    clinic = _create_clinic(client, owner)
    invite = _invite(client, owner["headers"], clinic["id"], roles=["nurse", "care_coordinator"],
                      invited_email="multi-role@example.com")
    accept = _accept(client, other_user["headers"], invite["raw_token"])
    assert accept.status_code == 200
    membership = accept.json()
    assert set(membership["roles"]) == {"nurse", "care_coordinator"}

    # Both roles independently qualify for branch read access (RBAC_MATRIX M02).
    listed = client.get(
        f"/api/v1/clinics/{clinic['id']}/branches",
        headers={**other_user["headers"], "X-Clinic-Id": clinic["id"]},
    )
    assert listed.status_code == 200


def test_user_has_independent_role_sets_across_two_clinics(client, owner, other_user):
    """other_user is Owner of clinic A (self-onboarded) and Nurse of clinic B
    (invited) — roles at A must never leak into what's permitted at B."""
    clinic_a = _create_clinic(client, other_user, name="Clinic A - independent roles")
    clinic_b = _create_clinic(client, owner, name="Clinic B - independent roles")

    invite = _invite(client, owner["headers"], clinic_b["id"], roles=["nurse"],
                      invited_email="cross-clinic@example.com")
    accept = _accept(client, other_user["headers"], invite["raw_token"])
    assert accept.status_code == 200
    assert accept.json()["roles"] == ["nurse"]

    # At clinic A, other_user is Owner -> can update settings.
    update_a = client.patch(
        f"/api/v1/clinics/{clinic_a['id']}",
        json={"legal_name": "A Co"},
        headers={**other_user["headers"], "X-Clinic-Id": clinic_a["id"]},
    )
    assert update_a.status_code == 200

    # At clinic B, other_user is only Nurse -> forbidden from the same action.
    update_b = client.patch(
        f"/api/v1/clinics/{clinic_b['id']}",
        json={"legal_name": "B Co"},
        headers={**other_user["headers"], "X-Clinic-Id": clinic_b["id"]},
    )
    assert update_b.status_code == 403


def test_multiple_active_memberships_without_header_requires_explicit_selection(
    client, owner, other_user
):
    clinic_a = _create_clinic(client, other_user, name="Clinic A - explicit select")
    clinic_b = _create_clinic(client, owner, name="Clinic B - explicit select")
    invite = _invite(client, owner["headers"], clinic_b["id"], roles=["nurse"],
                      invited_email="explicit-select@example.com")
    _accept(client, other_user["headers"], invite["raw_token"])

    # other_user now has 2 active memberships; omitting X-Clinic-Id must 400,
    # never silently guess one.
    resp = client.get("/api/v1/clinics/me", headers=other_user["headers"])
    assert resp.status_code == 400
    del clinic_a  # referenced only to document the 2-membership setup


# --- Cross-clinic isolation (highest priority) + client clinic_id tamper --


def test_cross_tenant_isolation_on_members(client, owner, other_user):
    _create_clinic(client, owner, name="Clinic A - members isolation")
    clinic_b = _create_clinic(client, other_user, name="Clinic B - members isolation")
    resp = client.get(
        f"/api/v1/clinics/{clinic_b['id']}/members",
        headers={**owner["headers"], "X-Clinic-Id": clinic_b["id"]},
    )
    assert resp.status_code == 403


def test_cross_tenant_isolation_on_services(client, owner, other_user):
    _create_clinic(client, owner, name="Clinic A - services isolation")
    clinic_b = _create_clinic(client, other_user, name="Clinic B - services isolation")
    resp = client.get(
        f"/api/v1/clinics/{clinic_b['id']}/services",
        headers={**owner["headers"], "X-Clinic-Id": clinic_b["id"]},
    )
    assert resp.status_code == 403


def test_cross_tenant_isolation_on_settings_update(client, owner, other_user):
    _create_clinic(client, owner, name="Clinic A - settings isolation")
    clinic_b = _create_clinic(client, other_user, name="Clinic B - settings isolation")
    resp = client.patch(
        f"/api/v1/clinics/{clinic_b['id']}",
        json={"legal_name": "Should not apply"},
        headers={**owner["headers"], "X-Clinic-Id": clinic_b["id"]},
    )
    assert resp.status_code == 403


def test_path_clinic_id_mismatch_rejected_even_with_valid_own_tenant(client, owner, other_user):
    """owner's TenantContext resolves to clinic_a (their only membership, no
    X-Clinic-Id needed); pointing the PATH at clinic_b must still 403 via
    `assert_path_clinic_matches_tenant`, proving a client-supplied path
    clinic_id is never trusted on its own even when the header is absent."""
    clinic_a = _create_clinic(client, owner, name="Clinic A - path tamper")
    clinic_b = _create_clinic(client, other_user, name="Clinic B - path tamper")
    del clinic_a

    resp = client.get(f"/api/v1/clinics/{clinic_b['id']}", headers=owner["headers"])
    assert resp.status_code == 403

    resp2 = client.patch(
        f"/api/v1/clinics/{clinic_b['id']}",
        json={"legal_name": "tampered"},
        headers=owner["headers"],
    )
    assert resp2.status_code == 403


def test_branch_create_rejects_body_for_wrong_clinic_path(client, owner, other_user):
    clinic_a = _create_clinic(client, owner, name="Clinic A - branch tamper")
    clinic_b = _create_clinic(client, other_user, name="Clinic B - branch tamper")
    del clinic_a
    resp = client.post(
        f"/api/v1/clinics/{clinic_b['id']}/branches",
        json={"name": "Sneaky Branch", "working_hours": {}},
        headers=owner["headers"],
    )
    assert resp.status_code == 403


# --- Suspended/deactivated read-vs-write split ------------------------------


def test_suspended_clinic_allows_reads_blocks_writes(client, owner, super_admin):
    clinic = _create_clinic(client, owner)
    client.post(
        f"/api/v1/clinics/{clinic['id']}/branches",
        json={"name": "Pre-suspend Branch", "working_hours": {}},
        headers=owner["headers"],
    )
    suspend = client.post(
        f"/api/v1/clinics/{clinic['id']}/suspend",
        headers={**super_admin["headers"], "X-Clinic-Id": clinic["id"]},
    )
    assert suspend.status_code == 200

    # Reads still work for the clinic's own (still-active) Owner membership.
    get_clinic = client.get(f"/api/v1/clinics/{clinic['id']}", headers=owner["headers"])
    assert get_clinic.status_code == 200
    list_branches = client.get(
        f"/api/v1/clinics/{clinic['id']}/branches", headers=owner["headers"]
    )
    assert list_branches.status_code == 200
    assert list_branches.json()["total"] == 1

    # Writes are blocked: settings update, branch create, service create.
    assert client.patch(
        f"/api/v1/clinics/{clinic['id']}", json={"legal_name": "x"}, headers=owner["headers"]
    ).status_code == 403
    assert client.post(
        f"/api/v1/clinics/{clinic['id']}/branches",
        json={"name": "Blocked Branch", "working_hours": {}},
        headers=owner["headers"],
    ).status_code == 403
    assert client.post(
        f"/api/v1/clinics/{clinic['id']}/services",
        json={"name": "Blocked Service", "price": 1000},
        headers=owner["headers"],
    ).status_code == 403


def test_deactivated_clinic_blocks_writes(client, owner):
    clinic = _create_clinic(client, owner)
    deactivate = client.post(
        f"/api/v1/clinics/{clinic['id']}/deactivate", headers=owner["headers"]
    )
    assert deactivate.status_code == 200
    assert deactivate.json()["status"] == "deactivated"

    blocked = client.patch(
        f"/api/v1/clinics/{clinic['id']}", json={"legal_name": "x"}, headers=owner["headers"]
    )
    assert blocked.status_code == 403
    blocked_branch = client.post(
        f"/api/v1/clinics/{clinic['id']}/branches",
        json={"name": "Blocked", "working_hours": {}},
        headers=owner["headers"],
    )
    assert blocked_branch.status_code == 403


# --- Branch status transitions + branch-scoped membership ------------------


def test_branch_status_pause_and_invalid_value_rejected(client, owner):
    clinic = _create_clinic(client, owner)
    branch = client.post(
        f"/api/v1/clinics/{clinic['id']}/branches",
        json={"name": "Pausable Branch", "working_hours": {}},
        headers=owner["headers"],
    ).json()

    paused = client.post(
        f"/api/v1/clinics/{clinic['id']}/branches/{branch['id']}/status",
        json={"status": "paused"},
        headers=owner["headers"],
    )
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"

    invalid = client.post(
        f"/api/v1/clinics/{clinic['id']}/branches/{branch['id']}/status",
        json={"status": "deleted"},
        headers=owner["headers"],
    )
    assert invalid.status_code == 422


def test_membership_branch_ids_scoping_persists_and_updates(client, owner, other_user):
    clinic = _create_clinic(client, owner)
    branch1 = client.post(
        f"/api/v1/clinics/{clinic['id']}/branches",
        json={"name": "Branch One", "working_hours": {}},
        headers=owner["headers"],
    ).json()
    branch2 = client.post(
        f"/api/v1/clinics/{clinic['id']}/branches",
        json={"name": "Branch Two", "working_hours": {}},
        headers=owner["headers"],
    ).json()

    invite = _invite(
        client, owner["headers"], clinic["id"], roles=["nurse"],
        invited_email="branch-scoped@example.com", branch_ids=[branch1["id"]],
    )
    accept = _accept(client, other_user["headers"], invite["raw_token"])
    membership = accept.json()
    assert membership["branch_ids"] == [branch1["id"]]

    updated = client.patch(
        f"/api/v1/clinics/{clinic['id']}/members/{membership['id']}",
        json={"branch_ids": [branch1["id"], branch2["id"]]},
        headers=owner["headers"],
    )
    assert updated.status_code == 200
    assert set(updated.json()["branch_ids"]) == {branch1["id"], branch2["id"]}


# --- Subscription entitlement resolution + role gating ---------------------


def test_subscription_read_forbidden_for_role_without_read_access(client, owner, other_user):
    """RBAC_MATRIX M04: subscription is Owner ✓ / Admin+Accountant R / all
    other clinic roles ✗ — a Nurse must be forbidden from reading it."""
    clinic = _create_clinic(client, owner)
    invite = _invite(client, owner["headers"], clinic["id"], roles=["nurse"],
                      invited_email="nurse-no-sub-read@example.com")
    _accept(client, other_user["headers"], invite["raw_token"])

    resp = client.get(
        f"/api/v1/clinics/{clinic['id']}/subscription",
        headers={**other_user["headers"], "X-Clinic-Id": clinic["id"]},
    )
    assert resp.status_code == 403


def test_subscription_read_allowed_for_accountant(client, owner, other_user):
    clinic = _create_clinic(client, owner)
    invite = _invite(client, owner["headers"], clinic["id"], roles=["accountant"],
                      invited_email="accountant@example.com")
    _accept(client, other_user["headers"], invite["raw_token"])

    resp = client.get(
        f"/api/v1/clinics/{clinic['id']}/subscription",
        headers={**other_user["headers"], "X-Clinic-Id": clinic["id"]},
    )
    assert resp.status_code == 200
    assert resp.json()["entitlements"]["max_branches"] >= 1


# --- Platform admin: audited, not a silent bypass ---------------------------


def test_platform_admin_list_clinics_requires_platform_role_and_is_audited(
    client, owner, super_admin, db
):
    from app.models.governance import AuditLog

    _create_clinic(client, owner)

    denied = client.get("/api/v1/clinics", headers=owner["headers"])
    assert denied.status_code == 403

    allowed = client.get("/api/v1/clinics", headers=super_admin["headers"])
    assert allowed.status_code == 200
    assert allowed.json()["total"] >= 1

    audit_row = (
        db.query(AuditLog)
        .filter(
            AuditLog.action == "platform_admin_list_access",
            AuditLog.actor_id == super_admin["user_id"],
        )
        .order_by(AuditLog.timestamp.desc())
        .first()
    )
    assert audit_row is not None
    assert audit_row.actor_type == "admin"


def test_platform_override_suspend_writes_audit_row_with_clinic_and_actor(
    client, owner, super_admin, db
):
    from app.models.governance import AuditLog

    clinic = _create_clinic(client, owner)
    suspend = client.post(
        f"/api/v1/clinics/{clinic['id']}/suspend",
        headers={**super_admin["headers"], "X-Clinic-Id": clinic["id"]},
    )
    assert suspend.status_code == 200

    override_row = (
        db.query(AuditLog)
        .filter(
            AuditLog.action == "platform_cross_tenant_access",
            AuditLog.clinic_id == clinic["id"],
        )
        .first()
    )
    assert override_row is not None
    assert override_row.actor_id == super_admin["user_id"]
    assert override_row.severity == "warning"

    action_row = (
        db.query(AuditLog)
        .filter(AuditLog.action == "clinic_suspend", AuditLog.clinic_id == clinic["id"])
        .first()
    )
    assert action_row is not None
    assert action_row.actor_id == super_admin["user_id"]


# --- No PHI/ciphertext leak --------------------------------------------------


def test_audit_log_never_stores_invitation_email_or_raw_token(client, owner, db):
    from app.models.governance import AuditLog

    clinic = _create_clinic(client, owner)
    invite = _invite(
        client, owner["headers"], clinic["id"], roles=["nurse"],
        invited_email="secret-address@example.com",
    )
    row = (
        db.query(AuditLog)
        .filter(
            AuditLog.action == "clinic_invitation_create",
            AuditLog.resource_id == invite["id"],
        )
        .first()
    )
    assert row is not None
    # Only opaque ids/metadata are persisted — never the invitee's contact
    # info or the single-use raw token.
    assert row.resource_id == invite["id"]
    for field in (row.action, row.resource_type, row.actor_type, row.outcome, row.severity):
        assert "secret-address@example.com" not in str(field)
        assert invite["raw_token"] not in str(field)


def test_clinic_schemas_expose_no_patient_phi_columns():
    """Static guard: the clinic-saas response schemas must never grow a field
    that shadows a `PatientProfile` encrypted PHI column name — those models
    are architecturally disjoint in this phase (DATA_MODEL.md: "none of these
    columns carry PHI")."""
    from app.schemas.clinic import ClinicBranchOut, ClinicOut
    from app.schemas.clinic_membership import ClinicInvitationOut, ClinicMembershipOut
    from app.schemas.clinic_service import ClinicServiceOut
    from app.schemas.clinic_subscription import ClinicSubscriptionDetailOut

    patient_phi_fields = {
        "dob",
        "known_conditions",
        "allergies",
        "family_history",
        "lifestyle_profile",
    }
    for schema in (
        ClinicOut,
        ClinicBranchOut,
        ClinicMembershipOut,
        ClinicInvitationOut,
        ClinicServiceOut,
        ClinicSubscriptionDetailOut,
    ):
        field_names = set(schema.model_fields.keys())
        assert not (field_names & patient_phi_fields), (
            f"{schema.__name__} unexpectedly exposes a PHI-shaped field: "
            f"{field_names & patient_phi_fields}"
        )


# --- Controlled errors -------------------------------------------------------


def test_unauthenticated_request_returns_401_with_detail(client):
    resp = client.post("/api/v1/clinics", json={"name": "No Auth"})
    assert resp.status_code == 401
    assert resp.json().get("detail")


def test_invalid_payload_returns_422_with_detail(client, owner):
    resp = client.post("/api/v1/clinics", json={"name": ""}, headers=owner["headers"])
    assert resp.status_code == 422
    assert resp.json().get("detail")


def test_branch_not_found_returns_404_with_detail(client, owner):
    clinic = _create_clinic(client, owner)
    resp = client.patch(
        f"/api/v1/clinics/{clinic['id']}/branches/does-not-exist",
        json={"phone": "0900000000"},
        headers=owner["headers"],
    )
    assert resp.status_code == 404
    assert resp.json().get("detail")


# --- Pagination --------------------------------------------------------------


def test_branch_list_pagination_honors_skip_and_limit(client, owner):
    clinic = _create_clinic(client, owner)
    for i in range(3):
        resp = client.post(
            f"/api/v1/clinics/{clinic['id']}/branches",
            json={"name": f"Paginated Branch {i}", "working_hours": {}},
            headers=owner["headers"],
        )
        assert resp.status_code == 201

    page1 = client.get(
        f"/api/v1/clinics/{clinic['id']}/branches?skip=0&limit=2", headers=owner["headers"]
    ).json()
    assert page1["total"] == 3
    assert len(page1["items"]) == 2

    page2 = client.get(
        f"/api/v1/clinics/{clinic['id']}/branches?skip=2&limit=2", headers=owner["headers"]
    ).json()
    assert page2["total"] == 3
    assert len(page2["items"]) == 1

    page1_ids = {b["id"] for b in page1["items"]}
    page2_ids = {b["id"] for b in page2["items"]}
    assert page1_ids.isdisjoint(page2_ids)


def test_service_list_pagination_honors_limit(client, owner):
    clinic = _create_clinic(client, owner)
    for i in range(3):
        resp = client.post(
            f"/api/v1/clinics/{clinic['id']}/services",
            json={"name": f"Service {i}", "price": 1000 + i},
            headers=owner["headers"],
        )
        assert resp.status_code == 201

    listed = client.get(
        f"/api/v1/clinics/{clinic['id']}/services?limit=1", headers=owner["headers"]
    ).json()
    assert listed["total"] == 3
    assert len(listed["items"]) == 1


def test_member_and_invitation_list_pagination(client, owner, other_user):
    clinic = _create_clinic(client, owner)
    for i in range(2):
        _invite(client, owner["headers"], clinic["id"], roles=["nurse"],
                invited_email=f"page-member-{i}@example.com")

    invitations = client.get(
        f"/api/v1/clinics/{clinic['id']}/invitations?limit=1", headers=owner["headers"]
    ).json()
    assert invitations["total"] == 2
    assert len(invitations["items"]) == 1

    invite = _invite(client, owner["headers"], clinic["id"], roles=["nurse"],
                      invited_email="page-accept@example.com")
    _accept(client, other_user["headers"], invite["raw_token"])

    members = client.get(
        f"/api/v1/clinics/{clinic['id']}/members?limit=1", headers=owner["headers"]
    ).json()
    # Owner + the accepted member = 2 total, but limit=1 must cap the page.
    assert members["total"] == 2
    assert len(members["items"]) == 1
