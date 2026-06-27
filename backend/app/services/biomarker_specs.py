"""
Physiological plausibility specs per biomarker.
Used for write-time guardrails — NOT for clinical classification (that is clinical_rules.py
/ lab_normalization.py / lab_interpreter.py).

These bounds are LOOSE (max/min a living human can have), not reference ranges.
They are intentionally wide so we only flag clear impossibilities or unit mismatches.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Biomarker plausibility table
# ---------------------------------------------------------------------------
# Keys should match canonical names in lab_interpreter.BIOMARKERS.
# si_unit / alt_unit must match normalized forms used in lab_normalization.
#
# For each biomarker:
#   si_unit      — the canonical unit the app stores in (from BiomarkerSpec.unit)
#   alt_unit     — the SI/alternative unit (from BiomarkerSpec.si_unit); may equal si_unit
#   si_max/min   — absolute physiological bounds in the canonical (stored) unit
#   alt_max/min  — absolute physiological bounds in the alternative SI unit
#
# Convention: "si_unit" here means the unit in which values are STORED
# (which may be mg/dL, not mmol/L — see lab_interpreter.py BiomarkerSpec.unit).
# "alt_unit" is the SI alternative (mmol/L for lipids, µmol/L for creatinine).
# ---------------------------------------------------------------------------

BIOMARKER_PLAUSIBILITY: dict[str, dict] = {
    # ---- Renal ----
    "creatinine": {
        # Stored in mg/dL (BiomarkerSpec.unit = "mg/dL"), alt SI = µmol/L
        "si_unit": "mg/dL",
        "alt_unit": "µmol/L",
        "si_max_plausible": 30.0,      # mg/dL — critically high but documented
        "si_min_plausible": 0.1,       # mg/dL
        "alt_max_plausible": 2650.0,   # µmol/L
        "alt_min_plausible": 9.0,      # µmol/L
    },
    # ---- Glucose ----
    "fasting_glucose": {
        # Stored in mg/dL
        "si_unit": "mg/dL",
        "alt_unit": "mmol/L",
        "si_max_plausible": 1500.0,
        "si_min_plausible": 20.0,
        "alt_max_plausible": 83.3,
        "alt_min_plausible": 1.1,
    },
    "postprandial_glucose": {
        "si_unit": "mg/dL",
        "alt_unit": "mmol/L",
        "si_max_plausible": 1500.0,
        "si_min_plausible": 20.0,
        "alt_max_plausible": 83.3,
        "alt_min_plausible": 1.1,
    },
    # ---- Lipids ----
    "total_cholesterol": {
        "si_unit": "mg/dL",
        "alt_unit": "mmol/L",
        "si_max_plausible": 1000.0,
        "si_min_plausible": 50.0,
        "alt_max_plausible": 25.8,
        "alt_min_plausible": 1.3,
    },
    "ldl": {
        "si_unit": "mg/dL",
        "alt_unit": "mmol/L",
        "si_max_plausible": 800.0,
        "si_min_plausible": 0.0,
        "alt_max_plausible": 20.7,
        "alt_min_plausible": 0.0,
    },
    "hdl": {
        "si_unit": "mg/dL",
        "alt_unit": "mmol/L",
        "si_max_plausible": 200.0,
        "si_min_plausible": 5.0,
        "alt_max_plausible": 5.2,
        "alt_min_plausible": 0.1,
    },
    "triglyceride": {
        "si_unit": "mg/dL",
        "alt_unit": "mmol/L",
        "si_max_plausible": 10000.0,
        "si_min_plausible": 10.0,
        "alt_max_plausible": 113.0,
        "alt_min_plausible": 0.1,
    },
    # ---- Liver enzymes (U/L only) ----
    "alt": {
        "si_unit": "U/L",
        "alt_unit": "U/L",
        "si_max_plausible": 15000.0,
        "si_min_plausible": 0.0,
    },
    "ast": {
        "si_unit": "U/L",
        "alt_unit": "U/L",
        "si_max_plausible": 15000.0,
        "si_min_plausible": 0.0,
    },
    "ggt": {
        "si_unit": "U/L",
        "alt_unit": "U/L",
        "si_max_plausible": 5000.0,
        "si_min_plausible": 0.0,
    },
    # ---- HbA1c ----
    "hba1c": {
        "si_unit": "%",
        "alt_unit": "%",
        "si_max_plausible": 20.0,
        "si_min_plausible": 2.0,
    },
    # ---- Uric acid ----
    "uric_acid": {
        # If this biomarker appears; stored in mg/dL
        "si_unit": "mg/dL",
        "alt_unit": "µmol/L",
        "si_max_plausible": 33.0,
        "si_min_plausible": 0.5,
        "alt_max_plausible": 2000.0,
        "alt_min_plausible": 30.0,
    },
    # ---- Urea / BUN ----
    "urea": {
        # Stored in mg/dL
        "si_unit": "mg/dL",
        "alt_unit": "mmol/L",
        "si_max_plausible": 1000.0,
        "si_min_plausible": 1.0,
        "alt_max_plausible": 166.5,
        "alt_min_plausible": 0.2,
    },
    # ---- CBC ----
    "hemoglobin": {
        "si_unit": "g/dL",
        "alt_unit": "g/dL",
        "si_max_plausible": 25.0,
        "si_min_plausible": 1.0,
    },
    "wbc": {
        "si_unit": "10^9/L",
        "alt_unit": "10^9/L",
        "si_max_plausible": 500.0,
        "si_min_plausible": 0.0,
    },
    "platelet": {
        "si_unit": "10^9/L",
        "alt_unit": "10^9/L",
        "si_max_plausible": 3000.0,
        "si_min_plausible": 0.0,
    },
    "rbc": {
        "si_unit": "10^12/L",
        "alt_unit": "10^12/L",
        "si_max_plausible": 10.0,
        "si_min_plausible": 0.5,
    },
    "hematocrit": {
        "si_unit": "%",
        "alt_unit": "%",
        "si_max_plausible": 75.0,
        "si_min_plausible": 5.0,
    },
    # ---- Electrolytes ----
    "sodium": {
        "si_unit": "mmol/L",
        "alt_unit": "mmol/L",
        "si_max_plausible": 200.0,
        "si_min_plausible": 100.0,
    },
    "potassium": {
        "si_unit": "mmol/L",
        "alt_unit": "mmol/L",
        "si_max_plausible": 10.0,
        "si_min_plausible": 1.0,
    },
}


# ---------------------------------------------------------------------------
# Plausibility check function
# ---------------------------------------------------------------------------

def _norm_unit(u: str) -> str:
    """Normalize unit string for comparison (handle micro-sign variants)."""
    return (
        u.replace("µ", "u")
        .replace("μ", "u")
        .replace("mc", "u")
        .strip()
        .lower()
    )


def check_plausibility(biomarker_name: str, value: float, unit: str) -> dict:
    """
    Check whether (value, unit) is physiologically plausible for biomarker_name.

    Returns:
        {
            "plausible":  bool,   # True when value fits the claimed unit
            "suspicious": bool,   # True when value fits the OTHER unit better
            "reason":     str,    # human-readable explanation
        }

    Rules:
    - If biomarker not in BIOMARKER_PLAUSIBILITY → plausible=True (unknown — skip)
    - If value is within [min, max] for the claimed unit → plausible=True
    - If value is outside claimed-unit range but within other-unit range → suspicious
    - If value is outside all known ranges → plausible=False, suspicious=False
    """
    spec = BIOMARKER_PLAUSIBILITY.get(biomarker_name)
    if spec is None:
        return {
            "plausible": True,
            "suspicious": False,
            "reason": "unknown biomarker — not validated",
        }

    claimed_norm = _norm_unit(unit)
    si_norm = _norm_unit(spec["si_unit"])
    alt_norm = _norm_unit(spec.get("alt_unit", spec["si_unit"]))

    # Determine which set of bounds to use for the claimed unit.
    if claimed_norm == si_norm:
        max_key, min_key = "si_max_plausible", "si_min_plausible"
        other_max_key, other_min_key = "alt_max_plausible", "alt_min_plausible"
        other_unit_label = spec.get("alt_unit", spec["si_unit"])
    elif claimed_norm == alt_norm:
        max_key, min_key = "alt_max_plausible", "alt_min_plausible"
        other_max_key, other_min_key = "si_max_plausible", "si_min_plausible"
        other_unit_label = spec["si_unit"]
    else:
        # Unit is neither canonical nor alt — try si bounds as a best-effort.
        max_key, min_key = "si_max_plausible", "si_min_plausible"
        other_max_key, other_min_key = "alt_max_plausible", "alt_min_plausible"
        other_unit_label = spec.get("alt_unit", spec["si_unit"])

    claimed_max = spec.get(max_key, float("inf"))
    claimed_min = spec.get(min_key, 0.0)
    other_max = spec.get(other_max_key, float("inf"))
    other_min = spec.get(other_min_key, 0.0)

    # Treat si_unit == alt_unit (e.g. U/L enzymes) as a single-unit biomarker.
    single_unit = si_norm == alt_norm

    plausible_for_claimed = claimed_min <= value <= claimed_max
    plausible_for_other = other_min <= value <= other_max

    if plausible_for_claimed:
        return {"plausible": True, "suspicious": False, "reason": "OK"}

    if not single_unit and plausible_for_other:
        return {
            "plausible": False,
            "suspicious": True,
            "reason": (
                f"Value {value} implausible for {unit} "
                f"but plausible for {other_unit_label} — possible unit mismatch"
            ),
        }

    return {
        "plausible": False,
        "suspicious": False,
        "reason": (
            f"Value {value} {unit} is implausible for {biomarker_name} in any known unit"
        ),
    }
