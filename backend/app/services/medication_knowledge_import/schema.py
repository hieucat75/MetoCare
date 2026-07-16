"""Pydantic input contract for medication knowledge authoring files.

Structural validation only (types, required/optional, controlled-vocabulary
literals, cross-field shape checks). Business rules that need a DB session
(medication identity resolution, specialty-code existence) live in
provenance.py; business rules that need only a fixed Python-level allowlist
live in validators.py. This module never touches the database.

See docs/medication-management/MEDICATION_PHASE_A_PR_A1_IMPLEMENTATION_PLAN.md
Section 3 for the authored template this schema encodes, and
MEDICATION_PHASE_A_BLOCKING_FINDINGS.md for why `references` is required
here even though A1a does not yet persist it anywhere.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field, model_validator

KnowledgeType = Literal[
    "usage",
    "patient_education",
    "side_effect",
    "monitoring",
    "contraindication",
]

Locale = Literal["vi"]
Audience = Literal["patient", "caregiver"]
EvidenceLevel = Literal["strong", "moderate", "emerging", "expert_opinion"]
SourceType = Literal["formulary", "clinical_guideline", "product_label", "peer_reviewed", "other"]
SideEffectLevel = Literal["common", "uncommon", "rare", "serious"]


class MedicationIdentity(BaseModel):
    """Human-readable identity resolved to a real drug_ingredient_id by
    provenance.py — this module does not touch the database, so resolution
    success/failure is not knowable here."""

    name_inn: str = Field(min_length=1)


class KnowledgeMetadata(BaseModel):
    knowledge_type: KnowledgeType
    medication_identity: MedicationIdentity
    locale: Locale
    audience: Audience


class UsageContent(BaseModel):
    body: str = Field(min_length=1)


class PatientEducationContent(BaseModel):
    theme: str = Field(min_length=1)
    body: str = Field(min_length=1)


class SideEffectContent(BaseModel):
    level: SideEffectLevel
    concept_code: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1)


class MonitoringContent(BaseModel):
    parameter: str = Field(min_length=1, max_length=128)
    patient_context: str = Field(min_length=1, max_length=64)
    guidance: str = Field(min_length=1)


class ContraindicationContent(BaseModel):
    condition_type: str = Field(min_length=1, max_length=64)
    condition_key: str = Field(min_length=1, max_length=64)
    condition_detail: str = Field(min_length=1)


# Maps knowledge_type -> the content model that shape must match. Kept as a
# plain dict (not a discriminated union) so orchestrator/validators code can
# look up the right model without re-deriving this mapping.
CONTENT_MODEL_BY_TYPE: dict[str, type[BaseModel]] = {
    "usage": UsageContent,
    "patient_education": PatientEducationContent,
    "side_effect": SideEffectContent,
    "monitoring": MonitoringContent,
    "contraindication": ContraindicationContent,
}


class ReferenceEntry(BaseModel):
    """One structured citation. Fields per PTH's explicit minimum spec —
    see MEDICATION_PHASE_A_BLOCKING_FINDINGS.md Finding 1. Persisted target
    (a real drug_references-style table) does not exist yet; this schema
    validates the input file's shape regardless of where it will land."""

    publisher: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_type: SourceType
    url: str | None = None
    document_identifier: str | None = None
    publication_date: dt.date
    source_version: str = Field(min_length=1)
    accessed_at: dt.date

    @model_validator(mode="after")
    def _require_url_or_document_identifier(self) -> ReferenceEntry:
        if not self.url and not self.document_identifier:
            raise ValueError(
                "reference must have a url or a document_identifier — "
                "an untraceable citation is not a structured reference"
            )
        return self


class ReviewMetadata(BaseModel):
    source: str = Field(min_length=1, max_length=255)
    version: str = Field(min_length=1)
    evidence_level: EvidenceLevel
    reviewed_at: dt.date
    authored_by: str = Field(min_length=1, max_length=255)
    ai_generated: Literal[False] = Field(
        description="Must be false — clinical facts must be human-authored, never AI-generated."
    )
    specialty_codes: list[str] = Field(default_factory=list)


class Disclaimer(BaseModel):
    acknowledged: Literal[True] = Field(
        description="Must be true — every knowledge item must acknowledge the standard disclaimer."
    )


class KnowledgeFile(BaseModel):
    """The full authoring file. `content` is validated structurally as a
    dict here; validators.py re-parses it against CONTENT_MODEL_BY_TYPE
    keyed on metadata.knowledge_type, since Pydantic's discriminated-union
    machinery adds complexity this module doesn't need for 5 fixed types."""

    metadata: KnowledgeMetadata
    content: dict
    references: list[ReferenceEntry] = Field(min_length=1)
    review_metadata: ReviewMetadata
    disclaimer: Disclaimer

    @model_validator(mode="after")
    def _content_matches_knowledge_type(self) -> KnowledgeFile:
        model_cls = CONTENT_MODEL_BY_TYPE[self.metadata.knowledge_type]
        try:
            model_cls.model_validate(self.content)
        except Exception as exc:  # noqa: BLE001 — re-raised with context below
            raise ValueError(
                f"content does not match the shape required for "
                f"knowledge_type={self.metadata.knowledge_type!r}: {exc}"
            ) from exc
        return self

    def typed_content(self) -> BaseModel:
        """Return `content` parsed into its concrete per-type model."""
        model_cls = CONTENT_MODEL_BY_TYPE[self.metadata.knowledge_type]
        return model_cls.model_validate(self.content)
