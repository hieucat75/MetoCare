"""Terms of Use & Privacy Policy acceptance record.

Distinct from:
- ``governance.Consent`` — patient→party data-sharing consent (doctor linking).
- ``meto.MetoConsent`` — granular per-data-type AI consent.

This table captures the one-time legal acceptance a user makes at the end of
registration: which Terms/Privacy versions they accepted, when, and the client
context (app version, locale, timezone, ip, platform) for auditability.

Recorded once per (user_id, terms_version); a future Terms version yields a new
row so re-acceptance is tracked over time.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from ._mixins import TimestampMixin, UUIDPrimaryKey


class TermsConsent(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "terms_consents"
    __table_args__ = (
        UniqueConstraint("user_id", "terms_version", name="uq_terms_consent_user_version"),
    )

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    terms_version: Mapped[str] = mapped_column(String(32), nullable=False)
    privacy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    accepted_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Client context — all optional (best-effort capture from the browser/request).
    app_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    locale: Mapped[str | None] = mapped_column(String(32), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    device_platform: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Where/how the acceptance happened, and the UI language shown at the time.
    accepted_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    accepted_language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Future-proofing: set when a user withdraws this consent.
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
