"""Concrete MDI promoters (§1.5) — turn confirmed candidates into canonical records.

Registered into the promoter registry at app startup (see ``bootstrap``). Each
promoter is invoked from ``service.confirm_candidate`` / ``merge_candidate`` inside
the request transaction (``commit=False``) so the candidate status, PromotionLink,
and canonical write all commit atomically.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.domain.lab_normalization import is_unit_convertible
from app.models.clinical import LabResult, Medication
from app.models.medical_document import ExtractionCandidate
from app.services import lab as lab_svc
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


def _parse_date(raw: str | None) -> dt.date | None:
    """Parse a VN dd/mm/yyyy (or dd-mm-yyyy) report date.

    Returns None on any unparseable/ambiguous input — NEVER fabricates "today"
    (review P1): a wrong date silently places an old lab at the top of the trend.
    The lab pipeline handles a null test_date by falling back to insert time and
    sorting undated rows last.
    """
    if raw:
        for sep in ("/", "-", "."):
            parts = raw.split(sep)
            if len(parts) == 3:
                try:
                    d, m, y = (int(p) for p in parts)
                    if y < 100:
                        y += 2000
                    return dt.date(y, m, d)
                except ValueError:
                    continue
    return None


class LabPromoter:
    """Promote a confirmed lab-result candidate into a canonical LabResult
    (+HealthMetric for trends) via the existing lab pipeline (BRD §E)."""

    def promote(
        self,
        db: Session,
        candidate: ExtractionCandidate,
        *,
        actor_user_id: str,
        merge_target_id: str | None = None,
    ) -> PromotionOutcome:
        fields = candidate.fields_json or {}
        test_name = (fields.get("test_name") or "").strip()
        if not test_name or fields.get("value") is None:
            raise PromotionInvalid("Ứng viên xét nghiệm thiếu tên hoặc giá trị.")

        if merge_target_id:
            target = db.get(LabResult, merge_target_id)
            if (
                target is None
                or target.deleted_at is not None
                or target.patient_id != candidate.patient_id
            ):
                raise PromotionDenied("Không tìm thấy kết quả để gộp hoặc không có quyền.")
            return PromotionOutcome("lab_result", target.id, ACTION_MERGED_INTO)

        unit = fields.get("unit") or ""
        # CRITICAL patient-safety (review P0): if this analyte has canonical
        # thresholds but the extracted unit can't be confidently mapped to the
        # canonical/SI unit, refuse to promote — otherwise the value would be
        # classified against the wrong-unit thresholds (silent false-normal /
        # inverted message). The patient corrects the unit and re-confirms.
        canonical = fields.get("canonical")
        if canonical and not is_unit_convertible(canonical, unit):
            raise PromotionInvalid(
                "Đơn vị xét nghiệm chưa rõ — vui lòng sửa đơn vị rồi xác nhận lại."
            )
        # Preserve the ORIGINAL value/unit (§E — never lose what the patient saw);
        # create_manual_entry normalizes to canonical SI for internal trend/classify
        # while keeping original_* for display.
        _doc, rows = lab_svc.create_manual_entry(
            db,
            patient_id=candidate.patient_id,
            requester_id=actor_user_id,
            lab_name=None,
            test_date=_parse_date(fields.get("specimen_date")),
            results=[
                {
                    "test_name": test_name,
                    "value": fields.get("value"),
                    "unit": unit,
                    "reference_range": fields.get("reference_range"),
                    "original_test_name": fields.get("original_test_name") or test_name,
                    "original_value": fields.get("value"),
                    "original_unit": unit,
                }
            ],
            commit=False,
        )
        return PromotionOutcome("lab_result", rows[0].id, ACTION_CREATED)
