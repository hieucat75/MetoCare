"""Clinic membership + invitation lifecycle (Clinic SaaS Phase C0, M03).

Invariants enforced here (service layer, not DB — cross-row/cross-column
checks aren't DB-expressible, same class of guard as `CarePlan`'s AI-status
`@validates` hooks, `TENANT_ARCHITECTURE.md` §2.3):

- `roles` must be a non-empty subset of `ClinicRole`.
- At least one ACTIVE membership with `owner` in `roles` must remain per
  clinic at all times ("cannot demote/lock the last Owner", BR-M03-04).
- Invitation tokens are single-use (status flips on accept/revoke) and
  time-boxed (`expires_at`); the raw token is never persisted, only its hash
  (mirrors `users.password_hash`).

Every mutation is scoped by the caller's `TenantContext.clinic_id` (never a
client-supplied clinic_id) and audited.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.clock import as_naive_utc, utcnow
from app.models.clinic import (
    ClinicInvitation,
    ClinicInvitationStatus,
    ClinicMembership,
    ClinicMembershipStatus,
    ClinicRole,
)
from app.services import audit
from app.services.clinic_branch import ClinicBranchError, assert_branch_ids_belong_to_clinic

INVITATION_TTL_DAYS = 7
_VALID_ROLES = frozenset(r.value for r in ClinicRole)


class ClinicMembershipError(ValueError):
    """Domain error for invalid role/last-owner/invitation-state transitions.

    Routes translate this to a controlled 400/409/410 HTTPException — never a
    raw 500."""


def _validate_roles(roles: list[str]) -> None:
    if not roles:
        raise ClinicMembershipError("Cần chọn ít nhất một vai trò.")
    invalid = set(roles) - _VALID_ROLES
    if invalid:
        raise ClinicMembershipError(f"Vai trò không hợp lệ: {', '.join(sorted(invalid))}.")


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _generate_token() -> str:
    return secrets.token_urlsafe(32)


def _has_other_active_owner(
    db: Session, *, clinic_id: str, exclude_membership_id: str | None = None
) -> bool:
    stmt = select(ClinicMembership).where(
        ClinicMembership.clinic_id == clinic_id,
        ClinicMembership.status == ClinicMembershipStatus.ACTIVE,
    )
    if exclude_membership_id is not None:
        stmt = stmt.where(ClinicMembership.id != exclude_membership_id)
    for membership in db.execute(stmt).scalars():
        if ClinicRole.OWNER in (membership.roles or []):
            return True
    return False


def create_invitation(
    db: Session,
    *,
    clinic_id: str,
    actor_id: str,
    roles: list[str],
    branch_ids: list[str] | None = None,
    invited_email: str | None = None,
    invited_phone: str | None = None,
) -> tuple[ClinicInvitation, str]:
    """Create a pending invitation. Returns (invitation, raw_token) — the raw
    token is returned exactly once for the caller to deliver out-of-band
    (email/SMS); it is never stored or logged."""
    if not invited_email and not invited_phone:
        raise ClinicMembershipError("Cần cung cấp email hoặc số điện thoại để mời.")
    _validate_roles(roles)
    try:
        assert_branch_ids_belong_to_clinic(db, clinic_id=clinic_id, branch_ids=branch_ids or [])
    except ClinicBranchError as exc:
        raise ClinicMembershipError(str(exc)) from exc

    existing = db.execute(
        select(ClinicInvitation).where(
            ClinicInvitation.clinic_id == clinic_id,
            ClinicInvitation.status == ClinicInvitationStatus.PENDING,
            (ClinicInvitation.invited_email == invited_email)
            if invited_email
            else (ClinicInvitation.invited_phone == invited_phone),
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ClinicMembershipError(
            "Đã có lời mời đang chờ xử lý cho địa chỉ/số điện thoại này."
        )

    raw_token = _generate_token()
    invitation = ClinicInvitation(
        clinic_id=clinic_id,
        invited_email=invited_email,
        invited_phone=invited_phone,
        roles=roles,
        branch_ids=branch_ids or [],
        token_hash=_hash_token(raw_token),
        status=ClinicInvitationStatus.PENDING,
        expires_at=utcnow() + dt.timedelta(days=INVITATION_TTL_DAYS),
        invited_by_user_id=actor_id,
    )
    db.add(invitation)
    db.flush()
    audit.record(
        db,
        actor_type="user",
        actor_id=actor_id,
        action="clinic_invitation_create",
        resource_type="clinic_invitation",
        resource_id=invitation.id,
        clinic_id=clinic_id,
    )
    return invitation, raw_token


def list_invitations(
    db: Session, *, clinic_id: str, skip: int = 0, limit: int = 50
) -> tuple[list[ClinicInvitation], int]:
    total = db.execute(
        select(func.count())
        .select_from(ClinicInvitation)
        .where(ClinicInvitation.clinic_id == clinic_id)
    ).scalar_one()
    items = list(
        db.execute(
            select(ClinicInvitation)
            .where(ClinicInvitation.clinic_id == clinic_id)
            .order_by(ClinicInvitation.created_at.desc())
            .offset(skip)
            .limit(limit)
        ).scalars()
    )
    return items, total


def revoke_invitation(
    db: Session, *, clinic_id: str, invitation_id: str, actor_id: str
) -> ClinicInvitation:
    invitation = db.execute(
        select(ClinicInvitation).where(
            ClinicInvitation.id == invitation_id, ClinicInvitation.clinic_id == clinic_id
        )
    ).scalar_one_or_none()
    if invitation is None:
        raise ClinicMembershipError("Không tìm thấy lời mời.")
    if invitation.status != ClinicInvitationStatus.PENDING:
        raise ClinicMembershipError("Lời mời này không còn hiệu lực để thu hồi.")
    invitation.status = ClinicInvitationStatus.REVOKED
    db.flush()
    audit.record(
        db,
        actor_type="user",
        actor_id=actor_id,
        action="clinic_invitation_revoke",
        resource_type="clinic_invitation",
        resource_id=invitation.id,
        clinic_id=clinic_id,
    )
    return invitation


def accept_invitation(db: Session, *, raw_token: str, accepting_user_id: str) -> ClinicMembership:
    token_hash = _hash_token(raw_token)
    invitation = db.execute(
        select(ClinicInvitation).where(ClinicInvitation.token_hash == token_hash)
    ).scalar_one_or_none()
    if invitation is None or invitation.status != ClinicInvitationStatus.PENDING:
        raise ClinicMembershipError("Lời mời không hợp lệ hoặc đã được sử dụng.")
    if as_naive_utc(invitation.expires_at) < utcnow():
        invitation.status = ClinicInvitationStatus.EXPIRED
        # Commit here (not just flush): the route only calls db.commit() on
        # the success path, and `get_session()`'s `finally: db.close()`
        # implicitly rolls back an uncommitted flush when this exception
        # propagates — without this commit, the status flip to `expired`
        # would be silently discarded every time.
        db.commit()
        raise ClinicMembershipError("Lời mời đã hết hạn.")

    # Atomic conditional accept (Codex PR #96 review, P1 finding #1): the
    # PENDING check above is a plain SELECT and is not by itself safe under
    # concurrency — two simultaneous callers could both read PENDING before
    # either commits, and both create a membership from what is supposed to
    # be a single-use token. This UPDATE only succeeds for whichever caller
    # wins the race (rowcount == 1); the loser gets the same
    # invalid-or-already-used error a genuinely stale token would produce.
    result = db.execute(
        update(ClinicInvitation)
        .where(
            ClinicInvitation.id == invitation.id,
            ClinicInvitation.status == ClinicInvitationStatus.PENDING,
        )
        .values(status=ClinicInvitationStatus.ACCEPTED, accepted_by_user_id=accepting_user_id)
    )
    if result.rowcount != 1:
        raise ClinicMembershipError("Lời mời không hợp lệ hoặc đã được sử dụng.")
    db.refresh(invitation)

    membership = db.execute(
        select(ClinicMembership).where(
            ClinicMembership.user_id == accepting_user_id,
            ClinicMembership.clinic_id == invitation.clinic_id,
        )
    ).scalar_one_or_none()
    if membership is None:
        membership = ClinicMembership(
            user_id=accepting_user_id,
            clinic_id=invitation.clinic_id,
            roles=invitation.roles,
            branch_ids=invitation.branch_ids,
            status=ClinicMembershipStatus.ACTIVE,
            is_primary=False,
            joined_at=dt.date.today(),
            invited_by_user_id=invitation.invited_by_user_id,
        )
        db.add(membership)
    else:
        # Reactivating a previously removed/suspended membership, or
        # re-accepting with an updated role/branch offer.
        membership.roles = invitation.roles
        membership.branch_ids = invitation.branch_ids
        membership.status = ClinicMembershipStatus.ACTIVE
        membership.joined_at = dt.date.today()
        membership.left_at = None
    db.flush()

    audit.record(
        db,
        actor_type="user",
        actor_id=accepting_user_id,
        action="clinic_invitation_accept",
        resource_type="clinic_membership",
        resource_id=membership.id,
        clinic_id=invitation.clinic_id,
    )
    return membership


def list_memberships(
    db: Session, *, clinic_id: str, skip: int = 0, limit: int = 50
) -> tuple[list[ClinicMembership], int]:
    total = db.execute(
        select(func.count())
        .select_from(ClinicMembership)
        .where(ClinicMembership.clinic_id == clinic_id)
    ).scalar_one()
    items = list(
        db.execute(
            select(ClinicMembership)
            .where(ClinicMembership.clinic_id == clinic_id)
            .order_by(ClinicMembership.created_at.desc())
            .offset(skip)
            .limit(limit)
        ).scalars()
    )
    return items, total


def get_membership(db: Session, *, clinic_id: str, membership_id: str) -> ClinicMembership | None:
    return db.execute(
        select(ClinicMembership).where(
            ClinicMembership.id == membership_id, ClinicMembership.clinic_id == clinic_id
        )
    ).scalar_one_or_none()


def get_membership_by_id(db: Session, *, membership_id: str) -> ClinicMembership | None:
    """Fetch by id only — used by `/clinics/me/membership`, where the caller's
    own `TenantContext.membership_id` already proves ownership; no separate
    clinic_id match is needed (unlike `get_membership`, called from
    clinic-scoped staff-management routes where the path `clinic_id` must be
    reconfirmed)."""
    return db.get(ClinicMembership, membership_id)


def list_my_memberships(db: Session, *, user_id: str) -> list[ClinicMembership]:
    """All ACTIVE memberships for one user, across every clinic — the
    clinic-switcher's data source (`TENANT_ARCHITECTURE.md` §2.9's
    "no X-Clinic-Id + multiple active memberships -> caller must choose"
    case needs a way to list the choices)."""
    return list(
        db.execute(
            select(ClinicMembership)
            .where(
                ClinicMembership.user_id == user_id,
                ClinicMembership.status == ClinicMembershipStatus.ACTIVE,
            )
            .order_by(ClinicMembership.is_primary.desc(), ClinicMembership.created_at.asc())
        ).scalars()
    )


def update_membership(
    db: Session,
    *,
    membership: ClinicMembership,
    actor_id: str,
    roles: list[str] | None = None,
    branch_ids: list[str] | None = None,
    status_value: str | None = None,
) -> ClinicMembership:
    """Update roles/branch scope/status, enforcing the "last Owner" invariant
    (BR-M03-04): a change is rejected if it would leave the clinic with zero
    active Owner memberships."""
    would_lose_owner = False
    is_currently_owner_active = (
        membership.status == ClinicMembershipStatus.ACTIVE
        and ClinicRole.OWNER in (membership.roles or [])
    )
    next_roles = roles if roles is not None else membership.roles
    next_status = status_value if status_value is not None else membership.status
    will_remain_active_owner = (
        next_status == ClinicMembershipStatus.ACTIVE and ClinicRole.OWNER in (next_roles or [])
    )
    if is_currently_owner_active and not will_remain_active_owner:
        would_lose_owner = not _has_other_active_owner(
            db, clinic_id=membership.clinic_id, exclude_membership_id=membership.id
        )
    if would_lose_owner:
        raise ClinicMembershipError(
            "Không thể thực hiện — phòng khám phải luôn còn ít nhất một Chủ sở hữu đang hoạt động."
        )

    if roles is not None:
        _validate_roles(roles)
        membership.roles = roles
    if branch_ids is not None:
        try:
            assert_branch_ids_belong_to_clinic(
                db, clinic_id=membership.clinic_id, branch_ids=branch_ids
            )
        except ClinicBranchError as exc:
            raise ClinicMembershipError(str(exc)) from exc
        membership.branch_ids = branch_ids
    if status_value is not None:
        membership.status = status_value
        if status_value == ClinicMembershipStatus.REMOVED:
            membership.left_at = dt.date.today()

    db.flush()
    audit.record(
        db,
        actor_type="user",
        actor_id=actor_id,
        action="clinic_membership_update",
        resource_type="clinic_membership",
        resource_id=membership.id,
        clinic_id=membership.clinic_id,
    )
    return membership
