"""Doctor Review Workflow API endpoints.

Handles queue retrieval, recommendation submission, doctor review decisions, and single reads.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, current_user, get_session, require_roles
from app.core.clock import utcnow
from app.models.ai import AIClinicalRecommendation
from app.models.care import Doctor, DoctorClinic, Encounter
from app.models.governance import Consent
from app.models.user import User, UserRole
from app.schemas.ai import DoctorReviewDecision
from app.schemas.clinical import AIClinicalRecommendationOut
from app.services.doctor_review import DoctorReviewService, PermissionDenied

router = APIRouter(prefix="/review", tags=["doctor_review"])


def _check_recommendation_read_access(
    db: Session,
    rec: AIClinicalRecommendation,
    user: CurrentUser,
) -> None:
    role = user.role
    # Admin/Reviewer bypass
    if role in (UserRole.INTERNAL_ADMIN, UserRole.SUPER_ADMIN, UserRole.MEDICAL_REVIEWER):
        return

    if role == UserRole.DOCTOR:
        doctor_rec = db.execute(
            select(Doctor).where(Doctor.user_id == user.id)
        ).scalar_one_or_none()
        if not doctor_rec:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not registered as a doctor.",
            )

        # 1. Directly reviewed by this doctor
        if rec.reviewed_by_doctor_id == doctor_rec.id:
            return

        # 2. Linked to an encounter assigned to this doctor
        if rec.encounter_id:
            enc = db.get(Encounter, rec.encounter_id)
            if enc and enc.doctor_id == doctor_rec.id:
                return

        # 3. Active consent for this doctor or their clinics
        clinic_ids = {doctor_rec.clinic_id} if doctor_rec.clinic_id else set()
        clinic_stmt = select(DoctorClinic.clinic_id).where(
            DoctorClinic.doctor_id == doctor_rec.id,
            DoctorClinic.is_active.is_(True),
        )
        clinic_ids.update(db.execute(clinic_stmt).scalars().all())
        clinic_ids.discard(None)

        now = utcnow()
        grantees = [doctor_rec.id, user.id] + list(clinic_ids)
        consent_stmt = select(Consent).where(
            Consent.consent_type == "ai_use",
            Consent.patient_id == rec.patient_id,
            Consent.granted_to.in_(grantees),
            (Consent.revoked_at.is_(None)) | (Consent.revoked_at > now),
            Consent.valid_from <= now,
            (Consent.valid_until.is_(None)) | (Consent.valid_until >= now),
        )
        has_consent = db.execute(consent_stmt).scalars().first() is not None
        if has_consent:
            return

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this recommendation.",
        )

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient permissions to access this recommendation.",
    )


@router.get("/queue", response_model=list[AIClinicalRecommendationOut])
def get_pending_queue(
    user: CurrentUser = Depends(require_roles(UserRole.DOCTOR)),
    db: Session = Depends(get_session),
) -> list[AIClinicalRecommendationOut]:
    """GET pending review queue for doctor."""
    db_user = db.get(User, user.id)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return DoctorReviewService(db).get_pending_queue(db_user)


@router.post(
    "/{rec_id}/submit",
    response_model=AIClinicalRecommendationOut,
    status_code=status.HTTP_201_CREATED,
)
def submit_recommendation(
    rec_id: str,
    user: CurrentUser = Depends(require_roles(UserRole.AI_SERVICE, UserRole.SUPER_ADMIN)),
    db: Session = Depends(get_session),
) -> AIClinicalRecommendationOut:
    """Submit a recommendation for review. Only AI_SERVICE or SUPER_ADMIN."""
    db_user = db.get(User, user.id)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    try:
        rec = DoctorReviewService(db).submit_for_review(rec_id, db_user)
        db.commit()
        db.refresh(rec)
        return rec
    except PermissionDenied as e:
        if "disabled" in str(e):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(e),
            ) from e
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


@router.post("/{rec_id}/review", response_model=AIClinicalRecommendationOut)
def review_recommendation(
    rec_id: str,
    payload: DoctorReviewDecision,
    user: CurrentUser = Depends(require_roles(UserRole.DOCTOR)),
    db: Session = Depends(get_session),
) -> AIClinicalRecommendationOut:
    """Submit doctor decision on a recommendation."""
    db_user = db.get(User, user.id)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    try:
        if payload.verdict == "accepted":
            action_val: Literal["accept", "reject", "request_info"] = "accept"
        elif payload.verdict == "rejected":
            action_val = "reject"
        else:  # "request_info"
            action_val = "request_info"
        rec = DoctorReviewService(db).review(
            recommendation_id=rec_id,
            action=action_val,
            doctor=db_user,
            notes=payload.notes,
        )
        db.commit()
        db.refresh(rec)
        return rec
    except PermissionDenied as e:
        if "disabled" in str(e):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(e),
            ) from e
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        ) from e
    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e),
            ) from e
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.get("/{rec_id}", response_model=AIClinicalRecommendationOut)
def get_recommendation(
    rec_id: str,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> AIClinicalRecommendationOut:
    """Get recommendation by ID. Subject to assignment & role restrictions."""
    rec = db.get(AIClinicalRecommendation, rec_id)
    if not rec or rec.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"AIClinicalRecommendation {rec_id} not found.",
        )
    _check_recommendation_read_access(db, rec, user)
    return rec
