"""Concrete MDI promoters (§1.5) — turn confirmed candidates into canonical records.

Registered into the promoter registry at app startup (see ``bootstrap``). Each
promoter is invoked from ``service.confirm_candidate`` / ``merge_candidate`` inside
the request transaction (``commit=False``) so the candidate status, PromotionLink,
and canonical write all commit atomically.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.clinical import Medication
from app.models.medical_document import ExtractionCandidate
from app.services import medication as medication_svc

from .promoter import (
    ACTION_CREATED,
    ACTION_MERGED_INTO,
    PromotionDenied,
    PromotionInvalid,
    PromotionOutcome,
)


def _compose_dose(fields: dict) -> str | None:
    """Prefer an explicit dose; else fall back to strength (+form) for display."""
    dose = (fields.get("dose") or "").strip()
    if dose:
        return dose
    parts = [str(fields.get(k)).strip() for k in ("strength", "form") if fields.get(k)]
    return " ".join(parts) or None


def _compose_note(fields: dict) -> str | None:
    """Roll instructions/route/duration into the free-text note (no PHI beyond
    what the patient photographed and confirmed)."""
    bits = [
        fields.get("instructions"),
        f"Đường dùng: {fields['route']}" if fields.get("route") else None,
        f"Thời gian: {fields['duration']}" if fields.get("duration") else None,
    ]
    joined = " · ".join(b for b in bits if b)
    return joined or None


class MedicationPromoter:
    """Promote a confirmed medication candidate via the statement-first path."""

    def promote(
        self,
        db: Session,
        candidate: ExtractionCandidate,
        *,
        actor_user_id: str,
        merge_target_id: str | None = None,
    ) -> PromotionOutcome:
        fields = candidate.fields_json or {}
        name = (fields.get("name") or "").strip()
        if not name:
            raise PromotionInvalid("Ứng viên thuốc thiếu tên — không thể xác nhận.")

        if merge_target_id:
            return self._merge(db, candidate, merge_target_id)

        record = medication_svc.add_medication(
            db,
            patient_id=candidate.patient_id,
            data={
                "name": name,
                "dose": _compose_dose(fields),
                "frequency": fields.get("frequency"),
                "note": _compose_note(fields),
            },
            actor_user_id=actor_user_id,
            actor_role="patient",
            source_type="ocr_confirmed",
            commit=False,
        )
        return PromotionOutcome("medication", record.id, ACTION_CREATED)

    def _merge(
        self, db: Session, candidate: ExtractionCandidate, merge_target_id: str
    ) -> PromotionOutcome:
        # BOLA (P1-4): the merge target MUST belong to the same patient as the
        # candidate — never let a patient graft a candidate onto another patient's
        # canonical medication.
        target = db.get(Medication, merge_target_id)
        if (
            target is None
            or target.deleted_at is not None
            or target.patient_id != candidate.patient_id
            # A record retired to the terminal entered_in_error state must not be
            # resurrected by grafting a new OCR candidate onto it (P2 state-guard).
            or target.lifecycle_status == "entered_in_error"
        ):
            raise PromotionDenied("Không tìm thấy thuốc để gộp hoặc không có quyền.")
        return PromotionOutcome("medication", target.id, ACTION_MERGED_INTO)
