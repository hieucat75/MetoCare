"""DoctorReviewService — manages the doctor review workflow for AI recommendations.

See MEDICAL_SAFETY_PACKAGE.md §1.4, §1.5, §2.
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.feature_flags import FeatureFlag, is_enabled
from app.models.ai import AIClinicalRecommendation, RecommendationStatus
from app.models.care import Doctor, DoctorClinic, Encounter
from app.models.governance import Consent
from app.models.user import User, UserRole
from app.services import audit


class PermissionDenied(PermissionError):
    """Raised when an actor lacks permission to perform a clinical review action."""


class DoctorReviewService:
    def __init__(self, db: Session):
        self.db = db

    def submit_for_review(self, recommendation_id: str, actor: User) -> AIClinicalRecommendation:
        """Set status PENDING_REVIEW. Only AI_SERVICE or SUPER_ADMIN."""
        if not is_enabled(FeatureFlag.DOCTOR_REVIEW_GATE):
            raise PermissionDenied("DOCTOR_REVIEW_GATE is disabled (fail closed).")

        # Verify role/actor permission
        is_ai = False
        if actor is not None:
            if hasattr(actor, "role") and str(actor.role) == "ai_service":
                is_ai = True
            elif hasattr(actor, "email") and actor.email == "ai_service@metocare.internal":
                is_ai = True

        is_admin = actor is not None and hasattr(actor, "role") and str(actor.role) == "super_admin"

        if not (is_ai or is_admin):
            audit.record(
                self.db,
                actor_type=str(actor.role) if actor else "unknown",
                actor_id=actor.id if actor else None,
                action="ai.recommendation_submit_attempt",
                resource_type="ai_clinical_recommendation",
                resource_id=recommendation_id,
                outcome="denied",
                severity="high",
            )
            raise PermissionDenied(
                "Only AI_SERVICE or SUPER_ADMIN can submit recommendations for review."
            )

        rec = self.db.get(AIClinicalRecommendation, recommendation_id)
        if not rec:
            raise ValueError(f"AIClinicalRecommendation {recommendation_id} not found.")

        # AI code path can only set to pending_review
        rec.status = RecommendationStatus.PENDING_REVIEW
        self.db.flush()

        audit.record(
            self.db,
            actor_type="ai_service" if is_ai else "super_admin",
            actor_id=actor.id if actor else None,
            action="ai.recommendation_submitted",
            resource_type="ai_clinical_recommendation",
            resource_id=recommendation_id,
            outcome="success",
            severity="info",
        )

        return rec

    def review(
        self,
        recommendation_id: str,
        action: Literal["accept", "reject", "request_info"],
        doctor: User,
        notes: str | None = None,
    ) -> AIClinicalRecommendation:
        """DOCTOR only. Sets status, reviewed_by_doctor_id, reviewed_at, safety_cleared."""
        if not is_enabled(FeatureFlag.DOCTOR_REVIEW_GATE):
            raise PermissionDenied("DOCTOR_REVIEW_GATE is disabled (fail closed).")

        # 1. Hard-block non-DOCTOR actors
        if doctor.role != UserRole.DOCTOR:
            audit.record(
                self.db,
                actor_type=str(doctor.role),
                actor_id=doctor.id,
                action=f"ai.recommendation_review_attempt_{action}",
                resource_type="ai_clinical_recommendation",
                resource_id=recommendation_id,
                outcome="denied",
                severity="warning",
            )
            raise PermissionDenied("Only users with role DOCTOR can review recommendations.")

        # Find doctor's clinic record
        doctor_rec = self.db.execute(
            select(Doctor).where(Doctor.user_id == doctor.id)
        ).scalar_one_or_none()
        if not doctor_rec:
            raise PermissionDenied("User is not registered as a doctor.")

        rec = self.db.get(AIClinicalRecommendation, recommendation_id)
        if not rec:
            raise ValueError(f"AIClinicalRecommendation {recommendation_id} not found.")

        # Ensure recommendation is in pending_review
        if rec.status != RecommendationStatus.PENDING_REVIEW:
            raise ValueError(f"Recommendation {recommendation_id} is not in pending_review status.")

        # 2. Update status and safety clearance via direct SQL UPDATE.
        # We MUST NOT use ORM attribute assignment for status/safety_cleared here because
        # AIClinicalRecommendation @validates hooks block 'accepted'/'superseded' from direct
        # assignment (C1 guard). The doctor review service is the ONLY authorised path to
        # set these values; it does so via SQL UPDATE, bypassing the ORM-level validator.
        now = utcnow()

        if action == "accept":
            new_status = RecommendationStatus.ACCEPTED
            new_safety_cleared = True
        elif action == "request_info":
            new_status = RecommendationStatus.REQUEST_INFO
            # Leave safety_cleared as-is (do NOT treat as rejection)
            new_safety_cleared = rec.safety_cleared
        else:  # reject
            new_status = RecommendationStatus.REJECTED
            new_safety_cleared = False

        self.db.execute(
            update(AIClinicalRecommendation)
            .where(AIClinicalRecommendation.id == recommendation_id)
            .values(
                status=new_status,
                safety_cleared=new_safety_cleared,
                reviewed_by_doctor_id=doctor_rec.id,
                reviewed_at=now,
            )
        )

        if action == "accept":
            # 3. Supersede older recommendations of the same type for this patient (bulk)
            prior_ids_result = self.db.execute(
                select(AIClinicalRecommendation.id).where(
                    AIClinicalRecommendation.patient_id == rec.patient_id,
                    AIClinicalRecommendation.recommendation_type == rec.recommendation_type,
                    AIClinicalRecommendation.status == RecommendationStatus.ACCEPTED,
                    AIClinicalRecommendation.id != recommendation_id,
                )
            ).scalars().all()
            if prior_ids_result:
                self.db.execute(
                    update(AIClinicalRecommendation)
                    .where(AIClinicalRecommendation.id.in_(prior_ids_result))
                    .values(status=RecommendationStatus.SUPERSEDED)
                )
                for prior_id in prior_ids_result:
                    audit.record(
                        self.db,
                        actor_type="system",
                        actor_id=None,
                        action="ai.recommendation_superseded",
                        resource_type="ai_clinical_recommendation",
                        resource_id=prior_id,
                        outcome="success",
                        severity="info",
                    )

        self.db.flush()

        if action == "accept":
            audit_action = "ai.recommendation_accepted"
        elif action == "request_info":
            audit_action = "ai.recommendation_request_info"
        else:
            audit_action = "ai.recommendation_rejected"

        audit.record(
            self.db,
            actor_type="doctor",
            actor_id=doctor.id,
            action=audit_action,
            resource_type="ai_clinical_recommendation",
            resource_id=recommendation_id,
            outcome="success",
            severity="info",
        )

        return rec

    def get_pending_queue(self, doctor: User) -> list[AIClinicalRecommendation]:
        """Returns pending_review items for doctor's clinics."""
        if not is_enabled(FeatureFlag.DOCTOR_REVIEW_GATE):
            return []

        if doctor.role != UserRole.DOCTOR:
            return []

        doctor_rec = self.db.execute(
            select(Doctor).where(Doctor.user_id == doctor.id)
        ).scalar_one_or_none()
        if not doctor_rec:
            return []

        # Get doctor's clinics
        clinic_ids = set()
        if doctor_rec.clinic_id:
            clinic_ids.add(doctor_rec.clinic_id)

        clinic_stmt = select(DoctorClinic.clinic_id).where(
            DoctorClinic.doctor_id == doctor_rec.id,
            DoctorClinic.is_active.is_(True),
        )
        clinic_ids.update(self.db.execute(clinic_stmt).scalars().all())

        # Get patient IDs with active consent
        now = utcnow()
        grantees = [doctor_rec.id, doctor.id] + list(clinic_ids)

        consent_stmt = select(Consent).where(
            Consent.consent_type == "ai_use",
            Consent.granted_to.in_(grantees),
            (Consent.revoked_at.is_(None)) | (Consent.revoked_at > now),
            Consent.valid_from <= now,
            (Consent.valid_until.is_(None)) | (Consent.valid_until >= now),
        )
        active_consents = self.db.execute(consent_stmt).scalars().all()
        consented_patient_ids = {c.patient_id for c in active_consents}

        stmt = select(AIClinicalRecommendation).where(
            AIClinicalRecommendation.status == RecommendationStatus.PENDING_REVIEW
        )

        clauses = []
        if consented_patient_ids:
            clauses.append(AIClinicalRecommendation.patient_id.in_(consented_patient_ids))

        # Join with Encounter to get recommendations linked to encounters of this doctor
        encounter_sub = select(AIClinicalRecommendation.id).join(
            Encounter, AIClinicalRecommendation.encounter_id == Encounter.id
        ).where(
            Encounter.doctor_id == doctor_rec.id,
            AIClinicalRecommendation.status == RecommendationStatus.PENDING_REVIEW,
        )
        clauses.append(AIClinicalRecommendation.id.in_(encounter_sub))

        stmt = stmt.where(or_(*clauses))
        return list(self.db.execute(stmt).scalars().all())
