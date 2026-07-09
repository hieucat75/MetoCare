"""Cross-cutting governance models: Consent + AuditLog.

Data_Model_Overview §3.2, §4.5 and Security_Compliance_Framework. Consent gates
access to patient data; AuditLog is append-only and records every access/action
(including AI reads) without storing sensitive content.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.database import Base

from ._mixins import _NOW, TimestampMixin, UUIDPrimaryKey


class Consent(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "consents"

    patient_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    consent_type: Mapped[str] = mapped_column(String(48), nullable=False)
    data_scope: Mapped[str] = mapped_column(String(128), nullable=False)
    # doctor / clinic id the consent is granted to
    granted_to: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    valid_from: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW, nullable=False
    )
    valid_until: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    def is_active(self, at: dt.datetime, scope: str, grantee: str) -> bool:
        from app.core.clock import as_naive_utc

        at = as_naive_utc(at)
        valid_from = as_naive_utc(self.valid_from)
        valid_until = as_naive_utc(self.valid_until)
        revoked_at = as_naive_utc(self.revoked_at)

        if revoked_at is not None and at >= revoked_at:
            return False
        if valid_from is not None and at < valid_from:
            return False
        if valid_until is not None and at > valid_until:
            return False
        if self.granted_to != grantee:
            return False
        # "*" scope means full; otherwise exact match.
        return self.data_scope in ("*", scope)


class AuditLog(UUIDPrimaryKey, Base):
    """Append-only. No update/delete in application code. No sensitive content."""

    __tablename__ = "audit_logs"

    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(48), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(36), index=True)
    outcome: Mapped[str] = mapped_column(String(16), default="success")  # success/deny
    severity: Mapped[str] = mapped_column(String(16), default="info")  # info/warning/high
    ip_address: Mapped[str | None] = mapped_column(String(64))
    device: Mapped[str | None] = mapped_column(String(128))
    timestamp: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW, index=True, nullable=False
    )
    # Clinic SaaS Phase C0 (DATA_MODEL.md §9): NULL = platform-global event.
    # No FK constraint — mirrors `granted_to`/`resource_id`'s bare-string
    # convention; AuditLog intentionally never references entities that might
    # later be pruned/archived independent of the append-only log.
    clinic_id: Mapped[str | None] = mapped_column(String(36))
    # Clinic SaaS C1 (BR-M05-02 and later BRs needing before/after capture,
    # e.g. appointment reschedule, invoice discount): structured, PHI-free
    # metadata only — reference IDs and business-rule values (old/new price,
    # old/new status), never note/lab/diagnosis content. Same discipline as
    # `resource_id` (audit.py docstring).
    details: Mapped[dict | None] = mapped_column(JSON)

    __table_args__ = (Index("ix_audit_logs_clinic_timestamp", "clinic_id", "timestamp"),)
