"""Notification API routes (T23 — Notification Scaffold).

Endpoints:
  GET    /notifications              PATIENT, DOCTOR, ADMIN — own notifications
  PATCH  /notifications/{id}/read   mark single notification as read (own only)
  POST   /notifications/read-all    mark all own notifications as read
  POST   /notifications             INTERNAL_ADMIN / SUPER_ADMIN — create for any user

RBAC:
  AI_SERVICE   → 403 on all notification endpoints
  CLINIC_ADMIN → 403 on all notification endpoints
  MEDICAL_REVIEWER → 403 on creation, allowed to read own
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, current_user, get_session
from app.models.user import UserRole
from app.schemas.notification import NotificationCreate, NotificationOut
from app.services import notification as notification_svc

router = APIRouter(prefix="/notifications", tags=["notifications"])

# ---------------------------------------------------------------------------
# Role constants
# ---------------------------------------------------------------------------

_ADMIN_ROLES: frozenset[str] = frozenset({
    UserRole.INTERNAL_ADMIN,
    UserRole.SUPER_ADMIN,
})

_READ_ALLOWED_ROLES: frozenset[str] = frozenset({
    UserRole.PATIENT,
    UserRole.DOCTOR,
    UserRole.INTERNAL_ADMIN,
    UserRole.SUPER_ADMIN,
    UserRole.MEDICAL_REVIEWER,
})

_BLOCKED_ROLES: frozenset[str] = frozenset({
    UserRole.AI_SERVICE,
    UserRole.CLINIC_ADMIN,
})


def _require_read_access(user: CurrentUser) -> None:
    """Raise 403 for roles blocked from notification endpoints."""
    if user.role in _BLOCKED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{user.role}' is not permitted to access notification endpoints.",
        )


# ---------------------------------------------------------------------------
# GET /notifications — own notifications (paginated, optional unread filter)
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=list[NotificationOut],
    status_code=status.HTTP_200_OK,
    summary="List own notifications",
)
def list_notifications(
    unread_only: bool = Query(False, description="Return only unread notifications"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> list[NotificationOut]:
    """Return the caller's notifications, newest first.

    Query params:
    - ``unread_only=true`` — filter to unread only
    - ``limit`` / ``offset`` — pagination (default 20 / 0)

    Allowed roles: PATIENT, DOCTOR, INTERNAL_ADMIN, SUPER_ADMIN, MEDICAL_REVIEWER.
    AI_SERVICE and CLINIC_ADMIN → 403.
    """
    _require_read_access(user)

    if user.role not in _READ_ALLOWED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{user.role}' is not permitted.",
        )

    notifications = notification_svc.list_notifications(
        db,
        user_id=user.id,
        unread_only=unread_only,
        limit=limit,
        offset=offset,
    )
    return [NotificationOut.model_validate(n) for n in notifications]


# ---------------------------------------------------------------------------
# PATCH /notifications/{notification_id}/read — mark single as read
# ---------------------------------------------------------------------------

@router.patch(
    "/{notification_id}/read",
    response_model=NotificationOut,
    status_code=status.HTTP_200_OK,
    summary="Mark a notification as read",
)
def mark_notification_read(
    notification_id: str,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> NotificationOut:
    """Mark a single notification as read.

    The notification must belong to the calling user (ownership enforced).
    Allowed roles: PATIENT, DOCTOR, INTERNAL_ADMIN, SUPER_ADMIN, MEDICAL_REVIEWER.
    AI_SERVICE and CLINIC_ADMIN → 403.
    """
    _require_read_access(user)

    if user.role not in _READ_ALLOWED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{user.role}' is not permitted.",
        )

    notif = notification_svc.mark_read(
        db, notification_id=notification_id, user_id=user.id
    )
    return NotificationOut.model_validate(notif)


# ---------------------------------------------------------------------------
# POST /notifications/read-all — mark all own notifications as read
# ---------------------------------------------------------------------------

@router.post(
    "/read-all",
    status_code=status.HTTP_200_OK,
    summary="Mark all own notifications as read",
)
def mark_all_notifications_read(
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> dict:
    """Mark all unread notifications for the calling user as read.

    Returns ``{"count": N}`` — number of notifications marked.
    Allowed roles: PATIENT, DOCTOR, INTERNAL_ADMIN, SUPER_ADMIN, MEDICAL_REVIEWER.
    AI_SERVICE and CLINIC_ADMIN → 403.
    """
    _require_read_access(user)

    if user.role not in _READ_ALLOWED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{user.role}' is not permitted.",
        )

    count = notification_svc.mark_all_read(db, user_id=user.id)
    return {"count": count}


# ---------------------------------------------------------------------------
# POST /notifications — admin creates a notification for any user
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=NotificationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a notification (admin only)",
)
def create_notification(
    payload: NotificationCreate,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> NotificationOut:
    """Create a notification for any user.

    Only INTERNAL_ADMIN and SUPER_ADMIN may call this endpoint.
    All other roles → 403.
    """
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins may create notifications.",
        )

    notif = notification_svc.create_notification(
        db,
        user_id=payload.user_id,
        type=payload.type,
        title=payload.title,
        body=payload.body,
        metadata=payload.metadata,
    )
    return NotificationOut.model_validate(notif)
