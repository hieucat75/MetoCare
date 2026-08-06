"""Unit tests for the general medical-report extractor (BRD §F / §1.9)."""

from __future__ import annotations

from app.services.mdi.extractors_general import GeneralReportExtractor

_RPT = """BỆNH VIỆN ABC - PHIẾU XUẤT VIỆN
Ngày ra viện: 18/03/2026
Chẩn đoán: Tăng huyết áp vô căn
Kết luận: Huyết áp kiểm soát tốt khi dùng thuốc
Lời dặn: Ăn nhạt, tập thể dục đều
Tái khám: sau 4 tuần
"""


def _extract(text: str):
    return GeneralReportExtractor().extract(text=text, doc_type="general", ocr_confidence=0.9)


def test_typed_candidates_extracted():
    cands = _extract(_RPT)
    by_type = {c.candidate_type: c.fields["text"] for c in cands}
    assert by_type["diagnosis"] == "Tăng huyết áp vô căn"
    assert by_type["follow_up"] == "sau 4 tuần"
    assert by_type["recommendation"] == "Ăn nhạt, tập thể dục đều"
    assert "finding" in by_type


def test_summary_and_date_captured():
    c = _extract(_RPT)[0]
    assert c.fields["report_date"] == "18/03/2026"
    assert c.fields["summary"]  # non-empty structured summary


def test_dedupe_key_stable():
    a = [c.dedupe_key for c in _extract(_RPT)]
    b = [c.dedupe_key for c in _extract(_RPT)]
    assert a == b


def test_no_section_labels_yields_empty():
    assert _extract("Chỉ là văn bản tự do không có nhãn mục.") == []


def test_multi_label_on_one_line_splits_into_separate_candidates():
    """P1: a follow_up sharing a line with a diagnosis must be its own candidate."""
    cands = _extract("Chẩn đoán: Tăng huyết áp - Tái khám: sau 2 tuần\n")
    by_type = {c.candidate_type: c.fields["text"] for c in cands}
    assert by_type["diagnosis"] == "Tăng huyết áp -"  # bounded before the next label
    assert by_type["follow_up"] == "sau 2 tuần"


def test_medication_order_line_retyped_to_medication():
    """P1: a dose-bearing 'chỉ định' line is a medication order — routed to the
    medication path (reconciliation), never a record-only procedure."""
    cands = _extract("Chỉ định: Metformin 500mg x 2 viên/ngày\n")
    med = cands[0]
    assert med.candidate_type == "medication"
    assert med.fields["name"]  # MedicationPromoter reads fields["name"]


def test_label_on_own_line_reads_content_below():
    """P2: header label with content on the next line is still extracted."""
    cands = _extract("Chẩn đoán:\nTăng huyết áp vô căn\n")
    assert cands and cands[0].candidate_type == "diagnosis"
    assert cands[0].fields["text"] == "Tăng huyết áp vô căn"


# ── CLIN PS-8: a whole OCR line must never become a medication name ──────────

def test_general_report_med_line_parses_name_not_whole_sentence():
    """CLIN PS-8: the re-typed medication candidate carries a PARSED drug name,
    not the entire report line — otherwise a paragraph lands in Medication.name
    and from there in the med list, the Meto context and the reminder copy."""
    content = (
        "Bệnh nhân đã dùng Metformin 500mg trước khi nhập viện, tiếp tục uống "
        "ngày 2 lần sau ăn theo hướng dẫn của bác sĩ điều trị tại khoa nội tiết"
    )
    cands = _extract(f"Lời dặn: {content}\n")
    med = next(c for c in cands if c.candidate_type == "medication")
    name = med.fields["name"]
    assert "Metformin" in name
    assert len(name) <= 120
    assert "hướng dẫn của bác sĩ" not in name
    assert med.fields["strength"] == "500mg"
    assert med.fields["text"] == content  # full line kept as provenance


def test_general_report_unparseable_med_line_keeps_original_type():
    """CLIN PS-8: if no drug name can be parsed out, keep the original candidate
    type rather than forcing a garbage medication."""
    cands = _extract("Kết luận: 500mg\n")
    assert cands
    assert cands[0].candidate_type == "finding"
    assert "name" not in cands[0].fields


def test_promoter_rejects_overlong_medication_name():
    """CLIN PS-8 (defence in depth): the promoter refuses an implausible name."""
    import pytest
    from app.models.medical_document import ExtractionCandidate
    from app.services.mdi.promoter import PromotionInvalid
    from app.services.mdi.promoters import MedicationPromoter

    cand = ExtractionCandidate(
        patient_id="p1",
        candidate_type="medication",
        fields_json={"name": "Bệnh nhân đã dùng thuốc " * 20},
        dedupe_key="k",
        status="needs_review",
    )
    with pytest.raises(PromotionInvalid):
        MedicationPromoter().promote(None, cand, actor_user_id="u1")
