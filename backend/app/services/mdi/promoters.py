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

from .extractors_general import MAX_MEDICATION_NAME_LEN
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
    """Roll instructions/quantity/route/duration into the free-text note (no PHI
    beyond what the patient photographed and confirmed).

    CLIN PS-2: the extracted ``quantity`` (a bare number captured from "SL/số
    lượng: N", "x N", or "N viên/ống…") is preserved here as an explicit
    "Số lượng" note rather than injected into ``dose``. In VN prescriptions that
    number is most often the *dispensed total*, not a per-administration amount,
    so promoting it into the dose could dangerously misstate the dose (e.g. a
    30-tablet "dose"). Recording it in the note keeps the information on the
    confirmed medication statement — patient-reviewable and provenance-preserved
    (the raw value stays in ``candidate.fields_json``) — without that hazard."""
    quantity = fields.get("quantity")
    bits = [
        fields.get("instructions"),
        f"Số lượng: {str(quantity).strip()}" if quantity not in (None, "") else None,
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
        # CLIN PS-8 (defence in depth, the extractor is the primary control): a
        # medication name that long is a mis-parsed OCR line, not a drug. Letting
        # it through would pollute the medication list, the Meto context block and
        # the reminder body — and is the cleanest prompt-injection vehicle.
        if len(name) > MAX_MEDICATION_NAME_LEN:
            raise PromotionInvalid("Tên thuốc quá dài — vui lòng sửa lại tên thuốc rồi xác nhận.")

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


class RecordOnlyPromoter:
    """Promoter for general-report candidate types with NO separate canonical table
    (diagnosis / procedure / finding / recommendation / follow_up — §1.9).

    Confirming marks the candidate confirmed and records a PromotionLink back to the
    candidate itself as the confirmed record; the unified timeline (Journey 3) reads
    confirmed candidates directly. A diagnosis thus becomes a confirmed record ONLY
    on explicit patient confirmation — never automatically (§1.9). A follow_up's
    actual reminder is scheduled by the Journey-3 reminder engine; confirmation here
    records the intent without auto-scheduling.
    """

    def promote(
        self,
        db: Session,
        candidate: ExtractionCandidate,
        *,
        actor_user_id: str,
        merge_target_id: str | None = None,
    ) -> PromotionOutcome:
        if merge_target_id:
            # These types have no separate canonical record to merge into.
            raise PromotionDenied("Loại mục này không hỗ trợ gộp.")
        if not (candidate.fields_json or {}).get("text", "").strip():
            raise PromotionInvalid("Nội dung mục trống — không thể xác nhận.")
        return PromotionOutcome(candidate.candidate_type, candidate.id, ACTION_CREATED)


def _canonical_for(test_name: str | None) -> str | None:
    """Resolve a lab label to its canonical analyte using the HARDENED matcher.

    Same matcher as the /lab-uploads path and the OCR lab extractor, so all three
    agree. Labels with no safe canonical (non-HDL, VLDL, lipid ratios) resolve to
    None rather than to a neighbouring analyte.
    """
    if not test_name:
        return None
    from app.services.lab_parser import _match_biomarker, _strip_accents, build_alias_index

    matched = _match_biomarker(_strip_accents(test_name.lower()), build_alias_index())
    return matched[0].canonical if matched else None


def _provenance_for(test_name: str | None) -> dict:
    """Provenance for the label AS CONFIRMED, re-derived at promotion time.

    Not the provenance the extractor recorded: `_apply_corrections` can change
    `test_name` before promotion, so the extractor's entry describes the label the
    OCR read, which may no longer be the label being promoted. Recording the stale
    one would be worse than recording nothing — it would attribute the stored
    analyte to an alias that never fired for it.
    """
    from app.services.lab_parser import resolve_with_provenance

    return resolve_with_provenance(test_name)


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
        # Re-derive the canonical from the (possibly corrected) test_name rather
        # than trusting the stored field. `_apply_corrections` merges an arbitrary
        # flat dict into fields_json before promotion, so the stored `canonical`
        # is patient-influenced: blanking it skipped this guard entirely, and
        # correcting `test_name` to another analyte left a stale `canonical` so
        # the guard validated the OLD analyte's units while `create_manual_entry`
        # stored and classified the row as the NEW one. Both routes reached the
        # silent false-normal this guard exists to prevent.
        # Resolve with the hardened matcher and NEVER fall back to the stored
        # `canonical`. `_apply_corrections` merges an arbitrary flat dict into
        # fields_json before promotion, so a correction of {"canonical": null}
        # used to blank the field, make this guard vacuous, and let
        # create_manual_entry re-derive with the unhardened matcher — the exact
        # silent false-normal the guard exists to stop.
        canonical = _canonical_for(test_name)
        if canonical is None:
            # No safe canonical for this label (non-HDL, VLDL, a lipid ratio, or
            # simply unrecognised). Refuse rather than store an unclassifiable row
            # that a later reader would try to interpret.
            raise PromotionInvalid(
                "Không nhận dạng được chỉ số xét nghiệm từ tên này — "
                "vui lòng sửa tên xét nghiệm rồi xác nhận lại."
            )
        if not is_unit_convertible(canonical, unit):
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
                    # Hand the hardened resolution down so the storage layer does
                    # not re-derive it with a different (weaker) matcher.
                    "canonical": canonical,
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
        # Persist provenance for the label AS CONFIRMED onto the candidate, next
        # to the promotion it produced. The candidate is the durable audit record
        # linking "what the report said" to "what we stored", and fields_json is
        # already encrypted, so this adds no new PHI surface. Without it, a
        # wrong-analyte report cannot be reconstructed after the fact: the stored
        # row names a canonical and nothing says which alias bridged them.
        provenance = _provenance_for(test_name)
        provenance["promoted_lab_result_id"] = rows[0].id
        candidate.fields_json = {
            **fields,
            "promotion_provenance": provenance,
        }
        return PromotionOutcome("lab_result", rows[0].id, ACTION_CREATED)
