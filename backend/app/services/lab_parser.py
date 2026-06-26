"""Lab-report text parser: OCR/plain text -> structured ``RawLabValue`` rows.

Heuristic, dependency-free. For each text line it looks for a *known* biomarker
label (Vietnamese + English aliases from ``lab_interpreter``) and the first
numeric value + optional unit + optional reference range on that line. Only
recognised canonical biomarkers are emitted — unrecognised noise is dropped so
the review form stays clean. The first occurrence of each canonical wins.

This is intentionally conservative: it never fabricates a value, and a parse
confidence (separate from OCR confidence) downgrades lines where the unit does
not look like the expected unit.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass

from app.domain.hospital_profiles import HospitalProfile, detect_hospital
from app.domain.lab_catalog import get_catalog as _get_catalog
from app.domain.lab_interpreter import (
    _ALIAS_INDEX,
    BIOMARKERS,
    BiomarkerSpec,
    ConfidenceDetail,
    RawLabValue,
)

_logger = logging.getLogger(__name__)

# A number: 1,234.5 / 5.6 / 5,6 (VN decimal comma) / 110
_NUMBER = r"\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?"
# unit token: %, mg/dL, mmol/L, U/L, 10^9/L, g/dL, mIU/L, pmol/L, mL/min/1.73m² …
_UNIT = r"[%a-zA-Zµμ][a-zA-Z0-9µμ/^.²]*(?:/[a-zA-Z0-9.²]+)*"
_VALUE_RE = re.compile(rf"(?P<value>{_NUMBER})\s*(?P<unit>{_UNIT})?")
# reference range like "3.9 - 6.1" or "(3.9-6.1)"
_RANGE_RE = re.compile(rf"(?P<lo>{_NUMBER})\s*[-–—]\s*(?P<hi>{_NUMBER})")

# Machine/instrument suffix patterns in lowercase/accent-stripped form.
# Applied to the text AFTER a biomarker label match to skip machine names that
# appear between the label and the actual numeric value.
# Example: "AST (GOT) (Cobas C502)* 25.37 U/L"
#   label="AST (GOT)" matched → after=" (Cobas C502)* 25.37 U/L"
#   → strip "(Cobas C502)*" → " 25.37 U/L" → correct value 25.37
_AFTER_LABEL_STRIP_RE = re.compile(
    r"(?:"
    r"\(\s*cobas\s+[a-z]*\s*\d*\s*\)"          # (cobas c502), (cobas pro), (cobas 8000)
    r"|\(\s*c\s*\d{3,4}\s*\)"                   # (c502), (c702)
    r"|\(\s*au\s*\d{3,4}\s*\)"                  # (au480), (au680)
    r"|\(\s*qx\s*[\w.]*\s*\)"                   # (qx200), (qx.sh.xxx)
    r"|\(\s*sysmex\s+[a-z0-9\s-]*\)"            # (sysmex xn-1000)
    r"|\(\s*architect\s*[a-z0-9\s]*\)"          # (architect i2000)
    r"|\(\s*(?:abbott|roche|siemens|beckman|coulter|olympus|hitachi)\s*[a-z0-9\s-]*\)"
    r"|\*"                                       # trailing asterisk
    r")\s*",
    re.IGNORECASE,
)


def _strip_machine_suffixes(text: str) -> str:
    """Strip machine/instrument suffixes that precede the numeric lab value.

    Prevents model numbers (e.g. 502 from "(Cobas C502)") from being extracted
    as the result when the machine suffix appears between the test-name label and
    the actual result in the OCR text line.  Applied iteratively until stable.
    """
    prev = None
    result = text
    while result != prev:
        prev = result
        result = _AFTER_LABEL_STRIP_RE.sub("", result, count=1).lstrip()
    return result


@dataclass
class ParsedLine:
    raw_label: str
    canonical: str
    value: float
    unit: str | None
    reference_range: str | None
    parse_confidence: float


def _to_float(token: str) -> float | None:
    t = token.strip().replace(" ", "")
    # 1,234.5 -> 1234.5 ; 5,6 -> 5.6
    if "," in t and "." in t:
        t = t.replace(",", "")
    elif "," in t:
        # treat comma as decimal separator unless it looks like a thousands group
        if re.fullmatch(r"\d{1,3}(,\d{3})+", t):
            t = t.replace(",", "")
        else:
            t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )


def _match_biomarker(
    line_noacc_lc: str,
    alias_index: dict | None = None,
) -> tuple[BiomarkerSpec, int] | None:
    """Find the biomarker whose alias appears in the accent-stripped, lower-cased
    line. Returns ``(spec, end_index)`` of the longest matching alias (so
    'ldl cholesterol' beats 'cholesterol'), or None. The end index lets the caller
    read the value AFTER the label, never digits embedded in the name (e.g. the
    '1' in 'HbA1c')."""
    idx = alias_index if alias_index is not None else _ALIAS_INDEX
    best: tuple[int, BiomarkerSpec, int] | None = None  # (alias_len, spec, end_idx)
    for alias, spec in idx.items():
        a = _strip_accents(alias.lower())
        if not a:
            continue
        if len(a) <= 3:
            # Word-boundary match for very short aliases (hb, tg, hct …).
            m = re.search(rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])", line_noacc_lc)
        else:
            pos = line_noacc_lc.find(a)
            m = None if pos < 0 else re.compile(re.escape(a)).match(line_noacc_lc, pos)
        if m is None:
            continue
        if best is None or len(a) > best[0]:
            best = (len(a), spec, m.end())
    if best is None:
        return None
    return best[1], best[2]


def _norm_unit(u: str) -> str:
    """Lowercase + normalize µ/μ/mc unicode/OCR variants so unit comparisons are stable.

    Handles: µ (U+00B5), μ (U+03BC), and the 'mc' OCR prefix (e.g. mcIU/mL, mcmol/L).
    'mol' is NOT normalized to 'µmol' — only explicit µ/μ/mc prefixes are replaced.
    """
    return (
        u.replace("µ", "u")
         .replace("μ", "u")
         .replace("mc", "u")
         .strip()
         .lower()
    )


# Global text corrections applied BEFORE hospital-profile and parser logic.
# Targets known Azure Document Intelligence OCR misreads that affect unit parsing.
_GLOBAL_OCR_CORRECTIONS: dict[str, str] = {
    "pIU/mL": "µIU/mL",  # Azure DI misreads µ as p before IU (TSH, Insulin)
    "pIU/L": "µIU/L",
    "ρIU/mL": "µIU/mL",  # Greek rho (U+03C1) OCR confusion for µ
    "ρIU/L": "µIU/L",
}

# Regex corrections for patterns that cannot be safely handled with simple string replace.
# Applied after _GLOBAL_OCR_CORRECTIONS, before hospital-profile corrections.
_GLOBAL_OCR_CORRECTIONS_RE: list[tuple[re.Pattern[str], str]] = [
    # Azure DI drops the µ prefix from µmol/L, emitting bare mol/L (e.g. creatinine, urea).
    # Lookbehind excludes letters AND digits so digit-adjacent forms (e.g. 88.42mol/L)
    # are not rewritten — the value-unit regex handles those correctly as-is.
    (re.compile(r"(?<![a-zA-Zµμ0-9])mol/L"), "µmol/L"),
]


def _is_incompatible(unit: str, spec: BiomarkerSpec) -> bool:
    n = _norm_unit(unit)
    return any(_norm_unit(bad) == n for bad in spec.incompatible_units)


def _try_si_convert(unit: str, value: float, spec: BiomarkerSpec) -> float | None:
    """Return value converted to canonical units if unit matches spec.si_unit, else None."""
    if spec.si_unit is None:
        return None
    if _norm_unit(unit) == _norm_unit(spec.si_unit):
        return round(value * spec.si_factor, 4)
    return None


def parse_lab_text(
    text: str,
    hospital_profile: HospitalProfile | None = None,
) -> list[RawLabValue]:
    """Parse OCR/plain text into recognised ``RawLabValue`` rows (first per canonical)."""
    if not text:
        return []

    # Apply global OCR corrections first (e.g. Azure DI µ→p misread, mol/L drop).
    for bad, good in _GLOBAL_OCR_CORRECTIONS.items():
        text = text.replace(bad, good)
    for pattern, replacement in _GLOBAL_OCR_CORRECTIONS_RE:
        text = pattern.sub(replacement, text)

    if hospital_profile is None:
        hospital_profile = detect_hospital(text)

    _combined = dict(_ALIAS_INDEX)
    if hospital_profile:
        corrected = text
        for bad, good in hospital_profile.ocr_corrections.items():
            corrected = corrected.replace(bad, good)
        text = corrected
        for canonical, extras in hospital_profile.additional_aliases.items():
            base_spec = _ALIAS_INDEX.get(canonical)
            if base_spec:
                for a in extras:
                    _combined[a.lower()] = base_spec

    seen: dict[str, RawLabValue] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or len(line) < 2:
            continue
        # Work on an accent-stripped copy — digits/units are ASCII, so this is
        # lossless for value extraction and lets indices line up with the match.
        line_noacc = _strip_accents(line)
        matched = _match_biomarker(line_noacc.lower(), _combined)
        if matched is None:
            continue
        spec, label_end = matched
        if spec.canonical in seen:
            continue

        # raw_test_name: exact printed label, same char count as accent-stripped line.
        raw_test_name = line[:label_end].strip()

        # Lookup Vietnamese display name from catalog.
        try:
            _cat_entry = _get_catalog()["biomarkers"].get(spec.canonical, {})
            display_name_vi = _cat_entry.get("name_vn") or spec.canonical
        except Exception:
            display_name_vi = spec.canonical

        # Read the value strictly AFTER the matched label.
        # Strip any machine/instrument suffixes first (e.g. "(Cobas C502)*") to
        # prevent model numbers like 502 from being misread as the lab value.
        after = _strip_machine_suffixes(line_noacc[label_end:])
        vm = _VALUE_RE.search(after)
        if vm is None:
            continue
        value = _to_float(vm.group("value"))
        if value is None:
            continue
        unit = (vm.group("unit") or "").strip(" :.-") or None

        # Extract reference range from the remainder of the line (after value+unit).
        # Supports: "3.9–6.1", "44 - 80", "< 55", "> 60".
        after_unit = after[vm.end():].strip()
        ocr_ref: str | None = None
        rm = _RANGE_RE.search(after_unit)
        if rm:
            lo = _to_float(rm.group("lo"))
            hi = _to_float(rm.group("hi"))
            if lo is not None and hi is not None and 0 < lo < hi < 10000:
                ocr_ref = f"{lo}–{hi}"
        elif after_unit:
            lt_m = re.match(r"<\s*(\d[0-9.,]*)", after_unit)
            if lt_m:
                v = _to_float(lt_m.group(1))
                if v is not None:
                    ocr_ref = f"<{v}"
            else:
                gt_m = re.match(r">\s*(\d[0-9.,]*)", after_unit)
                if gt_m:
                    v = _to_float(gt_m.group(1))
                    if v is not None:
                        ocr_ref = f">{v}"

        # ── Multi-dimensional confidence ─────────────────────────────────────
        # mapping_confidence: always 1.0 here — we only emit rows with an exact
        # alias match from _ALIAS_INDEX (no fuzzy matching emitted).
        mapping_conf = 1.0

        # Always capture printed value/unit BEFORE any SI conversion so the
        # review UI can show "as printed" values alongside the canonical ones.
        orig_value: float = value
        orig_unit: str = unit or spec.unit

        # ocr_confidence (proxy): did OCR produce a recognizable unit token?
        # 0.5 (not 0.7) when unit absent: ensures overall stays below the 0.75
        # threshold even at high engine quality (e.g. 0.725 × 0.95 = 0.69 < 0.75),
        # so missing-unit rows always require patient verification.
        ocr_conf_dim = 1.0 if unit else 0.5

        # conversion_confidence: how well does the extracted unit match the spec?
        conv_conf = 1.0
        incompatible = False
        if not unit:
            conv_conf = 0.7
        elif _is_incompatible(unit, spec):
            conv_conf = 0.0
            incompatible = True
        else:
            converted = _try_si_convert(unit, value, spec)
            if converted is not None:
                value = converted
                unit = spec.unit
                conv_conf = 1.0
            elif spec.unit:
                if _norm_unit(unit) == _norm_unit(spec.unit):
                    conv_conf = 1.0
                else:
                    u_root = re.sub(r"[^a-z]", "", unit.lower())[:3]
                    s_root = re.sub(r"[^a-z]", "", spec.unit.lower())[:3]
                    if u_root and s_root and u_root != s_root:
                        conv_conf = 0.6
                    else:
                        conv_conf = 0.9

        # clinical_confidence: physiological plausibility (hard gate on 0 or 1).
        clin_conf = 1.0
        if spec.physiological_min is not None and value < spec.physiological_min:
            clin_conf = 0.0
        elif spec.physiological_max is not None and value > spec.physiological_max:
            clin_conf = 0.0

        # Hard gates: incompatible unit or physiological impossibility → overall 0.
        if incompatible or clin_conf == 0.0:
            overall = 0.0
        else:
            overall = round(
                0.40 * ocr_conf_dim
                + 0.25 * mapping_conf
                + 0.25 * conv_conf
                + 0.10 * clin_conf,
                4,
            )

        # Build human-readable reasons for the review UI.
        reasons: list[str] = []
        if ocr_conf_dim < 1.0:
            reasons.append("⚠ OCR: đơn vị không trích xuất được từ văn bản")
        else:
            reasons.append("✓ OCR: giá trị và đơn vị được trích xuất")
        reasons.append("✓ Ánh xạ: chỉ số được nhận diện chính xác")
        if conv_conf == 0.0:
            reasons.append("⚠ Chuyển đổi: đơn vị không phù hợp lâm sàng")
        elif conv_conf == 0.6:
            reasons.append("⚠ Chuyển đổi: đơn vị không khớp chính xác với hệ chuẩn")
        elif conv_conf == 0.7:
            reasons.append("⚠ Chuyển đổi: thiếu đơn vị để xác nhận")
        else:
            reasons.append("✓ Chuyển đổi: đơn vị khớp hoặc đã quy đổi thành công")
        if clin_conf == 0.0:
            reasons.append("⚠ Lâm sàng: giá trị ngoài khoảng sinh lý — có thể lỗi OCR")
        else:
            reasons.append("✓ Lâm sàng: giá trị trong khoảng sinh lý")

        detail = ConfidenceDetail(
            ocr=ocr_conf_dim,
            mapping=mapping_conf,
            conversion=conv_conf,
            clinical=clin_conf,
            overall=overall,
            reasons=reasons,
        )

        _logger.debug(
            "ocr_confidence_breakdown",
            extra={
                "canonical": spec.canonical,
                "overall": overall,
                "ocr": ocr_conf_dim,
                "mapping": mapping_conf,
                "conversion": conv_conf,
                "clinical": clin_conf,
                "extracted_unit": unit or "",
                "expected_unit": spec.unit or "",
            },
        )

        seen[spec.canonical] = RawLabValue(
            test_name=spec.canonical,
            value=value,
            unit=unit or spec.unit,
            ocr_confidence=overall,
            confidence_detail=detail,
            original_value=orig_value,
            original_unit=orig_unit,
            raw_test_name=raw_test_name,
            display_name_vi=display_name_vi,
            ocr_reference_range=ocr_ref,
        )
    # Preserve biomarker declaration order for a stable, readable draft.
    order = {spec.canonical: i for i, spec in enumerate(BIOMARKERS)}
    return [seen[c] for c in sorted(seen, key=lambda c: order.get(c, 999))]


# --------------------------------------------------------------------------- #
# Test-date extraction
# --------------------------------------------------------------------------- #

# Label → priority (higher wins). Accent-stripped, lower-cased. The sample/
# collection date is the truest "when the blood was drawn"; the print/report date
# is least meaningful, so it ranks lowest.
_DATE_LABELS: tuple[tuple[str, int, str], ...] = (
    ("ngay lay mau", 5, "Ngày lấy mẫu"),
    ("ngay thu mau", 5, "Ngày thu mẫu"),
    ("collection date", 5, "Collection date"),
    ("sample date", 5, "Sample date"),
    ("ngay xet nghiem", 4, "Ngày xét nghiệm"),
    ("ngay xn", 4, "Ngày XN"),
    ("test date", 4, "Test date"),
    ("date of test", 4, "Date of test"),
    ("ngay thuc hien", 3, "Ngày thực hiện"),
    ("ngay ket qua", 2, "Ngày kết quả"),
    ("ngay tra ket qua", 2, "Ngày trả kết quả"),
    ("result date", 2, "Result date"),
    ("ngay in bao cao", 1, "Ngày in báo cáo"),
    ("ngay in", 1, "Ngày in"),
    ("report date", 1, "Report date"),
    ("ngay bao cao", 1, "Ngày báo cáo"),
)

# DD/MM/YYYY with / . or - separators.
_DMY_RE = re.compile(r"\b(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{4})\b")
# "ngay DD thang MM nam YYYY" (accent-stripped).
_VN_LONG_RE = re.compile(r"ngay\s+(\d{1,2})\s+thang\s+(\d{1,2})\s+nam\s+(\d{4})")

# Sanity window: a real exam date is in the past 50 years and not in the future.
_MIN_YEAR = 1975


@dataclass
class ExtractedDate:
    iso: str            # YYYY-MM-DD
    raw_label: str | None
    confidence: float


def _valid_dmy(d: int, m: int, y: int) -> str | None:
    """Return an ISO date string if (d, m, y) is a sane calendar date, else None.
    Uses no `Date.now()` (unavailable in some sandboxes) — a fixed upper bound year
    plus calendar validation. The endpoint applies the strict ≤today check."""
    if not (1 <= m <= 12 and 1 <= d <= 31 and _MIN_YEAR <= y <= 2100):
        return None
    days_in_month = [31, 29 if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0) else 28,
                     31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if d > days_in_month[m - 1]:
        return None
    return f"{y:04d}-{m:02d}-{d:02d}"


def _find_date_in(text_noacc: str) -> str | None:
    m = _VN_LONG_RE.search(text_noacc)
    if m:
        iso = _valid_dmy(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if iso:
            return iso
    m = _DMY_RE.search(text_noacc)
    if m:
        return _valid_dmy(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def parse_test_date(text: str) -> ExtractedDate | None:
    """Detect the lab's *exam* date from OCR text. Prefers the highest-priority
    labelled date (sample > test > performed > result > printed); falls back to a
    bare date anywhere with low confidence. Returns None if nothing parses.

    Never defaults to "today" — an undetected date must be filled by the patient."""
    if not text:
        return None
    lines = [_strip_accents(ln).lower() for ln in text.splitlines()]
    best: tuple[int, ExtractedDate] | None = None  # (priority, result)

    for i, line in enumerate(lines):
        for label, priority, display in _DATE_LABELS:
            idx = line.find(label)
            if idx < 0:
                continue
            # Look after the label on the same line, then the next line.
            iso = _find_date_in(line[idx + len(label):])
            search_window = "same"
            if iso is None and i + 1 < len(lines):
                iso = _find_date_in(lines[i + 1])
                search_window = "next"
            if iso is None:
                continue
            conf = 0.9 if (priority >= 4 and search_window == "same") else 0.75
            if best is None or priority > best[0]:
                best = (priority, ExtractedDate(iso=iso, raw_label=display, confidence=conf))

    if best is not None:
        return best[1]

    # Fallback: any sane date anywhere, but low confidence + no label.
    for line in lines:
        iso = _find_date_in(line)
        if iso:
            return ExtractedDate(iso=iso, raw_label=None, confidence=0.4)
    return None
