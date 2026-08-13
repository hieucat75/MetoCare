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
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from types import MappingProxyType

from app.domain.hospital_profiles import HospitalProfile, detect_hospital
from app.domain.lab_catalog import get_catalog as _get_catalog
from app.domain.lab_interpreter import (
    _ALIAS_INDEX,
    BIOMARKERS,
    OCR_CONFIDENCE_THRESHOLD,
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
    r"\(\s*cobas\s+[a-z]*\s*\d*\s*\)"  # (cobas c502), (cobas pro), (cobas 8000)
    r"|\(\s*c\s*\d{3,4}\s*\)"  # (c502), (c702)
    r"|\(\s*au\s*\d{3,4}\s*\)"  # (au480), (au680)
    r"|\(\s*qx\s*[\w.]*\s*\)"  # (qx200), (qx.sh.xxx)
    r"|\(\s*sysmex\s+[a-z0-9\s-]*\)"  # (sysmex xn-1000)
    r"|\(\s*architect\s*[a-z0-9\s]*\)"  # (architect i2000)
    r"|\(\s*(?:abbott|roche|siemens|beckman|coulter|olympus|hitachi)\s*[a-z0-9\s-]*\)"
    r"|\*"  # trailing asterisk
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
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


# Aliases the parser must recognise that the shared ``_ALIAS_INDEX`` does not
# carry. Their absence is the direct cause of OCR-F3: the index holds
# "hdl-cholesterol" (hyphen) but not "hdl cholesterol" (space) nor the
# VN-report word order "cholesterol hdl", so a printed "HDL Cholesterol" only
# matched the generic "cholesterol" alias and was stored as total cholesterol.
# Some hospital profiles already declare these, but only when a profile is
# detected — these make the behaviour unconditional.
_PARSER_EXTRA_ALIASES: dict[str, tuple[str, ...]] = {
    "hdl": ("hdl cholesterol", "cholesterol hdl", "hdl chol", "chol hdl"),
    "ldl": ("ldl cholesterol", "cholesterol ldl", "ldl chol", "chol ldl"),
}

# Labels that contain a known alias but denote an analyte this catalogue has NO
# canonical biomarker for. Emitting the contained alias would silently file a
# different analyte (e.g. non-HDL / VLDL cholesterol stored as HDL or total
# cholesterol; a lipid *ratio* stored as a concentration). Matched against the
# accent-stripped, lower-cased line — one lab row per line — and the whole row
# is dropped rather than mis-mapped.
_UNMAPPABLE_LABEL_RE = re.compile(
    r"(?:"
    r"non[\s\-_.]*hdl"  # non-HDL cholesterol — no canonical biomarker
    r"|(?<![a-z0-9])vldl"  # VLDL cholesterol / VLDL-C — no canonical biomarker
    r"|remnant\s+cholesterol"
    r"|cholesterol\s+con\s+lai"
    r"|(?:chol|cholesterol|tc|ldl|tg|triglycerid\w*)\s*/\s*hdl"  # lipid ratios
    r"|hdl\s*/\s*(?:chol|cholesterol|tc|ldl)"
    #
    # SPECIMEN qualifiers. Every canonical in the table is a SERUM/blood analyte,
    # and nothing downstream carries a specimen, so a urine line resolved to the
    # serum canonical and was stored, classified and trended as blood.
    #
    # This is the same "wrong analyte" class as the lipid neighbours above, and it
    # is worse in one direction: the value ranges do not overlap, so it does not
    # look like noise. Urine creatinine runs 50-200 mg/dL against a serum
    # reference of 0.6-1.2 with critical around 4, so a routine urinalysis line
    # told the patient their kidney function was catastrophically abnormal. In the
    # other direction urine glucose 5.5 mmol/L became a fasting_glucose of ~99
    # mg/dL and classified NORMAL — a fabricated normal blood sugar, with the
    # glycosuria that was actually on the report silently dropped.
    #
    # Urinalysis is in nearly every VN check-up packet and the whole premise of
    # the document path is "photograph whatever the hospital gave you", so this is
    # a routine input, not an edge case. The review card shows the printed label,
    # so confirming "Creatinin niệu" looks entirely correct to the patient.
    #
    # Dropping the row is the same trade as everywhere else here: a missing urine
    # result is a gap the patient can see; a urine value stored as blood is not.
    r"|(?<![a-z0-9])nieu(?![a-z0-9])"  # "niệu" accent-stripped — VN for urinary
    r"|nuoc\s*tieu"  # "nước tiểu" — urine
    r"|(?<![a-z0-9])urin\w*"  # urine / urinary / urinalysis
    r"|24\s*h\s*urine|urine\s*24"
    r"|(?<![a-z0-9])acr(?![a-z0-9])"  # albumin/creatinine ratio
    r"|albumin\s*/\s*creatinin\w*"
    r"|(?<![a-z0-9])upcr(?![a-z0-9])"
    r"|(?<![a-z0-9])(?:dich\s*nao\s*tuy|csf)(?![a-z0-9])"  # CSF, same reasoning
    r")"
)


@lru_cache(maxsize=1024)
def _alias_pattern(alias_noacc: str) -> re.Pattern[str]:
    """Compile a word-boundary-aware pattern for an accent-stripped alias.

    A bare substring search lets a generic alias match inside a more specific
    name (``ldl`` inside ``vldl``, ``ldl-c`` inside ``vldl-c``). Boundaries are
    expressed as alphanumeric lookarounds rather than ``\\b`` because aliases
    legitimately end in punctuation (``na+``, ``k+``, ``cl-``).

    Trailing digits are tolerated for aliases longer than 3 chars so glued OCR
    output ("Cholesterol210") still parses, while short aliases keep the strict
    digit-blocking boundary that stops ``hb`` matching inside ``hba1c``.
    """
    lead = r"(?<![a-z0-9])" if alias_noacc[0].isalnum() else ""
    if not alias_noacc[-1].isalnum():
        trail = ""
    elif len(alias_noacc) <= 3:
        trail = r"(?![a-z0-9])"
    else:
        trail = r"(?![a-z])"
    # Separators inside an alias are matched FLEXIBLY: a single space in the
    # alias matches any run of space / hyphen / underscore / dot in the label.
    # Printed VN reports write the same analyte as "HDL Cholesterol",
    # "HDL-Cholesterol" and "HDL - Cholesterol", and enumerating a fixed alias per
    # spelling is how "HDL - Cholesterol" kept resolving to total_cholesterol
    # after the space form had been fixed. Note "/" is deliberately NOT a
    # separator here: "Cholesterol/HDL" is a RATIO, a different quantity, and
    # must stay unmappable rather than collapse onto "cholesterol hdl".
    #
    # Length is preserved by construction (the pattern matches the original
    # string; nothing is rewritten), so the caller's end-index into the raw line
    # stays exact.
    body = r"[\s\-_.]+".join(re.escape(part) for part in alias_noacc.split(" ") if part)
    return re.compile(lead + body + trail)



def _profile_by_name(name: str):
    """Resolve a profile by name for the memoised index (keeps the cache key hashable)."""
    from app.domain.hospital_profiles import HOSPITAL_PROFILES

    for profile in HOSPITAL_PROFILES:
        if profile.name == name:
            return profile
    return None


@lru_cache(maxsize=32)
def _cached_alias_index(profile_name: str | None) -> dict:
    """Memoised alias index. Keyed by profile NAME so the result is hashable."""
    combined = dict(_ALIAS_INDEX)
    for canonical, extras in _PARSER_EXTRA_ALIASES.items():
        base = _ALIAS_INDEX.get(canonical)
        if base:
            for alias in extras:
                combined.setdefault(alias, base)

    profile = _profile_by_name(profile_name) if profile_name else None
    if profile:
        for canonical, extras in profile.additional_aliases.items():
            base_spec = _ALIAS_INDEX.get(canonical)
            if base_spec:
                for alias in extras:
                    combined[alias.lower()] = base_spec
    return combined


def build_alias_index(hospital_profile=None) -> Mapping[str, BiomarkerSpec]:
    """THE alias index. Every analyte-resolution call site must use this.

    `_ALIAS_INDEX` alone is NOT safe to match against. It carries
    "hdl-cholesterol" (hyphen) but neither "hdl cholesterol" (space) nor the VN
    report order "cholesterol hdl", while `total_cholesterol` carries the bare
    alias "cholesterol". Under longest-alias-wins the spans for "HDL Cholesterol"
    are `hdl`(0-3) and `cholesterol`(4-15) — neither contains the other, so
    nothing is shadowed and the LONGER `cholesterol` wins. The printed label says
    HDL; the stored analyte is total cholesterol.

    That is exactly what happened on the MDI path, which called
    `_match_biomarker` with no index and so silently used the bare
    `_ALIAS_INDEX`, while `/lab-uploads` built a combined index inline and was
    safe. Two code paths, two different answers for the same printed label.
    Routing every caller through this one function makes that class of drift
    impossible rather than merely fixed once.
    """
    # Read-only view over the MEMOIZED dict. Returning the dict itself handed
    # every caller a shared, cached, mutable mapping keyed by profile name: one
    # caller doing `idx["x"] = spec` would silently corrupt analyte resolution for
    # every later request using that profile, and the corruption would persist for
    # the process lifetime. No caller mutates it today; MappingProxyType is O(1)
    # and makes that impossible to start doing by accident.
    return MappingProxyType(_cached_alias_index(getattr(hospital_profile, "name", None)))


def _match_biomarker(
    line_noacc_lc: str,
    alias_index: dict | None = None,
) -> tuple[BiomarkerSpec, int] | None:
    """Find the biomarker whose alias appears in the accent-stripped, lower-cased
    line. Returns ``(spec, end_index)`` of the most *specific* matching alias, or
    None. The end index lets the caller read the value AFTER the label, never
    digits embedded in the name (e.g. the '1' in 'HbA1c').

    Specificity rules, in order:

    1. Labels with no canonical biomarker (``_UNMAPPABLE_LABEL_RE``) match
       nothing at all — a wrong analyte is worse than a dropped row.
    2. A match wholly contained inside a longer match is discarded, so
       ``cholesterol`` can never win inside ``hdl cholesterol`` /
       ``cholesterol hdl`` / ``cholesterol toan phan``.
    3. Of what remains, the longest alias wins; ties break on earliest position
       so the result is deterministic regardless of alias-index ordering.
    """
    idx = alias_index if alias_index is not None else _ALIAS_INDEX
    if _UNMAPPABLE_LABEL_RE.search(line_noacc_lc):
        return None

    won = _winning_span(line_noacc_lc, idx)
    if won is None:
        return None
    _start, end, spec, _alias = won
    return spec, end


def _winning_span(
    line_noacc_lc: str, idx: dict
) -> tuple[int, int, BiomarkerSpec, str] | None:
    """The shared span-selection, returning the WINNING ALIAS as well.

    `_match_biomarker` deliberately keeps its two-tuple return (many callers
    unpack it), so the alias that actually won is carried here instead of widening
    that signature. It is what `resolve_with_provenance` records: "resolved to
    `ldl`" is not auditable on its own, because it does not say WHICH of the
    dozens of aliases fired, and that is precisely the question asked when a row
    turns out to name the wrong analyte.
    """
    spans: list[tuple[int, int, BiomarkerSpec, str]] = []
    for alias, spec in idx.items():
        a = _strip_accents(alias.lower())
        if not a:
            continue
        for m in _alias_pattern(a).finditer(line_noacc_lc):
            spans.append((m.start(), m.end(), spec, alias))
    if not spans:
        return None

    def _is_shadowed(span) -> bool:
        start, end = span[0], span[1]
        return any(
            o[0] <= start and end <= o[1] and (o[1] - o[0]) > (end - start)
            for o in spans
        )

    survivors = [s for s in spans if not _is_shadowed(s)]
    return min(survivors, key=lambda s: (-(s[1] - s[0]), s[0]))


def resolve_with_provenance(label: str | None, hospital_profile=None) -> dict:
    """Resolve a printed lab label AND record how the resolution was reached.

    Storing only the canonical key makes a wrong-analyte incident un-investigable
    after the fact: the row says `ldl`, the report said something else, and
    nothing records which alias bridged them or whether a hospital-profile alias
    was involved. That is the exact question P0-1 raised, and it could not be
    answered from the data.

    Returns a flat, JSON-serializable dict — never raises. `canonical` is None for
    a label with no safe canonical (non-HDL, VLDL, a ratio), and `reason` says
    which rule dropped it, so "we produced nothing" is distinguishable from "we
    were never asked".
    """
    raw = (label or "").strip()
    if not raw:
        return {"original_label": label, "canonical": None, "reason": "empty_label"}

    normalized = _strip_accents(raw.lower())
    if _UNMAPPABLE_LABEL_RE.search(normalized):
        # Deliberate refusal, not a lookup miss — the distinction matters when
        # someone asks why a line on the report never became a row.
        return {
            "original_label": raw,
            "canonical": None,
            "reason": "unmappable_label",
            "matcher": "hardened",
        }

    idx = build_alias_index(hospital_profile)
    won = _winning_span(normalized, idx)
    if won is None:
        return {
            "original_label": raw,
            "canonical": None,
            "reason": "no_alias_matched",
            "matcher": "hardened",
        }

    _start, _end, spec, alias = won
    profile_name = getattr(hospital_profile, "name", None)
    return {
        "original_label": raw,
        "canonical": spec.canonical,
        "matched_alias": alias,
        "alias_source": _alias_source(alias, hospital_profile),
        "hospital_profile": profile_name,
        "matcher": "hardened",
        "reason": "matched",
    }


def _alias_source(alias: str, hospital_profile=None) -> str:
    """Which of the THREE alias layers contributed the winning alias.

    `build_alias_index` merges the shared `_ALIAS_INDEX`, the parser's own
    `_PARSER_EXTRA_ALIASES`, and any hospital-profile aliases. Collapsing that to
    base-or-profile mislabels every parser-extra alias as profile-contributed —
    which would send an investigator looking at the wrong lab's configuration.
    A profile-scoped alias resolving a report from a DIFFERENT lab is a specific,
    checkable failure, so the layer has to be reported accurately to be useful.
    """
    if alias in _ALIAS_INDEX:
        return "base"
    for extras in _PARSER_EXTRA_ALIASES.values():
        if alias in extras:
            return "parser_extra"
    if hospital_profile is not None:
        for extras in getattr(hospital_profile, "additional_aliases", {}).values():
            if alias in extras or alias.lower() in {e.lower() for e in extras}:
                return "profile"
    return "unknown"


def _norm_unit(u: str) -> str:
    """Lowercase + normalize µ/μ/mc unicode/OCR variants so unit comparisons are stable.

    Handles: µ (U+00B5), μ (U+03BC), and the 'mc' OCR prefix (e.g. mcIU/mL, mcmol/L).
    'mol' is NOT normalized to 'µmol' — only explicit µ/μ/mc prefixes are replaced.
    """
    return u.replace("µ", "u").replace("μ", "u").replace("mc", "u").strip().lower()


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


# Count-per-volume units the main `_UNIT` pattern cannot reach because they
# begin with a digit ("10^12/L", "10 12/L" when OCR drops the caret). Used only
# by the CBC dimensional guard, never to change the emitted unit string.
_COUNT_UNIT_RE = re.compile(
    r"10\s*[\^*]?\s*\d{1,2}\s*/\s*[lL1]|10\s*[¹²³⁶⁹]+\s*/\s*[lL1]",
)


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

    if hospital_profile:
        corrected = text
        for bad, good in hospital_profile.ocr_corrections.items():
            corrected = corrected.replace(bad, good)
        text = corrected
    # One shared builder — see build_alias_index for why matching against the
    # bare _ALIAS_INDEX is unsafe.
    _combined = build_alias_index(hospital_profile)

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
        after_unit = after[vm.end() :].strip()
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

        # ── P0: erythrocyte analyte/unit safety ──────────────────────────────
        # "Hồng cầu" heads the RBC count line AND is contained in every VN
        # hematocrit phrase, so the label alone cannot decide which analyte this
        # is. The UNIT decides — dimension only, never magnitude: choosing the
        # analyte by plausibility is exactly what let a hematocrit fraction
        # (0.50 L/L) be stored as a critically low red cell count.
        #
        # An explicit label ("RBC") carrying a foreign unit is NOT relabelled —
        # that would be guessing which half of the pair is wrong. It is dropped,
        # so the row reaches review rather than a confident wrong classification.
        from app.domain import analyte_units as _au

        # `_UNIT` cannot match a digit-initial token, so a printed "10^12/L"
        # reaches here as NO unit and `spec.unit` is substituted downstream —
        # which is precisely the "assume compatible" behaviour this guard exists
        # to remove (an HCT line reading 5.0 10^12/L would emit "hematocrit
        # 5.0 %", a fabricated unit and a false critical low). Recover the count
        # unit from the text after the value for the dimensional check only.
        _eff_unit = unit
        if not _eff_unit and vm is not None:
            _cm = _COUNT_UNIT_RE.search(after[vm.end() :])
            if _cm:
                _eff_unit = _cm.group(0)

        if _eff_unit and spec.canonical in _au.ALLOWED_UNITS:
            unit = _eff_unit
            _label = _strip_accents(raw_test_name).lower()
            # `resolve_erythrocyte_analyte` only ever names rbc/hematocrit — a
            # guarded analyte outside that pair (haemoglobin, #155 item 2) has no
            # erythrocyte identity to imply, so `_implied is None` for it is
            # NORMAL, not a foreign unit. Only gate reassignment/refusal on this
            # signal when it actually resolved to an erythrocyte analyte; the
            # general dimensional check below covers the rest.
            _implied = _au.resolve_erythrocyte_analyte(unit)
            _label_is_ambiguous = (
                any(_strip_accents(a) in _label for a in _au.AMBIGUOUS_ERYTHROCYTE_ALIASES)
                and "rbc" not in _label
            )
            if _implied is not None and _implied != spec.canonical:
                if not _label_is_ambiguous:
                    _logger.info(
                        "cbc_row_refused reason=explicit_analyte_foreign_unit "
                        "canonical=%s unit=%s", spec.canonical, unit,
                    )
                    continue  # explicit analyte + foreign unit → never emit
                _reassigned = _combined.get(_implied)
                if _reassigned is None or _reassigned.canonical in seen:
                    continue
                spec = _reassigned
            _compat = _au.unit_compatibility(spec.canonical, unit)
            if _compat in (_au.UnitCompatibility.INCOMPATIBLE, _au.UnitCompatibility.UNKNOWN):
                _logger.info(
                    "cbc_row_refused reason=%s canonical=%s unit=%s",
                    _compat.value, spec.canonical, unit,
                )
                continue
            # Relabel and convert together — never one without the other. This
            # also normalises an already-correct hematocrit fraction (0.50 L/L)
            # to the canonical percent, so both screens compare like with like.
            _converted = _au.to_canonical_unit(spec.canonical, value, unit)
            if _converted is None:
                _logger.info(
                    "cbc_row_refused reason=unconvertible canonical=%s unit=%s",
                    spec.canonical, unit,
                )
                continue
            value, unit = _converted
            # #155 item 3: the printed range shares the pre-conversion unit and
            # must go through the identical conversion, or a converted value ends
            # up sitting against a raw, unconverted range.
            ocr_ref = _au.to_canonical_range(spec.canonical, ocr_ref, orig_unit)

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
                0.40 * ocr_conf_dim + 0.25 * mapping_conf + 0.25 * conv_conf + 0.10 * clin_conf,
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

        # A row the parser is not confident about must never present as settled:
        # anything below the module-wide review threshold (and therefore every
        # hard-gated 0.0 from an incompatible unit or an impossible value) is
        # flagged so it cannot be persisted without explicit user confirmation.
        requires_review = overall < OCR_CONFIDENCE_THRESHOLD

        # NEVER substitute the canonical unit for a guarded analyte. Doing so
        # fabricates the one fact the read-path guard depends on: an unlabelled
        # "Hồng cầu 0.50" would be stored as `rbc 0.50 10^12/L`, which looks
        # canonical, passes `physiological_min=0.5` on the boundary, and then
        # classifies CRITICAL — the original incident, with the allowlist
        # bypassed because the unit now appears correct. Persisting None lets the
        # serializer's UNKNOWN branch fire and surface the row for review.
        _emit_unit = unit if (unit or spec.canonical in _au.ALLOWED_UNITS) else spec.unit
        seen[spec.canonical] = RawLabValue(
            test_name=spec.canonical,
            value=value,
            unit=_emit_unit,
            ocr_confidence=overall,
            confidence_detail=detail,
            requires_review=requires_review,
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
    iso: str  # YYYY-MM-DD
    raw_label: str | None
    confidence: float


def _valid_dmy(d: int, m: int, y: int) -> str | None:
    """Return an ISO date string if (d, m, y) is a sane calendar date, else None.
    Uses no `Date.now()` (unavailable in some sandboxes) — a fixed upper bound year
    plus calendar validation. The endpoint applies the strict ≤today check."""
    if not (1 <= m <= 12 and 1 <= d <= 31 and _MIN_YEAR <= y <= 2100):
        return None
    days_in_month = [
        31,
        29 if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0) else 28,
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ]
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
            iso = _find_date_in(line[idx + len(label) :])
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
