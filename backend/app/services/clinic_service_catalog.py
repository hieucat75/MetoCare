"""Clinic service/pricing catalog CRUD (Clinic SaaS C0 base + C1 M05 fields).

Named `clinic_service_catalog` (not `clinic_service`) to stay distinct from
the `ClinicService` ORM model it wraps. Price-change audit goes through the
standard `audit.record()` call, not a bespoke history table (DATA_MODEL.md
§5) — historical invoices snapshot price at creation time, never a live
reference to this row.

BR-M05-03 (warn before deactivating a service with future bookings) and
BR-M05-04 (package-benefit consumption decrement) are **not implemented
here** — both require an appointment/billing concept that doesn't exist yet
in this codebase (M07/M10, later C1 milestones per
`docs/clinic-saas/MASTER_PROGRAM_PLAN.md` §3's dependency graph). Deferred,
not skipped — picked up when M07/M10 land.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.clinic import ClinicService, ClinicServiceStatus, ClinicServiceType
from app.services import audit
from app.services.clinic_branch import assert_branch_ids_belong_to_clinic
from app.services.clinic_membership import (
    ClinicMembershipError,
    assert_doctor_ids_belong_to_clinic,
)

_TWO_DP = Decimal("0.01")


class ClinicServiceError(ValueError):
    """Domain error for invalid service state (duplicate name/code, invalid
    doctor scope). Routes translate this to a controlled 400/409 — never a
    raw 500, same pattern as `ClinicBranchError`."""


# Codex round-4 fix: the round-2 validator (removed) ran only on Create and
# only checked 2 of these 5 fields, so `type=single` could still carry
# `included_items`/`benefits`/`cancellation_refund_policy`, and PATCH had no
# equivalent check at all. `_PACKAGE_ONLY_FIELDS` is every field §5.3 scopes
# to `type=package`; `_PACKAGE_REQUIRED_FIELDS` is the subset the BRD text
# names as required package metadata (`duration_months`, `included_items`,
# `benefits`, `cancellation_refund_policy`) — `package_visit_count` is a
# pre-existing (C0) convenience field, package-only but not itself mandatory.
_PACKAGE_ONLY_FIELDS = (
    "duration_months",
    "package_visit_count",
    "included_items",
    "benefits",
    "cancellation_refund_policy",
)
_PACKAGE_REQUIRED_FIELDS = (
    "duration_months",
    "included_items",
    "benefits",
    "cancellation_refund_policy",
)


def _assert_type_field_consistency(*, type_value: str, field_values: dict) -> None:
    """Validate the FINAL (post-merge) type/package-field state — identical
    logic for `create_service` (fresh state) and `update_service` (existing
    row merged with the PATCH payload, so a type change or a field clear is
    validated against what the row will actually look like, not just the
    fields present in this one request). No silent drop or auto-clear —
    every violation is a controlled `ClinicServiceError` (400)."""
    set_package_fields = [f for f in _PACKAGE_ONLY_FIELDS if field_values.get(f) is not None]
    if type_value == ClinicServiceType.SINGLE and set_package_fields:
        raise ClinicServiceError(
            "Dịch vụ đơn lẻ (type=single) không được có: " + ", ".join(set_package_fields) + "."
        )
    if type_value == ClinicServiceType.PACKAGE:
        missing = [f for f in _PACKAGE_REQUIRED_FIELDS if field_values.get(f) is None]
        if missing:
            raise ClinicServiceError(
                "Dịch vụ dạng gói (type=package) cần đầy đủ: " + ", ".join(missing) + "."
            )


def _assert_name_available(
    db: Session, *, clinic_id: str, name: str, exclude_service_id: str | None = None
) -> None:
    stmt = select(ClinicService).where(
        ClinicService.clinic_id == clinic_id, ClinicService.name == name
    )
    if exclude_service_id is not None:
        stmt = stmt.where(ClinicService.id != exclude_service_id)
    if db.execute(stmt).scalar_one_or_none() is not None:
        raise ClinicServiceError(f"Dịch vụ có tên '{name}' đã tồn tại trong phòng khám này.")


def _assert_code_available(
    db: Session, *, clinic_id: str, code: str, exclude_service_id: str | None = None
) -> None:
    stmt = select(ClinicService).where(
        ClinicService.clinic_id == clinic_id, ClinicService.code == code
    )
    if exclude_service_id is not None:
        stmt = stmt.where(ClinicService.id != exclude_service_id)
    if db.execute(stmt).scalar_one_or_none() is not None:
        raise ClinicServiceError(f"Mã dịch vụ '{code}' đã tồn tại trong phòng khám này.")


def create_service(
    db: Session,
    *,
    clinic_id: str,
    actor_id: str,
    name: str,
    code: str,
    specialty: str,
    duration_minutes: int,
    price: float,
    type: str = ClinicServiceType.SINGLE,
    branch_ids: list[str] | None = None,
    doctor_ids: list[str] | None = None,
    package_visit_count: int | None = None,
    duration_months: int | None = None,
    included_items: dict | None = None,
    benefits: dict | None = None,
    cancellation_refund_policy: dict | None = None,
) -> ClinicService:
    assert_branch_ids_belong_to_clinic(db, clinic_id=clinic_id, branch_ids=branch_ids or [])
    try:
        assert_doctor_ids_belong_to_clinic(db, clinic_id=clinic_id, doctor_ids=doctor_ids or [])
    except ClinicMembershipError as exc:
        raise ClinicServiceError(str(exc)) from exc
    _assert_name_available(db, clinic_id=clinic_id, name=name)
    _assert_code_available(db, clinic_id=clinic_id, code=code)
    _assert_type_field_consistency(
        type_value=type,
        field_values={
            "duration_months": duration_months,
            "package_visit_count": package_visit_count,
            "included_items": included_items,
            "benefits": benefits,
            "cancellation_refund_policy": cancellation_refund_policy,
        },
    )

    service = ClinicService(
        clinic_id=clinic_id,
        name=name,
        code=code,
        specialty=specialty,
        duration_minutes=duration_minutes,
        price=price,
        type=type,
        branch_ids=branch_ids,
        doctor_ids=doctor_ids,
        package_visit_count=package_visit_count,
        duration_months=duration_months,
        included_items=included_items,
        benefits=benefits,
        cancellation_refund_policy=cancellation_refund_policy,
        status=ClinicServiceStatus.ACTIVE,
    )
    db.add(service)
    try:
        db.flush()
    except IntegrityError as exc:
        # Codex second-pass review P1: the pre-checks above are a
        # check-then-insert race (two concurrent creates can both pass
        # `_assert_name_available`/`_assert_code_available` before either
        # commits). The DB unique constraints are the real guarantee; a
        # race that reaches them must still surface as a controlled 409,
        # not a raw 500.
        db.rollback()
        raise ClinicServiceError(
            "Tên hoặc mã dịch vụ đã tồn tại trong phòng khám này (xung đột đồng thời)."
        ) from exc
    audit.record(
        db,
        actor_type="user",
        actor_id=actor_id,
        action="clinic_service_create",
        resource_type="clinic_service",
        resource_id=service.id,
        clinic_id=clinic_id,
    )
    return service


def get_service(db: Session, *, clinic_id: str, service_id: str) -> ClinicService | None:
    return db.execute(
        select(ClinicService).where(
            ClinicService.id == service_id, ClinicService.clinic_id == clinic_id
        )
    ).scalar_one_or_none()


def list_services(
    db: Session,
    *,
    clinic_id: str,
    branch_ids: list[str] | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[ClinicService], int]:
    """`branch_ids` (when given) filters to services visible at ANY of those
    branches (AC-M05-03: branch-restricted services must not appear when the
    caller's context doesn't cover them). A service's own `branch_ids IS
    NULL` means "all branches" (always visible).

    Codex PR review fix: the JSON-array membership check can't be expressed
    portably in a SQL WHERE clause (SQLite/Postgres), so it must run in
    Python — but that means it has to run BEFORE pagination, not after,
    otherwise `total`/`offset`/`limit` are computed against the wrong
    (unfiltered) row set, silently truncating or hiding visible rows on
    later pages. Per-clinic catalog size is small enough that loading the
    full unpaginated set here is cheap."""
    stmt = select(ClinicService).where(ClinicService.clinic_id == clinic_id)
    all_items = list(db.execute(stmt.order_by(ClinicService.created_at.desc())).scalars())
    if branch_ids is not None:
        branch_id_set = set(branch_ids)
        all_items = [
            s
            for s in all_items
            if s.branch_ids is None or branch_id_set.intersection(s.branch_ids)
        ]
    total = len(all_items)
    items = all_items[skip : skip + limit]
    return items, total


def update_service(
    db: Session, *, service: ClinicService, actor_id: str, **fields
) -> ClinicService:
    allowed = (
        "name",
        "code",
        "specialty",
        "duration_minutes",
        "price",
        "type",
        "branch_ids",
        "doctor_ids",
        "package_visit_count",
        "duration_months",
        "included_items",
        "benefits",
        "cancellation_refund_policy",
        "status",
    )
    # DB-level NOT NULL columns (name/price/type/status) plus BRD-required-
    # at-creation fields (code/specialty/duration_minutes, §5.3 "Bắt buộc")
    # that are nullable at the DB layer but must never be cleared once set —
    # Codex second-pass review P1: the "explicit null clears a field" fix
    # above was too broad and let PATCH null out a required field post-create.
    # doctor_ids/branch_ids/package-only fields remain genuinely clearable.
    not_nullable = ("name", "price", "type", "status", "code", "specialty", "duration_minutes")
    rejected_nulls = [k for k in not_nullable if k in fields and fields[k] is None]
    if rejected_nulls:
        raise ClinicServiceError(
            f"Không thể đặt giá trị null cho trường bắt buộc: {', '.join(rejected_nulls)}."
        )
    if fields.get("branch_ids") is not None:
        assert_branch_ids_belong_to_clinic(
            db, clinic_id=service.clinic_id, branch_ids=fields["branch_ids"]
        )
    if fields.get("doctor_ids") is not None:
        try:
            assert_doctor_ids_belong_to_clinic(
                db, clinic_id=service.clinic_id, doctor_ids=fields["doctor_ids"]
            )
        except ClinicMembershipError as exc:
            raise ClinicServiceError(str(exc)) from exc
    if fields.get("name") is not None and fields["name"] != service.name:
        _assert_name_available(
            db, clinic_id=service.clinic_id, name=fields["name"], exclude_service_id=service.id
        )
    if fields.get("code") is not None and fields["code"] != service.code:
        _assert_code_available(
            db, clinic_id=service.clinic_id, code=fields["code"], exclude_service_id=service.id
        )

    # Codex round-4 fix: validate the FINAL merged state (existing row +
    # this PATCH payload), not just the fields present in the request —
    # otherwise PATCH could freely break the type/package-field invariant
    # Create enforces (change type without clearing incompatible fields,
    # clear required package metadata while staying type=package, etc.).
    final_type = fields["type"] if "type" in fields else service.type
    final_package_field_values = {
        f: (fields[f] if f in fields else getattr(service, f)) for f in _PACKAGE_ONLY_FIELDS
    }
    _assert_type_field_consistency(type_value=final_type, field_values=final_package_field_values)

    old_price = service.price
    changed_price = False
    for key, value in fields.items():
        # No `value is not None` gate: `fields` only contains keys the
        # caller explicitly set (route uses `model_dump(exclude_unset=True)`),
        # so an explicit `null` for a nullable field (doctor_ids, package
        # metadata, etc.) is a real "clear this field" request, not an
        # omitted field — Codex PR review finding, previously silently
        # ignored.
        if key in allowed:
            if key == "price" and value is not None and value != service.price:
                changed_price = True
            setattr(service, key, value)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ClinicServiceError(
            "Tên hoặc mã dịch vụ đã tồn tại trong phòng khám này (xung đột đồng thời)."
        ) from exc
    audit.record(
        db,
        actor_type="user",
        actor_id=actor_id,
        action="clinic_service_price_change" if changed_price else "clinic_service_update",
        resource_type="clinic_service",
        resource_id=service.id,
        clinic_id=service.clinic_id,
        details=(
            # str(), not float(): Decimal isn't JSON-native and float() would
            # reintroduce the exact precision loss this fix is for. Quantize
            # both sides to 2dp explicitly: `old_price` comes from a DB read
            # (already scale-2 via Numeric(12,2)) but `service.price` here is
            # the just-assigned, pre-flush Pydantic value, which may not
            # carry the same trailing-zero scale — quantize so the audit
            # trail is consistently formatted either way.
            {
                "old_price": str(Decimal(old_price).quantize(_TWO_DP)),
                "new_price": str(Decimal(service.price).quantize(_TWO_DP)),
            }
            if changed_price
            else None
        ),
    )
    return service
