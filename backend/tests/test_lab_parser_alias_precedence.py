"""Regression suite for OCR-F3 — lab_parser alias precedence + review gating.

Finding (docs/launch-readiness/06-OCR-QUALITY-REPORT.md §4.3, OCR-F3):
``lab_parser.parse_lab_text("HDL Cholesterol")`` resolved to ``total_cholesterol``
because the substring alias matcher accepted the shorter, more generic alias
("cholesterol") before the more specific one ("HDL cholesterol"). An HDL value
was therefore stored, SI-converted and trended as total cholesterol, and the row
came back with ``requires_review=False`` at ``confidence_detail.overall == 0.0``.

The suite is table-driven so every shorter-name-inside-longer-name collision in
the alias table is asserted by exact canonical key.
"""

from __future__ import annotations

import pytest
from app.domain.lab_interpreter import OCR_CONFIDENCE_THRESHOLD
from app.services import lab_parser


def _canonicals(line: str) -> list[str]:
    return [v.test_name for v in lab_parser.parse_lab_text(line)]


# --------------------------------------------------------------------------- #
# 1. Most-specific-wins: (line, expected canonical)
# --------------------------------------------------------------------------- #

_PRECEDENCE_CASES: tuple[tuple[str, str], ...] = (
    # ── lipid panel: "cholesterol" is the generic that shadowed everything ──
    ("HDL Cholesterol: 1.2 mmol/L [>1.0]", "hdl"),
    ("HDL-Cholesterol 1.2 mmol/L", "hdl"),
    ("Cholesterol HDL: 1.2 mmol/L", "hdl"),
    ("HDL-C: 1.2 mmol/L", "hdl"),
    ("Cholesterol tốt (HDL): 1.2 mmol/L", "hdl"),
    ("LDL Cholesterol: 2.8 mmol/L [<3.4]", "ldl"),
    ("LDL-Cholesterol (tính): 2.8 mmol/L", "ldl"),
    ("Cholesterol LDL: 2.8 mmol/L", "ldl"),
    ("LDL-C 4.24 mmol/L", "ldl"),
    ("Cholesterol xấu: 2.8 mmol/L", "ldl"),
    ("Cholesterol: 4.5 mmol/L [<5.2]", "total_cholesterol"),
    ("Cholesterol toàn phần 5.99 mmol/L", "total_cholesterol"),
    ("CHOLESTEROL TOAN PHAN 5.99 mmol/L", "total_cholesterol"),
    ("Total Cholesterol 4.5 mmol/L", "total_cholesterol"),
    # ── haemoglobin vs glycated haemoglobin ──
    ("Hemoglobin: 14.0 g/dL", "hemoglobin"),
    ("Hemoglobin A1c: 5.8 %", "hba1c"),
    ("Haemoglobin A1c 5.8 %", "hba1c"),
    ("Glycated hemoglobin 5.8 %", "hba1c"),
    ("Glycohemoglobin 5.8 %", "hba1c"),
    ("HbA1c: 5.8 %", "hba1c"),
    # ── RBC vs haematocrit ──
    ("Hồng cầu: 4.8 T/L", "rbc"),
    ("Dung tích hồng cầu: 42 %", "hematocrit"),
    # ── fasting vs random glucose ──
    ("Glucose lúc đói: 126 mg/dL", "fasting_glucose"),
    ("Random glucose 145 mg/dL", "random_glucose"),
    ("Glucose ngẫu nhiên: 145 mg/dL", "random_glucose"),
    # ── triglyceride "TG" vs thyroglobulin "TG serum" ──
    ("Triglyceride 320 mg/dL", "triglyceride"),
    ("TG serum 12 ng/mL", "thyroglobulin"),
    # ── urea / uric acid short-alias hygiene ──
    ("Urea 4.47 mmol/L", "urea"),
    ("Uric acid 6.2 mg/dL", "uric_acid"),
)


@pytest.mark.parametrize(("line", "expected"), _PRECEDENCE_CASES)
def test_most_specific_alias_wins(line: str, expected: str) -> None:
    """Every label must resolve to its own biomarker, never to a shorter alias."""
    assert _canonicals(line) == [expected], (
        f"{line!r} resolved to {_canonicals(line)}, expected [{expected!r}]"
    )


# --------------------------------------------------------------------------- #
# 2. Labels with NO canonical biomarker must resolve to nothing.
#    Mapping them onto a contained shorter alias is a silent clinical error.
# --------------------------------------------------------------------------- #

_UNMAPPABLE_LINES: tuple[str, ...] = (
    "Non-HDL Cholesterol: 3.3 mmol/L",
    "Non HDL cholesterol 3.3 mmol/L",
    "Cholesterol non-HDL 3.3 mmol/L",
    "VLDL Cholesterol 0.8 mmol/L",
    "VLDL-C 0.8 mmol/L",
    "Remnant cholesterol 0.7 mmol/L",
    "Tỷ số Cholesterol/HDL: 4.2",
    "Chỉ số LDL/HDL: 2.3",
    "Bilirubin toàn phần: 12 µmol/L",
    "Bilirubin trực tiếp: 3.2 µmol/L",
    "Bilirubin gián tiếp: 8.8 µmol/L",
    "Direct bilirubin 0.3 mg/dL",
    "Total bilirubin 1.1 mg/dL",
)


@pytest.mark.parametrize("line", _UNMAPPABLE_LINES)
def test_unmappable_label_yields_no_row(line: str) -> None:
    assert _canonicals(line) == [], f"{line!r} wrongly resolved to {_canonicals(line)}"


# --------------------------------------------------------------------------- #
# 3. Whole-panel ordering: the generic row must not steal the specific rows.
# --------------------------------------------------------------------------- #

_LIPID_PANEL = """\
Cholesterol: 4.5 mmol/L [<5.2]
HDL Cholesterol: 1.2 mmol/L [>1.0]
LDL Cholesterol: 2.8 mmol/L [<3.4]
Non-HDL Cholesterol: 3.3 mmol/L
Triglyceride: 1.8 mmol/L [<1.7]
"""


def test_full_lipid_panel_resolves_each_row_independently() -> None:
    by_name = {v.test_name: v for v in lab_parser.parse_lab_text(_LIPID_PANEL)}
    assert set(by_name) == {"total_cholesterol", "hdl", "ldl", "triglyceride"}
    # mmol/L → mg/dL SI conversion, so compare the as-printed originals.
    assert by_name["total_cholesterol"].original_value == pytest.approx(4.5)
    assert by_name["hdl"].original_value == pytest.approx(1.2)
    assert by_name["ldl"].original_value == pytest.approx(2.8)
    assert by_name["hdl"].raw_test_name.lower().startswith("hdl")


# --------------------------------------------------------------------------- #
# 4. Zero / low confidence must never present as settled.
# --------------------------------------------------------------------------- #


def test_zero_confidence_row_requires_review() -> None:
    """4.5 mg/dL total cholesterol is physiologically impossible → overall 0.0."""
    rows = lab_parser.parse_lab_text("Cholesterol: 4.5 mg/dL")
    assert rows, "expected a parsed row"
    row = rows[0]
    assert row.confidence_detail is not None
    assert row.confidence_detail.overall == 0.0
    assert row.requires_review is True


def test_incompatible_unit_row_requires_review() -> None:
    rows = lab_parser.parse_lab_text("Glucose 4.78 mIU/mL")
    assert rows and rows[0].ocr_confidence == 0.0
    assert rows[0].requires_review is True


def test_missing_unit_row_requires_review() -> None:
    rows = lab_parser.parse_lab_text("Glucose lúc đói: 126")
    assert rows, "expected a parsed row"
    assert rows[0].confidence_detail is not None
    assert rows[0].confidence_detail.overall < OCR_CONFIDENCE_THRESHOLD
    assert rows[0].requires_review is True


def test_high_confidence_row_does_not_require_review() -> None:
    rows = lab_parser.parse_lab_text("HDL Cholesterol: 1.2 mmol/L [>1.0]")
    assert rows and rows[0].test_name == "hdl"
    assert rows[0].confidence_detail is not None
    assert rows[0].confidence_detail.overall >= OCR_CONFIDENCE_THRESHOLD
    assert rows[0].requires_review is False
