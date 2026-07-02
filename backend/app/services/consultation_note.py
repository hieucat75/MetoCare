"""Consultation notes — APPEND-ONLY doctor recommendations (T10).

There is intentionally NO update or delete function. A correction is a new note.
Patients may read notes only after the consultation is COMPLETED.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.consultation import (
    Consultation,
    ConsultationNote,
    ConsultationStatus,
)
from app.services import audit
from app.services.consultation import get_consultation_or_404
from app.services.doctor import get_doctor_by_user_id


def add_note(
    db: Session,
    *,
    consultation_id: str,
    doctor_user_id: str,
    content: str,
    note_type: str = "recommendation",
) -> ConsultationNote:
    """Append a note. The consultation must belong to the calling doctor."""
    consultation = get_consultation_or_404(db, consultation_id)
    doctor = get_doctor_by_user_id(db, doctor_user_id)
    if doctor is None or doctor.id != consultation.doctor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You may only add notes to your own consultation.",
        )
    if not content or not content.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Note content must not be empty.",
        )
    note = ConsultationNote(
        consultation_id=consultation_id,
        doctor_id=doctor.id,
        content=content,
        note_type=note_type or "recommendation",
    )
    db.add(note)
    db.flush()
    audit.record(
        db,
        actor_type="doctor",
        actor_id=doctor.id,
        action="consultation_note_created",
        resource_type="consultation_note",
        resource_id=note.id,
        severity="info",
    )
    db.commit()
    db.refresh(note)
    return note


def list_notes(
    db: Session,
    *,
    consultation_id: str,
    requester_role: str,
    requester_user_id: str,
    patient_profile_id: str | None = None,
) -> list[ConsultationNote]:
    """List notes. Doctor (owner) always; patient (owner) only after COMPLETED."""
    consultation: Consultation = get_consultation_or_404(db, consultation_id)
    role = (requester_role or "").lower()

    if role == "doctor":
        doctor = get_doctor_by_user_id(db, requester_user_id)
        if doctor is None or doctor.id != consultation.doctor_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You may only read notes for your own consultation.",
            )
    elif role == "patient":
        if patient_profile_id is None or consultation.patient_id != patient_profile_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You may only read notes for your own consultation.",
            )
        if consultation.status != ConsultationStatus.COMPLETED:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Notes are available only after the consultation is completed.",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{requester_role}' cannot read consultation notes.",
        )

    rows = db.execute(
        select(ConsultationNote)
        .where(ConsultationNote.consultation_id == consultation_id)
        .order_by(ConsultationNote.created_at.asc())
    ).scalars()
    return list(rows)
