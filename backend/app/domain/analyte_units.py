"""Fail-closed unit/analyte compatibility for CBC analytes.

Production showed one stored CBC row two different ways: `rbc 0.50 L/L` against a
printed range of `0.42-0.47 L/L` labelled "Nguy hiểm" on one screen, and the same
row against the registry range `4.2-5.9 x10^12/L` labelled "Rất thấp" on another.
Both severities were confident, contradictory, and wrong — because the analyte
identity itself was wrong.

Mechanism: a hematocrit line printed as a fraction (`0.50 L/L`) resolved to
canonical `rbc`, and nothing downstream objected.

- `lab_parser._is_incompatible` is a DENYLIST over `spec.incompatible_units`,
  which is empty for both `rbc` and `hematocrit`. An unlisted unit is accepted.
- `rbc.physiological_min` is 0.5, so the hematocrit fraction 0.50 lands exactly
  on the boundary and passes the magnitude check.
- `rbc.critical_low` is 2.5, so 0.50 then classifies CRITICAL.

A denylist cannot express "this analyte has exactly one unit". This module is the
allowlist: a guarded analyte declares every unit it accepts, and anything else is
refused rather than assumed compatible.

Deliberately scoped. Only analytes in `ALLOWED_UNITS` are guarded; every other
biomarker keeps its existing behaviour, so this stays a P0 safety fix rather than
a repricing of the whole catalogue. The unified LabResult contract is separate
follow-up work.
"""

from __future__ import annotations

import re
from enum import StrEnum

#: Patient-facing text for a row whose analyte/unit pair cannot be trusted.
#: Deliberately says nothing clinical — the value is not interpretable, so any
#: "high"/"low"/"critical" wording would be a claim we cannot support.
NEEDS_REVIEW_MESSAGE = "Chỉ số cần được kiểm tra lại do đơn vị hoặc loại xét nghiệm chưa khớp."


class UnitCompatibility(StrEnum):
    #: Analyte carries no allowlist — legacy path, this module makes no claim.
    NOT_GUARDED = "not_guarded"
    #: Unit is the analyte's canonical unit.
    CANONICAL = "canonical"
    #: Unit is an accepted equivalent; convert before classifying.
    CONVERTIBLE = "convertible"
    #: Unit belongs to a different analyte / dimension. Never classify.
    INCOMPATIBLE = "incompatible"
    #: Unit not recognised at all. Fail closed — never classify.
    UNKNOWN = "unknown"


_SUPERSCRIPT_DIGITS = {
    "⁰": "0",
    "¹": "1",
    "²": "2",
    "³": "3",
    "⁴": "4",
    "⁵": "5",
    "⁶": "6",
    "⁷": "7",
    "⁸": "8",
    "⁹": "9",
}


def _expand_superscripts(u: str) -> str:
    """`10¹²/L` -> `10^12/L`.

    A plain character substitution yields `1012/L`, which matches nothing — the
    exponent marker has to be reintroduced, or the guard silently fails open on
    the most common printed spelling.
    """
    out: list[str] = []
    i = 0
    while i < len(u):
        if u[i] in _SUPERSCRIPT_DIGITS:
            digits = ""
            while i < len(u) and u[i] in _SUPERSCRIPT_DIGITS:
                digits += _SUPERSCRIPT_DIGITS[u[i]]
                i += 1
            out.append("^" + digits)
        else:
            out.append(u[i])
            i += 1
    return "".join(out)


def normalize_unit(unit: str | None) -> str:
    """Canonical spelling for comparison: case, spacing, u variants, superscripts.

    `10^12/L`, `10¹²/L`, `10*12/L`, `x10^12/L` and `T/L` are the same dimension
    printed several ways; a guard that misses any spelling fails open.
    """
    if not unit:
        return ""
    u = _expand_superscripts(unit.strip().lower())
    u = u.replace("µ", "u").replace("μ", "u")
    u = u.replace(" ", "").replace("×", "x").replace("*", "^")
    if u.startswith("x"):
        u = u[1:]
    return u


#: canonical analyte -> {normalized unit: factor to reach the canonical unit}.
ALLOWED_UNITS: dict[str, dict[str, float]] = {
    # Red cell COUNT. One dimension: cells per volume.
    # An omission here does not fail safe: an unrecognised unit is refused, so a
    # legitimate RBC result printed in an unlisted spelling would be lost rather
    # than mis-filed. Older VN printouts use "triệu/mm³" (million per mm³), which
    # is numerically identical to 10^12/L.
    "rbc": {
        "10^12/l": 1.0,
        "10^12/1": 1.0,  # OCR reads L as 1
        "t/l": 1.0,  # tera/L — numerically identical
        "t/1": 1.0,  # same OCR L->1 misread
        "tera/l": 1.0,
        "10^6/ul": 1.0,  # 10^6/uL == 10^12/L
        "10^6/mm3": 1.0,
        "m/ul": 1.0,
        "m/mm3": 1.0,
        "trieu/mm3": 1.0,  # accent-stripped "triệu/mm³"
        "triệu/mm3": 1.0,
    },
    # Red cell VOLUME FRACTION. Canonical percent; L/L is the same quantity x100.
    "hematocrit": {
        "%": 1.0,
        "vol%": 1.0,
        "l/l": 100.0,
        "v/v": 100.0,
        "ratio": 100.0,
    },
    # Haemoglobin MASS CONCENTRATION. Canonical g/dL; g/L is the same quantity /10.
    # #155: absent here meant `to_canonical_unit("hemoglobin", 140, "g/L")` returned
    # None, so a normal 140 g/L haemoglobin was never converted and then read as
    # physiologically impossible against the g/dL bounds [1, 25].
    "hemoglobin": {
        "g/dl": 1.0,
        "g/l": 0.1,
    },
}

#: Canonical unit per guarded analyte.
CANONICAL_UNIT: dict[str, str] = {
    "rbc": "10^12/L",
    "hematocrit": "%",
    "hemoglobin": "g/dL",
}

#: Labels naming the erythrocyte without saying whether the COUNT or the VOLUME
#: FRACTION is meant. "Hồng cầu" alone is genuinely ambiguous on a VN report: it
#: heads the RBC count line and is also embedded in every hematocrit phrase. The
#: unit disambiguates it; nothing else may.
AMBIGUOUS_ERYTHROCYTE_ALIASES: frozenset[str] = frozenset(
    {"hồng cầu", "hong cau", "red blood cell", "red blood cells"}
)


def unit_compatibility(canonical: str | None, unit: str | None) -> UnitCompatibility:
    """Classify an (analyte, unit) pair. Fails closed for guarded analytes."""
    if not canonical:
        return UnitCompatibility.NOT_GUARDED
    key = canonical.strip().lower()
    allowed = ALLOWED_UNITS.get(key)
    if allowed is None:
        return UnitCompatibility.NOT_GUARDED
    u = normalize_unit(unit)
    if not u:
        # A guarded analyte with no unit cannot be classified — the whole point
        # of the guard is that magnitude alone does not identify the analyte.
        return UnitCompatibility.UNKNOWN
    if u in allowed:
        if u == normalize_unit(CANONICAL_UNIT[key]):
            return UnitCompatibility.CANONICAL
        return UnitCompatibility.CONVERTIBLE
    # Recognised, but as some OTHER guarded analyte's unit — a mis-mapping.
    for other, other_units in ALLOWED_UNITS.items():
        if other != key and u in other_units:
            return UnitCompatibility.INCOMPATIBLE
    return UnitCompatibility.UNKNOWN


def is_unsafe_pair(canonical: str | None, unit: str | None) -> bool:
    """True when this stored pair must never yield a confident severity.

    Used on the READ path so rows already written to production stop presenting
    a clinical claim, before any data remediation runs.
    """
    return unit_compatibility(canonical, unit) in (
        UnitCompatibility.INCOMPATIBLE,
        UnitCompatibility.UNKNOWN,
    )


def to_canonical_unit(canonical: str, value: float, unit: str | None) -> tuple[float, str] | None:
    """Convert to the analyte's canonical unit, or None when not permitted.

    Relabelling without converting is how `0.50 L/L` became "RBC 0.50", so the
    conversion is part of this same call, never a separate step a caller can skip.
    """
    key = canonical.strip().lower()
    allowed = ALLOWED_UNITS.get(key)
    if allowed is None:
        return None
    factor = allowed.get(normalize_unit(unit))
    if factor is None:
        return None
    return round(value * factor, 4), CANONICAL_UNIT[key]


#: Matches the exact shapes `_parse_reference_cell` (lab_table_extractor) and the
#: text parser render into `ocr_reference_range`: "0.42–0.47", "<55", ">60". No
#: surrounding whitespace, en-dash separator — never a source of truth on its own,
#: only ever a display string this module re-derives from the parsed bounds.
#: `_RANGE_DASH_RE`/`_LESS_THAN_RE`/`_GREATER_THAN_RE` (lab_table_extractor)
#: preserve a comma decimal verbatim ("0,42–0,47"), so a bound must accept one too
#: or a VN-formatted range silently fails to convert and is returned unchanged —
#: leaving a converted value sitting next to its own untouched printed range,
#: exactly the defect this function exists to close.
_RANGE_RE = re.compile(r"^(-?\d+(?:[.,]\d+)?)–(-?\d+(?:[.,]\d+)?)$")
_LT_RE = re.compile(r"^<(-?\d+(?:[.,]\d+)?)$")
_GT_RE = re.compile(r"^>(-?\d+(?:[.,]\d+)?)$")


def _to_float_bound(token: str) -> float:
    return float(token.replace(",", "."))


def _format_bound(value: float) -> str:
    """`42.0` -> `"42"`; `13.5` -> `"13.5"` — a whole-number bound must not grow a
    spurious `.0` that never appeared on the printed report."""
    if value == int(value):
        return str(int(value))
    return f"{value:g}"


def to_canonical_range(canonical: str, range_str: str | None, unit: str | None) -> str | None:
    """Convert a printed reference-range string into the analyte's canonical unit.

    A reference range is printed in the SAME unit as its measured value and is
    never repeated on its own ("0.42–0.47" beside "0.50 L/L"). Converting the
    value alone and leaving the range as raw passthrough text is how a converted
    `hematocrit 50 %` ended up sitting next to an unconverted `0.42-0.47` range —
    the value and its range must go through the identical conversion, together.

    Returns ``range_str`` unchanged when it is not one of the two printed shapes,
    or when the unit does not convert for this analyte — never fabricates a bound.
    """
    if not range_str or not unit:
        return range_str
    text = range_str.strip()
    m = _RANGE_RE.match(text)
    if m:
        lo = to_canonical_unit(canonical, _to_float_bound(m.group(1)), unit)
        hi = to_canonical_unit(canonical, _to_float_bound(m.group(2)), unit)
        if lo is None or hi is None:
            return range_str
        return f"{_format_bound(lo[0])}–{_format_bound(hi[0])}"
    for op, pattern in (("<", _LT_RE), (">", _GT_RE)):
        m = pattern.match(text)
        if m:
            bound = to_canonical_unit(canonical, _to_float_bound(m.group(1)), unit)
            if bound is None:
                return range_str
            return f"{op}{_format_bound(bound[0])}"
    return range_str


def resolve_erythrocyte_analyte(unit: str | None) -> str | None:
    """Which erythrocyte analyte does this unit imply? None when undecidable.

    Unit dimension is the ONLY signal used here. Magnitude is deliberately not
    consulted: deciding analyte identity from plausibility is exactly what let a
    hematocrit fraction masquerade as a critically low red cell count.
    """
    u = normalize_unit(unit)
    if not u:
        return None
    if u in ALLOWED_UNITS["rbc"]:
        return "rbc"
    if u in ALLOWED_UNITS["hematocrit"]:
        return "hematocrit"
    return None


def guarded_status(canonical: str | None, value: float | None, unit: str | None):
    """Single decision for a guarded analyte: (status, converted_value) or None.

    Returns None when the analyte is not guarded, so the caller keeps its legacy
    path. Otherwise the status is authoritative and already accounts for:
      * alias resolution — ALLOWED_UNITS is canonical-keyed while `classify_value`
        is alias-keyed, so a row typed "hct" would otherwise skip the guard here
        and be classified there;
      * dimensional compatibility — fail closed on incompatible/unknown;
      * conversion to the canonical unit BEFORE classification;
      * the physiological floor. This is the one that matters for rows already in
        the database: before this fix the write path stamped the canonical unit
        onto unit-free rows, so `rbc 0.50 10^12/L` is stored and now reads as
        perfectly CANONICAL — compatible, convertible 1:1, and then `critical`
        against critical_low=2.5. The domain layer calls 0.50 physiologically
        impossible for a red cell count; every read path must agree.

    Existed as four divergent copies before this helper; they had already drifted
    on value-None handling, alias resolution and plausibility — which is the same
    class of drift that produced the two-screens-disagree bug in the first place.
    """
    from app.domain.lab_interpreter import _ALIAS_INDEX, classify_value, normalize_biomarker

    if not canonical:
        return None
    key = normalize_biomarker(canonical) or canonical.strip().lower()
    if key not in ALLOWED_UNITS:
        return None
    if value is None or is_unsafe_pair(key, unit):
        return ("unknown", None)
    converted = to_canonical_unit(key, value, unit)
    if converted is None:
        return ("unknown", None)
    canonical_value = converted[0]

    spec = _ALIAS_INDEX.get(key)
    if spec is not None:
        if spec.physiological_min is not None and canonical_value < spec.physiological_min:
            return ("unknown", canonical_value)
        if spec.physiological_max is not None and canonical_value > spec.physiological_max:
            return ("unknown", canonical_value)

    status = classify_value(key, canonical_value)
    if status is None:
        return ("unknown", canonical_value)
    return (status.value, canonical_value)
