"""PatientProfile model (Data_Model_Overview §3.2).

Classification: Sensitive health data. Access must be consent-gated + audited
(enforced at the service layer, not the model).
"""

from __future__ import annotations

from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.crypto import EncryptedString
from app.core.database import Base

from ._mixins import TimestampMixin, UUIDPrimaryKey


class PatientProfile(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "patient_profiles"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), index=True, unique=True, nullable=False
    )
    # ---- PHI: field-level encrypted at rest ----
    # All columns below are nullable (a patient may not have entered them), so
    # a failed decrypt falls back to None like any other "not provided" value
    # rather than raising — consistent with the existing nullable contract.
    full_name: Mapped[str | None] = mapped_column(EncryptedString(on_decrypt_failure="none"))
    dob: Mapped[str | None] = mapped_column(
        EncryptedString(on_decrypt_failure="none")
    )  # ISO date string, encrypted
    phone: Mapped[str | None] = mapped_column(EncryptedString(on_decrypt_failure="none"))
    address: Mapped[str | None] = mapped_column(EncryptedString(on_decrypt_failure="none"))
    known_conditions: Mapped[str | None] = mapped_column(EncryptedString(on_decrypt_failure="none"))
    allergies: Mapped[str | None] = mapped_column(EncryptedString(on_decrypt_failure="none"))
    family_history: Mapped[str | None] = mapped_column(EncryptedString(on_decrypt_failure="none"))
    lifestyle_profile: Mapped[str | None] = mapped_column(
        EncryptedString(on_decrypt_failure="none")
    )
    # ---- Non-identity attributes (used in scoring/queries) — plaintext ----
    gender: Mapped[str | None] = mapped_column(String(16))
    height_cm: Mapped[float | None] = mapped_column(Float)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    waist_cm: Mapped[float | None] = mapped_column(Float)
    risk_segment: Mapped[str | None] = mapped_column(String(64))
