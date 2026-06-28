"""Derived Metrics Engine — registry of computed biomarkers.

All formulas are evidence-based and transparent. Each metric:
- Returns None result (not error) when inputs are insufficient.
- Lists missing_inputs so the caller knows what's needed.
- Includes a human-readable formula string and Vietnamese note.
- Never raises on missing data — graceful degradation only.

Clinical references:
- eGFR: CKD-EPI 2021 race-free equation (NEJM 2021)
- Friedewald LDL: Friedewald et al. (JAMA 1972) — valid only when TG < 4.5 mmol/L
- TyG Index: Simental-Mendía et al. (Eur J Clin Invest 2008)
- FIB-4: Sterling et al. (Hepatology 2006)
- Metabolic Syndrome: IDF/AHA 2009 harmonized criteria

No LLM. No I/O. Pure computation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class DerivedMetricInput:
    canonical: str
    value: float  # in SI/canonical unit as stored in LabResult


@dataclass
class DerivedMetricResult:
    canonical: str
    display_name_vi: str
    value: float | None  # None when insufficient data
    unit: str
    status: str  # normal / borderline / abnormal / insufficient_data
    formula: str  # human-readable formula
    inputs_used: list[str]  # canonical names that were used
    missing_inputs: list[str]  # canonical names that were absent or invalid
    note_vi: str | None = None  # brief Vietnamese note


def _lookup(inputs: dict[str, float], *keys: str) -> tuple[float | None, list[str]]:
    """Look up multiple input keys; return (value, missing_list) for single key,
    or use _lookup_multi for multiple."""
    missing = [k for k in keys if k not in inputs or inputs[k] is None]
    if missing:
        return None, missing
    if len(keys) == 1:
        return inputs[keys[0]], []
    return tuple(inputs[k] for k in keys), []  # type: ignore[return-value]


def _lookup_multi(
    inputs: dict[str, float], *keys: str
) -> tuple[dict[str, float] | None, list[str]]:
    missing = [k for k in keys if k not in inputs or inputs[k] is None]
    if missing:
        return None, missing
    return {k: inputs[k] for k in keys}, []


# ---------------------------------------------------------------------------
# eGFR — CKD-EPI 2021 Race-free equation
# ---------------------------------------------------------------------------


def compute_egfr(
    creatinine_umol_l: float,
    age_years: int,
    is_male: bool,
) -> DerivedMetricResult:
    """CKD-EPI 2021 race-free eGFR.

    Input: creatinine in µmol/L.
    Formula: eGFR = 142 × min(Scr/κ, 1)^α × max(Scr/κ, 1)^(−1.200)
             × 0.9938^age × [1.012 if female]

    Where (for 2021 race-free):
        κ (kappa) = 0.9 (female) or 0.7 (male)  [in mg/dL]
        α = −0.241 (female) or −0.302 (male)
    """
    # Convert µmol/L → mg/dL for the CKD-EPI formula.
    scr_mg_dl = creatinine_umol_l / 88.42

    kappa = 0.7 if is_male else 0.9
    alpha = -0.302 if is_male else -0.241
    sex_factor = 1.0 if is_male else 1.012

    ratio = scr_mg_dl / kappa
    # CKD-EPI 2021 race-free: 142 × min(Scr/κ,1)^α × max(Scr/κ,1)^−1.200 × 0.9938^age × sex_factor
    egfr = (
        142.0
        * (min(ratio, 1.0) ** alpha)
        * (max(ratio, 1.0) ** -1.200)
        * (0.9938**age_years)
        * sex_factor
    )
    egfr = round(egfr, 1)

    if egfr >= 90:
        status = "normal"
    elif egfr >= 60:
        status = "borderline"  # mildly reduced
    elif egfr >= 30:
        status = "abnormal"  # moderately reduced
    elif egfr >= 15:
        status = "abnormal"  # severely reduced
    else:
        status = "abnormal"  # kidney failure

    note = (
        "eGFR <60 mL/min/1.73m² kéo dài ≥3 tháng là tiêu chí CKD. "
        "Cần bác sĩ đánh giá thêm nguyên nhân và giai đoạn."
    )
    if egfr >= 90:
        note = "Chức năng thận trong giới hạn bình thường theo eGFR."

    return DerivedMetricResult(
        canonical="egfr_ckd_epi",
        display_name_vi="Mức lọc cầu thận (eGFR CKD-EPI)",
        value=egfr,
        unit="mL/min/1.73m²",
        status=status,
        formula=(
            "eGFR = 142 × min(Scr/κ,1)^α × max(Scr/κ,1)^(-1.2) × 0.9938^age × sex_factor "
            "[CKD-EPI 2021; Scr in mg/dL, κ=0.7(M)/0.9(F), α=-0.302(M)/-0.241(F)]"
        ),
        inputs_used=["creatinine", "age", "sex"],
        missing_inputs=[],
        note_vi=note,
    )


def compute_egfr_from_inputs(
    inputs: dict[str, float],
    age_years: int | None,
    is_male: bool,
) -> DerivedMetricResult:
    missing = []
    creatinine = inputs.get("creatinine")
    if creatinine is None:
        missing.append("creatinine")
    if age_years is None:
        missing.append("age")
    if missing:
        return DerivedMetricResult(
            canonical="egfr_ckd_epi",
            display_name_vi="Mức lọc cầu thận (eGFR CKD-EPI)",
            value=None,
            unit="mL/min/1.73m²",
            status="insufficient_data",
            formula="CKD-EPI 2021 race-free",
            inputs_used=[],
            missing_inputs=missing,
        )

    # creatinine in LabResult is stored in mg/dL (canonical unit from BiomarkerSpec).
    # Convert mg/dL → µmol/L: 1 mg/dL = 88.42 µmol/L.
    creatinine_umol_l = creatinine * 88.42
    return compute_egfr(creatinine_umol_l, age_years, is_male)


# ---------------------------------------------------------------------------
# Non-HDL Cholesterol
# ---------------------------------------------------------------------------


def compute_non_hdl(
    total_cholesterol_mmol_l: float,
    hdl_mmol_l: float,
) -> DerivedMetricResult:
    non_hdl = round(total_cholesterol_mmol_l - hdl_mmol_l, 3)

    if non_hdl < 3.4:
        status = "normal"
    elif non_hdl <= 4.1:
        status = "borderline"
    else:
        status = "abnormal"

    return DerivedMetricResult(
        canonical="non_hdl_cholesterol",
        display_name_vi="Cholesterol không HDL",
        value=non_hdl,
        unit="mmol/L",
        status=status,
        formula="Non-HDL = Total Cholesterol − HDL",
        inputs_used=["total_cholesterol", "hdl"],
        missing_inputs=[],
        note_vi=(
            "Non-HDL bao gồm tất cả lipoprotein chứa apoB "
            "— chỉ số dự báo nguy cơ tim mạch tốt hơn LDL đơn thuần."
        ),
    )


def compute_non_hdl_from_inputs(inputs: dict[str, float]) -> DerivedMetricResult:
    """Inputs: total_cholesterol (mg/dL), hdl (mg/dL); converts to mmol/L internally."""
    tc = inputs.get("total_cholesterol")
    hdl = inputs.get("hdl")
    missing = []
    if tc is None:
        missing.append("total_cholesterol")
    if hdl is None:
        missing.append("hdl")
    if missing:
        return DerivedMetricResult(
            canonical="non_hdl_cholesterol",
            display_name_vi="Cholesterol không HDL",
            value=None,
            unit="mmol/L",
            status="insufficient_data",
            formula="Non-HDL = Total Cholesterol − HDL",
            inputs_used=[],
            missing_inputs=missing,
        )

    # Convert mg/dL → mmol/L (factor 38.67)
    tc_si = tc / 38.67
    hdl_si = hdl / 38.67
    return compute_non_hdl(tc_si, hdl_si)


# ---------------------------------------------------------------------------
# LDL (Friedewald)
# ---------------------------------------------------------------------------


def compute_ldl_friedewald(
    total_cholesterol_mmol_l: float,
    hdl_mmol_l: float,
    triglyceride_mmol_l: float,
) -> DerivedMetricResult:
    """Friedewald LDL estimate. Only valid when TG < 4.5 mmol/L."""
    if triglyceride_mmol_l >= 4.5:
        return DerivedMetricResult(
            canonical="ldl_friedewald",
            display_name_vi="LDL tính (Friedewald)",
            value=None,
            unit="mmol/L",
            status="insufficient_data",
            formula="LDL = Total_Chol − HDL − TG/2.2 (only valid when TG < 4.5 mmol/L)",
            inputs_used=["total_cholesterol", "hdl"],
            missing_inputs=["triglyceride_too_high"],
            note_vi="TG ≥4.5 mmol/L — công thức Friedewald không hợp lệ; cần đo LDL trực tiếp.",
        )

    ldl = round(total_cholesterol_mmol_l - hdl_mmol_l - triglyceride_mmol_l / 2.2, 3)
    ldl = max(ldl, 0.0)  # physiologically cannot be negative

    if ldl < 2.6:
        status = "normal"
    elif ldl <= 3.4:
        status = "borderline"
    else:
        status = "abnormal"

    return DerivedMetricResult(
        canonical="ldl_friedewald",
        display_name_vi="LDL tính (Friedewald)",
        value=ldl,
        unit="mmol/L",
        status=status,
        formula="LDL = Total_Chol − HDL − TG/2.2 [Friedewald 1972; values in mmol/L]",
        inputs_used=["total_cholesterol", "hdl", "triglyceride"],
        missing_inputs=[],
        note_vi="Công thức ước tính — kết quả có thể sai lệch khi TG gần ngưỡng 4.5 mmol/L.",
    )


def compute_ldl_friedewald_from_inputs(inputs: dict[str, float]) -> DerivedMetricResult:
    """Inputs: total_cholesterol, hdl, triglyceride (mg/dL); converts to mmol/L."""
    tc = inputs.get("total_cholesterol")
    hdl = inputs.get("hdl")
    tg = inputs.get("triglyceride")
    missing = []
    if tc is None:
        missing.append("total_cholesterol")
    if hdl is None:
        missing.append("hdl")
    if tg is None:
        missing.append("triglyceride")
    if missing:
        return DerivedMetricResult(
            canonical="ldl_friedewald",
            display_name_vi="LDL tính (Friedewald)",
            value=None,
            unit="mmol/L",
            status="insufficient_data",
            formula="LDL = Total_Chol − HDL − TG/2.2 (mmol/L)",
            inputs_used=[],
            missing_inputs=missing,
        )

    tc_si = tc / 38.67
    hdl_si = hdl / 38.67
    tg_si = tg / 88.57
    return compute_ldl_friedewald(tc_si, hdl_si, tg_si)


# ---------------------------------------------------------------------------
# TyG Index (Triglyceride-Glucose Index)
# ---------------------------------------------------------------------------


def compute_tyg(
    fasting_glucose_mg_dl: float,
    triglyceride_mg_dl: float,
) -> DerivedMetricResult:
    """TyG = ln(TG_mg_dL × Glucose_mg_dL / 2)."""
    product = triglyceride_mg_dl * fasting_glucose_mg_dl / 2.0
    if product <= 0:
        return DerivedMetricResult(
            canonical="tyg_index",
            display_name_vi="Chỉ số TyG (kháng insulin)",
            value=None,
            unit="",
            status="insufficient_data",
            formula="TyG = ln(TG_mg/dL × Glucose_mg/dL / 2)",
            inputs_used=["triglyceride", "fasting_glucose"],
            missing_inputs=["invalid_values"],
        )

    tyg = round(math.log(product), 4)

    if tyg < 8.5:
        status = "normal"  # low_risk
    elif tyg <= 9.0:
        status = "borderline"  # intermediate
    else:
        status = "abnormal"  # high_insulin_resistance

    return DerivedMetricResult(
        canonical="tyg_index",
        display_name_vi="Chỉ số TyG (kháng insulin)",
        value=tyg,
        unit="",
        status=status,
        formula="TyG = ln(TG_mg/dL × Glucose_mg/dL / 2) [Simental-Mendía 2008]",
        inputs_used=["triglyceride", "fasting_glucose"],
        missing_inputs=[],
        note_vi=(
            "Chỉ số tham khảo kháng insulin — không thay thế HOMA-IR hay xét nghiệm chuyên sâu."
        ),
    )


def compute_tyg_from_inputs(inputs: dict[str, float]) -> DerivedMetricResult:
    """Inputs: fasting_glucose (mg/dL), triglyceride (mg/dL)."""
    glucose = inputs.get("fasting_glucose")
    tg = inputs.get("triglyceride")
    missing = []
    if glucose is None:
        missing.append("fasting_glucose")
    if tg is None:
        missing.append("triglyceride")
    if missing:
        return DerivedMetricResult(
            canonical="tyg_index",
            display_name_vi="Chỉ số TyG (kháng insulin)",
            value=None,
            unit="",
            status="insufficient_data",
            formula="TyG = ln(TG_mg/dL × Glucose_mg/dL / 2)",
            inputs_used=[],
            missing_inputs=missing,
        )
    return compute_tyg(glucose, tg)


# ---------------------------------------------------------------------------
# FIB-4 Score (Liver fibrosis)
# ---------------------------------------------------------------------------


def compute_fib4(
    age_years: int,
    ast_u_l: float,
    alt_u_l: float,
    platelet_10_9_l: float,
) -> DerivedMetricResult:
    """FIB-4 = (age × AST) / (platelet × √ALT)."""
    if alt_u_l <= 0 or platelet_10_9_l <= 0:
        return DerivedMetricResult(
            canonical="fib4_score",
            display_name_vi="Chỉ số FIB-4 (xơ hóa gan)",
            value=None,
            unit="",
            status="insufficient_data",
            formula="FIB-4 = (age × AST) / (platelet × √ALT)",
            inputs_used=["age", "ast", "alt", "platelet"],
            missing_inputs=["invalid_values"],
        )

    fib4 = round((age_years * ast_u_l) / (platelet_10_9_l * math.sqrt(alt_u_l)), 4)

    if fib4 < 1.3:
        status = "normal"  # low_risk
    elif fib4 <= 2.67:
        status = "borderline"  # indeterminate
    else:
        status = "abnormal"  # high_risk

    return DerivedMetricResult(
        canonical="fib4_score",
        display_name_vi="Chỉ số FIB-4 (xơ hóa gan)",
        value=fib4,
        unit="",
        status=status,
        formula="FIB-4 = (age × AST) / (platelet × √ALT) [Sterling et al. 2006]",
        inputs_used=["age", "ast", "alt", "platelet"],
        missing_inputs=[],
        note_vi="Chỉ số tầm soát — cần sinh thiết gan để xác nhận xơ hóa gan.",
    )


def compute_fib4_from_inputs(
    inputs: dict[str, float],
    age_years: int | None,
) -> DerivedMetricResult:
    missing = []
    if age_years is None:
        missing.append("age")
    ast = inputs.get("ast")
    alt = inputs.get("alt")
    platelet = inputs.get("platelet")
    if ast is None:
        missing.append("ast")
    if alt is None:
        missing.append("alt")
    if platelet is None:
        missing.append("platelet")
    if missing:
        return DerivedMetricResult(
            canonical="fib4_score",
            display_name_vi="Chỉ số FIB-4 (xơ hóa gan)",
            value=None,
            unit="",
            status="insufficient_data",
            formula="FIB-4 = (age × AST) / (platelet × √ALT)",
            inputs_used=[],
            missing_inputs=missing,
        )
    return compute_fib4(age_years, ast, alt, platelet)


# ---------------------------------------------------------------------------
# Metabolic Syndrome (IDF/AHA 2009 harmonized criteria)
# ---------------------------------------------------------------------------


@dataclass
class MetabolicSyndromeResult:
    canonical: str
    display_name_vi: str
    met_criteria: list[str]
    unmet_criteria: list[str]
    criteria_count: int
    status: str  # "meets_criteria" | "does_not_meet" | "insufficient_data"
    formula: str
    inputs_used: list[str]
    missing_inputs: list[str]
    note_vi: str | None = None


def compute_metabolic_syndrome(
    inputs: dict[str, float],
    is_male: bool,
    waist_cm: float | None = None,
) -> MetabolicSyndromeResult:
    """IDF/AHA 2009 harmonized criteria — needs ≥3 of 5 criteria.

    Inputs (all in canonical mg/dL or mmol/L as stored):
    - fasting_glucose: mg/dL
    - triglyceride: mg/dL
    - hdl: mg/dL
    - systolic_bp / diastolic_bp: mmHg (via inputs dict or from health metrics)
    - waist_cm: cm (from HealthMetric, passed separately)
    """
    met: list[str] = []
    unmet: list[str] = []
    missing: list[str] = []
    used: list[str] = []

    # 1. Waist circumference (Asian cutoffs)
    if waist_cm is not None:
        used.append("waist_cm")
        cutoff = 90.0 if is_male else 80.0
        if waist_cm > cutoff:
            met.append("waist_circumference")
        else:
            unmet.append("waist_circumference")
    else:
        missing.append("waist_cm")

    # 2. Fasting glucose ≥100 mg/dL
    glucose = inputs.get("fasting_glucose")
    if glucose is not None:
        used.append("fasting_glucose")
        if glucose >= 100.0:
            met.append("fasting_glucose")
        else:
            unmet.append("fasting_glucose")
    else:
        missing.append("fasting_glucose")

    # 3. Triglyceride ≥150 mg/dL
    tg = inputs.get("triglyceride")
    if tg is not None:
        used.append("triglyceride")
        if tg >= 150.0:
            met.append("triglyceride")
        else:
            unmet.append("triglyceride")
    else:
        missing.append("triglyceride")

    # 4. HDL: <40 mg/dL men, <50 mg/dL women
    hdl = inputs.get("hdl")
    if hdl is not None:
        used.append("hdl")
        hdl_cutoff = 40.0 if is_male else 50.0
        if hdl < hdl_cutoff:
            met.append("hdl_low")
        else:
            unmet.append("hdl_low")
    else:
        missing.append("hdl")

    # 5. Blood pressure: systolic ≥130 OR diastolic ≥85
    sbp = inputs.get("systolic_bp")
    dbp = inputs.get("diastolic_bp")
    if sbp is not None or dbp is not None:
        if sbp is not None:
            used.append("systolic_bp")
        if dbp is not None:
            used.append("diastolic_bp")
        bp_met = (sbp is not None and sbp >= 130) or (dbp is not None and dbp >= 85)
        if bp_met:
            met.append("blood_pressure")
        else:
            unmet.append("blood_pressure")
    else:
        missing.append("blood_pressure")

    criteria_count = len(met)

    # Need data on at least 3 criteria to make a judgment.
    available_criteria = len(met) + len(unmet)
    if available_criteria < 3:
        status = "insufficient_data"
    elif criteria_count >= 3:
        status = "meets_criteria"
    else:
        status = "does_not_meet"

    return MetabolicSyndromeResult(
        canonical="metabolic_syndrome",
        display_name_vi="Hội chứng chuyển hóa (IDF/AHA 2009)",
        met_criteria=met,
        unmet_criteria=unmet,
        criteria_count=criteria_count,
        status=status,
        formula=(
            "Cần ≥3/5 tiêu chí: vòng bụng, glucose đói ≥100, TG ≥150, "
            "HDL thấp, huyết áp ≥130/85 [IDF/AHA 2009 harmonized]"
        ),
        inputs_used=used,
        missing_inputs=missing,
        note_vi=(
            "Hội chứng chuyển hóa làm tăng nguy cơ tim mạch và tiểu đường type 2. "
            "Cần bác sĩ đánh giá toàn diện."
        ),
    )


# ---------------------------------------------------------------------------
# Registry — compute all applicable derived metrics from a flat inputs dict
# ---------------------------------------------------------------------------


def compute_all_derived(
    inputs: dict[str, float],
    age_years: int | None = None,
    is_male: bool = True,
    waist_cm: float | None = None,
) -> list[DerivedMetricResult]:
    """Run all derived metric calculators against the available inputs.

    Returns a list of DerivedMetricResult (even those with value=None, so the
    caller knows what was attempted and what inputs are missing).
    """
    results: list[DerivedMetricResult] = []

    # eGFR
    results.append(compute_egfr_from_inputs(inputs, age_years, is_male))

    # Non-HDL
    results.append(compute_non_hdl_from_inputs(inputs))

    # Friedewald LDL
    results.append(compute_ldl_friedewald_from_inputs(inputs))

    # TyG
    results.append(compute_tyg_from_inputs(inputs))

    # FIB-4
    results.append(compute_fib4_from_inputs(inputs, age_years))

    # Metabolic syndrome returns a different dataclass; wrap it.
    ms = compute_metabolic_syndrome(inputs, is_male, waist_cm)
    results.append(
        DerivedMetricResult(
            canonical=ms.canonical,
            display_name_vi=ms.display_name_vi,
            value=float(ms.criteria_count),
            unit="criteria_met",
            status=ms.status,
            formula=ms.formula,
            inputs_used=ms.inputs_used,
            missing_inputs=ms.missing_inputs,
            note_vi=ms.note_vi,
        )
    )

    return results
