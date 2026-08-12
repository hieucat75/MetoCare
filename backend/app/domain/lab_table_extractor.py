"""Table-first OCR extraction pipeline (Azure Document Intelligence).

Implements the 4-layer architecture from the OCR strategy reset:

  Layer 1 — OcrTableRow: pure structural extraction from Azure DI table cells.
             No clinical knowledge. Preserves original_test_name/value/unit/reference_range.

  Layer 2 — Hospital detection (delegates to hospital_profiles.detect_hospital).
             Provider-aware: detect_hospital() run on full document text before table
             extraction so column profiles and test-name cleaning are applied correctly.

  Layer 3 — MedicalMapper: maps display_test_name → metric_type + display_name_vi.
             Uses _ALIAS_INDEX from lab_interpreter. display_test_name has machine
             suffixes like "(Cobas C502)" stripped before matching.

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

from app.domain.hospital_profiles import (
    HospitalProfile,
)
from app.domain.hospital_profiles import (
    detect_hospital_result as _detect_hospital_result,
)
from app.domain.lab_catalog import get_catalog as _get_catalog
from app.domain.lab_interpreter import (
    _ALIAS_INDEX,
    BIOMARKERS,
    BiomarkerSpec,
    ConfidenceDetail,
    RawLabValue,
)

_logger = logging.getLogger("mcp.lab_table_extractor")

# ─────────────────────────────────────────────────────── Layer 1 ──────────────


@dataclass
class OcrTableRow:
    """One row extracted from an Azure DI table — Layer 1 output.

    Carries only what was literally printed on the lab report.
    No clinical mapping, no conversion applied at this stage.
    """

    original_test_name: str  # raw test name as printed, e.g. "Glucose (máu) (Cobas C502)"
    display_test_name: str  # cleaned for alias matching (machine suffixes stripped)
    original_value_str: str  # raw numeric string as printed, e.g. "4.78"
    original_unit: str | None  # as printed, e.g. "mmol/L"; None when cell absent
    original_reference_range: str | None  # as printed, e.g. "3.9–6.1"; None when absent
    raw_cells: list[str] = field(default_factory=list)  # all cells in row (for debug)
    row_confidence: float = 0.95  # Azure table cells don't report per-row confidence
    page_number: int = 0
    source: str = "azure_table"
    # P0 safety flag: True when value_str looks like a machine model number
    # (e.g. "502" from "Cobas C502").  Rows with this flag must NOT be auto-saved.
    suspect_machine_id: bool = False


# ──────────────────────────────────────────────────── Column vocabulary ────────

# Header keywords that identify each column role.
# Accent-stripped lowercase match.
# NOTE: "method" columns are detected and explicitly EXCLUDED from value_col.
_COL_ROLE_KEYWORDS: dict[str, frozenset[str]] = {
    "stt": frozenset(
        {
            "stt",
            "no",
            "no.",
            "tt",
            "so thu tu",
            "order",
            "#",
            "sn",
        }
    ),
    "test_name": frozenset(
        {
            "ten xet nghiem",
            "ten chi so",
            "xet nghiem",
            "chi so",
            "test name",
            "analyte",
            "parameter",
            "examination",
            "chi so xet nghiem",
            "ten xet nghiem ky thuat",
            # Vinmec: "Chỉ định" ("chi dinh" / "chi đinh" — "đ" doesn't decompose under NFD)
            "chi dinh",
            "chi đinh",
            # Medlatec: "Danh mục khám"
            "danh muc kham",
            "danh muc",
        }
    ),
    "value": frozenset(
        {
            "ket qua",
            "gia tri",
            "result",
            "value",
            "so lieu",
            "nong do",
            "ham luong",
            "ket qua do",
            "concentration",
            "level",
            "measurement",
        }
    ),
    "unit": frozenset(
        {
            "don vi",
            "unit",
            "dv",
            "units",
            # "Đơn vị" normalizes to "đon vi" (not "don vi") because "đ" ≠ "d" under NFD.
            "đon vi",
        }
    ),
    "reference": frozenset(
        {
            "gia tri bt",
            "gia tri binh thuong",
            "khoang tham chieu",
            "tham chieu",
            "reference",
            "normal",
            "normal range",
            "reference range",
            "binh thuong",
            "gia tri tham chieu",
            "khoang binh thuong",
            "khoang chuan",
            "giai han binh thuong",
            "reference interval",
        }
    ),
    # Columns typed as "method" or "instrument" must NEVER be used as value_col.
    "method": frozenset(
        {
            "phuong phap",
            "may xet nghiem",
            "may",
            "method",
            "instrument",
            "analyzer",
            "thiet bi",
            "thiet bi do",
            "machine",
            "he thong",
            "cobas",
            "may do",
            "phuong phap may",
            "phuong phap / may",
            "pp/may",
            "pp / may",
        }
    ),
    # Price columns must NEVER be used as value_col (Medlatec: "Đơn giá").
    "price": frozenset(
        {
            "don gia",
            "gia tien",
            "phi",
            "thanh tien",
            "price",
            "cost",
            "tien",
            "phi dich vu",
        }
    ),
    # Note/comment columns contain abnormal flags like "Tăng", "Giảm" — not values.
    "note": frozenset(
        {
            "ghi chu",
            "ghi chu ket qua",
            "nhan xet",
            "note",
            "comment",
            "ket luan",
            "canh bao",
            "tang",
            "giam",
        }
    ),
    # Vinmec: "Quy trình" (procedure/method name) — not a result.
    "procedure": frozenset(
        {
            "quy trinh",
            "procedure",
            "method name",
            "ten quy trinh",
        }
    ),
    # Vinmec: "Thiết bị" (device/analyzer) — must NEVER map to value_col.
    "device": frozenset(
        {
            "thiet bi",
            "device",
            "may do",
            "analyzer",
            "instrument",
            "cobas pro",
            "cobas",
            "sysmex",
        }
    ),
}

# ──────────────────────────────────────────── Instrument name blocklist ─────

# Machine/instrument identifiers that appear in hospital lab report columns
# (e.g. Medlatec "Phương pháp / Máy" column).  These strings must NEVER be
# parsed as numeric result values.  Case-insensitive match after accent strip.
_INSTRUMENT_NAME_BLOCKLIST: frozenset[str] = frozenset(
    {
        "cobas",
        "cobas c502",
        "cobas c702",
        "cobas e601",
        "cobas 8000",
        "architect",
        "sysmex",
        "beckman",
        "coulter",
        "siemens",
        "roche",
        "abbott",
        "olympus",
        "hitachi",
        "c502",
        "c702",
        "e601",
        "au480",
        "au680",
    }
)

# Regex to detect a 3-4 digit numeric suffix that is part of a model name,
# e.g. the "502" in "Cobas C502" or "8000" in "Cobas 8000".
_MODEL_SUFFIX_RE = re.compile(r"[A-Za-z]\s*(\d{3,4})")


def _is_instrument_cell(text: str) -> bool:
    """Return True when *text* contains a known instrument/machine name.

    Strips accents and lowercases before matching so Vietnamese-accented variants
    (if any) are also caught.
    """
    norm = _strip_accents_lower(text)
    for name in _INSTRUMENT_NAME_BLOCKLIST:
        if name in norm:
            return True
    # Generic pattern: letter immediately followed by 3-4 digit model number
    # e.g. "C502", "E601", "AU480"
    if _MODEL_SUFFIX_RE.search(text):
        return True
    return False


def _row_contains_instrument(raw_cells: list[str]) -> bool:
    """Return True when any cell in the row contains an instrument name."""
    return any(_is_instrument_cell(c) for c in raw_cells)


def _is_pure_instrument_cell(text: str) -> bool:
    """True when a cell contains ONLY an instrument/machine name (no medical test-name prefix).

    Differentiates dedicated instrument columns ("Cobas C502", "Sysmex XN-1000")
    from test-name cells that embed a machine suffix ("AST (GOT) (Cobas C502)*").
    The latter have meaningful medical text that survives stripping; pure instrument
    cells have nothing meaningful remaining after stripping known patterns.

    Used for majority-vote instrument-column detection so that the test_name column
    (which contains inline machine suffixes) is NOT mis-classified as the method column.
    """
    if not text:
        return False
    t = text.strip()
    if not _is_instrument_cell(t):
        return False
    # Apply all machine-suffix strip patterns.  For a pure instrument cell like
    # "Cobas C502" (no surrounding parens) these patterns won't match — the text
    # itself IS the instrument name, detected by _is_instrument_cell above.
    cleaned = t
    for pat in _TEST_NAME_STRIP_PATTERNS:
        cleaned = pat.sub("", cleaned)
    cleaned = cleaned.strip()
    # If nothing meaningful remains → pure instrument cell.
    if len(cleaned) <= 2:
        return True
    # If the remaining text is still an instrument name (e.g. bare "Cobas C502"
    # without enclosing parens can't be stripped by paren-based patterns),
    # confirm via _is_instrument_cell.
    return _is_instrument_cell(cleaned)


# ─────────────────────────────────────── Provider-aware test name cleaner ──────

# Patterns that appear in test name cells but are NOT part of the test name.
# Medlatec embeds machine suffix inline, e.g. "Glucose (máu) (Cobas C502)".
# Strip these before alias matching so the alias index can find the correct biomarker.
_TEST_NAME_STRIP_PATTERNS: list[re.Pattern] = [
    # Machine/analyzer suffixes — handles both compact and spaced model numbers:
    # "(Cobas C502)", "(Cobas C 502)", "(Cobas 8000)", "(Cobas Pro)", "(Cobas e601)", etc.
    re.compile(r"\(\s*Cobas\s+[A-Za-z]+\s*[0-9]*\s*\)", re.IGNORECASE),
    # Bare model codes: (C502), (C 502), (C702), (C 702)
    re.compile(r"\(\s*C\s*\d{3,4}\s*\)", re.IGNORECASE),
    # QX series: (QX200), (QX 200)
    re.compile(r"\(\s*QX\s*[.\w]*\s*\)", re.IGNORECASE),
    # Beckman AU series: (AU480), (AU 680)
    re.compile(r"\(\s*AU\s*\d{3,4}\s*\)", re.IGNORECASE),
    # Sysmex: (Sysmex XN-1000), (Sysmex XN 1000)
    re.compile(r"\(\s*Sysmex\s+[A-Za-z0-9\s-]+\s*\)", re.IGNORECASE),
    # Abbott Architect series: (Architect i2000), (Architect Plus), (Architect c16000)
    re.compile(r"\(\s*Architect\s+[A-Za-z0-9\s+]*\s*\)", re.IGNORECASE),
    # Standalone Architect (no model number)
    re.compile(r"\(\s*Architect\s*\)", re.IGNORECASE),
    # Other major instrument brands — Abbott, Roche, Siemens, Beckman, Olympus, Hitachi.
    # These never appear as medically meaningful abbreviations (unlike GOT, GPT, etc.).
    re.compile(
        r"\(\s*(?:Abbott|Roche|Siemens|Beckman|Coulter|Olympus|Hitachi)\s*[A-Za-z0-9\s-]*\s*\)",
        re.IGNORECASE,
    ),
    # Trailing asterisk often added by Medlatec to flagged results, e.g. "Cholesterol*"
    re.compile(r"\*\s*$"),
]


def clean_test_name(name: str, hospital_id: str | None = None) -> str:  # noqa: ARG001
    """Strip machine/instrument suffixes from a test name before alias lookup.

    Applies globally (not limited to specific hospital_id) because Medlatec-style
    inline machine suffixes can in principle appear from any provider.

    Examples::

        clean_test_name("Glucose (máu) (Cobas C502)") -> "Glucose (máu)"
        clean_test_name("Triglyceride (Cobas C502)")   -> "Triglyceride"
        clean_test_name("ALT (GPT)")                   -> "ALT (GPT)"

    The ``hospital_id`` parameter is accepted for future provider-specific overrides
    but is not used currently.
    """
    result = name
    for pattern in _TEST_NAME_STRIP_PATTERNS:
        result = pattern.sub("", result)
    return result.strip()


_NUMBER_RE = re.compile(r"\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?")
_UNIT_RE = re.compile(r"[%a-zA-Zµμ][a-zA-Z0-9µμ/^.²]*(?:/[a-zA-Z0-9.²]+)*")
_RANGE_DASH_RE = re.compile(r"(\d[0-9.,]*)\s*[-–—]\s*(\d[0-9.,]*)")
_LESS_THAN_RE = re.compile(r"<\s*(\d[0-9.,]*)")
_GREATER_THAN_RE = re.compile(r">\s*(\d[0-9.,]*)")


def _strip_accents_lower(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn"
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
    after = text[m.end() :].strip()
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


# Column roles that must NEVER be used as value_col.
_NON_VALUE_ROLES: frozenset[str] = frozenset(
    {
        "method",
        "price",
        "note",
        "procedure",
        "device",
        "stt",
    }
)


def _detect_column_roles(
    cells_raw: list[dict],
    header_row_indices: set[int],
    max_col: int,
) -> dict[str, int | None]:
    roles: dict[str, int | None] = {
        "stt": None,
        "test_name": None,
        "value": None,
        "unit": None,
        "reference": None,
        "method": None,
        "price": None,
        "note": None,
        "procedure": None,
        "device": None,
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
                if roles.get(role) is None:
                    roles[role] = ci
                break

    # ── Majority-vote instrument column detection ─────────────────────────────
    # Count data-row cells per column where _is_pure_instrument_cell returns True.
    # "Pure instrument" = cell contains ONLY an instrument name with no medical prefix.
    # This prevents test_name cells like "AST (GOT) (Cobas C502)*" from being
    # classified as the instrument column (the old first-hit scan stopped there,
    # wrongly marking the test_name column as method, which then corrupted value_col).
    _pure_instr_counts: dict[int, int] = {}
    _col_data_counts: dict[int, int] = {}
    for cell in cells_raw:
        ri = cell.get("rowIndex", 0)
        if ri in header_row_indices:
            continue
        ci = cell.get("columnIndex", 0)
        content = (cell.get("content") or "").strip()
        _col_data_counts[ci] = _col_data_counts.get(ci, 0) + 1
        if content and _is_pure_instrument_cell(content):
            _pure_instr_counts[ci] = _pure_instr_counts.get(ci, 0) + 1

    # A column is the instrument column when >40% of its data cells are pure
    # instrument names.  This threshold is robust to occasional mixed cells.
    inferred_method_col: int | None = None
    for ci, count in _pure_instr_counts.items():
        total = _col_data_counts.get(ci, 1)
        ratio = count / total
        if ratio > 0.4:
            inferred_method_col = ci
            _logger.debug(
                "table_extractor_method_col_majority_vote col=%d ratio=%.2f",
                ci,
                ratio,
            )
            break

    if inferred_method_col is not None and roles.get("method") is None:
        roles["method"] = inferred_method_col
        _logger.debug(
            "table_extractor_method_col_detected col=%d (majority vote)",
            inferred_method_col,
        )

    if roles["test_name"] is None or roles["value"] is None:
        for role, col in _infer_column_roles_positional(max_col).items():
            if roles.get(role) is None:
                roles[role] = col

    # Safety: if value_col ended up on a non-value column (method, price, device,
    # procedure, note), fall back to positional heuristics for value_col.
    non_value_cols: set[int] = {roles[r] for r in _NON_VALUE_ROLES if roles.get(r) is not None}
    non_value_cols.discard(None)  # type: ignore[arg-type]
    if roles["value"] in non_value_cols:
        bad_col = roles["value"]
        _logger.warning(
            "table_extractor_value_col_was_non_value col=%d — falling back to positional",
            bad_col,
        )
        positional = _infer_column_roles_positional(max_col)
        fallback_value = positional.get("value")
        if fallback_value not in non_value_cols:
            roles["value"] = fallback_value
        else:
            # Last resort: first column that is not stt, test_name, or non-value.
            excluded = {roles.get("stt"), roles.get("test_name")} | non_value_cols
            excluded.discard(None)  # type: ignore[arg-type]
            for ci in range(max_col + 1):
                if ci not in excluded:
                    roles["value"] = ci
                    break

    # ── Hard constraint: value_col must always be AFTER test_name_col ─────────
    # This is the P0 column-locking rule: the result column is always to the RIGHT
    # of the test name column.  Enforced as a hard post-processing step so no
    # fallback path can accidentally assign a left column as the result source.
    if (
        roles.get("value") is not None
        and roles.get("test_name") is not None
        and roles["value"] <= roles["test_name"]  # type: ignore[operator]
    ):
        _logger.warning(
            "table_extractor_value_col_left_of_test_name "
            "value_col=%d test_name_col=%d — shifting right",
            roles["value"],
            roles["test_name"],
        )
        bad_val = roles["value"]
        test_col = roles["test_name"]
        nv: set[int] = non_value_cols | {test_col}
        roles["value"] = None
        for ci in range(test_col + 1, max_col + 1):  # type: ignore[operator]
            if ci not in nv:
                roles["value"] = ci
                break
        _logger.debug(
            "table_extractor_value_col_corrected old=%d new=%s",
            bad_val,
            roles.get("value"),
        )

    return roles


def extract_table_rows(
    analyze_result: dict,
    hospital_id: str | None = None,
    profile: HospitalProfile | None = None,
) -> list[OcrTableRow]:
    """Layer 1: Extract OcrTableRow list from Azure DI analyzeResult.tables.

    Preserves original test names, values, units, and reference ranges exactly
    as printed. No clinical knowledge applied here.

    When ``hospital_id`` is provided the test name cleaner applies provider-aware
    stripping of machine suffixes (e.g. "(Cobas C502)") before alias matching.
    """
    rows: list[OcrTableRow] = []
    for table in analyze_result.get("tables") or []:
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
            cell.get("rowIndex", 0)
            for cell in cells_raw
            if (cell.get("kind") or "").lower() == "columnheader"
        }
        if not header_row_indices:
            header_row_indices = {0}

        # If the profile provides an explicit column map, validate it against the
        # actual table structure before using it.  A column map is compatible when:
        #   1. The table has at least as many columns as the map's max index.
        #   2. The cell at (header_row, cm.test_name) looks like a test-name column header
        #      AND the cell at (header_row, cm.value) looks like a value/result column header.
        # When incompatible, fall back to heuristic column detection.
        _use_column_map = False
        if profile is not None and profile.column_map is not None:
            cm = profile.column_map
            if cm.value <= max_col:
                # Gather header text for the mapped test_name and value columns.
                _col_headers: dict[int, str] = {}
                for hdr_ri in header_row_indices:
                    for c in cells_raw:
                        if c.get("rowIndex") == hdr_ri:
                            ci = c.get("columnIndex", -1)
                            _col_headers[ci] = _strip_accents_lower(c.get("content", ""))

                _test_name_header = _col_headers.get(cm.test_name, "")
                _value_header = _col_headers.get(cm.value, "")
                _unit_header = _col_headers.get(cm.unit, "") if cm.unit is not None else ""

                # The column_map is valid when:
                #   - test_name column header matches test_name keywords (or no headers exist)
                #   - value column header does NOT match test_name keywords
                #   - unit column header (if declared) does NOT look like a reference range
                _test_name_ok = (
                    not _test_name_header  # Azure DI returned no header cells (common for
                    # scanned PDFs) — trust the profile's declared column_map, which was
                    # defined by a human who reviewed real reports from this hospital.
                    or any(
                        kw in _test_name_header or _test_name_header in kw
                        for kw in _COL_ROLE_KEYWORDS["test_name"]
                    )
                )
                _value_not_name_col = not any(
                    kw in _value_header or _value_header in kw
                    for kw in _COL_ROLE_KEYWORDS["test_name"]
                )
                # If the declared unit column's header looks like a reference column,
                # the table has a different layout — unit is likely embedded in value.
                _unit_col_ok = not _unit_header or not any(
                    kw in _unit_header or _unit_header in kw
                    for kw in _COL_ROLE_KEYWORDS["reference"]
                )
                if _test_name_ok and _value_not_name_col and _unit_col_ok:
                    _use_column_map = True
                else:
                    _logger.warning(
                        "table_extractor_column_map_incompatible hospital=%s "
                        "test_name_col=%d header=%r value_col=%d value_header=%r "
                        "unit_col=%s unit_header=%r — falling back to heuristics",
                        profile.hospital_id,
                        cm.test_name,
                        _test_name_header,
                        cm.value,
                        _value_header,
                        cm.unit,
                        _unit_header,
                    )

        if _use_column_map and profile is not None and profile.column_map is not None:
            cm = profile.column_map
            roles: dict[str, int | None] = {
                "stt": cm.stt,
                "test_name": cm.test_name,
                "value": cm.value,
                "unit": cm.unit,
                "reference": cm.reference,
                "method": None,
                "price": None,
                "note": None,
                "procedure": None,
                "device": None,
            }
            # Mark all skip_cols as method (excluded from value extraction)
            for sc in cm.skip_cols:
                # Assign to method slot if not already used, otherwise track in non_value set
                if roles["method"] is None:
                    roles["method"] = sc
                # If more than one skip col, they'll be handled by non_value_cols check below
            _logger.debug(
                "table_extractor_profile_column_map hospital=%s roles=%s",
                profile.hospital_id,
                roles,
            )
        else:
            roles = _detect_column_roles(cells_raw, header_row_indices, max_col)

        # Handle multiple skip_cols: ensure value_col is not among them.
        if _use_column_map and profile is not None and profile.column_map is not None:
            non_value_cols_from_profile: set[int] = set(profile.column_map.skip_cols)
            if roles["value"] in non_value_cols_from_profile:
                _logger.error(
                    "table_extractor_profile_column_map value_col=%d is in skip_cols=%s "
                    "— profile misconfigured",
                    roles["value"],
                    profile.column_map.skip_cols,
                )
                # Fall back to heuristic detection
                roles = _detect_column_roles(cells_raw, header_row_indices, max_col)

        test_name_col = roles.get("test_name")
        value_col = roles.get("value")
        unit_col = roles.get("unit")
        ref_col = roles.get("reference")

        if test_name_col is None or value_col is None:
            _logger.debug("table_extractor_no_cols table_cols=%d", max_col + 1)
            continue

        # Build footer row set using profile.footer_patterns (accent-stripped match).
        footer_rows: set[int] = set()
        if profile is not None and profile.footer_patterns:
            for ri_check in range(max_row + 1):
                if ri_check in header_row_indices:
                    continue
                row_text = " ".join(cell_map.get((ri_check, ci), "") for ci in range(max_col + 1))
                row_norm = _strip_accents_lower(row_text)
                if any(fp in row_norm for fp in profile.footer_patterns):
                    footer_rows.add(ri_check)

        for ri in range(max_row + 1):
            if ri in header_row_indices or ri in footer_rows:
                continue

            test_name = cell_map.get((ri, test_name_col), "").strip()
            if not test_name or len(test_name) < 2:
                continue
            if re.fullmatch(r"\d+\.?", test_name):
                continue  # pure STT row

            # Clean machine suffix for alias matching (e.g. strip "(Cobas C502)").
            test_name_clean = clean_test_name(test_name, hospital_id=hospital_id)

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

            # ── Sanity check: instrument/machine-model number detection ──────
            # After we have value_str, verify it is not a machine model number
            # that leaked from a non-value column or from test_name cell itself.
            suspect_machine_id = False

            # 1) If ANY cell in this row (other than the value cell) is an
            #    instrument cell AND value_str appears to be a 3-4 digit integer
            #    that matches a model number suffix, flag it.
            try:
                value_float = float(value_str.replace(",", "."))
                is_bare_integer = value_float == int(value_float)
                if is_bare_integer and 100 <= value_float <= 9999:
                    for col_idx, cell_text in enumerate(raw_cells):
                        if col_idx == value_col:
                            continue
                        if _is_instrument_cell(cell_text):
                            # Check if value_str appears as a suffix in that cell.
                            m = _MODEL_SUFFIX_RE.search(cell_text)
                            if m and m.group(1) == str(int(value_float)):
                                suspect_machine_id = True
                                _logger.warning(
                                    "table_extractor_suspect_machine_id "
                                    "row=%d value=%s matched model suffix in cell %r",
                                    ri,
                                    value_str,
                                    cell_text,
                                )
                                break
            except (ValueError, OverflowError):
                pass

            # 2) If the raw value cell itself contains an instrument name,
            #    the value_col was mis-detected — flag the row.
            if _is_instrument_cell(value_raw):
                suspect_machine_id = True
                _logger.warning(
                    "table_extractor_instrument_in_value_cell row=%d cell=%r",
                    ri,
                    value_raw,
                )

            row_confidence = 0.0 if suspect_machine_id else 0.95

            _logger.debug(
                "table_extractor_row ri=%d "
                "raw=%r cleaned_name=%r "
                "val_col=%d val_raw=%r val_str=%r "
                "unit_col=%s unit=%r ref=%r suspect=%s",
                ri,
                raw_cells,
                test_name_clean,
                value_col,
                value_raw,
                value_str,
                unit_col,
                unit_str,
                ref_str,
                suspect_machine_id,
            )

            rows.append(
                OcrTableRow(
                    original_test_name=test_name,
                    display_test_name=test_name_clean,
                    original_value_str=value_str,
                    original_unit=unit_str,
                    original_reference_range=ref_str,
                    raw_cells=raw_cells,
                    row_confidence=row_confidence,
                    source="azure_table",
                    suspect_machine_id=suspect_machine_id,
                )
            )

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
    """Find the best alias match using a 3-tier priority ladder.

    Tiers (lower = higher priority; within a tier, longer alias wins):
      0 — exact:    normalised alias equals the full name string
      1 — prefix:   alias starts at position 0 of the name
      2 — substring: alias found anywhere (original behaviour, preserved for recall)

    This prevents a long alias embedded mid-name (e.g. "cholesterol" in
    "hdl-cholesterol") from beating a shorter alias that starts at position 0
    (e.g. "hdl-c"), which caused HDL/LDL to be mis-mapped to total_cholesterol.
    No existing match is dropped — only priority is reordered.
    """
    # (tier, alias_len, match_end, spec)
    best: tuple[int, int, int, BiomarkerSpec] | None = None

    for alias, spec in _ALIAS_INDEX.items():
        a = "".join(
            c
            for c in unicodedata.normalize("NFD", alias.lower())
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

        if name_noacc_lc == a:
            tier = 0
        elif m.start() == 0:
            tier = 1
        else:
            tier = 2

        candidate = (tier, len(a), m.end(), spec)
        if best is None or tier < best[0] or (tier == best[0] and len(a) > best[1]):
            best = candidate

    return (best[3], best[2]) if best else None


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
    hospital_id: str | None = None,
    detection_confidence: float = 1.0,
) -> list[RawLabValue]:
    """Layers 3+4: Map OcrTableRow list → RawLabValue list for interpret_panel().

    When ``hospital_id`` is None (unknown provider) or ``detection_confidence``
    is below 0.7 (hospital found only in lines 11-50 of the document), every
    row is marked ``requires_review=True`` — none are auto-promoted to metrics.
    Unknown-provider rows are additionally capped at confidence 0.5.
    """
    seen: dict[str, RawLabValue] = {}

    for row in table_rows:
        # ── P0 safety gate: block rows flagged as suspect machine ID ──────────
        if row.suspect_machine_id:
            _logger.warning(
                "table_extractor_blocked_suspect_machine_id "
                "test=%r value=%r — row excluded from clean output",
                row.original_test_name,
                row.original_value_str,
            )
            continue

        unit_raw = _apply_unit_corrections(row.original_unit or "").strip() or None

        # Use display_test_name (machine suffix stripped) for alias matching.
        # This fixes the P0 Medlatec bug where "Glucose (máu) (Cobas C502)" failed lookup.
        name_noacc = _strip_accents_lower(row.display_test_name)
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
            "✓ OCR: trích xuất từ ô bảng (table-first)"
            if orig_unit
            else "⚠ OCR: ô đơn vị trống trong bảng",
            "✓ Ánh xạ: chỉ số được nhận diện chính xác",
            "⚠ Chuyển đổi: đơn vị không phù hợp lâm sàng"
            if conv_conf == 0.0
            else "⚠ Chuyển đổi: đơn vị cần xác nhận"
            if conv_conf < 1.0
            else "✓ Chuyển đổi: đơn vị khớp hoặc đã quy đổi thành công",
            "⚠ Lâm sàng: giá trị ngoài khoảng sinh lý"
            if clin_conf == 0.0
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

        # ── requires_review gate ───────────────────────────────────────────────────
        # Any of the following conditions trigger manual review (not auto-saved):
        #  • row_confidence == 0 (suspect machine ID or other parser error)
        #  • overall confidence below 0.5
        #  • original_unit is missing (ambiguous value)
        #  • clinical check failed (incompatible unit or impossible value)
        requires_review = (
            row.row_confidence == 0.0
            or overall < 0.5
            or orig_unit is None
            or incompatible
            or clin_conf == 0.0
            or row.suspect_machine_id
        )

        # ── Provider confidence safety gate ─────────────────────────────────────
        # Two conditions force requires_review:
        #  1. hospital_id is None — unrecognised provider; confidence capped at 0.5.
        #  2. detection_confidence < 0.7 — hospital found only in lines 11-50 of
        #     the document, meaning the header match was weak.  In both cases no
        #     row is auto-promoted; the user must confirm each value in review UI.
        if hospital_id is None:
            overall = min(overall, 0.5)
            requires_review = True
        elif detection_confidence < 0.7:
            requires_review = True

        # CBC dimensional guard — the SECOND write path. `build_alias_index`'s
        # docstring already records what happens when two extraction paths answer
        # differently; without this, production (which runs Azure table-first)
        # bypasses the lab_parser fix entirely.
        #
        from app.domain import analyte_units as _au

        _guarded = spec.canonical in _au.ALLOWED_UNITS
        if _guarded and unit:
            # Disambiguate the generic erythrocyte label by unit dimension, the
            # same way lab_parser does. Refusing without reassigning made this
            # path DROP a hematocrit printed as "Hồng cầu 0.50 L/L" — safe, but
            # the patient simply loses the value, and production runs
            # table-first, so the drop was the live behaviour rather than the
            # conversion the text path performs.
            _label = _strip_accents_lower(row.original_test_name or "")
            _implied = _au.resolve_erythrocyte_analyte(unit)
            _ambiguous = (
                any(
                    _strip_accents_lower(a) in _label
                    for a in _au.AMBIGUOUS_ERYTHROCYTE_ALIASES
                )
                and "rbc" not in _label
            )
            if _implied and _implied != spec.canonical and _ambiguous:
                _reassigned = _ALIAS_INDEX.get(_implied)
                if _reassigned is not None and _reassigned.canonical not in seen:
                    spec = _reassigned
                    display_name_vi = (
                        _get_catalog()["biomarkers"]
                        .get(spec.canonical, {})
                        .get("name_vn")
                        or display_name_vi
                    )
            _compat = _au.unit_compatibility(spec.canonical, unit)
            if _compat in (_au.UnitCompatibility.INCOMPATIBLE, _au.UnitCompatibility.UNKNOWN):
                _logger.info(
                    "cbc_row_refused reason=%s canonical=%s unit=%s",
                    _compat.value, spec.canonical, unit,
                )
                continue  # wrong dimension for this analyte → never emit
            _conv = _au.to_canonical_unit(spec.canonical, value, unit)
            if _conv is None:
                continue
            value, unit = _conv

        # Never fabricate the canonical unit for a guarded analyte — that is the
        # fact the read-path guard depends on. See lab_parser for the full note.
        seen[spec.canonical] = RawLabValue(
            test_name=spec.canonical,
            value=value,
            unit=unit if (unit or _guarded) else spec.unit,
            ocr_confidence=overall,
            confidence_detail=detail,
            # Preserve original as-printed value and unit — never overwrite after conversion.
            original_value=orig_value,
            original_unit=orig_unit if (orig_unit or _guarded) else spec.unit,
            raw_test_name=row.original_test_name,
            display_name_vi=display_name_vi,
            ocr_reference_range=row.original_reference_range,
            requires_review=requires_review,
            suspect_machine_id=row.suspect_machine_id,
        )

    return [seen[c] for c in sorted(seen, key=lambda c: _BIOMARKER_ORDER.get(c, 999))]


def _get_full_text(analyze_result: dict) -> str:
    """Join all cell content from the analyzeResult into a single string.

    Used by extract_and_map() to run detect_hospital() on the full document
    text rather than just table cells, ensuring header patterns are found
    even when they appear outside table boundaries.

    Important: the top-level ``content`` string and page lines are placed FIRST
    so that hospital name patterns (typically in document header) fall within the
    first 30 lines that detect_hospital() inspects.
    """
    parts: list[str] = []
    # Top-level content (full OCR text — hospital name usually here)
    if analyze_result.get("content"):
        parts.append(analyze_result["content"])
    # Pages / lines (text-parser path)
    for page in analyze_result.get("pages") or []:
        for line in page.get("lines") or []:
            parts.append(line.get("content") or "")
    # Table cells (table-first path — appended last to not push header beyond 30 lines)
    for table in analyze_result.get("tables") or []:
        for cell in table.get("cells") or []:
            parts.append(cell.get("content") or "")
    return "\n".join(parts)


def extract_and_map(
    analyze_result: dict,
    ocr_conf: float = 0.95,
) -> list[RawLabValue]:
    """Full Layer 1→4 pipeline: analyzeResult dict → RawLabValue list.

    Runs hospital detection on the full document text (Layer 2) before extracting
    table rows, so provider-specific column profiles and test-name cleaning are
    applied correctly.

    Returns an empty list when no usable table rows are found, signalling
    build_draft() to fall back to the text+regex path.
    """
    # Layer 2: detect hospital from full document text (position-weighted confidence).
    full_text = _get_full_text(analyze_result)
    detection = _detect_hospital_result(full_text)
    profile = detection.profile if detection.profile.hospital_id != "unknown" else None
    hospital_id = profile.hospital_id if profile else None
    if hospital_id:
        _logger.info(
            "table_extractor_hospital_detected hospital_id=%s confidence=%.2f",
            hospital_id,
            detection.confidence,
        )
    else:
        _logger.info(
            "table_extractor_unknown_provider — "
            "all rows will require_review=True, confidence capped at 0.5"
        )

    table_rows = extract_table_rows(analyze_result, hospital_id=hospital_id, profile=profile)
    if not table_rows:
        return []
    raw_values = map_table_rows_to_raw_values(
        table_rows,
        ocr_conf=ocr_conf,
        hospital_id=hospital_id,
        detection_confidence=detection.confidence,
    )
    _logger.info(
        "table_extractor rows_extracted=%d rows_mapped=%d conf=%.2f hospital=%s",
        len(table_rows),
        len(raw_values),
        ocr_conf,
        hospital_id or "unknown",
    )
    return raw_values
