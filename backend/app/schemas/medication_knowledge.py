"""K2 Slice 1 response contracts (MEDICATION_K2_KNOWLEDGE_API_IMPLEMENTATION_PLAN.md
§6, §10). Two separate shapes — patient (`PatientMedicationKnowledgeOut`) and
doctor (`DoctorIngredientKnowledgeOut`) — never a shared/superset model.

`evidence_level`/`theme` are `str | None` with no default passed at
construction when the persisted value falls outside ADR-15's locked
vocabulary (§D/§F) — combined with `response_model_exclude_unset=True` on
both routes, an omitted field is genuinely ABSENT from the JSON response,
not present as `null` (ADR-15 §G: "item returned WITHOUT evidence_level
field"). `usage` being explicitly `None` (no approved row) is always passed
as a constructor kwarg, so it stays present as `"usage": null` — the two
"empty" states are deliberately NOT interchangeable.

`frequency`/`action_level` do not appear anywhere in this file (ADR-15
§B/§C, K2 plan §5) — enforced by a schema-introspection test, not just by
omission here.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel


class SafetyNotice(BaseModel):
    code: str
    text: str
    locale: str
    version: str


class ReferenceOut(BaseModel):
    """`DrugReference.source_type` only (ADR-15 §E) — never confused with
    the unrelated `medications.source_type` (ADR-04)."""

    publisher: str
    title: str
    source_type: str
    url: str | None = None
    document_identifier: str | None = None
    publication_date: dt.date
    source_version: str


# --------------------------------------------------------------------------
# Patient contract (§6.1) — bounded provenance, no internal identifiers.
# --------------------------------------------------------------------------


class PatientUsageOut(BaseModel):
    content: str
    evidence_level: str | None = None
    last_reviewed_at: dt.datetime


class PatientEducationItemOut(BaseModel):
    theme: str | None = None
    content: str
    evidence_level: str | None = None
    last_reviewed_at: dt.datetime


class PatientSideEffectOut(BaseModel):
    label: str
    description: str
    evidence_level: str | None = None
    last_reviewed_at: dt.datetime


class PatientMonitoringOut(BaseModel):
    guidance: str
    evidence_level: str | None = None
    last_reviewed_at: dt.datetime


class PatientContraindicationOut(BaseModel):
    condition_detail: str
    evidence_level: str | None = None
    last_reviewed_at: dt.datetime


class PatientMedicationKnowledgeOut(BaseModel):
    knowledge_vocabulary_version: str
    usage: PatientUsageOut | None
    patient_education: list[PatientEducationItemOut]
    side_effects: list[PatientSideEffectOut]
    monitoring: list[PatientMonitoringOut]
    contraindications: list[PatientContraindicationOut]
    safety_notice: SafetyNotice


# --------------------------------------------------------------------------
# Doctor contract (§6.2) — structured clinical content, richer provenance,
# still no workflow/governance metadata.
# --------------------------------------------------------------------------


class DoctorUsageOut(BaseModel):
    content: str
    source: str
    version: str
    evidence_level: str | None = None
    last_reviewed_at: dt.datetime


class DoctorEducationItemOut(BaseModel):
    theme: str | None = None
    content: str
    source: str
    version: str
    evidence_level: str | None = None
    last_reviewed_at: dt.datetime


class DoctorSideEffectOut(BaseModel):
    concept_code: str
    label: str
    description: str
    source: str
    version: str
    evidence_level: str | None = None
    last_reviewed_at: dt.datetime
    references: list[ReferenceOut]


class DoctorMonitoringOut(BaseModel):
    parameter: str
    patient_context: str
    guidance: str
    source: str
    version: str
    evidence_level: str | None = None
    last_reviewed_at: dt.datetime
    references: list[ReferenceOut]


class DoctorContraindicationOut(BaseModel):
    condition_type: str
    condition_key: str
    condition_detail: str
    source: str
    version: str
    evidence_level: str | None = None
    last_reviewed_at: dt.datetime
    references: list[ReferenceOut]


class DoctorIngredientKnowledgeOut(BaseModel):
    knowledge_vocabulary_version: str
    usage: DoctorUsageOut | None
    patient_education: list[DoctorEducationItemOut]
    side_effects: list[DoctorSideEffectOut]
    monitoring: list[DoctorMonitoringOut]
    contraindications: list[DoctorContraindicationOut]
    safety_notice: SafetyNotice
