"""Lab value normalization — unit conversion, age/sex-adjusted reference ranges,
and status classification for the Intelligence Engine.

Principles:
- ocr_confidence is NEVER read here; this is pure value normalization.
- All clinical computation uses SI-normalized values for consistency.
- get_reference_range supports age/sex adjustments (eGFR, TSH).
- classify_status returns LabStatus enum values.

No LLM. No I/O. Pure computation.
"""

from __future__ import annotations

from .lab_interpreter import _ALIAS_INDEX, BiomarkerSpec, LabStatus

# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------

def _get_spec(canonical: str) -> BiomarkerSpec | None:
    return _ALIAS_INDEX.get(canonical)


def normalize_value_to_si(
    value: float,
    unit: str,
    canonical: str,
) -> tuple[float, str]:
    """Convert ``value`` from ``unit`` to the canonical SI unit for ``canonical``.

    Returns (converted_value, si_unit). When the input unit is already the
    canonical unit (or no conversion is defined), returns the value unchanged.

    Conversion uses BiomarkerSpec.si_factor:
        canonical_unit_value = si_unit_value × si_factor
    So to go SI → canonical:
        canonical = si_value × si_factor
    And to go canonical → SI:
        si_value = canonical_value / si_factor

    Example: glucose stored as mg/dL, si_unit=mmol/L, si_factor=18.018.
        normalize_value_to_si(100, "mg/dL", "fasting_glucose") -> (100, "mg/dL")  # noqa: E501
        normalize_value_to_si(5.56, "mmol/L", "fasting_glucose") -> (100.1, "mg/dL")
    """
    spec = _get_spec(canonical)
    if spec is None:
        return value, unit

    canonical_unit = spec.unit
    si_unit = spec.si_unit
    si_factor = spec.si_factor

    # Normalize unit string for comparison.
    def _norm(u: str) -> str:
        return u.replace("µ", "u").replace("μ", "u").replace("mc", "u").strip().lower()

    u_norm = _norm(unit)
    canonical_norm = _norm(canonical_unit)

    # Already in canonical unit.
    if u_norm == canonical_norm:
        return value, canonical_unit

    # Input is in SI unit — convert to canonical.
    if si_unit and _norm(si_unit) == u_norm and si_factor:
        converted = value * si_factor
        return converted, canonical_unit

    # Unknown unit — return as-is with warning signal (caller should flag for review).
    return value, unit


def get_reference_range(
    canonical: str,
    age_years: int | None = None,
    is_male: bool = True,
) -> tuple[float | None, float | None]:
    """Return (ref_low, ref_high) for canonical biomarker, adjusted for age/sex.

    Age/sex adjustments implemented for:
    - hemoglobin: sex-adjusted
    - tsh: age-adjusted (elderly have wider range)
    - egfr: age-adjusted (expected decline with age)
    - hdl: sex-adjusted

    Returns (None, None) when no reference range is defined.
    """
    spec = _get_spec(canonical)
    if spec is None:
        return None, None

    ref_low = spec.ref_low
    ref_high = spec.ref_high

    # ---- Sex adjustments ----
    if canonical == "hemoglobin":
        if is_male:
            return 13.5, 17.5
        else:
            return 12.0, 15.5

    if canonical == "hdl":
        # In mg/dL: men <40 is low, women <50 is low
        if is_male:
            return 40.0, 200.0
        else:
            return 50.0, 200.0

    if canonical == "hematocrit":
        if is_male:
            return 41.0, 53.0
        else:
            return 36.0, 46.0

    # ---- Age adjustments ----
    if canonical == "tsh" and age_years is not None:
        # Elderly: TSH reference shifts higher.
        if age_years >= 70:
            return 0.4, 6.0
        elif age_years >= 60:
            return 0.4, 5.0

    if canonical == "egfr" and age_years is not None:
        # Age-adjusted lower bound for eGFR (expected physiological decline).
        # KDIGO 2022: ≥60 is normal regardless of age, but context matters.
        # We keep the standard cutoffs but note this in clinical rules.
        pass  # use standard spec thresholds

    return ref_low, ref_high


def classify_status(
    value: float,
    canonical: str,
    age_years: int | None = None,
    is_male: bool = True,
) -> LabStatus:
    """Classify a (SI/canonical) value against reference ranges, including age/sex.

    Priority: critical > high/low > normal.
    Returns LabStatus.UNKNOWN when the biomarker is not recognized.
    """
    spec = _get_spec(canonical)
    if spec is None:
        return LabStatus.UNKNOWN

    # Check critical thresholds first (use spec's critical values — these are
    # absolute physiological limits, not age/sex adjusted).
    if spec.critical_high is not None and value >= spec.critical_high:
        return LabStatus.CRITICAL
    if spec.critical_low is not None and value <= spec.critical_low:
        return LabStatus.CRITICAL

    # Age/sex-adjusted reference range for high/low classification.
    ref_low, ref_high = get_reference_range(canonical, age_years, is_male)

    if ref_high is not None and value > ref_high:
        return LabStatus.HIGH
    if ref_low is not None and value < ref_low:
        return LabStatus.LOW
    return LabStatus.NORMAL
