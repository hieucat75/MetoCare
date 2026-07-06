"""Admin AI-safety console — /admin/ai-sessions.

Backs the frontend "Giám sát an toàn AI" page. Sessions are Meto conversations
(the live AI chat); safety signals are aggregated from MetoAuditLog rows:

  - any ``escalation_triggered``   → safety_level "urgent",  flag "urgent_response"
  - any ``safety_flags_detected``  → safety_level "caution", flag "review_requested"
  - otherwise                      → safety_level "safe",    flag "none"

RBAC: INTERNAL_ADMIN / SUPER_ADMIN. Unlike the other /admin routes, these two
endpoints do NOT require step-up MFA verification (`require_mfa`) — safety
triage needs to stay reachable for admins who haven't completed MFA
enrollment/verification yet. RBAC role gating still applies.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_session, require_roles
from app.core.clock import utcnow
from app.models.meto import MetoAuditLog, MetoConversation
from app.models.user import User, UserRole
from app.schemas.admin import (
    AdminAiSessionListResponse,
    AdminAiSessionOut,
    AiSafetyLevel,
    AiSessionFlag,
)
from app.services import audit

router = APIRouter(prefix="/admin/ai-sessions", tags=["admin"])

_admin_only = require_roles(UserRole.INTERNAL_ADMIN, UserRole.SUPER_ADMIN)


def _classify(escalated: bool, flagged: bool) -> tuple[AiSafetyLevel, AiSessionFlag]:
    if escalated:
        return "urgent", "urgent_response"
    if flagged:
        return "caution", "review_requested"
    return "safe", "none"


def _explanation_label(escalated: bool, flagged: bool) -> str:
    """Controlled, non-PHI reason label for why this session is on the list.

    MUST NOT derive from conversation content (title/messages) — conv.title is
    auto-generated from the user's first message and can itself be PHI (e.g.
    a symptom description). Only a small fixed vocabulary is ever returned.
    """
    if escalated:
        return "urgent_response"
    if flagged:
        return "safety_flag"
    return "none"


def _safety_signals(db: Session, conversation_ids: list[str]) -> dict[str, tuple[bool, bool]]:
    """conversation_id -> (any escalation_triggered, any safety_flags_detected)."""
    if not conversation_ids:
        return {}
    rows = db.execute(
        select(
            MetoAuditLog.conversation_id,
            func.max(MetoAuditLog.escalation_triggered),
            func.max(MetoAuditLog.safety_flags_detected),
        )
        .where(MetoAuditLog.conversation_id.in_(conversation_ids))
        .group_by(MetoAuditLog.conversation_id)
    ).all()
    return {cid: (bool(esc), bool(flg)) for cid, esc, flg in rows}


def _display_name(user: User | None) -> str | None:
    if user is None:
        return None
    return user.full_name or user.email or user.phone


def _to_out(
    conv: MetoConversation,
    signals: tuple[bool, bool],
    owner: User | None,
    reviewer: User | None,
) -> AdminAiSessionOut:
    safety_level, flag = _classify(*signals)
    return AdminAiSessionOut(
        id=conv.id,
        patient_id=conv.user_id,
        patient_name=_display_name(owner),
        explanation_type=_explanation_label(*signals),
        safety_level=safety_level,
        flag=flag,
        created_at=conv.created_at,
        reviewed_by=_display_name(reviewer),
        reviewed_at=conv.reviewed_at,
    )


def _users_by_id(db: Session, user_ids: set[str]) -> dict[str, User]:
    if not user_ids:
        return {}
    rows = db.execute(select(User).where(User.id.in_(user_ids))).scalars().all()
    return {u.id: u for u in rows}


@router.get("", response_model=AdminAiSessionListResponse)
def list_admin_ai_sessions(
    safety_level: AiSafetyLevel | None = Query(default=None),
    flag: AiSessionFlag | None = Query(default=None),
    reviewed: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    actor: CurrentUser = Depends(_admin_only),
    db: Session = Depends(get_session),
) -> AdminAiSessionListResponse:
    """List AI sessions with derived safety metadata, newest first.

    ``safety_level`` / ``flag`` filters are applied after aggregating the
    audit signals (they are derived values, not columns).
    """
    conversations = (
        db.execute(
            select(MetoConversation)
            .where(MetoConversation.deleted_at.is_(None))
            .order_by(MetoConversation.created_at.desc())
        )
        .scalars()
        .all()
    )

    signals = _safety_signals(db, [c.id for c in conversations])

    filtered: list[MetoConversation] = []
    for conv in conversations:
        level, conv_flag = _classify(*signals.get(conv.id, (False, False)))
        if safety_level is not None and level != safety_level:
            continue
        if flag is not None and conv_flag != flag:
            continue
        if reviewed is not None and bool(conv.reviewed_at) != reviewed:
            continue
        filtered.append(conv)

    flagged_count = sum(
        1 for c in conversations if _classify(*signals.get(c.id, (False, False)))[1] != "none"
    )

    page = filtered[offset : offset + limit]
    user_ids = {c.user_id for c in page} | {
        c.reviewed_by_user_id for c in page if c.reviewed_by_user_id
    }
    users = _users_by_id(db, user_ids)

    items = [
        _to_out(
            c,
            signals.get(c.id, (False, False)),
            users.get(c.user_id),
            users.get(c.reviewed_by_user_id) if c.reviewed_by_user_id else None,
        )
        for c in page
    ]

    audit.record(
        db,
        actor_type="admin",
        actor_id=actor.id,
        action="admin_read",
        resource_type="ai_session_safety",
    )
    db.commit()
    return AdminAiSessionListResponse(
        total=len(filtered), flagged_count=flagged_count, items=items
    )


@router.patch("/{session_id}/review", response_model=AdminAiSessionOut)
def review_admin_ai_session(
    session_id: str,
    actor: CurrentUser = Depends(_admin_only),
    db: Session = Depends(get_session),
) -> AdminAiSessionOut:
    """Mark a session as reviewed by the current admin (idempotent, race-safe).

    Two admins can hit this endpoint for the same session at nearly the same
    time. A read-then-write (check reviewed_at, then set it) is NOT safe: both
    requests could read reviewed_at=None before either commits, and the second
    write would silently overwrite the first reviewer's identity and create a
    duplicate audit record.

    Instead this uses a single atomic conditional UPDATE — only the request
    whose WHERE clause actually matches a row (reviewed_at IS NULL) wins the
    row and gets to write an audit record; every other request (concurrent or
    a later idempotent retry) reads rowcount=0 and simply returns the
    winner's state without writing anything.
    """
    conv = db.get(MetoConversation, session_id)
    if conv is None or conv.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="AI session not found."
        )

    result = db.execute(
        sa_update(MetoConversation)
        .where(MetoConversation.id == session_id, MetoConversation.reviewed_at.is_(None))
        .values(reviewed_at=utcnow(), reviewed_by_user_id=actor.id)
    )
    won = result.rowcount == 1
    if won:
        audit.record(
            db,
            actor_type="admin",
            actor_id=actor.id,
            action="ai_session.review",
            resource_type="ai_session_safety",
            resource_id=session_id,
            outcome="success",
            severity="info",
        )
    db.commit()

    # The Core UPDATE above bypassed the ORM identity map, so `conv` may hold
    # stale (pre-update) attribute values whether we won or lost the race —
    # always re-read from the DB before building the response.
    db.refresh(conv)

    signals = _safety_signals(db, [conv.id]).get(conv.id, (False, False))
    users = _users_by_id(
        db,
        {conv.user_id} | ({conv.reviewed_by_user_id} if conv.reviewed_by_user_id else set()),
    )
    return _to_out(
        conv,
        signals,
        users.get(conv.user_id),
        users.get(conv.reviewed_by_user_id) if conv.reviewed_by_user_id else None,
    )
