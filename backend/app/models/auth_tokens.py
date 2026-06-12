"""Auth token / MFA persistence: RefreshToken, MfaBackupCode.

Refresh tokens are revocable (rotation + logout + blacklist) via the DB. Backup
codes are stored only as hashes (never plaintext).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from ._mixins import TimestampMixin, UUIDPrimaryKey


class RefreshToken(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    jti: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    # Whether the session this token belongs to was MFA-verified.
    mfa: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Rotation chain: all tokens of one login session share family_id; each
    # rotation increments generation. Reuse of a rotated (revoked) token revokes
    # the whole family (compromise signal).
    family_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    generation: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class MfaBackupCode(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "mfa_backup_codes"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
