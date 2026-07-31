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
