"""ConsentGuard service — unified consent verification (MEDICAL_SAFETY_PACKAGE.md §1.5, §2)."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.feature_flags import FeatureFlag, is_enabled
from app.models.governance import Consent
from app.models.patient import PatientProfile
from app.services import audit
from app.services.consent import ConsentError

logger = logging.getLogger("mcp")


class ConsentDenied(ConsentError):
    """Raised when access is denied by the consent guard."""


class ConsentGuard:
    def __init__(self, db: Session):
        self.db = db

    def require(
        self,
        patient_id: str,
        consent_type: str,  # "ai_use", "data_sharing", etc.
        data_scope: str,
        actor_id: str,
        actor_type: str = "user",
    ) -> None:
        """Raises ConsentDenied (→ HTTP 403) if no active matching Consent.
        Always writes AuditLog(outcome=denied) on failure.
        Always writes AuditLog(outcome=success, severity=info) on pass.
        """
        now = utcnow()

        # Step 1: Feature flag check
        if not is_enabled(FeatureFlag.CONSENT_GATE):
            logger.warning(
                "CONSENT_GATE is disabled. Bypassing check for patient %s (actor: %s).",
                patient_id,
                actor_id,
            )
            audit.record(
                self.db,
                actor_type=actor_type,
                actor_id=actor_id,
                action=f"consent.bypass:{consent_type}",
                resource_type="patient",
                resource_id=patient_id,
                outcome="success",
                severity="warning",
            )
            return

        # Step 2: Patient self-access check (only for non-AI actors)
        is_self = False
        if actor_type != "ai_service":
            if actor_id == patient_id:
                is_self = True
            else:
                profile = self.db.get(PatientProfile, patient_id)
                if profile is not None and profile.user_id == actor_id:
                    is_self = True

        # Step 3: Consent query check
        has_active_consent = False
        if is_self:
            has_active_consent = True
        else:
            stmt = select(Consent).where(
                Consent.patient_id == patient_id,
                Consent.consent_type == consent_type,
                Consent.granted_to == actor_id,
            )
            consents = self.db.execute(stmt).scalars().all()
            for consent in consents:
                if consent.is_active(now, data_scope, actor_id):
                    has_active_consent = True
                    break

        # Step 4: Audit & Raise/Return
        if has_active_consent:
            audit.record(
                self.db,
                actor_type=actor_type,
                actor_id=actor_id,
                action=f"consent.check:{consent_type}",
                resource_type="patient",
                resource_id=patient_id,
                outcome="success",
                severity="info",
            )
        else:
            audit.record(
                self.db,
                actor_type=actor_type,
                actor_id=actor_id,
                action=f"consent.check:{consent_type}",
                resource_type="patient",
                resource_id=patient_id,
                outcome="denied",
                severity="warning",
            )
            raise ConsentDenied(
                f"Actor {actor_id} (type: {actor_type}) has no active consent "
                f"of type '{consent_type}' for patient {patient_id} scope '{data_scope}'."
            )
