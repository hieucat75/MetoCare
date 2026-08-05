"""Authoritative analyte-aware unit normalization for canonical lab values.

ONE service, used by every path that writes a canonical ``LabResult``. Before
this existed there were two behaviours and both were wrong:

- the MDI document path called ``is_unit_convertible`` and REFUSED anything that
  was not already the canonical or SI unit, so no CBC line off a typical
  Vietnamese report could ever be confirmed — platelet ``20 G/L``, WBC
  ``0.8 G/L``, haemoglobin ``70 g/L`` were all rejected;
- ``/lab-uploads`` and manual entry had no guard at all. ``normalize_value_to_si``
  returns the value UNCHANGED under its ORIGINAL unit when it knows no
  conversion, and ``classify_value`` ignores the unit — so a perfectly normal
  haemoglobin of ``140 g/L`` was stored as ``140`` and classified against the
  ``12.0–17.5 g/dL`` range as **critical**. A false critical on a healthy
  patient, and the refusal message on the other path ("vui lòng sửa đơn vị")
  invited the patient to retype ``g/L`` as ``g/dL`` without touching the number,
  which lands in exactly the same place.

So the same printed report produced a refusal on one path and a fabricated
critical on another. That is what "one authoritative service" is for.

CASE IS SEMANTIC, and it is the single most dangerous detail here
--------------------------------------------------------------
``G/L`` (capital G, "giga per litre") means ``10^9/L`` — a CELL COUNT.
``g/L``  (lowercase g, "grams per litre") is a MASS CONCENTRATION.

They differ by one character's case and are not interconvertible. Lower-casing
the unit string before comparison — which every other normalizer in this codebase
does — silently merges them. Haemoglobin ``140 g/L`` read as ``140 G/L`` (or the
reverse for a white-cell count) is a wrong-dimension value that still looks
plausible. Tokenization here therefore preserves the numerator's case and
lower-cases only the volume denominator.

Conversions are keyed by the ANALYTE'S CANONICAL UNIT, not by dimension alone.
That is what enforces "apply only to compatible analytes": haemoglobin's table
has no entry for a count unit, so a count unit is rejected for haemoglobin
rather than converted; a cell count's table has no entry for a mass unit.

Nothing here is silent. Every rejection names its reason, and every success
carries the factor, the rule version and the token it matched, so a stored value
can be re-derived from what was printed.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import asdict, dataclass, field

from .lab_interpreter import _ALIAS_INDEX, BiomarkerSpec

# Bumped whenever a factor or an accepted unit changes. Stored on every converted
# row so a value can be traced to the exact rule set that produced it — without
# it, a corrected factor makes historical rows silently unexplainable.
CONVERSION_RULE_VERSION = "lab-units-1.0.0"

# Specimens this registry is valid for. Every canonical in the biomarker table is
# a serum/whole-blood analyte, and nothing downstream carries a specimen, so a
# urine value converted with a serum factor and classified against a serum range
# is a wrong-analyte result (urine creatinine 50-200 mg/dL against a serum
# reference of 0.6-1.2). Non-blood specimens are refused outright, not converted.
BLOOD_SPECIMENS = frozenset({"blood", "serum", "plasma", "whole_blood", None})

_SPECIMEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("urine", re.compile(r"nieu|nuoc\s*tieu|urin|24\s*h|acr\b|upcr\b", re.I)),
    ("csf", re.compile(r"dich\s*nao\s*tuy|csf\b", re.I)),
)


# ── unit tokenization ───────────────────────────────────────────────────────

# Count prefixes. Uppercase ONLY — see the module docstring; `g` is mass.
_COUNT_PREFIX = {"G": "10^9", "T": "10^12", "M": "10^6", "K": "10^3"}

_SUPERSCRIPT = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")


def normalize_unit_token(unit: str | None) -> str:
    """Canonical token for a printed unit. Preserves the numerator's case.

    Handles the notation variants OCR actually produces: ``G/L``, ``G/l``,
    ``10^9/L``, ``10⁹/L``, ``x10^9/L``, ``×10^9/L``, ``10*9/L``, ``T/L``,
    ``10^12/L``, ``g/L``, ``g/dL``, plus stray spacing, non-breaking spaces and
    the micro-sign variants.

    Returns "" for an empty/unparseable unit — callers must treat that as a
    refusal, never as "assume canonical".
    """
    if not unit:
        return ""
    # NFKC folds the Unicode superscripts (10⁹ -> 10^9 after the translate below)
    # and normalizes the micro sign; do it before anything else.
    u = unicodedata.normalize("NFKC", str(unit)).translate(_SUPERSCRIPT)
    u = u.replace(" ", " ").replace("×", "x").replace("∗", "*")
    u = re.sub(r"\s+", "", u)
    if not u:
        return ""
    # "x10^9/L" / "*10^9/L" -> "10^9/L"
    u = re.sub(r"^[x*]+(?=10)", "", u)
    # "10*9/L" and "10e9/L" -> "10^9/L"
    u = re.sub(r"^10[*e](?=\d)", "10^", u)
    u = u.replace("µ", "u").replace("μ", "u")

    if "/" not in u:
        return u.lower()
    numerator, _, denominator = u.partition("/")
    # The volume is case-insensitive (L, l, dL, dl); the numerator is NOT.
    denominator = denominator.lower()
    # A bare uppercase count prefix expands to its power-of-ten form, so `G/L`
    # and `10^9/L` become the same token while `g/L` stays a mass unit.
    if numerator in _COUNT_PREFIX:
        numerator = _COUNT_PREFIX[numerator]
    elif numerator.lower().startswith("10^"):
        numerator = numerator.lower()
    else:
        numerator = numerator.lower()
        # NFKC folds a Unicode superscript to a plain digit, so "10⁹" arrives as
        # "109" with the exponent marker gone — indistinguishable from a literal
        # one-hundred-and-nine. Restore it: no real unit numerator is "10" followed
        # by digits except a power of ten.
        numerator = re.sub(r"^10(\d{1,2})$", r"10^\1", numerator)
    return f"{numerator}/{denominator}"


# ── conversions, keyed by the analyte's CANONICAL unit ──────────────────────
#
# {canonical_unit_token: {source_token: factor}}  such that
#     canonical_value = source_value * factor
#
# Keying on the canonical unit is what restricts a conversion to compatible
# analytes: an entry only applies to analytes whose canonical unit is that key.
_CONVERSIONS: dict[str, dict[str, float]] = {
    # Mass concentration. 1 g/dL = 10 g/L, so g/L -> g/dL is x0.1.
    # Haemoglobin is the analyte this exists for: VN reports print g/L
    # (140 g/L = 14.0 g/dL), the spec's canonical is g/dL.
    "g/dl": {"g/l": 0.1},
    "g/l": {"g/dl": 10.0},
    # Cell counts. G/L IS 10^9/L (identity, not a scaling) — the conversion here
    # is of NOTATION, which is why the factor is 1.0 and why getting the
    # tokenizer's case handling right matters more than the arithmetic.
    # WBC, absolute differentials and platelets are 10^9/L.
    "10^9/l": {"10^9/l": 1.0},
    # RBC is 10^12/L; T/L is the same quantity.
    "10^12/l": {"10^12/l": 1.0},
}

# Analytes whose canonical unit is a cell count, listed so a mass unit offered
# for them is rejected with a DIMENSION reason rather than a generic "unknown".
_COUNT_UNITS = frozenset({"10^3/l", "10^6/l", "10^9/l", "10^12/l"})
_MASS_UNITS = frozenset({"g/l", "g/dl", "mg/dl", "mg/l", "ug/dl", "ug/l"})


def _dimension_of(token: str) -> str | None:
    if token in _COUNT_UNITS:
        return "count_concentration"
    if token in _MASS_UNITS:
        return "mass_concentration"
    return None


# ── result type ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class UnitConversion:
    """Outcome of normalizing one printed value. Immutable.

    `ok=False` is a REFUSAL, never a pass-through: on failure `normalized_value`
    is None so a caller cannot accidentally store the unconverted number under a
    canonical unit — the exact failure this class exists to prevent.
    """

    ok: bool
    canonical: str | None
    original_value: float | None
    original_unit: str | None
    normalized_value: float | None = None
    canonical_unit: str | None = None
    factor: float | None = None
    matched_token: str | None = None
    specimen: str | None = None
    reason: str = ""
    rule_version: str = CONVERSION_RULE_VERSION
    detail: dict = field(default_factory=dict)

    def provenance(self) -> dict:
        """Flat, JSON-serializable record of how this value was derived."""
        return {k: v for k, v in asdict(self).items() if k != "detail"} | self.detail


def _fail(canonical, value, unit, reason, specimen=None, **detail) -> UnitConversion:
    return UnitConversion(
        ok=False,
        canonical=canonical,
        original_value=value,
        original_unit=unit,
        specimen=specimen,
        reason=reason,
        detail=detail,
    )


def detect_specimen(label: str | None) -> str | None:
    """Specimen implied by the printed label, or None for blood/unspecified.

    The label is accent-STRIPPED first. The patterns are written accent-free
    ("nieu"), and a Vietnamese report prints "niệu" — matching the raw string
    silently detected nothing, so every urine label sailed through as blood.
    That is the whole defect this function exists to stop, so it has to strip.
    """
    if not label:
        return None
    from app.services.lab_parser import _strip_accents

    normalized = _strip_accents(str(label).lower())
    for name, pattern in _SPECIMEN_PATTERNS:
        if pattern.search(normalized):
            return name
    return None


def _spec_for(canonical: str | None) -> BiomarkerSpec | None:
    return _ALIAS_INDEX.get(canonical) if canonical else None


def accepted_units(canonical: str) -> tuple[str, ...]:
    """Every unit token this analyte can be converted FROM. For UI and errors.

    Naming the acceptable units is the difference between a message a patient can
    act on and one that invites a dangerous edit: "sửa đơn vị" led to retyping
    g/L as g/dL without converting the number, which produced the same wrong
    value the refusal was meant to stop.
    """
    spec = _spec_for(canonical)
    if spec is None:
        return ()
    canonical_token = normalize_unit_token(spec.unit)
    tokens = {canonical_token}
    if spec.si_unit:
        tokens.add(normalize_unit_token(spec.si_unit))
    tokens.update(_CONVERSIONS.get(canonical_token, {}))
    return tuple(sorted(t for t in tokens if t))


def convert_to_canonical(
    canonical: str | None,
    value: float | int | None,
    unit: str | None,
    *,
    label: str | None = None,
    specimen: str | None = None,
    assume_canonical_when_missing: bool = False,
) -> UnitConversion:
    """Normalize one printed value to its analyte's canonical unit.

    The full pipeline, in order, refusing rather than guessing at every step:
      1. analyte resolved (caller supplies the canonical; ambiguity is refused)
      2. specimen resolved and required to be blood/serum
      3. unit NOTATION normalized (no arithmetic yet)
      4. analyte/unit compatibility validated by DIMENSION
      5. an explicit, analyte-scoped factor applied
      6/7. original value and unit preserved by the caller; the normalized value
           is returned separately and never overwrites them
      10. provenance and rule version recorded on the result

    Steps 8 and 9 (reference range in the normalized domain, classify only after
    a successful conversion) belong to the caller and are enforced by
    `lab.normalize_and_classify`, which refuses to classify a failed conversion.
    """
    if canonical is None:
        return _fail(None, value, unit, "ambiguous_analyte")

    spec = _spec_for(canonical)
    if spec is None:
        # No canonical thresholds exist, so nothing can be misclassified. The
        # original is preserved verbatim and no conversion is claimed.
        return UnitConversion(
            ok=True,
            canonical=canonical,
            original_value=float(value) if value is not None else None,
            original_unit=unit,
            normalized_value=float(value) if value is not None else None,
            canonical_unit=unit,
            factor=1.0,
            matched_token=normalize_unit_token(unit),
            specimen=specimen,
            reason="no_spec_no_thresholds",
        )

    if value is None:
        return _fail(canonical, value, unit, "missing_value")
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return _fail(canonical, value, unit, "non_numeric_value")
    if not math.isfinite(numeric):
        return _fail(canonical, value, unit, "non_finite_value")

    resolved_specimen = specimen or detect_specimen(label)
    if resolved_specimen not in BLOOD_SPECIMENS:
        # A serum factor and a serum reference range applied to a urine value is
        # a wrong-analyte result, not merely an imprecise one.
        return _fail(
            canonical, numeric, unit, "specimen_mismatch",
            specimen=resolved_specimen, expected_specimen="blood/serum",
        )

    token = normalize_unit_token(unit)
    if not token:
        # A missing unit means two different things and they must not be merged.
        #
        # On a DOCUMENT path it means the printed unit was not read — the value
        # could be in any domain, so refusing is the only safe answer.
        #
        # On MANUAL ENTRY there is no printed unit to read: the patient typed a
        # number into a field the UI labels with the canonical unit, so the
        # canonical unit is the stated contract of that form, not a guess.
        # Refusing there would reject the primary manual-entry flow outright.
        #
        # The assumption is opt-in per caller and recorded in provenance, so a
        # value entered this way is never indistinguishable from one whose unit
        # was actually read.
        if not assume_canonical_when_missing:
            return _fail(
                canonical, numeric, unit, "missing_unit",
                specimen=resolved_specimen, accepted=list(accepted_units(canonical)),
            )
        token = normalize_unit_token(spec.unit)

    canonical_token = normalize_unit_token(spec.unit)
    si_token = normalize_unit_token(spec.si_unit) if spec.si_unit else None

    assumed = not normalize_unit_token(unit) and assume_canonical_when_missing
    if token == canonical_token:
        factor = 1.0
    elif token in _CONVERSIONS.get(canonical_token, {}):
        factor = _CONVERSIONS[canonical_token][token]
    elif si_token and token == si_token and spec.si_factor:
        # Analyte-SPECIFIC molar conversion (mmol/L <-> mg/dL). It depends on the
        # substance's molar mass, so it lives on the spec, not in a generic table.
        factor = float(spec.si_factor)
    else:
        want = _dimension_of(canonical_token)
        got = _dimension_of(token)
        if want and got and want != got:
            # The named case: a count unit offered for haemoglobin, or a mass
            # unit for a cell count. Both are plausible-looking OCR outcomes.
            return _fail(
                canonical, numeric, unit, "dimension_mismatch",
                specimen=resolved_specimen, expected_dimension=want,
                got_dimension=got, accepted=list(accepted_units(canonical)),
            )
        return _fail(
            canonical, numeric, unit, "unknown_conversion",
            specimen=resolved_specimen, token=token,
            accepted=list(accepted_units(canonical)),
        )

    converted = numeric * factor
    if not math.isfinite(converted):
        return _fail(
            canonical, numeric, unit, "conversion_overflow",
            specimen=resolved_specimen, factor=factor,
        )

    # Physiological bounds are checked AFTER conversion, in the canonical domain
    # — that is the only domain the bounds are expressed in. This is what catches
    # a right-dimension-but-wrong-magnitude unit (RBC printed in G/L rather than
    # T/L would arrive 1000x low).
    lo = getattr(spec, "physiological_min", None)
    hi = getattr(spec, "physiological_max", None)
    if (lo is not None and converted < lo) or (hi is not None and converted > hi):
        return _fail(
            canonical, numeric, unit, "impossible_converted_value",
            specimen=resolved_specimen, converted=converted,
            canonical_unit=spec.unit, physiological_min=lo, physiological_max=hi,
        )

    return UnitConversion(
        ok=True,
        canonical=canonical,
        original_value=numeric,
        original_unit=unit,
        normalized_value=converted,
        canonical_unit=spec.unit,
        factor=factor,
        matched_token=token,
        specimen=resolved_specimen,
        reason="converted",
        detail={"unit_assumed_canonical": True} if assumed else {},
    )


def convert_reference_range(
    canonical: str | None, low, high, unit: str | None
) -> tuple[float | None, float | None, bool]:
    """Convert a PRINTED reference range into the canonical unit.

    Returns (low, high, ok). A range must live in the same unit domain as the
    value it bounds: comparing a value normalized to g/dL against a range still
    printed in g/L inverts the interpretation entirely. On failure the caller
    must fall back to the analyte's own canonical range, never to the printed
    numbers.
    """
    if canonical is None or (low is None and high is None):
        return None, None, False
    out: list[float | None] = []
    for bound in (low, high):
        if bound is None:
            out.append(None)
            continue
        result = convert_to_canonical(canonical, bound, unit, specimen="blood")
        if not result.ok:
            return None, None, False
        out.append(result.normalized_value)
    return out[0], out[1], True
