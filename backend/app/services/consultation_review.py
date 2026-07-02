"""Consultation reviews + doctor rating aggregation (T10).

A patient may review a consultation only after it is COMPLETED, only their own,
and only once. Creating a review recomputes the doctor's rating_avg/rating_count.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.care import Doctor
from app.models.consultation import (
    ConsultationReview,
    ConsultationStatus,
)
from app.services import audit
from app.services.consultation import get_consultation_or_404


def create_review(
    db: Session,
    *,
    consultation_id: str,
    patient_profile_id: str,
    rating: int,
    feedback: str | None = None,
) -> ConsultationReview:
    consultation = get_consultation_or_404(db, consultation_id)
    if consultation.patient_id != patient_profile_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You may only review your own consultation.",
        )
    if consultation.status != ConsultationStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You can only review a completed consultation.",
        )
    existing = db.execute(
        select(ConsultationReview).where(
            ConsultationReview.consultation_id == consultation_id
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This consultation has already been reviewed.",
        )
    if rating is None or int(rating) < 1 or int(rating) > 5:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="rating must be between 1 and 5.",
        )

    review = ConsultationReview(
        consultation_id=consultation_id,
        patient_id=patient_profile_id,
        doctor_id=consultation.doctor_id,
        rating=int(rating),
        feedback=feedback,
    )
    db.add(review)
    db.flush()

    _recompute_doctor_rating(db, consultation.doctor_id)

    audit.record(
        db,
        actor_type="patient",
        actor_id=patient_profile_id,
        action="consultation_review_created",
        resource_type="consultation_review",
        resource_id=review.id,
        severity="info",
    )
    db.commit()
    db.refresh(review)
    return review


def _recompute_doctor_rating(db: Session, doctor_id: str) -> None:
    """Recompute rating_avg / rating_count for a doctor from all reviews."""
    count, avg = db.execute(
        select(func.count(ConsultationReview.id), func.avg(ConsultationReview.rating)).where(
            ConsultationReview.doctor_id == doctor_id
        )
    ).one()
    doctor = db.get(Doctor, doctor_id)
    if doctor is not None:
        doctor.rating_count = int(count or 0)
        doctor.rating_avg = round(float(avg), 2) if avg is not None else 0.0
        db.add(doctor)
    db.flush()
