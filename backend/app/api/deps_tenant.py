"""TenantContext — request-scoped clinic + role resolution (Clinic SaaS Phase C0).

`TENANT_ARCHITECTURE.md` §2.9/§4. Layered on top of `current_user`
(`app/api/deps.py`), exactly the way that module's docstring describes.

**The one rule this whole module exists to enforce**: a client-supplied
`clinic_id` (here, the `X-Clinic-Id` header) is NEVER trusted as the source
of authorization truth. It only *selects* among the caller's own active
`ClinicMembership` rows (a clinic/branch switcher UX) — every downstream
service/query must read `clinic_id` from the returned `TenantContext`, never
from a request body/query/path param directly, for any authorization
decision (`TENANT_ARCHITECTURE.md` §4 closing paragraph).

Two independent dependencies:
- `get_tenant_context` — the normal case, all 7 clinic roles.
- `require_platform_override` — Super/Internal Admin explicit, always-audited
  cross-tenant access (`TENANT_ARCHITECTURE.md` §5). Never a silent
  fallthrough of the normal resolution above.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, current_user, get_session, require_roles
from app.models.care import Clinic
from app.models.clinic import ClinicMembership, ClinicMembershipStatus
from app.models.user import UserRole
from app.services import audit

__all__ = [
    "TenantContext",
    "get_tenant_context",
    "require_platform_override",
    "require_platform_admin",
]

_NO_ACTIVE_MEMBERSHIP_DETAIL = "Bạn chưa là thành viên hoạt động của phòng khám nào."
_MUST_SELECT_CLINIC_DETAIL = (
    "Tài khoản thuộc nhiều phòng khám — vui lòng chọn phòng khám (X-Clinic-Id)."
)
_NOT_A_MEMBER_DETAIL = "Bạn không có quyền truy cập vào phòng khám này."
_CLINIC_NOT_FOUND_DETAIL = "Không tìm thấy phòng khám."


@dataclass(frozen=True)
class TenantContext:
    """The ONLY source of `clinic_id` any service/query layer may use for an
    authorization decision (never a client-supplied field, past this point).
    """

    user_id: str
    clinic_id: str
    membership_id: str | None
    roles: frozenset[str]
    branch_ids: frozenset[str]
    is_platform_override: bool = False


def get_tenant_context(
    x_clinic_id: str | None = Header(default=None, alias="X-Clinic-Id"),
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> TenantContext:
    """Resolve the caller's ACTIVE clinic + roles from their own memberships.

    - No `X-Clinic-Id` + exactly one active membership -> default to it.
    - No `X-Clinic-Id` + multiple active memberships -> 400 (explicit
      selection required, never a silent guess).
    - `X-Clinic-Id` present -> MUST match one of the caller's own active
      memberships, else 403 (never 404, to avoid leaking clinic existence).
    """
    memberships = list(
        db.execute(
            select(ClinicMembership).where(
                ClinicMembership.user_id == user.id,
                ClinicMembership.status == ClinicMembershipStatus.ACTIVE,
            )
        ).scalars()
    )
    if not memberships:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=_NO_ACTIVE_MEMBERSHIP_DETAIL
        )

    if x_clinic_id is None:
        if len(memberships) > 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=_MUST_SELECT_CLINIC_DETAIL
            )
        membership = memberships[0]
    else:
        membership = next((m for m in memberships if m.clinic_id == x_clinic_id), None)
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=_NOT_A_MEMBER_DETAIL
            )

    clinic = db.get(Clinic, membership.clinic_id)
    if clinic is None:
        # A membership row survives only via RESTRICT FKs, so this should be
        # unreachable in practice — guarded anyway, never assume.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_CLINIC_NOT_FOUND_DETAIL
        )

    return TenantContext(
        user_id=user.id,
        clinic_id=membership.clinic_id,
        membership_id=membership.id,
        roles=frozenset(membership.roles or []),
        branch_ids=frozenset(membership.branch_ids or []),
        is_platform_override=False,
    )


_platform_roles = require_roles(UserRole.SUPER_ADMIN, UserRole.INTERNAL_ADMIN)


def require_platform_override(
    x_clinic_id: str = Header(..., alias="X-Clinic-Id"),
    user: CurrentUser = Depends(_platform_roles),
    db: Session = Depends(get_session),
) -> TenantContext:
    """Explicit, always-audited Super/Internal Admin cross-tenant access.

    Distinct dependency from `get_tenant_context` — never reused as an
    implicit "admin passes every check" shortcut. `X-Clinic-Id` is REQUIRED
    (even an override must target one specific tenant, never "all tenants"
    implicitly), and every use unconditionally writes a
    `platform_cross_tenant_access` audit row before the handler runs
    (`TENANT_ARCHITECTURE.md` §5).
    """
    clinic = db.get(Clinic, x_clinic_id)
    if clinic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_CLINIC_NOT_FOUND_DETAIL
        )
    audit.record(
        db,
        actor_type="admin",
        actor_id=user.id,
        action="platform_cross_tenant_access",
        resource_type="clinic",
        resource_id=x_clinic_id,
        severity="warning",
        clinic_id=x_clinic_id,
    )
    db.commit()
    return TenantContext(
        user_id=user.id,
        clinic_id=x_clinic_id,
        membership_id=None,
        roles=frozenset(),
        branch_ids=frozenset(),
        is_platform_override=True,
    )


def require_platform_admin(
    user: CurrentUser = Depends(_platform_roles), db: Session = Depends(get_session)
) -> CurrentUser:
    """Super/Internal Admin ops-level access for genuinely multi-tenant
    operations (e.g. the platform-wide clinic listing, BR-M18-03's "ops-level
    audit query") — distinct from `require_platform_override`, which forces a
    single target clinic and is for single-tenant actions (suspend/restore).
    A "list every tenant" operation cannot honestly be scoped to one
    `clinic_id`, so this dependency still gates on the platform role and
    still audits, but does not pretend the request targets one clinic.
    """
    audit.record(
        db,
        actor_type="admin",
        actor_id=user.id,
        action="platform_admin_list_access",
        resource_type="clinic",
        severity="info",
    )
    db.commit()
    return user
