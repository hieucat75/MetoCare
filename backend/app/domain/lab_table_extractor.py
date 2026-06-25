"""Table-first OCR extraction pipeline (Azure Document Intelligence).

Implements the 4-layer architecture from the OCR strategy reset:

  Layer 1 — OcrTableRow: pure structural extraction from Azure DI table cells.
             No clinical knowledge. Preserves original_test_name/value/unit/reference_range.

  Layer 2 — Hospital detection (delegates to hospital_profiles.detect_hospital).

  Layer 3 — MedicalMapper: maps original_test_name → metric_type + display_name_vi.
             Uses _ALIAS_INDEX from lab_interpreter.

  Layer 4 — UnitNormalizer: SI conversion, ocr_reference_range, display_reference_range.

Entry point: ``extract_and_map(analyze_result) -> list[RawLabValue]``

The returned list is passed directly to ``lab_interpreter.interpret_panel()`` — same
contract as the text-parser path, so build_draft() can use either transparently.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field

from app.domain.lab_catalog import get_catalog as _get_catalog
from app.domain.lab_interpreter import (
    BIOMARKERS,
    BiomarkerSpec,
    ConfidenceDetail,
    RawLabValue,
    _ALIAS_INDEX,
)

_logger = logging.getLogger("mcp.lab_table_extractor")

# ─────────────────────────────────────────────────────── Layer 1 ──────────────


@dataclass
class OcrTableRow:
    """One row extracted from an Azure DI table — Layer 1 output.

    Carries only what was literally printed on the lab report.
    No clinical mapping, no conversion applied at this stage.
    """

    original_test_name: str
    original_value_str: str        # raw numeric string as printed, e.g. "4.78"
    original_unit: str | None      # as printed, e.g. "mmol/L"; None when cell absent
    original_reference_range: str | None  # as printed, e.g. "3.9–6.1"; None when absent
    raw_cells: list[str] = field(default_factory=list)  # all cells in row (for debug)
    row_confidence: float = 0.95   # Azure table cells don't report per-row confidence
    page_number: int = 0
    source: str = "azure_table"


# ──────────────────────────────────────────────────── Column vocabulary ────────

# Header keywords that identify each column role.
# Accent-stripped lowercase match.
_COL_ROLE_KEYWORDS: dict[str, frozenset[str]] = {
    "stt": frozenset({
        "stt", "no", "no.", "tt", "so thu tu", "order", "#", "sn",
    }),
    "test_name": frozenset({
        "ten xet nghiem", "ten chi so", "xet nghiem", "chi so",
        "test name", "test", "analyte", "parameter", "ten",
        "ten ket qua", "ket qua xet nghiem", "examination",
        "chi so xet nghiem", "ten xet nghiem ky thuat",
    }),
    "value": frozenset({
        "ket qua", "gia tri", "result", "value", "so lieu",
        "nong do", "ham luong", "ket qua do", "concentration",
        "level", "measurement",
    }),
    "unit": frozenset({"don vi", "unit", "dv", "units"}),
    "reference": frozenset({
        "gia tri bt", "gia tri binh thuong", "khoang tham chieu",
        "tham chieu", "reference", "normal", "normal range",
        "reference range", "binh thuong", "gia tri tham chieu",
        "khoang binh thuong", "khoang chuan", "giai han binh thuong",
        "reference interval",
    }),
}

_NUMBER_RE = re.compile(r"\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?")
_UNIT_RE = re.compile(r"[%a-zA-Zµμ][a-zA-Z0-9µμ/^.²]*(?:/[a-zA-Z0-9.²]+)*")
_RANGE_DASH_RE = re.compile(r"(\d[0-9.,]*)\s*[-–—]\s*(\d[0-9.,]*)")
_LESS_THAN_RE = re.compile(r"<\s*(\d[0-9.,]*)")
_GREATER_THAN_RE = re.compile(r">\s*(\d[0-9.,]*)")


def _strip_accents_lower(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s.lower())
        if unicodedata.category(c) != "Mn"
    )


def _to_float_cell(token: str) -> float | None:
    t = token.strip().replace(" ", "")
    if "," in t and "." in t:
        t = t.replace(",", "")
    elif "," in t:
        if re.fullmatch(r"\d{1,3}(,\d{3})+", t):
            t = t.replace(",", "")
        else:
            t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _parse_value_cell(text: str) -> tuple[str, str | None]:
    """Parse a value cell: '4.78 mmol/L', '4.78', or '<55'. Returns (value_str, unit|None)."""
    text = text.strip()
    if not text:
        return "", None
    m = _NUMBER_RE.search(text)
    if not m:
        return text, None
    value_str = m.group()
    after = text[m.end():].strip()
    um = _UNIT_RE.match(after)
    return value_str, (um.group().strip() if um else None)


def _parse_reference_cell(text: str) -> str | None:
    """Parse a reference range cell: '3.9-6.1', '44 - 80', '< 55', '> 60'."""
    text = text.strip()
    if not text:
        return None
    m = _RANGE_DASH_RE.search(text)
    if m:
        return f"{m.group(1)}–{m.group(2)}"
    m = _LESS_THAN_RE.match(text)
    if m:
        return f"<{m.group(1)}"
    m = _GREATER_THAN_RE.match(text)
    if m:
        return f">{m.group(1)}"
    return None


def _infer_column_roles_positional(max_col: int) -> dict[str, int | None]:
    """Heuristic column mapping when no readable header row is found."""
    col_count = max_col + 1
    if col_count <= 2:
        return {"stt": None, "test_name": 0, "value": 1, "unit": None, "reference": None}
    if col_count == 3:
        return {"stt": None, "test_name": 0, "value": 1, "unit": None, "reference": 2}
    if col_count == 4:
        return {"stt": 0, "test_name": 1, "value": 2, "unit": None, "reference": 3}
    return {"stt": 0, "test_name": 1, "value": 2, "unit": 3, "reference": 4}


def _detect_column_roles(
    cells_raw: list[dict],
    header_row_indices: set[int],
    max_col: int,
) -> dict[str, int | None]:
    roles: dict[str, int | None] = {
        "stt": None, "test_name": None, "value": None,
        "unit": None, "reference": None,
    }
    for cell in cells_raw:
        ri = cell.get("rowIndex", 0)
        ci = cell.get("columnIndex", 0)
        if ri not in header_row_indices:
            continue
        txt_norm = _strip_accents_lower((cell.get("content") or "").strip())
        if not txt_norm:
            continue
        for role, keywords in _COL_ROLE_KEYWORDS.items():
            if any(kw in txt_norm or txt_norm in kw for kw in keywords):
                if roles[role] is None:
                    roles[role] = ci
                break
    if roles["test_name"] is None or roles["value"] is None:
        for role, col in _infer_column_roles_positional(max_col).items():
            if roles.get(role) is None:
                roles[role] = col
    return roles


def extract_table_rows(analyze_result: dict) -> list[OcrTableRow]:
    """Layer 1: Extract OcrTableRow list from Azure DI analyzeResult.tables.

    Preserves original test names, values, units, and reference ranges exactly
    as printed. No clinical knowledge applied here.
    """
    rows: list[OcrTableRow] = []
    for table in (analyze_result.get("tables") or []):
        cells_raw = table.get("cells") or []
        if not cells_raw:
            continue

        cell_map: dict[tuple[int, int], str] = {}
        for cell in cells_raw:
            ri = cell.get("rowIndex", 0)
            ci = cell.get("columnIndex", 0)
            txt = (cell.get("content") or "").strip()
            cell_map[(ri, ci)] = txt

        if not cell_map:
            continue

        max_col = max(ci for _, ci in cell_map)
        max_row = max(ri for ri, _ in cell_map)

        header_row_indices: set[int] = {
            cell.get("rowIndex", 0) for cell in cells_raw
            if (cell.get("kind") or "").lower() == "columnheader"
        }
        if not header_row_indices:
            header_row_indices = {0}

        roles = _detect_column_roles(cells_raw, header_row_indices, max_col)
        test_name_col = roles.get("test_name")
        value_col = roles.get("value")
        unit_col = roles.get("unit")
        ref_col = roles.get("reference")

        if test_name_col is None or value_col is None:
            _logger.debug("table_extractor_no_cols table_cols=%d", max_col + 1)
            continue

        for ri in range(max_row + 1):
            if ri in header_row_indices:
                continue

            test_name = cell_map.get((ri, test_name_col), "").strip()
            if not test_name or len(test_name) < 2:
                continue
            if re.fullmatch(r"\d+\.?", test_name):
                continue  # pure STT row

            value_raw = cell_map.get((ri, value_col), "").strip()
            if not value_raw:
                continue

            value_str, unit_from_value = _parse_value_cell(value_raw)
            if not value_str:
                continue

            unit_str: str | None = None
            if unit_col is not None:
                u = cell_map.get((ri, unit_col), "").strip()
                if u:
                    unit_str = u
            if unit_str is None:
                unit_str = unit_from_value

            ref_str: str | None = None
            if ref_col is not None:
                ref_raw = cell_map.get((ri, ref_col), "").strip()
                if ref_raw:
                    ref_str = _parse_reference_cell(ref_raw)

            raw_cells = [cell_map.get((ri, ci), "") for ci in range(max_col + 1)]
            rows.append(OcrTableRow(
                original_test_name=test_name,
                original_value_str=value_str,
                original_unit=unit_str,
                original_reference_range=ref_str,
                raw_cells=raw_cells,
                source="azure_table",
            ))

    return rows


# ─────────────────────────────────────── Layer 3+4: mapping + normalization ────

_UNIT_OCR_CORRECTIONS: dict[str, str] = {
    "pIU/mL": "µIU/mL",
    "pIU/L": "µIU/L",
    "ρIU/mL": "µIU/mL",
    "ρIU/L": "µIU/L",
}
_UNIT_OCR_CORRECTIONS_RE: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?<![a-zA-Zµμ0-9])mol/L"), "µmol/L"),
]


def _norm_unit_tbl(u: str) -> str:
    return u.replace("µ", "u").replace("μ", "u").replace("mc", "u").strip().lower()


def _apply_unit_corrections(unit: str) -> str:
    for bad, good in _UNIT_OCR_CORRECTIONS.items():
        unit = unit.replace(bad, good)
    for pattern, replacement in _UNIT_OCR_CORRECTIONS_RE:
        unit = pattern.sub(replacement, unit)
    return unit


def _match_test_name(name_noacc_lc: str) -> tuple[BiomarkerSpec, int] | None:
    """Find the best alias match in _ALIAS_INDEX (mirrors lab_parser._match_biomarker)."""
    best: tuple[int, BiomarkerSpec, int] | None = None
    for alias, spec in _ALIAS_INDEX.items():
        a = "".join(
            c for c in unicodedata.normalize("NFD", alias.lower())
            if unicodedata.category(c) != "Mn"
        )
        if not a:
            continue
        if len(a) <= 3:
            m = re.search(rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])", name_noacc_lc)
        else:
            pos = name_noacc_lc.find(a)
            m = None if pos < 0 else re.compile(re.escape(a)).match(name_noacc_lc, pos)
        if m is None:
            continue
        if best is None or len(a) > best[0]:
            best = (len(a), spec, m.end())
    return (best[1], best[2]) if best else None


def _is_incompatible_unit(unit: str, spec: BiomarkerSpec) -> bool:
    n = _norm_unit_tbl(unit)
    return any(_norm_unit_tbl(bad) == n for bad in spec.incompatible_units)


def _try_si_convert_unit(unit: str, value: float, spec: BiomarkerSpec) -> float | None:
    if spec.si_unit is None:
        return None
    if _norm_unit_tbl(unit) == _norm_unit_tbl(spec.si_unit):
        return round(value * spec.si_factor, 4)
    return None


_BIOMARKER_ORDER: dict[str, int] = {s.canonical: i for i, s in enumerate(BIOMARKERS)}


def map_table_rows_to_raw_values(
    table_rows: list[OcrTableRow],
    ocr_conf: float = 0.95,
) -> list[RawLabValue]:
    """Layers 3+4: Map OcrTableRow list → RawLabValue list for interpret_panel()."""
    seen: dict[str, RawLabValue] = {}

    for row in table_rows:
        unit_raw = _apply_unit_corrections(row.original_unit or "").strip() or None

        name_noacc = _strip_accents_lower(row.original_test_name)
        match = _match_test_name(name_noacc)
        if match is None:
            _logger.debug("table_extractor_no_match name=%r", row.original_test_name)
            continue
        spec, _ = match

        if spec.canonical in seen:
            continue

        orig_value = _to_float_cell(row.original_value_str)
        if orig_value is None:
            continue

        try:
            cat_entry = _get_catalog()["biomarkers"].get(spec.canonical, {})
            display_name_vi = cat_entry.get("name_vn") or spec.canonical
        except Exception:
            display_name_vi = spec.canonical

        orig_unit = unit_raw
        value = orig_value
        unit = orig_unit
        conv_conf = 1.0
        incompatible = False

        if not unit:
            conv_conf = 0.7
        elif _is_incompatible_unit(unit, spec):
            conv_conf = 0.0
            incompatible = True
        else:
            converted = _try_si_convert_unit(unit, value, spec)
            if converted is not None:
                value = converted
                unit = spec.unit
            elif spec.unit:
                if _norm_unit_tbl(unit) == _norm_unit_tbl(spec.unit):
                    conv_conf = 1.0
                else:
                    u_root = re.sub(r"[^a-z]", "", unit.lower())[:3]
                    s_root = re.sub(r"[^a-z]", "", spec.unit.lower())[:3]
                    conv_conf = 0.6 if (u_root and s_root and u_root != s_root) else 0.9

        ocr_conf_dim = 1.0 if orig_unit else 0.5

        clin_conf = 1.0
        if spec.physiological_min is not None and value < spec.physiological_min:
            clin_conf = 0.0
        elif spec.physiological_max is not None and value > spec.physiological_max:
            clin_conf = 0.0

        if incompatible or clin_conf == 0.0:
            overall = 0.0
        else:
            overall = round(
                0.40 * ocr_conf_dim + 0.25 * 1.0 + 0.25 * conv_conf + 0.10 * clin_conf,
                4,
            )
        overall = round(overall * ocr_conf, 4)

        engine_note = (
            f"✓ Chất lượng OCR ảnh: {round(ocr_conf * 100)}%"
            if ocr_conf >= 0.9
            else f"⚠ Chất lượng OCR ảnh: {round(ocr_conf * 100)}% — kiểm tra lại giá trị"
        )
        reasons: list[str] = [
            engine_note,
            "✓ OCR: trích xuất từ ô bảng (table-first)" if orig_unit
            else "⚠ OCR: ô đơn vị trống trong bảng",
            "✓ Ánh xạ: chỉ số được nhận diện chính xác",
            "⚠ Chuyển đổi: đơn vị không phù hợp lâm sàng" if conv_conf == 0.0
            else "⚠ Chuyển đổi: đơn vị cần xác nhận" if conv_conf < 1.0
            else "✓ Chuyển đổi: đơn vị khớp hoặc đã quy đổi thành công",
            "⚠ Lâm sàng: giá trị ngoài khoảng sinh lý" if clin_conf == 0.0
            else "✓ Lâm sàng: giá trị trong khoảng sinh lý",
        ]

        detail = ConfidenceDetail(
            ocr=ocr_conf_dim,
            mapping=1.0,
            conversion=conv_conf,
            clinical=clin_conf,
            overall=overall,
            reasons=reasons,
        )

        seen[spec.canonical] = RawLabValue(
            test_name=spec.canonical,
            value=value,
            unit=unit or spec.unit,
            ocr_confidence=overall,
            confidence_detail=detail,
            original_value=orig_value,
            original_unit=orig_unit or spec.unit,
            raw_test_name=row.original_test_name,
            display_name_vi=display_name_vi,
            ocr_reference_range=row.original_reference_range,
        )

    return [seen[c] for c in sorted(seen, key=lambda c: _BIOMARKER_ORDER.get(c, 999))]


def extract_and_map(
    analyze_result: dict,
    ocr_conf: float = 0.95,
) -> list[RawLabValue]:
    """Full Layer 1→4 pipeline: analyzeResult dict → RawLabValue list.

    Returns an empty list when no usable table rows are found, signalling
    build_draft() to fall back to the text+regex path.
    """
    table_rows = extract_table_rows(analyze_result)
    if not table_rows:
        return []
    raw_values = map_table_rows_to_raw_values(table_rows, ocr_conf=ocr_conf)
    _logger.info(
        "table_extractor rows_extracted=%d rows_mapped=%d conf=%.2f",
        len(table_rows), len(raw_values), ocr_conf,
    )
    return raw_values
