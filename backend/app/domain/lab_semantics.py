"""Unified LabResult/HealthMetric semantic resolution.

The ONE place that decides display name, reference range (with provenance),
status, and severity for a canonical analyte + value + unit. Before this
existed, `LabResultOut._populate_clinical_message` (schemas/lab.py) and
`MetricOut._populate_clinical_message` (schemas/health.py) carried two
near-identical, independently-maintained copies of the same
guard → normalize → classify → message pipeline — plus a third
(`clinical_insight._status`) and a fourth (`builder._ctx_guarded_status`)
wrapping the same primitives differently. Four call sites computing "is this
value concerning" independently is exactly the class of defect #153/#154
were filed over (one stored value, two screens, two confident and
contradictory severities) — this module exists so there is only one answer.

Status/severity are ALWAYS computed against the canonical registry's
reference bounds (`lab_interpreter.BiomarkerSpec`/`analyte_units`), never
against whatever reference range was chosen for DISPLAY. A patient may pick
which printed range to show next to their result (source report vs
canonical fallback) — that is a display preference, not a clinical input,
and must never change what severity a value is classified as.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ReferenceSource(StrEnum):
    """Where the DISPLAYED reference range came from. Never influences status."""

    SOURCE_REPORT = "source_report"
    VALIDATED_LAB_RANGE = "validated_lab_range"
    CANONICAL_FALLBACK = "canonical_fallback"
    UNAVAILABLE = "unavailable"


class InterpretationState(StrEnum):
    CONFIRMED = "confirmed"
    NEEDS_REVIEW = "needs_review"


#: Bumped whenever the resolution algorithm changes in a way that could shift
#: an existing result's status/severity — stored alongside a resolved value so
#: a historical discrepancy can be traced to the rule set that produced it.
RULE_VERSION = "lab-semantics-1.0.0"


@dataclass(frozen=True)
class LabSemantics:
    canonical_analyte: str
    display_name: str
    normalized_value: float | None
    normalized_unit: str | None
    # Reference range for DISPLAY only — see ReferenceSource. Never the basis
    # for `status`/`severity`.
    reference_low: float | None
    reference_high: float | None
    reference_unit: str | None
    reference_display: str | None
    reference_source: str
    # Clinical classification — always computed against the canonical
    # registry, regardless of reference_source.
    status: str
    severity: str
    interpretation_state: str
    needs_review: bool
    clinical_message: str | None
    rule_version: str = RULE_VERSION


def _display_name(canonical: str) -> str:
    """Centralized analyte display name. The catalog's `name_vn` is the one
    authoritative source — no caller may hand-maintain its own label table."""
    from app.domain.lab_catalog import get_catalog

    try:
        entry = get_catalog()["biomarkers"].get(canonical)
    except Exception:  # noqa: BLE001 — display name must never crash resolution
        entry = None
    if entry and entry.get("name_vn"):
        return entry["name_vn"]
    return canonical


def _reference_display(low: float | None, high: float | None, unit: str | None) -> str | None:
    if low is None or high is None:
        return None
    lo = int(low) if low == int(low) else low
    hi = int(high) if high == int(high) else high
    return f"{lo}–{hi} {unit}" if unit else f"{lo}–{hi}"


def resolve_lab_semantics(
    canonical: str | None,
    value: float | None,
    unit: str | None,
    *,
    printed_reference_text: str | None = None,
    printed_reference_unit: str | None = None,
    normalized_value_si: float | None = None,
    normalized_unit_si: str | None = None,
) -> LabSemantics | None:
    """Resolve the full semantic tuple for one (analyte, value, unit) reading.

    Returns None when `canonical` is falsy/unrecognised — callers keep their
    existing fallback in that case (unknown biomarkers are out of scope here,
    same as the call sites this replaces).

    `printed_reference_text` is whatever range string the caller wants shown
    (already resolved from whichever source the patient/UI selected — this
    function does not adjudicate that choice). When present it is trusted
    for `reference_display`/`reference_source=SOURCE_REPORT`, converted to the
    analyte's canonical unit first if `printed_reference_unit` names a
    different unit (a guarded analyte's printed range is otherwise displayed
    unconverted next to a converted value — the same one-row-two-claims
    hazard #155 closed for the OCR extraction layer). When absent, the
    canonical registry's own bounds are used as `reference_source=
    CANONICAL_FALLBACK`.
    """
    from app.domain.analyte_units import (
        NEEDS_REVIEW_MESSAGE,
        guarded_status,
        to_canonical_range,
    )
    from app.domain.lab_interpreter import _ALIAS_INDEX, classify_value
    from app.domain.lab_normalization import is_unit_convertible, normalize_value_to_si
    from app.services.lab import get_clinical_message

    if not canonical:
        return None

    display_name = _display_name(canonical)

    # ── P0 guard first: an analyte/unit pair from different dimensions
    # (rbc + L/L) must never yield a severity, on any surface. ─────────────
    guarded = guarded_status(canonical, value, unit)
    if guarded is not None:
        status, guarded_value = guarded
        if status == "unknown":
            return LabSemantics(
                canonical_analyte=canonical,
                display_name=display_name,
                normalized_value=guarded_value if guarded_value is not None else value,
                normalized_unit=unit,
                reference_low=None,
                reference_high=None,
                reference_unit=None,
                reference_display=None,
                reference_source=ReferenceSource.UNAVAILABLE.value,
                status="unknown",
                severity="unknown",
                interpretation_state=InterpretationState.NEEDS_REVIEW.value,
                needs_review=True,
                clinical_message=NEEDS_REVIEW_MESSAGE,
            )
        spec = _ALIAS_INDEX.get(canonical)
        ref_low = spec.ref_low if spec else None
        ref_high = spec.ref_high if spec else None
        ref_unit = spec.unit if spec else unit
        if printed_reference_text:
            reference_display = (
                to_canonical_range(canonical, printed_reference_text, printed_reference_unit)
                if printed_reference_unit
                else printed_reference_text
            )
            reference_source = ReferenceSource.SOURCE_REPORT.value
        else:
            reference_display = _reference_display(ref_low, ref_high, ref_unit)
            reference_source = (
                ReferenceSource.CANONICAL_FALLBACK.value
                if reference_display
                else ReferenceSource.UNAVAILABLE.value
            )
        return LabSemantics(
            canonical_analyte=canonical,
            display_name=display_name,
            normalized_value=guarded_value,
            normalized_unit=ref_unit,
            reference_low=ref_low,
            reference_high=ref_high,
            reference_unit=ref_unit,
            reference_display=reference_display,
            reference_source=reference_source,
            status=status,
            severity=status,
            interpretation_state=InterpretationState.CONFIRMED.value,
            needs_review=False,
            clinical_message=get_clinical_message(canonical, status),
        )

    # ── Not a guarded (CBC-dimensional) analyte — the general path. ───────
    spec = _ALIAS_INDEX.get(canonical)
    if spec is None:
        return None

    # Atomic SI pair: normalized_value_si/normalized_unit_si must both be
    # present together, or not at all — pairing a value written by one path
    # with a unit written by a different one (e.g. a backfill that set the
    # value but left the unit NULL) computes a nonsense magnitude. Same
    # all-or-nothing requirement `_promote_row` already enforces at write time.
    if normalized_value_si is not None and normalized_unit_si is not None:
        raw_value = normalized_value_si
        raw_unit = normalized_unit_si
    else:
        raw_value = value
        raw_unit = unit or ""
    if raw_value is None:
        return None

    # Glucose-specific recovery: no human survives fasting glucose < 30 mg/dL
    # without emergency care, so a glucose value this small with a missing/
    # unrecognised unit MUST be mmol/L from an OCR path that dropped the unit
    # string, not a genuine mg/dL reading. MetricOut carried this heuristic
    # alone before consolidation; LabResultOut gains the same recovery here
    # rather than losing coverage in the merge.
    if canonical in ("fasting_glucose", "postprandial_glucose"):
        unit_clean = raw_unit.strip().lower().replace(" ", "")
        if unit_clean not in ("mg/dl", "mmol/l", "mmol") and raw_value < 30:
            raw_unit = "mmol/L"

    # Physiological-plausibility heuristic: a value that cannot be expressed
    # in the canonical unit must have been stored in the SI unit instead
    # (legacy rows promoted before a unit-normalization fix). Same heuristic
    # LabResultOut/MetricOut each carried independently.
    if spec.si_unit and spec.physiological_max is not None:
        unit_norm = raw_unit.strip().lower().replace("µ", "u").replace("μ", "u")
        canonical_norm = spec.unit.strip().lower().replace("µ", "u").replace("μ", "u")
        if unit_norm != canonical_norm and raw_value > spec.physiological_max:
            raw_unit = spec.si_unit

    # Fail closed on an unrecognised/unconvertible unit. normalize_value_to_si
    # passes an unrecognised unit through unchanged and classify_value ignores
    # the unit entirely — so an unconvertible unit must never reach
    # classification, or a value with the wrong (or missing) unit silently
    # gets compared against the wrong-dimension thresholds and reads as a
    # confident, wrong severity. This is the read-path counterpart to
    # lab_normalization.is_unit_convertible, already enforced at write time.
    if not is_unit_convertible(canonical, raw_unit):
        return LabSemantics(
            canonical_analyte=canonical,
            display_name=display_name,
            normalized_value=raw_value,
            normalized_unit=raw_unit or None,
            reference_low=spec.ref_low,
            reference_high=spec.ref_high,
            reference_unit=spec.unit,
            reference_display=None,
            reference_source=ReferenceSource.UNAVAILABLE.value,
            status="unknown",
            severity="unknown",
            interpretation_state=InterpretationState.NEEDS_REVIEW.value,
            needs_review=True,
            clinical_message=None,
        )

    normalized_value, normalized_unit = normalize_value_to_si(raw_value, raw_unit, canonical)
    status_enum = classify_value(canonical, normalized_value)
    status = status_enum.value if status_enum is not None else "unknown"

    if printed_reference_text:
        reference_display = printed_reference_text
        reference_source = ReferenceSource.SOURCE_REPORT.value
    else:
        reference_display = _reference_display(spec.ref_low, spec.ref_high, spec.unit)
        reference_source = (
            ReferenceSource.CANONICAL_FALLBACK.value
            if reference_display
            else ReferenceSource.UNAVAILABLE.value
        )

    if status == "unknown":
        return LabSemantics(
            canonical_analyte=canonical,
            display_name=display_name,
            normalized_value=normalized_value,
            normalized_unit=normalized_unit,
            reference_low=spec.ref_low,
            reference_high=spec.ref_high,
            reference_unit=spec.unit,
            reference_display=reference_display,
            reference_source=reference_source,
            status="unknown",
            severity="unknown",
            interpretation_state=InterpretationState.NEEDS_REVIEW.value,
            needs_review=True,
            clinical_message=None,
        )

    return LabSemantics(
        canonical_analyte=canonical,
        display_name=display_name,
        normalized_value=normalized_value,
        normalized_unit=normalized_unit,
        reference_low=spec.ref_low,
        reference_high=spec.ref_high,
        reference_unit=spec.unit,
        reference_display=reference_display,
        reference_source=reference_source,
        status=status,
        severity=status,
        interpretation_state=InterpretationState.CONFIRMED.value,
        needs_review=False,
        clinical_message=get_clinical_message(canonical, status),
    )
