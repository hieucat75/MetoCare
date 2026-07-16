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

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

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

# ADR-13's own example for a normalized identifier is lowercase snake_case
# ("egfr_lt_30"). Applied to concept_code/condition_key specifically —
# these are the two fields ADR-13 calls out as normalized identifiers
# (distinct from the free-text description/condition_detail fields).
# condition_type/theme/parameter are intentionally NOT pattern-constrained
# here: ADR-13 does not define a closed vocabulary for them, and inventing
# one would be a clinical-taxonomy decision outside Phase A's scope.
_NORMALIZED_IDENTIFIER_PATTERN = r"^[a-z][a-z0-9_]*$"


class _StrictModel(BaseModel):
    """Shared config for every model in this input contract:
    - extra="forbid": an unknown field (e.g. a stray `status` key) is a
      hard validation error, not silently ignored — this is meant to be an
      exact input contract, per Codex review finding P2 on the original cut.
    - str_strip_whitespace=True: a whitespace-only value fails min_length
      after stripping, instead of silently passing as "non-empty" — closes
      the blank-source/blank-url gap Codex review found.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MedicationIdentity(_StrictModel):
    """Human-readable identity resolved to a real drug_ingredient_id by
    provenance.py — this module does not touch the database, so resolution
    success/failure is not knowable here."""

    name_inn: str = Field(min_length=1)


class KnowledgeMetadata(_StrictModel):
    knowledge_type: KnowledgeType
    medication_identity: MedicationIdentity
    locale: Locale
    audience: Audience


class UsageContent(_StrictModel):
    body: str = Field(min_length=1)


class PatientEducationContent(_StrictModel):
    theme: str = Field(min_length=1, max_length=64)  # matches drug_patient_education.theme
    body: str = Field(min_length=1)


class SideEffectContent(_StrictModel):
    level: SideEffectLevel
    concept_code: str = Field(min_length=1, max_length=64, pattern=_NORMALIZED_IDENTIFIER_PATTERN)
    description: str = Field(min_length=1)


class MonitoringContent(_StrictModel):
    parameter: str = Field(min_length=1, max_length=128)
    patient_context: str = Field(min_length=1, max_length=64)
    guidance: str = Field(min_length=1)


class ContraindicationContent(_StrictModel):
    condition_type: str = Field(min_length=1, max_length=64)
    condition_key: str = Field(min_length=1, max_length=64, pattern=_NORMALIZED_IDENTIFIER_PATTERN)
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


class ReferenceEntry(_StrictModel):
    """One structured citation. Fields per PTH's explicit minimum spec —
    see MEDICATION_PHASE_A_BLOCKING_FINDINGS.md Finding 1. Persisted target
    (a real drug_references-style table) does not exist yet; this schema
    validates the input file's shape regardless of where it will land.

    `url` is a real HttpUrl (not a bare string) and `document_identifier`
    is non-blank when present — a whitespace-only or unparseable value can
    no longer satisfy the mandatory traceability gate (Codex review P1)."""

    publisher: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_type: SourceType
    url: HttpUrl | None = None
    document_identifier: str | None = Field(default=None, min_length=1)
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


class ReviewMetadata(_StrictModel):
    source: str = Field(min_length=1, max_length=255)
    version: str = Field(min_length=1, max_length=32)  # matches KnowledgeLifecycleMixin.version
    evidence_level: EvidenceLevel
    reviewed_at: dt.date
    authored_by: str = Field(min_length=1, max_length=255)
    ai_generated: Literal[False] = Field(
        description="Must be false — clinical facts must be human-authored, never AI-generated."
    )
    specialty_codes: list[str] = Field(default_factory=list)


class Disclaimer(_StrictModel):
    acknowledged: Literal[True] = Field(
        description="Must be true — every knowledge item must acknowledge the standard disclaimer."
    )


class KnowledgeFile(_StrictModel):
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
