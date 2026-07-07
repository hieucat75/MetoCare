"""Meto Clinical Copilot — doctor-facing AI decision-support schemas.

Contract-fixed response/request shapes for the four Clinical Copilot endpoints:
- ai-summary   (deterministic, no LLM)
- ai-analysis  (deterministic priority + LLM-phrased reasoning)
- ai-questions (LLM-suggested history-taking questions)
- ai-advice    (LLM-suggested counseling direction)

Every output type carries `sources` (or is itself a citation of deterministic
findings) + a `confidence` level + the mandatory disclaimer — this surface is
decision-SUPPORT only, never decision-making, and never diagnoses/prescribes.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.domain.policies import DISCLAIMER_VI

SourceRefType = Literal["lab", "metric", "medication", "condition", "allergy", "appointment"]
ConfidenceLevel = Literal["high", "medium", "low"]
RiskLevel = Literal["normal", "monitor", "see_doctor_soon", "urgent"]


class SourceRef(BaseModel):
    type: SourceRefType
    label: str
    date: str | None = None


class MedicationBrief(BaseModel):
    name: str
    dosage: str
    frequency: str


class AbnormalFindingBrief(BaseModel):
    metric_type: str
    label: str
    status: str  # "low"|"high"|"critical"
    value_display: str
    trend_label: str
    priority: str  # "monitor"|"watch"|"see_doctor"


class ClinicalSummaryOut(BaseModel):
    as_of: str  # ISO8601
    conditions: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    medications: list[MedicationBrief] = Field(default_factory=list)
    abnormal_findings: list[AbnormalFindingBrief] = Field(default_factory=list)
    notable_changes: list[str] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)
    confidence: ConfidenceLevel
    disclaimer: str = DISCLAIMER_VI


class RiskFlag(BaseModel):
    level: RiskLevel
    label_vi: str
    findings: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)


class ClinicalAnalysisOut(BaseModel):
    priority: RiskFlag
    key_issues: list[str] = Field(default_factory=list)
    contradictions_or_gaps: list[str] = Field(default_factory=list)
    differentials_to_exclude: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel
    disclaimer: str = DISCLAIMER_VI


QuestionGroup = Literal[
    "current_symptoms",
    "onset_timing",
    "severity_progression",
    "aggravating_relieving",
    "relevant_history",
    "medication_adherence",
    "warning_signs",
    "lifestyle",
]


class SuggestedQuestion(BaseModel):
    group: QuestionGroup
    question_vi: str
    reason_vi: str


class ClinicalQuestionsOut(BaseModel):
    questions: list[SuggestedQuestion] = Field(default_factory=list)
    confidence: ConfidenceLevel
    disclaimer: str = DISCLAIMER_VI


AdviceCategory = Literal["explain_patient", "home_monitoring", "when_to_visit", "suggested_tests"]


class AdviceItem(BaseModel):
    category: AdviceCategory
    text_vi: str


class ClinicalAdviceOut(BaseModel):
    items: list[AdviceItem] = Field(default_factory=list)
    confidence: ConfidenceLevel
    disclaimer: str = DISCLAIMER_VI


class ClinicalCopilotRequest(BaseModel):
    consultation_id: str | None = None
