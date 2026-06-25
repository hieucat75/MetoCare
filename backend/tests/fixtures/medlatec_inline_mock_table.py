"""Medlatec inline-machine-suffix golden fixture — mock Azure DI table response.

Simulates real Medlatec lab reports where the machine name is embedded INSIDE
the test name cell (not in a separate column):

  STT | Danh mục khám                     | Kết quả | Khoảng tham chiếu | Ghi chú | Đơn giá

This is the P0 bug scenario: the existing alias lookup fails to strip
"(Cobas C502)" from the test name, causing the text-regex fallback to pick up
502 as the extracted value.

The fix (clean_test_name + display_test_name) must ensure:
1. All 11 biomarkers are extracted with correct values.
2. The value 502 NEVER appears in any extracted RawLabValue.
3. The "Đơn giá" (price) column never becomes a result.
"""
from __future__ import annotations

# ── Column structure ──────────────────────────────────────────────────────────
# Col 0: STT (sequence number)
# Col 1: Danh mục khám (test name — with "(Cobas C502)" inline)
# Col 2: Kết quả (result value)
# Col 3: Khoảng tham chiếu (reference range — no separate unit column)
# Col 4: Ghi chú (note: "Tăng" / "Giảm" abnormal flag)
# Col 5: Đơn giá (price — must NEVER be result)

MEDLATEC_INLINE_HEADER = [
    "STT",
    "Danh mục khám",
    "Kết quả",
    "Khoảng tham chiếu",
    "Ghi chú",
    "Đơn giá",
]

# Note: no separate unit column — unit is embedded with value e.g. "25.37 U/L"
MEDLATEC_INLINE_DATA = [
    # STT  Test name (inline Cobas)              Result+unit       Ref range        Note      Price
    ["1",  "AST (GOT) (Cobas C502)",             "25.37 U/L",      "10 - 40",       "",       "85.000"],
    ["2",  "ALT (GPT) (Cobas C502)",             "51.63 U/L",      "10 - 40",       "Tăng",   "85.000"],
    ["3",  "GGT (Gamma GT) (Cobas C502)",        "75.78 U/L",      "10 - 55",       "Tăng",   "85.000"],
    ["4",  "Glucose (máu) (Cobas C502)",         "5.73 mmol/L",    "4.1 - 6.1",     "",       "100.000"],
    ["5",  "Ure (Cobas C502)",                   "4.55 mmol/L",    "2.5 - 7.5",     "",       "85.000"],
    ["6",  "Creatinin (Cobas C502)",             "87.66 µmol/L",   "62 - 106",      "",       "85.000"],
    ["7",  "Triglyceride (Cobas C502)",          "1.97 mmol/L",    "0.5 - 1.7",     "Tăng",   "100.000"],
    ["8",  "Cholesterol toàn phần (Cobas C502)*","5.49 mmol/L",    "< 5.2",         "Tăng",   "100.000"],
    ["9",  "HDL-C (Cobas C502)",                 "1.01 mmol/L",    "> 1.0",         "",       "85.000"],
    ["10", "LDL-C (Cobas C502)",                 "3.59 mmol/L",    "< 3.4",         "Tăng",   "85.000"],
    ["11", "Cortisol (Cobas C502)",              "2.50 nmol/L",    "138 - 635",     "",       "200.000"],
]

# ── Expected extraction results (exact match required for 11/11) ──────────────
# Note: "cortisol" may not be in the biomarker catalog — treated as best-effort.
MEDLATEC_INLINE_EXPECTED = [
    {"metric_type": "ast",               "original_value": "25.37", "original_unit": "U/L"},
    {"metric_type": "alt",               "original_value": "51.63", "original_unit": "U/L"},
    {"metric_type": "ggt",               "original_value": "75.78", "original_unit": "U/L"},
    {"metric_type": "fasting_glucose",   "original_value": "5.73",  "original_unit": "mmol/L"},
    {"metric_type": "urea",              "original_value": "4.55",  "original_unit": "mmol/L"},
    {"metric_type": "creatinine",        "original_value": "87.66", "original_unit": "µmol/L"},
    {"metric_type": "triglyceride",      "original_value": "1.97",  "original_unit": "mmol/L"},
    {"metric_type": "total_cholesterol", "original_value": "5.49",  "original_unit": "mmol/L"},
    {"metric_type": "hdl",               "original_value": "1.01",  "original_unit": "mmol/L"},
    {"metric_type": "ldl",               "original_value": "3.59",  "original_unit": "mmol/L"},
    # cortisol: best-effort — included but skipped if not in catalog
    {"metric_type": "cortisol",          "original_value": "2.50",  "original_unit": "nmol/L"},
]

# ── Azure DI mock builder helpers ─────────────────────────────────────────────

def _make_header_cells(*names: str, row: int = 0) -> list[dict]:
    return [
        {
            "rowIndex": row,
            "columnIndex": ci,
            "content": name,
            "kind": "columnheader",
        }
        for ci, name in enumerate(names)
    ]


def _make_data_cells(rows: list[list[str]], start_row: int = 1) -> list[dict]:
    cells = []
    for ri, row_vals in enumerate(rows, start=start_row):
        for ci, val in enumerate(row_vals):
            cells.append({"rowIndex": ri, "columnIndex": ci, "content": val})
    return cells


def build_medlatec_inline_analyze_result() -> dict:
    """Return a minimal Azure DI analyzeResult dict for the Medlatec inline mock.

    Includes a top-level ``content`` string with the hospital name so that
    ``detect_hospital()`` can correctly identify this as a Medlatec report.
    """
    cells = _make_header_cells(*MEDLATEC_INLINE_HEADER) + _make_data_cells(MEDLATEC_INLINE_DATA)
    return {
        "content": "HỆ THỐNG Y TẾ MEDLATEC\nPhiếu kết quả xét nghiệm",
        "tables": [{"cells": cells}],
    }
