"""Clinic branch CRUD (Clinic SaaS Phase C0, M02).

No hard delete — a branch's terminal state is `archived`, a status flip
(DATA_MODEL.md §2). Every mutation is scoped by the caller's
`TenantContext.clinic_id` (never a client-supplied clinic_id) and audited.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.clinic import ClinicBranch, ClinicBranchStatus
from app.services import audit


class ClinicBranchError(ValueError):
    """Domain error for invalid branch state (e.g. duplicate name within a
    clinic). Routes translate this to a controlled 409 — never a raw 500."""


def create_branch(
    db: Session,
    *,
    clinic_id: str,
    actor_id: str,
    name: str,
    working_hours: dict,
    address: dict | None = None,
    phone: str | None = None,
) -> ClinicBranch:
    existing = db.execute(
        select(ClinicBranch).where(
            ClinicBranch.clinic_id == clinic_id, ClinicBranch.name == name
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ClinicBranchError(f"Chi nhánh có tên '{name}' đã tồn tại trong phòng khám này.")

    branch = ClinicBranch(
        clinic_id=clinic_id,
        name=name,
        working_hours=working_hours,
        address=address,
        phone=phone,
        status=ClinicBranchStatus.ACTIVE,
    )
    db.add(branch)
    db.flush()
    audit.record(
        db,
        actor_type="user",
        actor_id=actor_id,
        action="clinic_branch_create",
        resource_type="clinic_branch",
        resource_id=branch.id,
        clinic_id=clinic_id,
    )
    return branch


def assert_branch_ids_belong_to_clinic(
    db: Session, *, clinic_id: str, branch_ids: list[str]
) -> None:
    """Raise unless every id in `branch_ids` names an actual `ClinicBranch`
    row scoped to `clinic_id`.

    Closes a real gap found in Codex's PR #96 review: `create_invitation`/
    `update_membership` (clinic_membership.py) and `create_service`/
    `update_service` (clinic_service_catalog.py) all accepted a caller-
    supplied `branch_ids` list and persisted it verbatim with no check that
    those ids belong to the clinic in scope — a caller could reference
    another clinic's branch id, silently corrupting cross-tenant references
    that a future branch-scoped access check (C1+) would rely on.
    """
    if not branch_ids:
        return
    found = set(
        db.execute(
            select(ClinicBranch.id).where(
                ClinicBranch.clinic_id == clinic_id, ClinicBranch.id.in_(branch_ids)
            )
        ).scalars()
    )
    missing = set(branch_ids) - found
    if missing:
        raise ClinicBranchError("Một hoặc nhiều chi nhánh không thuộc phòng khám này.")


def get_branch(db: Session, *, clinic_id: str, branch_id: str) -> ClinicBranch | None:
    """Scoped lookup — a branch belonging to another clinic is treated as
    not-found, never returned (BOLA/IDOR guard, THREAT_MODEL.md §1/§2)."""
    return db.execute(
        select(ClinicBranch).where(
            ClinicBranch.id == branch_id, ClinicBranch.clinic_id == clinic_id
        )
    ).scalar_one_or_none()


def list_branches(
    db: Session, *, clinic_id: str, skip: int = 0, limit: int = 50
) -> tuple[list[ClinicBranch], int]:
    total = db.execute(
        select(func.count())
        .select_from(ClinicBranch)
        .where(ClinicBranch.clinic_id == clinic_id)
    ).scalar_one()
    items = list(
        db.execute(
            select(ClinicBranch)
            .where(ClinicBranch.clinic_id == clinic_id)
            .order_by(ClinicBranch.created_at.desc())
            .offset(skip)
            .limit(limit)
        ).scalars()
    )
    return items, total


def update_branch(
    db: Session, *, branch: ClinicBranch, actor_id: str, **fields
) -> ClinicBranch:
    allowed = ("name", "address", "phone", "working_hours")
    new_name = fields.get("name")
    if new_name is not None and new_name != branch.name:
        existing = db.execute(
            select(ClinicBranch).where(
                ClinicBranch.clinic_id == branch.clinic_id,
                ClinicBranch.name == new_name,
                ClinicBranch.id != branch.id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ClinicBranchError(
                f"Chi nhánh có tên '{new_name}' đã tồn tại trong phòng khám này."
            )
    for key, value in fields.items():
        if key in allowed and value is not None:
            setattr(branch, key, value)
    db.flush()
    audit.record(
        db,
        actor_type="user",
        actor_id=actor_id,
        action="clinic_branch_update",
        resource_type="clinic_branch",
        resource_id=branch.id,
        clinic_id=branch.clinic_id,
    )
    return branch


def set_branch_status(
    db: Session, *, branch: ClinicBranch, actor_id: str, status_value: str
) -> ClinicBranch:
    branch.status = status_value
    db.flush()
    audit.record(
        db,
        actor_type="user",
        actor_id=actor_id,
        action="clinic_branch_status_change",
        resource_type="clinic_branch",
        resource_id=branch.id,
        clinic_id=branch.clinic_id,
    )
    return branch
