"""Consultation-scoped doctor data-sharing consent record.

One row per consultation. Created in the same transaction as the consultation
itself, so a consultation can never exist without the grant that authorised it.

Nothing in this table is PHI: identifiers, category keys, version stamps and
timestamps only. The categories column names *kinds* of data the patient agreed
to share — never any of the data itself.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.database import Base
from app.domain.consultation_consent_policy import PURPOSE_DOCTOR_CONSULTATION

from ._mixins import TimestampMixin, UUIDPrimaryKey


class ConsultationDataConsent(UUIDPrimaryKey, TimestampMixin, Base):
    """The patient's explicit grant to share health data for ONE consultation.

    ``is_active_at`` is the single definition of "this consent authorises access
    right now" and is the only thing the enforcement path should ask. It is
    fail-closed by construction: every condition must hold, and an unrecognised
    state is not active.
    """

    __tablename__ = "consultation_data_consents"
    __table_args__ = (
        # One consent per consultation. Revocation sets ``revoked_at`` on this
        # row; it is never deleted, and no second row can shadow it.
        UniqueConstraint("consultation_id", name="uq_consultation_data_consent_consultation"),
    )

    consultation_id: Mapped[str] = mapped_column(
        ForeignKey("consultations.id"), index=True, nullable=False
    )
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    # References the Doctor aggregate (doctors.id), NOT users.id — matches
    # Consultation.doctor_id so the two can be compared directly.
    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctors.id"), index=True, nullable=False)

    purpose: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PURPOSE_DOCTOR_CONSULTATION
    )
    # Semantics of the grant — the access decision fails closed on this.
    consent_version: Mapped[str] = mapped_column(String(16), nullable=False)
    # Copy the patient read — recorded for audit, not part of the decision.
    policy_version: Mapped[str] = mapped_column(String(16), nullable=False)

    # Category keys the patient granted. Never data, only kinds of data.
    categories: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    granted_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Client context — where the patient gave the consent ('web' | 'mobile').
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    client_app_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    locale: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Linkage to the append-only AuditLog row written when the grant was made.
    audit_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)

    def granted_categories(self) -> frozenset[str]:
        """Categories on this row, defensively coerced to a set of strings."""
        raw = self.categories or []
        if not isinstance(raw, (list, tuple)):
            return frozenset()
        return frozenset(c for c in raw if isinstance(c, str))

    def is_active_at(self, now: dt.datetime, *, current_consent_version: str) -> bool:
        """True iff this grant authorises doctor access at *now*.

        Fail-closed on every axis: revoked, wrong purpose, a stale consent
        version, or an empty category set all mean "no access".
        """
        from app.core.clock import as_naive_utc

        if self.purpose != PURPOSE_DOCTOR_CONSULTATION:
            return False
        if self.consent_version != current_consent_version:
            return False
        reference = as_naive_utc(now)
        revoked_at = as_naive_utc(self.revoked_at)
        if revoked_at is not None and reference >= revoked_at:
            return False
        granted_at = as_naive_utc(self.granted_at)
        if granted_at is None or reference < granted_at:
            return False
        return bool(self.granted_categories())
