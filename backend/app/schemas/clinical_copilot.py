"""Meto Clinical Copilot — doctor-facing AI decision-support schemas.

Contract-fixed response/request shapes for the four Clinical Copilot endpoints:
- ai-summary   (deterministic, no LLM)
- ai-analysis  (deterministic priority + LLM-phrased reasoning)
- ai-questions (LLM-suggested history-taking questions)
- ai-advice    (LLM-suggested counseling direction)

Every output type carries `sources` (or is itself a citation of deterministic
findings) + a `confidence` level + the mandatory disclaimer — this surface is
decision-SUPPORT only, never decision-making, and never diagnoses/prescribes.

`missing_data` + `confidence_note_vi` are populated on every response by a single
shared, deterministic completeness assessor (see
``app.services.clinical_copilot._assess_completeness``) — never by the LLM.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.domain.policies import DISCLAIMER_VI

SourceRefType = Literal[
    "lab", "metric", "medication", "condition", "allergy", "appointment", "consultation", "profile"
]
ConfidenceLevel = Literal["high", "medium", "low"]
RiskLevel = Literal["normal", "monitor", "see_doctor_soon", "urgent"]

MissingDataCategory = Literal[
    "demographics",
    "symptoms",
    "allergies",
    "medications",
    "medical_history",
    "vitals_metrics",
    "labs",
    "consultation_context",
]


class MissingDataItem(BaseModel):
    category: MissingDataCategory
    label_vi: str  # controlled label from a fixed lookup table — NEVER LLM-authored text


class SourceRef(BaseModel):
    id: str  # stable citation id. Two distinct id families:
    # - ROW-BACKED (stable/immutable for the life of the row — a fresh reading
    #   never overwrites or collides with an earlier one's id): e.g.
    #   "lab:<lab_result_id>", "metric:<health_metric_id>",
    #   "medication:<medication_id>", "consultation:<consultation_id>",
    #   "profile:<patient_id>". A "lab:<metric_type>"/"metric:<metric_type>"
    #   fallback (type-scoped, dateless) is used ONLY when no concrete row
    #   could be resolved for that finding.
    # - COLLECTION-ITEM REFERENCE (NOT stable/immutable across an edit): e.g.
    #   "condition:<index>", "allergy:<index>" — these index into a single
    #   encrypted JSON column on PatientProfile, not first-class DB rows, so
    #   the id can shift when the list is reordered/edited. Documented
    #   limitation, not a bug.
    type: SourceRefType
    label: str
    date: str | None = None  # ISO-8601; null ONLY if the underlying record genuinely
    # has no date — never invented


class CitedClaim(BaseModel):
    text: str
    sources: list[SourceRef] = Field(default_factory=list)
    basis: Literal["sourced", "needs_confirmation"]
    confidence: ConfidenceLevel  # per-claim, computed server-side from validation
    # outcome — NEVER trusted from the LLM


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
    missing_data: list[MissingDataItem] = Field(default_factory=list)
    confidence_note_vi: str | None = None
    disclaimer: str = DISCLAIMER_VI


class RiskFlag(BaseModel):
    level: RiskLevel
    label_vi: str
    findings: list[str] = Field(default_factory=list)
    missing_data: list[MissingDataItem] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)


class ClinicalAnalysisOut(BaseModel):
    priority: RiskFlag
    key_issues: list[CitedClaim] = Field(default_factory=list)
    contradictions_or_gaps: list[CitedClaim] = Field(default_factory=list)
    differentials_to_exclude: list[CitedClaim] = Field(default_factory=list)
    confidence: ConfidenceLevel
    missing_data: list[MissingDataItem] = Field(default_factory=list)
    confidence_note_vi: str | None = None
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
    missing_data: list[MissingDataItem] = Field(default_factory=list)
    confidence_note_vi: str | None = None
    disclaimer: str = DISCLAIMER_VI


AdviceCategory = Literal["explain_patient", "home_monitoring", "when_to_visit", "suggested_tests"]


class AdviceItem(BaseModel):
    category: AdviceCategory
    text_vi: str


class ClinicalAdviceOut(BaseModel):
    items: list[AdviceItem] = Field(default_factory=list)
    confidence: ConfidenceLevel
    missing_data: list[MissingDataItem] = Field(default_factory=list)
    confidence_note_vi: str | None = None
    disclaimer: str = DISCLAIMER_VI


class ClinicalCopilotRequest(BaseModel):
    consultation_id: str | None = None
