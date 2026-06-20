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

import re
import unicodedata
from dataclasses import dataclass

from app.domain.lab_interpreter import (
    _ALIAS_INDEX,
    BIOMARKERS,
    BiomarkerSpec,
    RawLabValue,
)

# A number: 1,234.5 / 5.6 / 5,6 (VN decimal comma) / 110
_NUMBER = r"\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?"
# unit token: %, mg/dL, mmol/L, U/L, 10^9/L, g/dL, mIU/L, pmol/L, mL/min/1.73m² …
_UNIT = r"[%a-zA-Zµμ][a-zA-Z0-9µμ/^.²]*(?:/[a-zA-Z0-9.²]+)*"
_VALUE_RE = re.compile(rf"(?P<value>{_NUMBER})\s*(?P<unit>{_UNIT})?")
# reference range like "3.9 - 6.1" or "(3.9-6.1)"
_RANGE_RE = re.compile(rf"(?P<lo>{_NUMBER})\s*[-–—]\s*(?P<hi>{_NUMBER})")


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


def _match_biomarker(line_noacc_lc: str) -> tuple[BiomarkerSpec, int] | None:
    """Find the biomarker whose alias appears in the accent-stripped, lower-cased
    line. Returns ``(spec, end_index)`` of the longest matching alias (so
    'ldl cholesterol' beats 'cholesterol'), or None. The end index lets the caller
    read the value AFTER the label, never digits embedded in the name (e.g. the
    '1' in 'HbA1c')."""
    best: tuple[int, BiomarkerSpec, int] | None = None  # (alias_len, spec, end_idx)
    for alias, spec in _ALIAS_INDEX.items():
        a = _strip_accents(alias.lower())
        if not a:
            continue
        if len(a) <= 3:
            # Word-boundary match for very short aliases (hb, tg, hct …).
            m = re.search(rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])", line_noacc_lc)
        else:
            idx = line_noacc_lc.find(a)
            m = None if idx < 0 else re.compile(re.escape(a)).match(line_noacc_lc, idx)
        if m is None:
            continue
        if best is None or len(a) > best[0]:
            best = (len(a), spec, m.end())
    if best is None:
        return None
    return best[1], best[2]


def parse_lab_text(text: str) -> list[RawLabValue]:
    """Parse OCR/plain text into recognised ``RawLabValue`` rows (first per canonical)."""
    if not text:
        return []
    seen: dict[str, RawLabValue] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or len(line) < 2:
            continue
        # Work on an accent-stripped copy — digits/units are ASCII, so this is
        # lossless for value extraction and lets indices line up with the match.
        line_noacc = _strip_accents(line)
        matched = _match_biomarker(line_noacc.lower())
        if matched is None:
            continue
        spec, label_end = matched
        if spec.canonical in seen:
            continue

        # Read the value strictly AFTER the matched label.
        after = line_noacc[label_end:]
        vm = _VALUE_RE.search(after)
        if vm is None:
            continue
        value = _to_float(vm.group("value"))
        if value is None:
            continue
        unit = (vm.group("unit") or "").strip(" :.-") or None

        # NOTE: any OCR'd reference range is intentionally ignored — the canonical
        # range from the biomarker taxonomy (applied by lab_interpreter) is more
        # reliable than a noisy scanned one.

        parse_conf = 1.0
        if unit and spec.unit:
            # crude unit agreement: share an alphabetic root?
            u_root = re.sub(r"[^a-z]", "", unit.lower())[:3]
            s_root = re.sub(r"[^a-z]", "", spec.unit.lower())[:3]
            if u_root and s_root and u_root != s_root:
                parse_conf = 0.6
        elif not unit:
            parse_conf = 0.8

        seen[spec.canonical] = RawLabValue(
            test_name=spec.canonical,
            value=value,
            unit=unit or spec.unit,
            ocr_confidence=parse_conf,
        )
    # Preserve biomarker declaration order for a stable, readable draft.
    order = {spec.canonical: i for i, spec in enumerate(BIOMARKERS)}
    return [seen[c] for c in sorted(seen, key=lambda c: order.get(c, 999))]
