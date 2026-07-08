"""Clinic service/pricing catalog CRUD (Clinic SaaS Phase C0, M05).

Named `clinic_service_catalog` (not `clinic_service`) to stay distinct from
the `ClinicService` ORM model it wraps. Price-change audit goes through the
standard `audit.record()` call, not a bespoke history table (DATA_MODEL.md
§5) — historical invoices snapshot price at creation time, never a live
reference to this row.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.clinic import ClinicService, ClinicServiceStatus
from app.services import audit


def create_service(
    db: Session,
    *,
    clinic_id: str,
    actor_id: str,
    name: str,
    price: float,
    branch_ids: list[str] | None = None,
    package_visit_count: int | None = None,
) -> ClinicService:
    service = ClinicService(
        clinic_id=clinic_id,
        name=name,
        price=price,
        branch_ids=branch_ids,
        package_visit_count=package_visit_count,
        status=ClinicServiceStatus.ACTIVE,
    )
    db.add(service)
    db.flush()
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
    db: Session, *, clinic_id: str, skip: int = 0, limit: int = 50
) -> tuple[list[ClinicService], int]:
    total = db.execute(
        select(func.count())
        .select_from(ClinicService)
        .where(ClinicService.clinic_id == clinic_id)
    ).scalar_one()
    items = list(
        db.execute(
            select(ClinicService)
            .where(ClinicService.clinic_id == clinic_id)
            .order_by(ClinicService.created_at.desc())
            .offset(skip)
            .limit(limit)
        ).scalars()
    )
    return items, total


def update_service(
    db: Session, *, service: ClinicService, actor_id: str, **fields
) -> ClinicService:
    allowed = ("name", "price", "branch_ids", "package_visit_count", "status")
    changed_price = False
    for key, value in fields.items():
        if key in allowed and value is not None:
            if key == "price" and value != service.price:
                changed_price = True
            setattr(service, key, value)
    db.flush()
    audit.record(
        db,
        actor_type="user",
        actor_id=actor_id,
        action="clinic_service_price_change" if changed_price else "clinic_service_update",
        resource_type="clinic_service",
        resource_id=service.id,
        clinic_id=service.clinic_id,
    )
    return service
