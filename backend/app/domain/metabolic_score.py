"""Metabolic Score — a transparent, reference tool (NOT a diagnosis).

Per ``docs/AI_Safety_Guardrail.md`` §3.1, the AI may "tính và giải thích Metabolic
Score (công cụ tham khảo)". This is a simple, explainable, deterministic scoring
function over common metabolic markers. It is intentionally NOT a validated
clinical risk model and must always be presented as a reference indicator.

Pure standard library. 0–100 scale where higher = more metabolic concern, mapped
to a coarse band. Each contributing factor is returned for explainability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ScoreBand(StrEnum):
    GOOD = "good"  # 0–24
    FAIR = "fair"  # 25–49
    ELEVATED = "elevated"  # 50–74
    HIGH_CONCERN = "high_concern"  # 75–100


@dataclass
class MetabolicInputs:
    waist_cm: float | None = None  # abdominal obesity proxy
    fasting_glucose: float | None = None  # mg/dL
    hba1c: float | None = None  # %
    triglyceride: float | None = None  # mg/dL
    hdl: float | None = None  # mg/dL
    systolic_bp: float | None = None  # mmHg
    is_male: bool = True


@dataclass
class ScoreFactor:
    name: str
    points: int
    detail: str


@dataclass
class MetabolicScoreResult:
    score: int
    band: ScoreBand
    factors: list[ScoreFactor] = field(default_factory=list)
    explanation: str = ""


def _band(score: int) -> ScoreBand:
    if score < 25:
        return ScoreBand.GOOD
    if score < 50:
        return ScoreBand.FAIR
    if score < 75:
        return ScoreBand.ELEVATED
    return ScoreBand.HIGH_CONCERN


def compute(inputs: MetabolicInputs) -> MetabolicScoreResult:
    """Sum weighted factor points, clamp to 0–100, map to a band.

    Weights are deliberately modest and additive so the result is explainable.
    Missing inputs simply contribute 0 (and are noted as unknown)."""
    factors: list[ScoreFactor] = []
    score = 0

    # Abdominal obesity (waist): thresholds ~ Asian cut-offs.
    if inputs.waist_cm is not None:
        cutoff = 90 if inputs.is_male else 80
        if inputs.waist_cm >= cutoff + 12:
            p = 20
        elif inputs.waist_cm >= cutoff:
            p = 12
        else:
            p = 0
        score += p
        factors.append(
            ScoreFactor("waist", p, f"Vòng bụng {inputs.waist_cm}cm (ngưỡng {cutoff}cm)")
        )

    # Glycemia
    if inputs.hba1c is not None:
        if inputs.hba1c >= 6.5:
            p = 25
        elif inputs.hba1c >= 5.7:
            p = 15
        else:
            p = 0
        score += p
        factors.append(ScoreFactor("hba1c", p, f"HbA1c {inputs.hba1c}%"))
    elif inputs.fasting_glucose is not None:
        if inputs.fasting_glucose >= 126:
            p = 25
        elif inputs.fasting_glucose >= 100:
            p = 15
        else:
            p = 0
        score += p
        factors.append(
            ScoreFactor("fasting_glucose", p, f"Đường huyết đói {inputs.fasting_glucose} mg/dL")
        )

    # Triglyceride
    if inputs.triglyceride is not None:
        if inputs.triglyceride >= 200:
            p = 15
        elif inputs.triglyceride >= 150:
            p = 8
        else:
            p = 0
        score += p
        factors.append(ScoreFactor("triglyceride", p, f"Triglyceride {inputs.triglyceride} mg/dL"))

    # HDL (low HDL is a risk; lower = more points)
    if inputs.hdl is not None:
        low_cut = 40 if inputs.is_male else 50
        if inputs.hdl < low_cut:
            p = 12
        else:
            p = 0
        score += p
        factors.append(ScoreFactor("hdl", p, f"HDL {inputs.hdl} mg/dL (ngưỡng {low_cut})"))

    # Blood pressure
    if inputs.systolic_bp is not None:
        if inputs.systolic_bp >= 140:
            p = 18
        elif inputs.systolic_bp >= 130:
            p = 10
        else:
            p = 0
        score += p
        factors.append(ScoreFactor("systolic_bp", p, f"Huyết áp tâm thu {inputs.systolic_bp} mmHg"))

    score = max(0, min(100, score))
    band = _band(score)

    band_label = {
        ScoreBand.GOOD: "Tốt",
        ScoreBand.FAIR: "Khá",
        ScoreBand.ELEVATED: "Cần lưu ý",
        ScoreBand.HIGH_CONCERN: "Cần lưu ý nhiều",
    }[band]
    explanation = (
        f"Metabolic Score của bạn là {score}/100 (mức: {band_label}). "
        "Đây là chỉ số tham khảo giúp bạn theo dõi xu hướng, không phải chẩn đoán. "
        "Nếu điểm ở mức cần lưu ý, bạn nên trao đổi với bác sĩ. "
        "Thông tin này không thay thế tư vấn bác sĩ."
    )

    return MetabolicScoreResult(score=score, band=band, factors=factors, explanation=explanation)
