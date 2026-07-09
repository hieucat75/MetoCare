"""Clinic SaaS C1 M05 — Services & Pricing catalog fields.

Covers the BRD `docs/brd/v2.0/m05-services-pricing.md` §5.3/§5.4/§5.5 delta
on top of the C0-shipped `ClinicService` CRUD (already smoke-tested in
`test_clinic_saas_api.py`): the new field set (code/specialty/duration/type/
doctor_ids/package fields), name+code uniqueness, doctor-scope validation,
branch-visibility filtering (AC-M05-03), and audited old->new price capture
(BR-M05-02). Also exercises this milestone's slice of
`docs/clinic-saas/MASTER_PROGRAM_PLAN.md` §7's mandatory security/tenant-
isolation test matrix for the fields introduced here.
"""

from __future__ import annotations

import os

import pytest
from app.core.security import create_access_token
from app.models.care import Doctor
from app.models.clinic import ClinicMembership
from app.models.user import User, UserRole


def _make_user(db, *, role: UserRole = UserRole.CLINIC_ADMIN) -> dict:
    user = User(
        email=f"m05-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=role,
        full_name="M05 Test User",
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


def _create_clinic(client, owner, name="Phòng khám M05 Test") -> dict:
    resp = client.post("/api/v1/clinics", json={"name": name}, headers=owner["headers"])
    assert resp.status_code == 201, resp.text
    return resp.json()


def _valid_service_payload(**overrides) -> dict:
    payload = {
        "name": "Khám nội tiết",
        "code": "SVC-M05-001",
        "specialty": "Nội tiết",
        "duration_minutes": 30,
        "price": 300000,
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Field validation
# ---------------------------------------------------------------------------


_PACKAGE_REQUIRED_KWARGS = {
    "type": "package",
    "duration_months": 6,
    "included_items": {"visit_count": 6, "lab_read_count": 2, "teleconsult_count": 0},
    "benefits": {"med_reminder": True, "followup_reminder": True, "metric_tracking": True},
    "cancellation_refund_policy": {"refund_pct_before_first_visit": 100},
}


def test_create_service_full_field_set(client, owner):
    clinic = _create_clinic(client, owner)
    resp = client.post(
        f"/api/v1/clinics/{clinic['id']}/services",
        json=_valid_service_payload(package_visit_count=6, **_PACKAGE_REQUIRED_KWARGS),
        headers=owner["headers"],
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["type"] == "package"
    assert body["included_items"]["visit_count"] == 6
    assert body["benefits"]["med_reminder"] is True


# ---------------------------------------------------------------------------
# Codex round-4 fix: type<->package-field consistency (Create + PATCH,
# merged-final-state invariant)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "package_field,value",
    [
        ("duration_months", 6),
        ("package_visit_count", 6),
        ("included_items", {"visit_count": 6}),
        ("benefits", {"med_reminder": True}),
        ("cancellation_refund_policy", {"refund_pct_before_first_visit": 100}),
    ],
)
def test_create_single_with_each_package_only_field_rejected(client, owner, package_field, value):
    clinic = _create_clinic(client, owner)
    resp = client.post(
        f"/api/v1/clinics/{clinic['id']}/services",
        json=_valid_service_payload(type="single", **{package_field: value}),
        headers=owner["headers"],
    )
    assert resp.status_code == 400, f"{package_field}: {resp.text}"


@pytest.mark.parametrize(
    "missing_field", ["duration_months", "included_items", "benefits", "cancellation_refund_policy"]
)
def test_create_package_missing_required_metadata_rejected(client, owner, missing_field):
    clinic = _create_clinic(client, owner)
    kwargs = {k: v for k, v in _PACKAGE_REQUIRED_KWARGS.items() if k != missing_field}
    resp = client.post(
        f"/api/v1/clinics/{clinic['id']}/services",
        json=_valid_service_payload(**kwargs),
        headers=owner["headers"],
    )
    assert resp.status_code == 400, f"missing {missing_field}: {resp.text}"


def test_patch_single_adding_package_only_field_rejected(client, owner):
    clinic = _create_clinic(client, owner)
    created = client.post(
        f"/api/v1/clinics/{clinic['id']}/services",
        json=_valid_service_payload(),  # type=single default
        headers=owner["headers"],
    ).json()

    resp = client.patch(
        f"/api/v1/clinics/{clinic['id']}/services/{created['id']}",
        json={"duration_months": 6},
        headers=owner["headers"],
    )
    assert resp.status_code == 400, resp.text


def test_patch_package_clearing_required_metadata_rejected(client, owner):
    clinic = _create_clinic(client, owner)
    created = client.post(
        f"/api/v1/clinics/{clinic['id']}/services",
        json=_valid_service_payload(**_PACKAGE_REQUIRED_KWARGS),
        headers=owner["headers"],
    ).json()

    resp = client.patch(
        f"/api/v1/clinics/{clinic['id']}/services/{created['id']}",
        json={"included_items": None},
        headers=owner["headers"],
    )
    assert resp.status_code == 400, resp.text


def test_patch_package_to_single_while_package_fields_remain_rejected(client, owner):
    clinic = _create_clinic(client, owner)
    created = client.post(
        f"/api/v1/clinics/{clinic['id']}/services",
        json=_valid_service_payload(**_PACKAGE_REQUIRED_KWARGS),
        headers=owner["headers"],
    ).json()

    # type=single without also clearing duration_months/included_items/etc.
    # in the same request -> merged final state still has package fields.
    resp = client.patch(
        f"/api/v1/clinics/{clinic['id']}/services/{created['id']}",
        json={"type": "single"},
        headers=owner["headers"],
    )
    assert resp.status_code == 400, resp.text


def test_patch_single_to_package_missing_required_metadata_rejected(client, owner):
    clinic = _create_clinic(client, owner)
    created = client.post(
        f"/api/v1/clinics/{clinic['id']}/services",
        json=_valid_service_payload(),  # type=single, no package fields
        headers=owner["headers"],
    ).json()

    resp = client.patch(
        f"/api/v1/clinics/{clinic['id']}/services/{created['id']}",
        json={"type": "package"},
        headers=owner["headers"],
    )
    assert resp.status_code == 400, resp.text


def test_patch_package_to_single_clearing_all_package_fields_accepted(client, owner):
    """The valid counterpart to the two rejection tests above: clearing every
    package-only field in the SAME request as the type change must succeed —
    the invariant is about the merged final state, not about type changes
    being forbidden outright."""
    clinic = _create_clinic(client, owner)
    created = client.post(
        f"/api/v1/clinics/{clinic['id']}/services",
        json=_valid_service_payload(package_visit_count=6, **_PACKAGE_REQUIRED_KWARGS),
        headers=owner["headers"],
    ).json()

    resp = client.patch(
        f"/api/v1/clinics/{clinic['id']}/services/{created['id']}",
        json={
            "type": "single",
            "duration_months": None,
            "package_visit_count": None,
            "included_items": None,
            "benefits": None,
            "cancellation_refund_policy": None,
        },
        headers=owner["headers"],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["type"] == "single"


def test_valid_single_and_valid_package_both_still_work(client, owner):
    clinic = _create_clinic(client, owner)
    single = client.post(
        f"/api/v1/clinics/{clinic['id']}/services",
        json=_valid_service_payload(name="Dịch vụ Đơn Lẻ OK", code="SVC-SINGLE-OK"),
        headers=owner["headers"],
    )
    package = client.post(
        f"/api/v1/clinics/{clinic['id']}/services",
        json=_valid_service_payload(
            name="Dịch vụ Gói OK", code="SVC-PACKAGE-OK", **_PACKAGE_REQUIRED_KWARGS
        ),
        headers=owner["headers"],
    )
    assert single.status_code == 201, single.text
    assert package.status_code == 201, package.text
    assert single.json()["type"] == "single"
    assert package.json()["type"] == "package"


def test_duration_minutes_out_of_range_rejected(client, owner):
    clinic = _create_clinic(client, owner)
    resp = client.post(
        f"/api/v1/clinics/{clinic['id']}/services",
        json=_valid_service_payload(duration_minutes=241),
        headers=owner["headers"],
    )
    assert resp.status_code == 422, resp.text


def test_code_lowercase_pattern_rejected(client, owner):
    clinic = _create_clinic(client, owner)
    resp = client.post(
        f"/api/v1/clinics/{clinic['id']}/services",
        json=_valid_service_payload(code="svc-lowercase"),
        headers=owner["headers"],
    )
    assert resp.status_code == 422, resp.text


# ---------------------------------------------------------------------------
# BR-M05: name/code uniqueness in tenant
# ---------------------------------------------------------------------------


def test_duplicate_name_in_same_tenant_rejected(client, owner):
    clinic = _create_clinic(client, owner)
    first = client.post(
        f"/api/v1/clinics/{clinic['id']}/services",
        json=_valid_service_payload(code="SVC-A"),
        headers=owner["headers"],
    )
    assert first.status_code == 201, first.text
    dup = client.post(
        f"/api/v1/clinics/{clinic['id']}/services",
        json=_valid_service_payload(code="SVC-B"),  # same name, different code
        headers=owner["headers"],
    )
    assert dup.status_code == 400, dup.text


def test_duplicate_code_in_same_tenant_rejected(client, owner):
    clinic = _create_clinic(client, owner)
    first = client.post(
        f"/api/v1/clinics/{clinic['id']}/services",
        json=_valid_service_payload(name="Dịch vụ A", code="SVC-DUP"),
        headers=owner["headers"],
    )
    assert first.status_code == 201, first.text
    dup = client.post(
        f"/api/v1/clinics/{clinic['id']}/services",
        json=_valid_service_payload(name="Dịch vụ B", code="SVC-DUP"),
        headers=owner["headers"],
    )
    assert dup.status_code == 400, dup.text


def test_duplicate_name_race_returns_controlled_conflict_not_500(client, owner, db):
    """Codex second-pass review P1: the service-layer pre-check
    (`_assert_name_available`) is a check-then-insert race. Simulate the race
    by inserting a same-name row directly via the ORM (bypassing the
    pre-check, as a genuine concurrent request would), then confirm the DB
    unique constraint fires and the API still returns a controlled 400/409,
    not a raw 500."""
    from app.models.clinic import ClinicService, ClinicServiceStatus, ClinicServiceType

    clinic = _create_clinic(client, owner)
    db.add(
        ClinicService(
            clinic_id=clinic["id"],
            name="Dịch vụ Đua",
            code="SVC-RACE-DB",
            specialty="Nội tiết",
            duration_minutes=30,
            price=100000,
            type=ClinicServiceType.SINGLE,
            status=ClinicServiceStatus.ACTIVE,
        )
    )
    db.commit()

    resp = client.post(
        f"/api/v1/clinics/{clinic['id']}/services",
        json=_valid_service_payload(name="Dịch vụ Đua", code="SVC-RACE-API"),
        headers=owner["headers"],
    )
    assert resp.status_code == 400, resp.text


def test_same_code_allowed_across_different_tenants(client, owner, other_user):
    clinic_a = _create_clinic(client, owner, name="Clinic A - code reuse")
    clinic_b = _create_clinic(client, other_user, name="Clinic B - code reuse")
    resp_a = client.post(
        f"/api/v1/clinics/{clinic_a['id']}/services",
        json=_valid_service_payload(code="SVC-SHARED"),
        headers=owner["headers"],
    )
    resp_b = client.post(
        f"/api/v1/clinics/{clinic_b['id']}/services",
        json=_valid_service_payload(code="SVC-SHARED"),
        headers=other_user["headers"],
    )
    assert resp_a.status_code == 201, resp_a.text
    assert resp_b.status_code == 201, resp_b.text


# ---------------------------------------------------------------------------
# BR-M05-03/§5.3: doctors ⊆ bác sĩ tenant
# ---------------------------------------------------------------------------


def test_doctor_id_outside_clinic_rejected(client, owner, db):
    clinic = _create_clinic(client, owner)
    stray_doctor = Doctor(full_name="BS Ngoài Phòng Khám")
    db.add(stray_doctor)
    db.commit()

    resp = client.post(
        f"/api/v1/clinics/{clinic['id']}/services",
        json=_valid_service_payload(doctor_ids=[stray_doctor.id]),
        headers=owner["headers"],
    )
    assert resp.status_code == 400, resp.text


def test_doctor_id_of_non_doctor_membership_rejected(client, owner, db):
    """Codex PR review P2 fix: an active membership with a doctor_profile_id
    but no 'doctor' role (e.g. an admin who happens to have one set) must
    not count as a valid tenant doctor."""
    clinic = _create_clinic(client, owner)
    doctor_profile = Doctor(full_name="BS Không Có Vai Trò Doctor")
    db.add(doctor_profile)
    db.commit()
    non_doctor_user = User(
        email=f"m05-nondoc-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=UserRole.CLINIC_ADMIN,
        full_name="Non-Doctor Membership User",
    )
    db.add(non_doctor_user)
    db.commit()
    membership = ClinicMembership(
        user_id=non_doctor_user.id,
        clinic_id=clinic["id"],
        roles=["admin"],
        branch_ids=[],
        doctor_profile_id=doctor_profile.id,
        status="active",
    )
    db.add(membership)
    db.commit()

    resp = client.post(
        f"/api/v1/clinics/{clinic['id']}/services",
        json=_valid_service_payload(doctor_ids=[doctor_profile.id]),
        headers=owner["headers"],
    )
    assert resp.status_code == 400, resp.text


def test_doctor_id_active_member_of_clinic_accepted(client, owner, db):
    clinic = _create_clinic(client, owner)
    doctor_profile = Doctor(full_name="BS Trong Phòng Khám")
    db.add(doctor_profile)
    db.commit()

    doctor_user = User(
        email=f"m05-doc-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="Doctor Membership User",
    )
    db.add(doctor_user)
    db.commit()
    doctor_membership = ClinicMembership(
        user_id=doctor_user.id,
        clinic_id=clinic["id"],
        roles=["doctor"],
        branch_ids=[],
        doctor_profile_id=doctor_profile.id,
        status="active",
    )
    db.add(doctor_membership)
    db.commit()

    resp = client.post(
        f"/api/v1/clinics/{clinic['id']}/services",
        json=_valid_service_payload(doctor_ids=[doctor_profile.id]),
        headers=owner["headers"],
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["doctor_ids"] == [doctor_profile.id]


# ---------------------------------------------------------------------------
# AC-M05-03: branch-restricted service invisible at another branch
# ---------------------------------------------------------------------------


def test_branch_restricted_service_hidden_from_other_branch(client, owner):
    clinic = _create_clinic(client, owner)
    branch_a = client.post(
        f"/api/v1/clinics/{clinic['id']}/branches",
        json={"name": "Chi nhánh A", "working_hours": {}},
        headers=owner["headers"],
    ).json()
    branch_b = client.post(
        f"/api/v1/clinics/{clinic['id']}/branches",
        json={"name": "Chi nhánh B", "working_hours": {}},
        headers=owner["headers"],
    ).json()
    client.post(
        f"/api/v1/clinics/{clinic['id']}/services",
        json=_valid_service_payload(branch_ids=[branch_a["id"]]),
        headers=owner["headers"],
    )

    at_branch_a = client.get(
        f"/api/v1/clinics/{clinic['id']}/services?branch_id={branch_a['id']}",
        headers=owner["headers"],
    )
    at_branch_b = client.get(
        f"/api/v1/clinics/{clinic['id']}/services?branch_id={branch_b['id']}",
        headers=owner["headers"],
    )
    assert at_branch_a.json()["total"] == 1
    assert len(at_branch_a.json()["items"]) == 1
    assert len(at_branch_b.json()["items"]) == 0


def test_branch_scoped_membership_cannot_see_other_branch_services_by_omitting_filter(
    client, owner, other_user, db
):
    """Codex PR review P1 fix: a membership scoped to Branch A must not see
    Branch-B-restricted services just by omitting `branch_id` — visibility
    must come from TenantContext, not client cooperation."""
    clinic = _create_clinic(client, owner)
    branch_a = client.post(
        f"/api/v1/clinics/{clinic['id']}/branches",
        json={"name": "Chi nhánh A", "working_hours": {}},
        headers=owner["headers"],
    ).json()
    branch_b = client.post(
        f"/api/v1/clinics/{clinic['id']}/branches",
        json={"name": "Chi nhánh B", "working_hours": {}},
        headers=owner["headers"],
    ).json()
    client.post(
        f"/api/v1/clinics/{clinic['id']}/services",
        json=_valid_service_payload(code="SVC-BONLY", branch_ids=[branch_b["id"]]),
        headers=owner["headers"],
    )
    membership = ClinicMembership(
        user_id=other_user["user_id"],
        clinic_id=clinic["id"],
        roles=["nurse"],
        branch_ids=[branch_a["id"]],
        status="active",
    )
    db.add(membership)
    db.commit()

    resp = client.get(
        f"/api/v1/clinics/{clinic['id']}/services",
        headers={**other_user["headers"], "X-Clinic-Id": clinic["id"]},
    )
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_branch_scoped_membership_cannot_request_other_branch_explicitly(
    client, owner, other_user, db
):
    """Codex PR review P1 fix: passing another branch's id explicitly must
    403, not silently return that branch's services."""
    clinic = _create_clinic(client, owner)
    branch_a = client.post(
        f"/api/v1/clinics/{clinic['id']}/branches",
        json={"name": "Chi nhánh A", "working_hours": {}},
        headers=owner["headers"],
    ).json()
    branch_b = client.post(
        f"/api/v1/clinics/{clinic['id']}/branches",
        json={"name": "Chi nhánh B", "working_hours": {}},
        headers=owner["headers"],
    ).json()
    membership = ClinicMembership(
        user_id=other_user["user_id"],
        clinic_id=clinic["id"],
        roles=["nurse"],
        branch_ids=[branch_a["id"]],
        status="active",
    )
    db.add(membership)
    db.commit()

    resp = client.get(
        f"/api/v1/clinics/{clinic['id']}/services?branch_id={branch_b['id']}",
        headers={**other_user["headers"], "X-Clinic-Id": clinic["id"]},
    )
    assert resp.status_code == 403


def test_unrestricted_owner_passing_foreign_branch_id_returns_404(client, owner, other_user):
    """Codex second-pass review P2: an Owner/Admin (unrestricted
    tenant.branch_ids) passing another CLINIC's branch id must 404, not
    silently filter to a misleading empty result."""
    clinic_a = _create_clinic(client, owner, name="Clinic A - foreign branch id")
    clinic_b = _create_clinic(client, other_user, name="Clinic B - foreign branch id")
    foreign_branch = client.post(
        f"/api/v1/clinics/{clinic_b['id']}/branches",
        json={"name": "Chi nhánh B", "working_hours": {}},
        headers=other_user["headers"],
    ).json()

    resp = client.get(
        f"/api/v1/clinics/{clinic_a['id']}/services?branch_id={foreign_branch['id']}",
        headers=owner["headers"],
    )
    assert resp.status_code == 404, resp.text


def test_unrestricted_service_visible_at_every_branch(client, owner):
    clinic = _create_clinic(client, owner)
    branch = client.post(
        f"/api/v1/clinics/{clinic['id']}/branches",
        json={"name": "Chi nhánh Bất kỳ", "working_hours": {}},
        headers=owner["headers"],
    ).json()
    client.post(
        f"/api/v1/clinics/{clinic['id']}/services",
        json=_valid_service_payload(),  # branch_ids omitted = all branches
        headers=owner["headers"],
    )
    resp = client.get(
        f"/api/v1/clinics/{clinic['id']}/services?branch_id={branch['id']}",
        headers=owner["headers"],
    )
    assert len(resp.json()["items"]) == 1


# ---------------------------------------------------------------------------
# BR-M05-02: price change audited with old->new value
# ---------------------------------------------------------------------------


def test_explicit_null_clears_nullable_field(client, owner):
    """Codex PR review P2 fix: PATCH with an explicit `null` for a genuinely
    optional nullable field (branch_ids — not package-scoped, so this is
    unaffected by the round-4 type/package-field invariant) must clear it,
    not be silently ignored. (Business-required fields like
    specialty/code/duration_minutes are covered separately — see
    test_explicit_null_on_required_field_rejected and
    test_explicit_null_on_business_required_field_rejected. Package-only
    fields are covered by the round-4 type-consistency tests above — Codex
    second-pass review P1 found the original version of this test targeted a
    field that should NOT be clearable; round-4 review found `included_items`
    specifically became package-only and so no longer fits this test either.)
    """
    clinic = _create_clinic(client, owner)
    branch = client.post(
        f"/api/v1/clinics/{clinic['id']}/branches",
        json={"name": "Chi nhánh Null Test", "working_hours": {}},
        headers=owner["headers"],
    ).json()
    created = client.post(
        f"/api/v1/clinics/{clinic['id']}/services",
        json=_valid_service_payload(branch_ids=[branch["id"]]),
        headers=owner["headers"],
    ).json()
    assert created["branch_ids"] == [branch["id"]]

    updated = client.patch(
        f"/api/v1/clinics/{clinic['id']}/services/{created['id']}",
        json={"branch_ids": None},
        headers=owner["headers"],
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["branch_ids"] is None


def test_explicit_null_on_business_required_field_rejected(client, owner):
    """Codex second-pass review P1: code/specialty/duration_minutes are
    nullable at the DB layer but required at creation (BRD §5.3) — PATCH
    must not be able to null them out post-create."""
    clinic = _create_clinic(client, owner)
    created = client.post(
        f"/api/v1/clinics/{clinic['id']}/services",
        json=_valid_service_payload(),
        headers=owner["headers"],
    ).json()

    for field in ("code", "specialty", "duration_minutes"):
        resp = client.patch(
            f"/api/v1/clinics/{clinic['id']}/services/{created['id']}",
            json={field: None},
            headers=owner["headers"],
        )
        assert resp.status_code == 400, f"{field}: {resp.text}"


def test_explicit_null_on_required_field_rejected(client, owner):
    """Codex PR review P2 fix: allowing explicit-null clears must not extend
    to NOT NULL DB columns (name/price/type/status) — that must stay a
    controlled 400, not a raw IntegrityError."""
    clinic = _create_clinic(client, owner)
    created = client.post(
        f"/api/v1/clinics/{clinic['id']}/services",
        json=_valid_service_payload(),
        headers=owner["headers"],
    ).json()

    resp = client.patch(
        f"/api/v1/clinics/{clinic['id']}/services/{created['id']}",
        json={"price": None},
        headers=owner["headers"],
    )
    assert resp.status_code == 400, resp.text


def test_price_change_creates_audit_record_with_old_new_value(client, owner, db):
    from app.models.governance import AuditLog

    clinic = _create_clinic(client, owner)
    created = client.post(
        f"/api/v1/clinics/{clinic['id']}/services",
        json=_valid_service_payload(price=300000),
        headers=owner["headers"],
    ).json()

    updated = client.patch(
        f"/api/v1/clinics/{clinic['id']}/services/{created['id']}",
        json={"price": 350000},
        headers=owner["headers"],
    )
    assert updated.status_code == 200, updated.text

    entry = (
        db.query(AuditLog)
        .filter(
            AuditLog.resource_id == created["id"],
            AuditLog.action == "clinic_service_price_change",
        )
        .order_by(AuditLog.timestamp.desc())
        .first()
    )
    assert entry is not None
    # str, not float: price is Decimal end-to-end (Codex second-pass review
    # P1, money precision) — audit details store the exact string form.
    assert entry.details == {"old_price": "300000.00", "new_price": "350000.00"}


def test_non_price_update_does_not_emit_price_change_action(client, owner, db):
    from app.models.governance import AuditLog

    clinic = _create_clinic(client, owner)
    created = client.post(
        f"/api/v1/clinics/{clinic['id']}/services",
        json=_valid_service_payload(),
        headers=owner["headers"],
    ).json()

    client.patch(
        f"/api/v1/clinics/{clinic['id']}/services/{created['id']}",
        json={"specialty": "Tim mạch"},
        headers=owner["headers"],
    )

    price_change_entries = (
        db.query(AuditLog)
        .filter(
            AuditLog.resource_id == created["id"],
            AuditLog.action == "clinic_service_price_change",
        )
        .all()
    )
    assert price_change_entries == []


# ---------------------------------------------------------------------------
# Cross-tenant isolation (MASTER_PROGRAM_PLAN.md §7 matrix, M05 slice)
# ---------------------------------------------------------------------------


def test_cross_tenant_cannot_update_other_clinics_service(client, owner, other_user):
    clinic_a = _create_clinic(client, owner, name="Clinic A - cross update")
    clinic_b = _create_clinic(client, other_user, name="Clinic B - cross update")
    service = client.post(
        f"/api/v1/clinics/{clinic_a['id']}/services",
        json=_valid_service_payload(),
        headers=owner["headers"],
    ).json()

    # other_user has no membership at clinic_a at all -> tenant resolution
    # itself must reject before ever reaching the service lookup.
    resp = client.patch(
        f"/api/v1/clinics/{clinic_a['id']}/services/{service['id']}",
        json={"price": 999999},
        headers={**other_user["headers"], "X-Clinic-Id": clinic_b["id"]},
    )
    assert resp.status_code in (403, 404)


# ---------------------------------------------------------------------------
# RBAC negative matrix (RBAC_MATRIX.md M05 row: Doctor/Nurse/Reception/Care
# Coordinator/Accountant = R, only Owner/Admin can write)
# ---------------------------------------------------------------------------


def test_doctor_role_cannot_create_service(client, owner, other_user, db):
    clinic = _create_clinic(client, owner)
    # Grant other_user a Doctor-only membership at clinic (no Owner/Admin role).
    membership = ClinicMembership(
        user_id=other_user["user_id"],
        clinic_id=clinic["id"],
        roles=["doctor"],
        branch_ids=[],
        status="active",
    )
    db.add(membership)
    db.commit()

    resp = client.post(
        f"/api/v1/clinics/{clinic['id']}/services",
        json=_valid_service_payload(),
        headers={**other_user["headers"], "X-Clinic-Id": clinic["id"]},
    )
    assert resp.status_code == 403, resp.text


def test_doctor_role_can_read_service_catalog(client, owner, other_user, db):
    clinic = _create_clinic(client, owner)
    client.post(
        f"/api/v1/clinics/{clinic['id']}/services",
        json=_valid_service_payload(),
        headers=owner["headers"],
    )
    membership = ClinicMembership(
        user_id=other_user["user_id"],
        clinic_id=clinic["id"],
        roles=["doctor"],
        branch_ids=[],
        status="active",
    )
    db.add(membership)
    db.commit()

    resp = client.get(
        f"/api/v1/clinics/{clinic['id']}/services",
        headers={**other_user["headers"], "X-Clinic-Id": clinic["id"]},
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
