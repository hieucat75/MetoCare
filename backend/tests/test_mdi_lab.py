"""Unit tests for the VN lab-report entity extractor (BRD §E)."""

from __future__ import annotations

from app.services.mdi.extractors_lab import LabExtractor

_LAB = """PHÒNG XÉT NGHIỆM ABC
Ngày lấy mẫu: 20/03/2026
Glucose: 6.2 mmol/L (3.9 - 6.4)
HbA1c 6.8 % 4.0-6.0
Cholesterol toàn phần: 5.1 mmol/L
Ghi chú: tái khám sau 3 tháng
"""


def _extract(text: str):
    return LabExtractor().extract(text=text, doc_type="lab_report", ocr_confidence=0.9)


def test_one_report_yields_many_lab_candidates():
    cands = _extract(_LAB)
    canon = {c.fields["canonical"] for c in cands}
    assert canon == {"fasting_glucose", "hba1c", "total_cholesterol"}
    assert all(c.candidate_type == "lab_result" for c in cands)


def test_hba1c_digit_in_name_not_read_as_value():
    """Regression: an analyte name with an embedded digit (HbA1c) must not have
    the digit parsed as the value."""
    hba1c = next(c for c in _extract(_LAB) if c.fields["canonical"] == "hba1c")
    assert hba1c.fields["value"] == 6.8
    assert hba1c.fields["unit"] == "%"
    assert hba1c.fields["reference_range"] == "4.0-6.0"


def test_original_value_and_unit_preserved_verbatim():
    """§E — the extractor never silently normalizes; original value/unit are kept."""
    glucose = next(c for c in _extract(_LAB) if c.fields["canonical"] == "fasting_glucose")
    assert glucose.fields["value"] == 6.2
    assert glucose.fields["unit"] == "mmol/L"
    assert glucose.fields["specimen_date"] == "20/03/2026"


def test_non_biomarker_lines_skipped():
    # Header/facility/note/date lines are not biomarkers → excluded.
    names = {c.fields["test_name"] for c in _extract(_LAB)}
    assert not any("Ghi chú" in n or "PHÒNG" in n for n in names)


def test_comma_decimal_parsed():
    cands = _extract("Glucose: 5,6 mmol/L")
    assert cands[0].fields["value"] == 5.6


def test_dedupe_key_stable_across_reextraction():
    a = [c.dedupe_key for c in _extract(_LAB)]
    b = [c.dedupe_key for c in _extract(_LAB)]
    assert a == b


def test_dedupe_key_ignores_numeric_formatting():
    """P2: "5.6" / "5.60" (same value) → one key across reprocess."""
    a = _extract("Glucose: 5.6 mmol/L")[0].dedupe_key
    b = _extract("Glucose: 5.60 mmol/L")[0].dedupe_key
    assert a == b


def test_is_unit_convertible_guards_unknown_units():
    """P0 helper: only the canonical/SI unit is confidently convertible."""
    from app.domain.lab_normalization import is_unit_convertible

    assert is_unit_convertible("fasting_glucose", "mmol/L") is True  # SI unit
    assert is_unit_convertible("fasting_glucose", "mg/dL") is True  # canonical
    assert is_unit_convertible("fasting_glucose", "xyz") is False  # garbled
    assert is_unit_convertible("fasting_glucose", "") is False  # dropped


def test_parse_date_never_fabricates_today():
    """P1: unparseable / ISO-ordered / empty dates → None, never today."""
    import datetime as dt

    from app.services.mdi.promoters import _parse_date

    assert _parse_date("20/03/2026") == dt.date(2026, 3, 20)
    assert _parse_date("2024-03-15") is None  # ISO order not misread as dd-mm-yyyy
    assert _parse_date("garbage") is None
    assert _parse_date(None) is None


# ── CLIN P0 (integration review): OCR lab labels must never resolve to a
# different analyte. `lab_interpreter.normalize_biomarker` step 4 is a bare
# containment scan, so "VLDL" resolved to `ldl` and "Non-HDL cholesterol" to
# `hdl`. Confirming such a row overwrote the real analyte with a much lower
# number and classified it optimal — a false negative on cardiovascular risk,
# invisible at review time because the card shows the printed label. The
# extractor now uses lab_parser._match_biomarker, which drops these outright.


def test_vldl_is_never_mapped_to_ldl():
    assert _extract("VLDL: 0.9 mmol/L") == []


def test_non_hdl_is_never_mapped_to_hdl():
    assert _extract("Non-HDL cholesterol: 3.9 mmol/L") == []
    assert _extract("non HDL: 3.9 mmol/L") == []


def test_lipid_ratio_is_never_mapped_to_a_concentration():
    assert _extract("Cholesterol/HDL: 4.1") == []


def test_real_lipid_analytes_still_resolve_correctly():
    by_name = {c.fields["test_name"]: c.fields["canonical"] for c in _extract(
        "LDL: 4.9 mmol/L\nHDL: 1.2 mmol/L\nTriglyceride: 2.1 mmol/L"
    )}
    assert by_name == {"LDL": "ldl", "HDL": "hdl", "Triglyceride": "triglyceride"}


def test_unmappable_label_does_not_suppress_its_neighbours():
    """A dropped VLDL row must not take the surrounding real rows with it."""
    got = {c.fields["canonical"] for c in _extract(
        "LDL: 4.9 mmol/L\nVLDL: 0.9 mmol/L\nHDL: 1.2 mmol/L"
    )}
    assert got == {"ldl", "hdl"}
