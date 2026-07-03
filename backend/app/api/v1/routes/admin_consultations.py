"""Admin consultation monitoring routes — read-only.

RBAC-restricted to INTERNAL_ADMIN / SUPER_ADMIN + MFA-verified sessions, mirroring
the other admin endpoints in ``admin.py``. Exposes a filtered consultation listing
and aggregate stats used by the admin overview + monitoring pages.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_session, require_mfa, require_roles
from app.models.user import UserRole
from app.schemas.admin import AdminConsultationOut, AdminConsultationStatsOut
from app.services import admin_consultations, audit

router = APIRouter(prefix="/admin", tags=["admin"])

_admin_only = require_roles(UserRole.INTERNAL_ADMIN, UserRole.SUPER_ADMIN)


@router.get("/consultations", response_model=list[AdminConsultationOut])
def list_consultations(
    status: str | None = Query(default=None),
    doctor_id: str | None = Query(default=None),
    patient_id: str | None = Query(default=None),
    date_from: dt.datetime | None = Query(default=None),
    date_to: dt.datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    actor: CurrentUser = Depends(_admin_only),
    _mfa: CurrentUser = Depends(require_mfa),
    db: Session = Depends(get_session),
) -> list[AdminConsultationOut]:
    """List consultations for admin monitoring (filtered, newest first)."""
    rows = admin_consultations.list_consultations(
        db,
        status=status,
        doctor_id=doctor_id,
        patient_id=patient_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    audit.record(
        db,
        actor_type="admin",
        actor_id=actor.id,
        action="admin_read",
        resource_type="consultation_list",
    )
    db.commit()
    return [AdminConsultationOut.model_validate(r) for r in rows]


@router.get("/consultations/stats", response_model=AdminConsultationStatsOut)
def consultation_stats(
    actor: CurrentUser = Depends(_admin_only),
    _mfa: CurrentUser = Depends(require_mfa),
    db: Session = Depends(get_session),
) -> AdminConsultationStatsOut:
    """Aggregate consultation KPIs (by-status counts, total, paid, mock revenue)."""
    stats = admin_consultations.consultation_stats(db)
    audit.record(
        db,
        actor_type="admin",
        actor_id=actor.id,
        action="admin_read",
        resource_type="consultation_stats",
    )
    db.commit()
    return AdminConsultationStatsOut.model_validate(stats)
