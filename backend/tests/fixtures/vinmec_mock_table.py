"""Vinmec golden fixture — mock Azure DI table response.

Simulates a real Vinmec lab report with column structure:
  Chỉ định | Kết quả | Đơn vị | Khoảng tham chiếu | Quy trình | Thiết bị

The "Thiết bị" column contains "Cobas Pro" — this must NEVER appear as a
numeric result value.  The "Quy trình" column contains procedure names — also
never a result.

Expected extraction: 16 biomarkers, all with correct value + unit.
"""
from __future__ import annotations

# ── Column structure ──────────────────────────────────────────────────────────
# Col 0: Chỉ định (test name)
# Col 1: Kết quả (result value)
# Col 2: Đơn vị (unit)
# Col 3: Khoảng tham chiếu (reference range)
# Col 4: Quy trình (procedure name)
# Col 5: Thiết bị (device/analyzer)

VINMEC_HEADER = [
    "Chỉ định",
    "Kết quả",
    "Đơn vị",
    "Khoảng tham chiếu",
    "Quy trình",
    "Thiết bị",
]

VINMEC_DATA = [
    # Test name,             Value,   Unit,       Reference range,    Procedure,           Device
    ["Ure",                  "4.47",  "mmol/L",   "2.5 - 7.5",        "Cobas Pro",         "Cobas Pro"],
    ["Creatinine",           "82.2",  "µmol/L",   "44 - 106",         "Cobas Pro",         "Cobas Pro"],
    ["Glucose lúc đói",      "4.78",  "mmol/L",   "3.9 - 6.1",        "Cobas Pro",         "Cobas Pro"],
    ["AST (GOT)",            "34.7",  "U/L",      "10 - 40",          "Cobas Pro",         "Cobas Pro"],
    ["ALT (GPT)",            "58.4",  "U/L",      "10 - 55",          "Cobas Pro",         "Cobas Pro"],
    ["Cholesterol toàn phần","5.99",  "mmol/L",   "< 5.2",            "Cobas Pro",         "Cobas Pro"],
    ["Triglyceride",         "2.7",   "mmol/L",   "0.5 - 1.7",        "Cobas Pro",         "Cobas Pro"],
    ["HDL-C",                "1.08",  "mmol/L",   "> 1.0",            "Cobas Pro",         "Cobas Pro"],
    ["LDL-C",                "4.24",  "mmol/L",   "< 3.4",            "Cobas Pro",         "Cobas Pro"],
    ["Natri (Na+)",          "140",   "mmol/L",   "135 - 145",        "Cobas Pro",         "Cobas Pro"],
    ["Kali (K+)",            "3.95",  "mmol/L",   "3.5 - 5.1",        "Cobas Pro",         "Cobas Pro"],
    ["Chloride (Cl-)",       "100.7", "mmol/L",   "98 - 106",         "Cobas Pro",         "Cobas Pro"],
    ["FT3",                  "4.64",  "pmol/L",   "2.63 - 5.70",      "Cobas Pro",         "Cobas Pro"],
    ["FT4",                  "18",    "pmol/L",   "9.01 - 19.05",     "Cobas Pro",         "Cobas Pro"],
    ["TSH",                  "1.26",  "µIU/mL",   "0.27 - 4.20",      "Cobas Pro",         "Cobas Pro"],
    ["Thyroglobulin",        "0.118", "ng/mL",    "1.4 - 78.0",       "Cobas Pro",         "Cobas Pro"],
]

# ── Expected extraction results (exact match required for 16/16) ──────────────
VINMEC_EXPECTED = [
    {"metric_type": "urea",              "original_value": "4.47",  "original_unit": "mmol/L"},
    {"metric_type": "creatinine",        "original_value": "82.2",  "original_unit": "µmol/L"},
    {"metric_type": "fasting_glucose",   "original_value": "4.78",  "original_unit": "mmol/L"},
    {"metric_type": "ast",               "original_value": "34.7",  "original_unit": "U/L"},
    {"metric_type": "alt",               "original_value": "58.4",  "original_unit": "U/L"},
    {"metric_type": "total_cholesterol", "original_value": "5.99",  "original_unit": "mmol/L"},
    {"metric_type": "triglyceride",      "original_value": "2.7",   "original_unit": "mmol/L"},
    {"metric_type": "hdl",               "original_value": "1.08",  "original_unit": "mmol/L"},
    {"metric_type": "ldl",               "original_value": "4.24",  "original_unit": "mmol/L"},
    {"metric_type": "sodium",            "original_value": "140",   "original_unit": "mmol/L"},
    {"metric_type": "potassium",         "original_value": "3.95",  "original_unit": "mmol/L"},
    {"metric_type": "chloride",          "original_value": "100.7", "original_unit": "mmol/L"},
    {"metric_type": "ft3",               "original_value": "4.64",  "original_unit": "pmol/L"},
    {"metric_type": "ft4",               "original_value": "18",    "original_unit": "pmol/L"},
    {"metric_type": "tsh",               "original_value": "1.26",  "original_unit": "µIU/mL"},
    {"metric_type": "thyroglobulin",     "original_value": "0.118", "original_unit": "ng/mL"},
]

# ── Azure DI mock builder helpers (same as test_lab_table_extractor.py) ───────

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


def build_vinmec_analyze_result() -> dict:
    """Return a minimal Azure DI analyzeResult dict for the Vinmec mock.

    Includes a top-level ``content`` string with the hospital name so that
    ``detect_hospital()`` can correctly identify this as a Vinmec report.
    """
    cells = _make_header_cells(*VINMEC_HEADER) + _make_data_cells(VINMEC_DATA)
    return {
        "content": "BỆNH VIỆN ĐA KHOA QUỐC TẾ VINMEC\nKết quả xét nghiệm",
        "tables": [{"cells": cells}],
    }
