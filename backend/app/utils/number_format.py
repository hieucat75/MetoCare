"""number_format.py — Shared lab/metric number formatter for Metocare backend.

Mirrors the frontend ``formatLabValue`` logic so that AI narrative prompts,
report generation, and any server-side text rendering produce consistent,
clean numbers instead of raw floating-point artefacts like ``174.48289999999997``.

Formatting rules (same as frontend):

+---------------------+-------------------------------+----------+
| Unit / type         | Rule                          | Example  |
+=====================+===============================+==========+
| mg/dL               | Integer (round)               | 174      |
| mmol/L              | 1 decimal                     | 5.6      |
| %                   | 1 decimal                     | 6.1      |
| BMI (kg/m²)         | 1 decimal                     | 22.4     |
| BP (mmHg)           | Integer                       | 120      |
| eGFR (mL/min)       | Integer                       | 89       |
| µmol/L              | Integer                       | 45       |
| g/dL                | ≤2 decimals, zeros trimmed    | 14.5     |
| IU/L                | Integer                       | 32       |
| mIU/L               | 1 decimal                     | 2.5      |
| Default (unknown)   | 2 decimals, trailing-zero trim| 1.23     |
+---------------------+-------------------------------+----------+

Usage::

    from app.utils.number_format import format_lab_value, format_lab_display

    text = format_lab_value(174.48289999999997, "mg/dL")  # "174"
    display = format_lab_display(5.7321, "mmol/L")        # "5.7 mmol/L"
"""

from __future__ import annotations

import math
import re

# ── Sentinel ──────────────────────────────────────────────────────────────────

_MISSING = "—"

# Hard cap on decimal places for any surfaced value (unit rules are the max
# precision; this is the absolute ceiling). Keeps AI/UI numbers clean.
_MAX_DECIMALS = 2

# ── Unit rule table ───────────────────────────────────────────────────────────
# Each entry is (compiled_regex, decimal_places).
# First match wins. All patterns are case-insensitive (re.IGNORECASE).

_UNIT_RULES: list[tuple[re.Pattern[str], int]] = [
    # ── 0 decimals (integer) ─────────────────────────────────────────────────
    (re.compile(r"mg/dl", re.IGNORECASE), 0),                      # mg/dL
    (re.compile(r"[µμu]mol/l", re.IGNORECASE), 0),                 # µmol/L / umol/L
    (re.compile(r"mmhg", re.IGNORECASE), 0),                       # mmHg
    (re.compile(r"\bbpm\b|beats?/min", re.IGNORECASE), 0),         # bpm / heart rate
    (re.compile(r"\bu/l\b|\biu/l\b", re.IGNORECASE), 0),          # IU/L, U/L
    (re.compile(r"ml/min", re.IGNORECASE), 0),                     # mL/min (eGFR)
    (re.compile(r"/[µμu]l\b", re.IGNORECASE), 0),                  # cells/µL
    (re.compile(r"^cm$", re.IGNORECASE), 0),                       # cm (height, waist)
    # ── 2 decimals ───────────────────────────────────────────────────────────
    (re.compile(r"g/dl", re.IGNORECASE), 2),                       # g/dL (haemoglobin)
    # ── 1 decimal ────────────────────────────────────────────────────────────
    (re.compile(r"mmol/l", re.IGNORECASE), 1),                     # mmol/L
    (re.compile(r"%", re.IGNORECASE), 1),                          # percentage
    (re.compile(r"kg/m[²2]", re.IGNORECASE), 1),                   # BMI
    (re.compile(r"°[cf]|celsius|fahrenheit", re.IGNORECASE), 1),   # temperature
    (re.compile(r"^kg$", re.IGNORECASE), 1),                       # weight kg
    (re.compile(r"g/l", re.IGNORECASE), 1),                        # g/L
    (re.compile(r"t/l", re.IGNORECASE), 1),                        # T/L (RBC)
    (re.compile(r"meq/l", re.IGNORECASE), 1),                      # mEq/L
    (re.compile(r"pmol/l", re.IGNORECASE), 1),                     # pmol/L
    (re.compile(r"nmol/l", re.IGNORECASE), 1),                     # nmol/L
    (re.compile(r"miu/(l|ml)", re.IGNORECASE), 1),                 # mIU/L, mIU/mL
    (re.compile(r"iu/ml\b", re.IGNORECASE), 1),                    # IU/mL
]


def _resolve_decimals(unit: str, value: float) -> int:
    """Return the number of decimal places for *unit*.

    Falls back to a magnitude heuristic when no unit rule matches:

    * Already an integer → 0
    * |value| ≥ 10      → 1
    * Otherwise         → 2  (unknown small float)
    """
    trimmed = unit.strip()
    for pattern, decimals in _UNIT_RULES:
        if pattern.search(trimmed):
            return decimals
    # Heuristic for unknown units
    if value == int(value):  # integer check
        return 0
    return 1 if abs(value) >= 10 else 2


def format_lab_value(
    value: float | int | str | None,
    unit: str | None = None,
) -> str:
    """Format a lab or metric value according to *unit*.

    Parameters
    ----------
    value:
        Numeric value. ``None`` or ``float('nan')`` / ``float('inf')``
        returns the missing sentinel ``"—"``.
        A ``str`` input is tried as a float first; non-numeric strings
        (e.g. ``"<5"``, ``"negative"``) are returned unchanged so that
        OCR literals pass through.
    unit:
        Unit string (case-insensitive, whitespace trimmed).
        ``None`` / empty → heuristic fallback.

    Returns
    -------
    str
        Formatted number (e.g. ``"174"``, ``"5.6"``, ``"14.5"``) or
        ``"—"`` for missing / invalid values. Trailing zeros are trimmed
        and precision is capped at 2 decimals, so no raw IEEE float
        artifact ever reaches a user/AI surface.

    Examples
    --------
    >>> format_lab_value(174.48289999999997, "mg/dL")
    '174'
    >>> format_lab_value(5.7321, "mmol/L")
    '5.7'
    >>> format_lab_value(14.50, "g/dL")
    '14.5'
    >>> format_lab_value(88.0, "µmol/L")
    '88'
    >>> format_lab_value(0.9916099999999999, "mg/dL")
    '1'
    >>> format_lab_value(None, "mg/dL")
    '—'
    >>> format_lab_value("<5", "µmol/L")
    '<5'
    """
    if value is None:
        return _MISSING

    # String input: try numeric parse; pass through non-numeric literals
    if isinstance(value, str):
        try:
            parsed = float(value)
        except (ValueError, TypeError):
            return value  # e.g. "<5", "negative"
        return format_lab_value(parsed, unit)

    # Guard: NaN / infinite
    if not math.isfinite(value):
        return _MISSING

    decimals: int
    if unit:
        decimals = _resolve_decimals(unit, value)
    else:
        decimals = 0 if value == int(value) else 1

    # P0 clinical-integrity: cap precision at 2 decimals (unit rule is the *max*)
    # and strip insignificant trailing zeros so no raw IEEE artifact
    # (e.g. 0.9916099999999999) or noisy "14.50"/"6.0" ever reaches a user/AI.
    decimals = min(decimals, _MAX_DECIMALS)
    formatted = f"{value:.{decimals}f}"
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    # Guard against "-0" from tiny negative rounding.
    if formatted in ("-0", ""):
        formatted = "0"
    return formatted


def format_lab_display(
    value: float | int | str | None,
    unit: str | None = None,
) -> str:
    """Format a lab value and append the unit string.

    Convenience wrapper around :func:`format_lab_value` for contexts
    where the unit should appear inline (e.g. ``"174 mg/dL"``).

    Parameters
    ----------
    value:
        Same as :func:`format_lab_value`.
    unit:
        Unit string. Appended after a space if non-empty.

    Returns
    -------
    str
        Combined string (e.g. ``"5.6 mmol/L"``) or ``"—"`` when the
        value is missing.

    Examples
    --------
    >>> format_lab_display(174.48289999999997, "mg/dL")
    '174 mg/dL'
    >>> format_lab_display(88.0, "µmol/L")
    '88 µmol/L'
    >>> format_lab_display(None, "mg/dL")
    '—'
    """
    formatted = format_lab_value(value, unit)
    if formatted == _MISSING:
        return _MISSING
    if not unit or not unit.strip():
        return formatted
    return f"{formatted} {unit.strip()}"
