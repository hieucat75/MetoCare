"""Notification Delivery (Master Plan §1.1, BRD §N).

A capability-gated fan-out over the transports that are actually available:
- **deterministic** (in-memory, CI/dev) — records deliveries; carries NO PHI
  (category + ids + deep link only), matching the "no PHI in payload" rule for
  any transport that could leave the device.
- **in-app** (DB-backed `Notification`, always available) — the patient's own
  record, so it may carry the title/body.
- **push** (APNs/FCM) — active only when device credentials are configured (DIST-RC).
- **email** — active only when an email provider is configured.

At the Engineering RC the deterministic + in-app transports always suffice, so
reminders function with no external credential. Push/email are inert until
configured (never assumed present).
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.core import environment_lock as env_lock
from app.core.config import get_settings
from app.models.notification import Notification
from app.services import notifications as deterministic_sink


def _push_configured(settings) -> bool:
    return bool(getattr(settings, "push_credentials_configured", False))


def _email_configured(settings) -> bool:
    return bool(getattr(settings, "email_provider_configured", False))


def deliver(
    db: Session,
    *,
    user_id: str,
    category: str,
    title: str,
    body: str,
    deep_link: str | None = None,
    metadata: dict | None = None,
) -> list[str]:
    """Deliver a notification via every available transport; return their names.

    ``metadata`` must be PHI-free (ids/flags only) — it is what the deterministic
    and (future) push transports carry. The in-app DB record additionally stores
    the human title/body (the patient's own access-controlled data).
    """
    settings = get_settings()
    meta = dict(metadata or {})
    if deep_link:
        meta["deep_link"] = deep_link
    delivered: list[str] = []

    # 1. deterministic (always; PHI-free payload)
    deterministic_sink.notify(user_id, category, **meta)
    delivered.append("deterministic")

    # 2. in-app (always available; patient's own record)
    db.add(
        Notification(
            user_id=user_id,
            type=category,
            title=title,
            body=body,
            is_read=False,
            metadata_=json.dumps(meta) if meta else None,
        )
    )
    db.flush()
    delivered.append("in_app")

    # 3/4. push / email — only when their credentials are configured (DIST-RC)
    # AND this environment is allowed to reach the outside world. A locked
    # (synthetic-only) environment must not be able to send a real person a
    # notification about data that should never have been there: the transports
    # are inert today only because no credentials are configured, and "inert by
    # accident" stops being true the moment someone adds them.
    if not env_lock.outbound_transports_permitted():
        return delivered
    if _push_configured(settings):  # pragma: no cover - no creds at ENG-RC
        delivered.append("push")
    if _email_configured(settings):  # pragma: no cover - no provider at ENG-RC
        delivered.append("email")

    return delivered
