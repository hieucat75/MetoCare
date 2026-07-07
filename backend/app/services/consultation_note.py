"""Consultation notes — APPEND-ONLY doctor recommendations (T10).

There is intentionally NO update or delete function. A correction is a new note.
Patients may read notes only after the consultation is COMPLETED.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
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
    status_: str = "finalized",
) -> ConsultationNote:
    """Append a note. The consultation must belong to the calling doctor.

    ``status_='draft'`` (Lưu nháp) and ``status_='finalized'`` (Hoàn tất) both
    create a brand new row — there is no update path, so re-saving a draft or
    finalizing never mutates a previous row.
    """
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
        status=status_,
        finalized_at=utcnow() if status_ == "finalized" else None,
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


def list_doctor_notes(
    db: Session,
    *,
    doctor_user_id: str,
    consultation_id: str | None = None,
    status_: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[dict]]:
    """Doctor-wide notes list, scoped to the calling doctor's own notes only.

    Returns only the LATEST note per consultation (the current draft or the
    most recently finalized note) so repeated drafts don't clutter the list —
    the append-only history is still fully available via the existing
    per-consultation ``GET /consultations/{id}/notes``. Each item includes the
    consultation's ``patient_id`` (joined) so the caller can enrich with a
    display name without a second round-trip per note.
    """
    doctor = get_doctor_by_user_id(db, doctor_user_id)
    if doctor is None:
        return 0, []

    stmt = (
        select(ConsultationNote, Consultation.patient_id)
        .join(Consultation, ConsultationNote.consultation_id == Consultation.id)
        .where(ConsultationNote.doctor_id == doctor.id)
    )
    if consultation_id:
        stmt = stmt.where(ConsultationNote.consultation_id == consultation_id)
    stmt = stmt.order_by(ConsultationNote.created_at.desc())
    rows = db.execute(stmt).all()

    latest_per_consultation: dict[str, dict] = {}
    for note, patient_id in rows:
        latest_per_consultation.setdefault(
            note.consultation_id,
            {
                "id": note.id,
                "consultation_id": note.consultation_id,
                "patient_id": patient_id,
                "note_type": note.note_type,
                "status": note.status,
                "content": note.content,
                "created_at": note.created_at,
                "finalized_at": note.finalized_at,
            },
        )
    latest = list(latest_per_consultation.values())

    if status_:
        latest = [n for n in latest if n["status"] == status_]

    latest.sort(key=lambda n: n["created_at"], reverse=True)
    total = len(latest)
    return total, latest[offset : offset + limit]


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
