"""Engine 1 — Personal Context Engine.

Builds a PatientContext from PatientProfile DB data + optional frontend override.
Provides context-aware risk stratification for all downstream engines.

Design: rule registry + context provider. No hardcoded biomarker logic here.
MedicationContextProvider is an abstract interface — Phase 1 uses lifestyle_profile JSON.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

# ── MedicationContextProvider interface ───────────────────────────────────────
# Phase 1: LifestyleProfileMedicationProvider (reads from lifestyle_profile JSON)
# Phase 4: DatabaseMedicationProvider (reads from patient_medications table)
# Engines always call get_medications(patient_id) — never read the field directly.

class MedicationContextProvider(ABC):
    @abstractmethod
    def get_medications(self, patient_id: str) -> list[str]:
        """Return list of normalized medication names for patient."""
        ...


class LifestyleProfileMedicationProvider(MedicationContextProvider):
    """Phase 1 implementation: parses medications from lifestyle_profile JSON or known_conditions."""

    def __init__(self, lifestyle_profile_json: str | None, known_conditions: str | None = None):
        self._profile_json = lifestyle_profile_json
        self._known_conditions = known_conditions

    def get_medications(self, patient_id: str) -> list[str]:
        meds: list[str] = []
        if self._profile_json:
            try:
                data = json.loads(self._profile_json)
                raw = data.get("medications", [])
                if isinstance(raw, list):
                    meds.extend([str(m).lower().strip() for m in raw])
                elif isinstance(raw, str):
                    meds.extend([m.strip().lower() for m in raw.split(",") if m.strip()])
            except (json.JSONDecodeError, TypeError):
                pass
        # Keyword scan on known_conditions for common medication mentions
        if self._known_conditions:
            text = self._known_conditions.lower()
            _MED_KEYWORDS = {
                "statin": ["statin", "rosuvastatin", "atorvastatin", "simvastatin", "crestor", "lipitor"],
                "metformin": ["metformin", "glucophage"],
                "insulin": ["insulin"],
                "levothyroxine": ["levothyroxine", "synthroid", "thyroxine"],
                "ace_inhibitor": ["lisinopril", "enalapril", "ramipril", "perindopril"],
                "arb": ["losartan", "valsartan", "olmesartan", "irbesartan"],
                "beta_blocker": ["metoprolol", "bisoprolol", "carvedilol", "atenolol"],
                "aspirin": ["aspirin", "aspégic"],
            }
            for normalized, keywords in _MED_KEYWORDS.items():
                if any(kw in text for kw in keywords) and normalized not in meds:
                    meds.append(normalized)
        return meds


# ── Risk flag parsing ──────────────────────────────────────────────────────────

_CONDITION_KEYWORDS: dict[str, list[str]] = {
    "has_diabetes": ["tiểu đường", "đái tháo đường", "diabetes", "t2dm", "dm2", "hba1c cao"],
    "has_hypertension": ["tăng huyết áp", "hypertension", "huyết áp cao", "hta"],
    "has_dyslipidemia": ["rối loạn lipid", "dyslipidemia", "tăng mỡ máu", "tăng cholesterol"],
    "has_cvd_history": ["nhồi máu cơ tim", "đột quỵ", "mi ", "stroke", "angina", "stent", "bypass", "nhồi máu"],
    "has_ckd": ["thận mạn", "suy thận", "ckd", "chronic kidney"],
    "has_fatty_liver": ["gan nhiễm mỡ", "fatty liver", "nafld", "mafld"],
}

def _parse_condition_flags(text: str | None) -> dict[str, bool]:
    if not text:
        return {k: False for k in _CONDITION_KEYWORDS}
    lower = text.lower()
    return {flag: any(kw in lower for kw in keywords) for flag, keywords in _CONDITION_KEYWORDS.items()}


_LIFESTYLE_EXERCISE_MAP = {
    "none": ["không tập", "ít vận động", "sedentary"],
    "light": ["đi bộ nhẹ", "light", "nhẹ nhàng"],
    "moderate": ["moderate", "tập thể dục", "vừa phải", "jogging"],
    "active": ["active", "tập nặng", "gym", "chạy bộ", "vận động nhiều"],
}

def _parse_exercise_level(text: str | None) -> str:
    if not text:
        return "unknown"
    lower = text.lower()
    for level, keywords in _LIFESTYLE_EXERCISE_MAP.items():
        if any(kw in lower for kw in keywords):
            return level
    return "unknown"


# ── CV Risk Category ───────────────────────────────────────────────────────────
# Simplified Framingham proxy — no LLM, no DB query, no external call.
# Returns: "low" | "intermediate" | "high" | "very_high"

def _compute_cv_risk_category(
    age: int | None,
    sex: str | None,
    is_smoker: bool,
    has_cvd_history: bool,
    has_diabetes: bool,
    has_hypertension: bool,
) -> str:
    if has_cvd_history:
        return "very_high"
    if has_diabetes and age is not None and age >= 40:
        return "high"
    score = 0
    if age is not None:
        if age >= 65:
            score += 3
        elif age >= 55:
            score += 2
        elif age >= 45:
            score += 1
    if sex == "male":
        score += 1
    if is_smoker:
        score += 2
    if has_hypertension:
        score += 1
    if score >= 5:
        return "high"
    if score >= 3:
        return "intermediate"
    return "low"


# ── PatientContext dataclass ───────────────────────────────────────────────────

@dataclass
class PatientContext:
    # Demographics
    age: int | None = None
    sex: str | None = None           # "male" | "female"

    # Biometrics
    height_cm: float | None = None
    weight_kg: float | None = None
    bmi: float | None = None
    waist_cm: float | None = None

    # Condition flags
    has_diabetes: bool = False
    has_hypertension: bool = False
    has_dyslipidemia: bool = False
    has_cvd_history: bool = False
    has_ckd: bool = False
    has_fatty_liver: bool = False

    # Lifestyle
    is_smoker: bool = False
    drinks_alcohol: bool = False
    is_vegetarian: bool = False
    exercise_level: str = "unknown"  # "none"|"light"|"moderate"|"active"|"unknown"

    # Medications (normalized names)
    medications: list[str] = field(default_factory=list)

    # Computed
    cv_risk_category: str = "low"   # "low"|"intermediate"|"high"|"very_high"

    # Metadata
    context_completeness: float = 0.0   # 0.0–1.0
    missing_context: list[str] = field(default_factory=list)

    def is_overweight(self) -> bool:
        return self.bmi is not None and self.bmi >= 25.0

    def is_obese(self) -> bool:
        return self.bmi is not None and self.bmi >= 30.0

    def has_metabolic_risk(self) -> bool:
        return self.has_diabetes or self.has_hypertension or self.is_overweight()

    def on_medication(self, med: str) -> bool:
        return med.lower() in [m.lower() for m in self.medications]


# ── PatientContextInput (from API request override) ───────────────────────────

@dataclass
class PatientContextInput:
    sex: str | None = None
    age: int | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    waist_cm: float | None = None
    medications: list[str] | None = None
    exercise_level: str | None = None
    is_smoker: bool | None = None
    is_vegetarian: bool | None = None


# ── PatientContextEngine ──────────────────────────────────────────────────────

class PatientContextEngine:
    """Build PatientContext from DB profile + optional request override.

    Usage:
        engine = PatientContextEngine(profile_row, request_override)
        ctx = engine.build()
    """

    # Completeness scoring weights (sum = 1.0)
    _COMPLETENESS_WEIGHTS: dict[str, float] = {
        "age": 0.10,
        "sex": 0.05,
        "height_weight": 0.10,
        "waist_cm": 0.10,
        "known_conditions": 0.15,
        "medications": 0.15,
        "exercise_level": 0.10,
        "smoking": 0.05,
        "diet": 0.05,
        "family_history": 0.10,
        "bp_known": 0.05,
    }

    def __init__(
        self,
        profile: Any | None,          # PatientProfile ORM row or None
        override: PatientContextInput | None = None,
    ):
        self._profile = profile
        self._override = override or PatientContextInput()

    def build(self) -> PatientContext:
        p = self._profile
        ov = self._override
        ctx = PatientContext()

        # --- Demographics ---
        ctx.age = ov.age or (self._compute_age(getattr(p, "dob", None)) if p else None)
        raw_sex = ov.sex or (getattr(p, "gender", None) if p else None)
        ctx.sex = raw_sex.lower() if raw_sex else None

        # --- Biometrics ---
        ctx.height_cm = ov.height_cm or (getattr(p, "height_cm", None) if p else None)
        ctx.weight_kg = ov.weight_kg or (getattr(p, "weight_kg", None) if p else None)
        ctx.waist_cm = ov.waist_cm or (getattr(p, "waist_cm", None) if p else None)
        if ctx.height_cm and ctx.weight_kg and ctx.height_cm > 0:
            ctx.bmi = round(ctx.weight_kg / (ctx.height_cm / 100) ** 2, 1)

        # --- Condition flags ---
        known = getattr(p, "known_conditions", None) if p else None
        lifestyle_raw = getattr(p, "lifestyle_profile", None) if p else None
        flags = _parse_condition_flags((known or "") + " " + (lifestyle_raw or ""))
        ctx.has_diabetes = flags["has_diabetes"]
        ctx.has_hypertension = flags["has_hypertension"]
        ctx.has_dyslipidemia = flags["has_dyslipidemia"]
        ctx.has_cvd_history = flags["has_cvd_history"]
        ctx.has_ckd = flags["has_ckd"]
        ctx.has_fatty_liver = flags["has_fatty_liver"]

        # --- Lifestyle ---
        lp_text = lifestyle_raw or ""
        ctx.exercise_level = ov.exercise_level or _parse_exercise_level(lp_text)
        ctx.is_smoker = ov.is_smoker if ov.is_smoker is not None else ("hút thuốc" in lp_text.lower() or "smoker" in lp_text.lower() or "smoking" in lp_text.lower())
        ctx.drinks_alcohol = "rượu" in lp_text.lower() or "alcohol" in lp_text.lower()
        ctx.is_vegetarian = ov.is_vegetarian if ov.is_vegetarian is not None else ("chay" in lp_text.lower() or "vegetarian" in lp_text.lower())

        # --- Medications ---
        med_provider = LifestyleProfileMedicationProvider(lifestyle_raw, known)
        ctx.medications = ov.medications or med_provider.get_medications(
            getattr(p, "id", "") if p else ""
        )

        # --- CV Risk ---
        ctx.cv_risk_category = _compute_cv_risk_category(
            ctx.age, ctx.sex, ctx.is_smoker,
            ctx.has_cvd_history, ctx.has_diabetes, ctx.has_hypertension,
        )

        # --- Completeness ---
        ctx.context_completeness, ctx.missing_context = self._score_completeness(ctx, p)
        return ctx

    @staticmethod
    def _compute_age(dob: str | None) -> int | None:
        if not dob:
            return None
        try:
            from datetime import date
            parts = dob.split("-")
            if len(parts) != 3:
                return None
            birth = date(int(parts[0]), int(parts[1]), int(parts[2]))
            today = date.today()
            return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
        except (ValueError, IndexError):
            return None

    def _score_completeness(self, ctx: PatientContext, profile: Any | None) -> tuple[float, list[str]]:
        missing: list[str] = []
        score = 0.0
        w = self._COMPLETENESS_WEIGHTS

        if ctx.age:
            score += w["age"]
        else:
            missing.append("Tuổi")

        if ctx.sex:
            score += w["sex"]
        else:
            missing.append("Giới tính")

        if ctx.height_cm and ctx.weight_kg:
            score += w["height_weight"]
        else:
            missing.append("Chiều cao / Cân nặng")

        if ctx.waist_cm:
            score += w["waist_cm"]
        else:
            missing.append("Vòng eo")

        if profile and getattr(profile, "known_conditions", None):
            score += w["known_conditions"]
        else:
            missing.append("Bệnh nền")

        if ctx.medications:
            score += w["medications"]
        else:
            missing.append("Thuốc đang dùng")

        if ctx.exercise_level not in ("unknown", None):
            score += w["exercise_level"]
        else:
            missing.append("Mức độ vận động")

        # smoking always has a value (bool), partial credit if lifestyle_profile present
        score += w["smoking"]

        # diet
        if ctx.is_vegetarian is not None:
            score += w["diet"]

        if profile and getattr(profile, "family_history", None):
            score += w["family_history"]
        else:
            missing.append("Tiền sử gia đình")

        return round(min(score, 1.0), 2), missing
