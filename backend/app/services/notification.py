"""Notification service (T23 — Notification Scaffold).

Functions:
  create_notification   — create a new notification for a user
  list_notifications    — list notifications for a user (optionally unread-only)
  mark_read             — mark a single notification as read (ownership check)
  mark_all_read         — mark all unread notifications as read for a user
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.notification import Notification


def create_notification(
    db: Session,
    *,
    user_id: str,
    type: str,
    title: str,
    body: str,
    metadata: dict[str, Any] | None = None,
) -> Notification:
    """Create and persist a new notification.

    Args:
        db:       database session
        user_id:  recipient user id
        type:     notification type string
        title:    short notification title
        body:     full notification text
        metadata: optional JSON-serialisable dict with extra context

    Returns:
        The newly created Notification instance.
    """
    notif = Notification(
        user_id=user_id,
        type=type,
        title=title,
        body=body,
        is_read=False,
        metadata_=json.dumps(metadata) if metadata is not None else None,
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return notif


def list_notifications(
    db: Session,
    *,
    user_id: str,
    unread_only: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> list[Notification]:
    """Return notifications for a user, newest first.

    Args:
        db:          database session
        user_id:     the recipient's user id
        unread_only: when True, return only unread notifications
        limit:       max rows to return (default 20)
        offset:      pagination offset (default 0)

    Returns:
        List of Notification rows, ordered by created_at descending.
    """
    stmt = (
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if unread_only:
        stmt = stmt.where(Notification.is_read == False)  # noqa: E712
    return list(db.execute(stmt).scalars().all())


def mark_read(
    db: Session,
    *,
    notification_id: str,
    user_id: str,
) -> Notification:
    """Mark a single notification as read.

    Performs an ownership check — the notification must belong to user_id.

    Args:
        db:              database session
        notification_id: the notification to mark
        user_id:         caller's user id (ownership check)

    Raises:
        404 — notification not found
        403 — notification belongs to a different user

    Returns:
        The updated Notification instance.
    """
    notif = db.get(Notification, notification_id)
    if notif is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found.",
        )
    if notif.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You may only mark your own notifications as read.",
        )
    if not notif.is_read:
        notif.is_read = True
        notif.read_at = dt.datetime.now(dt.UTC)
        db.add(notif)
        db.commit()
        db.refresh(notif)
    return notif


def mark_all_read(
    db: Session,
    *,
    user_id: str,
) -> int:
    """Mark all unread notifications for a user as read.

    Args:
        db:      database session
        user_id: the user whose notifications to mark

    Returns:
        Number of notifications that were updated.
    """
    now = dt.datetime.now(dt.UTC)
    result = db.execute(
        update(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.is_read == False,  # noqa: E712
        )
        .values(is_read=True, read_at=now)
    )
    db.commit()
    return result.rowcount
