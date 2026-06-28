"""KnowledgeCard schema — the single data model for all medical knowledge in MetoCare.

KnowledgeCard is loaded from YAML. Never hardcode medical knowledge in Python.
Every field is typed. Validation is strict.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

KnowledgeStatus = Literal["draft", "internal_review", "medical_review", "approved", "deprecated"]
EvidenceLevel = Literal["strong", "moderate", "emerging", "expert_opinion"]


@dataclass
class KnowledgeSections:
    definition: str = ""                    # Section 1: What is it?
    normal_physiology: str = ""             # Section 2: What role does it play?
    causes_of_abnormality: str = ""         # Section 3: Why can it become abnormal?
    clinical_significance: str = ""         # Section 4: Why doctors care
    limitations: str = ""                   # Section 5: When can be misleading
    related_biomarkers: list[str] = field(default_factory=list)    # Section 6: related canonicals
    derived_indicators: list[str] = field(default_factory=list)    # Section 7: derived metric names
    patient_explanation: str = ""           # Section 8: Simple Vietnamese, analogy ok
    common_questions: list[str] = field(default_factory=list)      # Section 9: FAQ list
    lifestyle_relevance: str = ""           # Section 10: How habits influence
    doctor_discussion_topics: list[str] = field(default_factory=list)  # Section 11: Q for doc
    guideline_notes: str = ""               # Section 12: Guideline concepts (NOT verbatim)
    references: list[str] = field(default_factory=list)            # Section 13: Structured refs


@dataclass
class KnowledgeCard:
    # Identity
    knowledge_id: str          # e.g. "ldl_elevated" — matches insight card_id
    # "biomarker" | "disease" | "pattern" | "derived_indicator" | "medication" | "lifestyle"
    knowledge_type: str
    version: str               # "1.0", "1.1", etc.
    language: str              # "vi"
    status: KnowledgeStatus

    # Governance
    last_reviewed: str         # ISO date string "2026-06-28"
    reviewer: str              # name or "auto_generated"
    medical_specialty: str     # "cardiology" | "endocrinology" | "nephrology" | "general"
    evidence_level: EvidenceLevel
    confidence: float          # 0.0–1.0
    future_review_due: str     # ISO date string

    # Discovery
    tags: list[str] = field(default_factory=list)
    related_cards: list[str] = field(default_factory=list)  # other knowledge_ids

    # Content
    sections: KnowledgeSections = field(default_factory=KnowledgeSections)

    # Display
    display_name_vi: str = ""
    short_summary_vi: str = ""   # 1-2 sentence summary for Claude context

    @classmethod
    def from_dict(cls, data: dict) -> KnowledgeCard:
        """Create KnowledgeCard from a dict (e.g. loaded from YAML).

        Handles nested sections dict → KnowledgeSections.
        Missing optional fields default gracefully.
        """
        sections_raw = data.get("sections", {}) or {}
        sections = KnowledgeSections(
            definition=sections_raw.get("definition", "") or "",
            normal_physiology=sections_raw.get("normal_physiology", "") or "",
            causes_of_abnormality=sections_raw.get("causes_of_abnormality", "") or "",
            clinical_significance=sections_raw.get("clinical_significance", "") or "",
            limitations=sections_raw.get("limitations", "") or "",
            related_biomarkers=sections_raw.get("related_biomarkers", []) or [],
            derived_indicators=sections_raw.get("derived_indicators", []) or [],
            patient_explanation=sections_raw.get("patient_explanation", "") or "",
            common_questions=sections_raw.get("common_questions", []) or [],
            lifestyle_relevance=sections_raw.get("lifestyle_relevance", "") or "",
            doctor_discussion_topics=sections_raw.get("doctor_discussion_topics", []) or [],
            guideline_notes=sections_raw.get("guideline_notes", "") or "",
            references=sections_raw.get("references", []) or [],
        )
        return cls(
            knowledge_id=data["knowledge_id"],
            knowledge_type=data.get("knowledge_type", "biomarker"),
            version=str(data.get("version", "1.0")),
            language=data.get("language", "vi"),
            status=data.get("status", "draft"),
            last_reviewed=data.get("last_reviewed", ""),
            reviewer=data.get("reviewer", "auto_generated"),
            medical_specialty=data.get("medical_specialty", "general"),
            evidence_level=data.get("evidence_level", "moderate"),
            confidence=float(data.get("confidence", 0.5)),
            future_review_due=data.get("future_review_due", ""),
            tags=data.get("tags", []) or [],
            related_cards=data.get("related_cards", []) or [],
            sections=sections,
            display_name_vi=data.get("display_name_vi", "") or "",
            short_summary_vi=data.get("short_summary_vi", "") or "",
        )
