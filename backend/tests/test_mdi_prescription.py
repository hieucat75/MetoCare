"""Unit tests for the VN prescription entity extractor (BRD §D)."""

from __future__ import annotations

from app.services.mdi.extractors_prescription import PrescriptionExtractor

_RX = """PHÒNG KHÁM ĐA KHOA ABC
Bác sĩ: Nguyễn Văn A
Ngày 15/03/2026
Chẩn đoán: Đái tháo đường type 2
1) Metformin 500mg - SL 60 viên
   Uống ngày 2 lần, sáng - tối, sau ăn
2) Amlodipine 5mg x 30 viên
   Uống ngày 1 lần vào buổi sáng trong 30 ngày
"""


def _extract(text: str):
    return PrescriptionExtractor().extract(text=text, doc_type="prescription", ocr_confidence=0.9)


def test_one_prescription_yields_many_medication_candidates():
    cands = _extract(_RX)
    assert len(cands) == 2
    names = {c.fields["name"] for c in cands}
    assert names == {"Metformin", "Amlodipine"}
    assert all(c.candidate_type == "medication" for c in cands)


def test_extracts_strength_form_quantity_frequency_route_duration():
    metformin = next(c for c in _extract(_RX) if c.fields["name"] == "Metformin")
    f = metformin.fields
    assert f["strength"] == "500mg"
    assert f["form"] == "viên"
    assert f["quantity"] == "60"
    assert "2 lần" in f["frequency"]
    assert f["route"] == "uống"
    amlo = next(c for c in _extract(_RX) if c.fields["name"] == "Amlodipine")
    assert amlo.fields["duration"] == "30 ngày"


def test_header_context_captured():
    ctx = _extract(_RX)[0].fields["prescription_context"]
    assert ctx["prescribed_date"] == "15/03/2026"
    assert "Đái tháo đường" in ctx["diagnosis"]
    assert "ABC" in ctx["facility"]


def test_dedupe_key_stable_across_reextraction():
    a = {c.fields["name"]: c.dedupe_key for c in _extract(_RX)}
    b = {c.fields["name"]: c.dedupe_key for c in _extract(_RX)}
    assert a == b  # same input → identical keys (no double-promote on re-upload)


def test_high_risk_fields_have_confidence_entries():
    m = _extract(_RX)[0]
    assert set(m.field_confidence) >= {"name", "strength", "frequency"}


def test_no_medicines_yields_empty():
    assert _extract("Chỉ là ghi chú, không có thuốc.") == []


def test_same_drug_different_regimen_stays_two_candidates():
    """P1-1: same name+strength+form but different frequency → NOT deduped away."""
    rx = (
        "1) Insulin 10ui\n"
        "   Tiêm sáng ngày 1 lần\n"
        "2) Insulin 10ui\n"
        "   Tiêm tối ngày 1 lần\n"
    )
    cands = _extract(rx)
    assert len(cands) == 2
    assert cands[0].dedupe_key != cands[1].dedupe_key


def test_dedupe_key_ignores_internal_whitespace_jitter():
    """P1-2: OCR whitespace jitter in the name must not change the key."""
    from app.services.mdi.extractors import make_dedupe_key

    a = make_dedupe_key("medication", "Meto  formin", "500mg", "viên")
    b = make_dedupe_key("medication", "Meto formin", "500mg", "viên")
    assert a == b
