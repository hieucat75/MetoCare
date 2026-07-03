"""Admin consultation monitoring service (read-only).

Powers the admin portal's consultation monitoring + overview KPIs. Provides a
filtered, joined listing (doctor + patient display names) and aggregate stats
(counts by status, total, paid count, mock revenue).

All functions are read-only — no state transitions happen here. RBAC + MFA are
enforced at the route layer (mirrors the other admin endpoints).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.care import Doctor
from app.models.consultation import (
    Consultation,
    ConsultationPayment,
    ConsultationStatus,
    PaymentStatus,
)
from app.models.patient import PatientProfile


def list_consultations(
    db: Session,
    *,
    status: str | None = None,
    doctor_id: str | None = None,
    patient_id: str | None = None,
    date_from: dt.datetime | None = None,
    date_to: dt.datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Return a filtered, newest-first list of consultations for admin monitoring.

    Joins the doctor's full name and the patient's display name, plus the current
    payment status. Read-only — no PHI beyond identity display names is exposed.
    """
    stmt = (
        select(
            Consultation,
            Doctor.full_name.label("doctor_name"),
            PatientProfile.full_name.label("patient_name"),
            ConsultationPayment.payment_status.label("payment_status"),
        )
        .join(Doctor, Doctor.id == Consultation.doctor_id)
        .join(PatientProfile, PatientProfile.id == Consultation.patient_id)
        .outerjoin(
            ConsultationPayment,
            ConsultationPayment.consultation_id == Consultation.id,
        )
        .where(Consultation.deleted_at.is_(None))
        .order_by(Consultation.created_at.desc())
    )

    if status:
        stmt = stmt.where(Consultation.status == status)
    if doctor_id:
        stmt = stmt.where(Consultation.doctor_id == doctor_id)
    if patient_id:
        stmt = stmt.where(Consultation.patient_id == patient_id)
    if date_from:
        stmt = stmt.where(Consultation.created_at >= date_from)
    if date_to:
        stmt = stmt.where(Consultation.created_at <= date_to)

    stmt = stmt.offset(offset).limit(limit)

    rows = db.execute(stmt).all()
    return [
        {
            "id": c.id,
            "patient_id": c.patient_id,
            "patient_name": patient_name,
            "doctor_id": c.doctor_id,
            "doctor_name": doctor_name,
            "status": c.status,
            "consultation_type": c.consultation_type,
            "consultation_price": c.consultation_price,
            "payment_status": payment_status,
            "created_at": c.created_at,
        }
        for c, doctor_name, patient_name, payment_status in rows
    ]


def consultation_stats(db: Session) -> dict:
    """Aggregate consultation KPIs for the admin overview.

    Returns counts by status (all statuses present, zero-filled), the grand
    total, the paid count, and mock revenue (SUM of consultation_price over
    consultations whose payment is PAID — a mock figure for the MVP).
    """
    by_status: dict[str, int] = {s.value: 0 for s in ConsultationStatus}

    status_rows = db.execute(
        select(Consultation.status, func.count())
        .where(Consultation.deleted_at.is_(None))
        .group_by(Consultation.status)
    ).all()
    for status_value, count in status_rows:
        by_status[str(status_value)] = int(count)

    total = sum(by_status.values())

    paid_count = int(
        db.execute(
            select(func.count())
            .select_from(Consultation)
            .join(
                ConsultationPayment,
                ConsultationPayment.consultation_id == Consultation.id,
            )
            .where(
                Consultation.deleted_at.is_(None),
                ConsultationPayment.payment_status == PaymentStatus.PAID,
            )
        ).scalar_one()
    )

    mock_revenue = float(
        db.execute(
            select(func.coalesce(func.sum(Consultation.consultation_price), 0.0))
            .join(
                ConsultationPayment,
                ConsultationPayment.consultation_id == Consultation.id,
            )
            .where(
                Consultation.deleted_at.is_(None),
                ConsultationPayment.payment_status == PaymentStatus.PAID,
            )
        ).scalar_one()
    )

    return {
        "by_status": by_status,
        "total": total,
        "paid_count": paid_count,
        "mock_revenue": mock_revenue,
    }
