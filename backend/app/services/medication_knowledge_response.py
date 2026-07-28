"""K2 Slice 1 response builders (MEDICATION_K2_KNOWLEDGE_API_IMPLEMENTATION_PLAN.md
§2.3, §5, §6, §7; ADR-15 §D/§E/§F/§G).

Calls ONLY `app.services.knowledge_retrieval` (K1.6's sanctioned read
surface) — never issues its own `db.query(DrugUsage)`/etc. Every citation
lookup uses a server-resolved row id, never a client-supplied one (K2 plan
§7 provenance invariant, closed by construction).

No mutation anywhere in this module. `frequency`/`action_level` are never
read or referenced (ADR-15 §B/§C, K2 plan §5).
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.core.feature_flags import FeatureFlag, is_enabled
from app.models.drug_knowledge_content import (
    DrugContraindication,
    DrugMonitoring,
    DrugPatientEducation,
    DrugSideEffect,
    DrugUsage,
)
from app.models.drug_knowledge_core import DrugProductIngredient
from app.schemas.medication_knowledge import (
    DoctorContraindicationOut,
    DoctorEducationItemOut,
    DoctorIngredientKnowledgeOut,
    DoctorMonitoringOut,
    DoctorSideEffectOut,
    DoctorUsageOut,
    PatientContraindicationOut,
    PatientEducationItemOut,
    PatientMedicationKnowledgeOut,
    PatientMonitoringOut,
    PatientSideEffectOut,
    PatientUsageOut,
    ReferenceOut,
    SafetyNotice,
)
from app.services import knowledge_retrieval

logger = logging.getLogger(__name__)

KNOWLEDGE_VOCABULARY_VERSION = "1.0"

# ADR-15 §D — locked v1 evidence_level vocabulary (experimental: no DB
# CHECK constraint yet, so fail-soft on drift is load-bearing, not defensive
# dead code).
_EVIDENCE_LEVEL_VALUES = frozenset(
    {
        "clinical_guideline",
        "product_label",
        "peer_reviewed_literature",
        "expert_consensus",
        "traditional_use",
        "unknown",
    }
)

# ADR-15 §F — locked v1 theme vocabulary (experimental).
_THEME_VALUES = frozenset(
    {
        "why_this_matters",
        "how_to_use_safely",
        "what_to_monitor",
        "common_side_effects",
        "when_to_seek_help",
        "special_considerations",
    }
)

# ADR-15 §E — DrugReference.source_type only, already DB CHECK-enforced;
# validated here too on the same fail-soft-by-default principle (§G).
_SOURCE_TYPE_VALUES = frozenset(
    {"formulary", "clinical_guideline", "product_label", "peer_reviewed", "other"}
)

_PATIENT_SAFETY_NOTICE = SafetyNotice(
    code="medication_knowledge_reference_only_v1",
    text="Thông tin này chỉ mang tính tham khảo, không thay thế chỉ định của bác sĩ.",
    locale="vi",
    version="1",
)

_DOCTOR_SAFETY_NOTICE = SafetyNotice(
    code="medication_knowledge_clinical_reference_only_v1",
    text="Nội dung tham khảo lâm sàng, không thay thế thông tin kê đơn đầy đủ.",
    locale="vi",
    version="1",
)


def _log_vocabulary_drift(*, knowledge_table: str, row_id: str, field: str, value: object) -> None:
    """PHI-free structured data-quality note (ADR-15 §G) — never patient
    free text, never PHI, never raised as an exception. Field-level
    fail-soft only: the request/item is never failed because of this."""
    logger.warning(
        "medication_knowledge_vocabulary_drift",
        extra={
            "knowledge_vocabulary_version": KNOWLEDGE_VOCABULARY_VERSION,
            "knowledge_table": knowledge_table,
            "knowledge_row_id": row_id,
            "field": field,
            "invalid_value": value,
        },
    )


def _evidence_kwargs(row, *, knowledge_table: str) -> dict:
    """`{}` when absent from the response is required (ADR-15 §G) —
    `evidence_level` is NOT NULL on every approved row (`_approved_
    invariants_check`), so a `None` result here always means "value present
    but outside the locked vocabulary", never "legitimately empty".

    Slice 0 (docs/medication-management/
    MEDICATION_KNOWLEDGE_SLICE0_ORIGIN_PROVENANCE_FLAGS_IMPLEMENTATION_PLAN.md
    §0.3 item 2): gated behind `MEDICATION_EXPERIMENTAL_VOCABULARY`
    (default OFF) at this service layer, not just the router — when OFF,
    every item still gets built and returned (`content`/`last_reviewed_at`/
    etc. unaffected), only this one field is omitted. Never returns
    `evidence_level: null`; `response_model_exclude_unset=True` on both K2
    routes makes an omitted kwarg genuinely absent from the JSON body, not
    present as null. Never mutates or deletes the stored `row.evidence_level`
    value — this function only decides what to serialize."""
    if not is_enabled(FeatureFlag.MEDICATION_EXPERIMENTAL_VOCABULARY):
        return {}
    value = row.evidence_level
    if value in _EVIDENCE_LEVEL_VALUES:
        return {"evidence_level": value}
    _log_vocabulary_drift(
        knowledge_table=knowledge_table, row_id=row.id, field="evidence_level", value=value
    )
    return {}


def _theme_kwargs(row) -> dict:
    """Slice 0: same `MEDICATION_EXPERIMENTAL_VOCABULARY` gate as
    `_evidence_kwargs` above — see that function's docstring."""
    if not is_enabled(FeatureFlag.MEDICATION_EXPERIMENTAL_VOCABULARY):
        return {}
    value = row.theme
    if value in _THEME_VALUES:
        return {"theme": value}
    _log_vocabulary_drift(
        knowledge_table="drug_patient_education", row_id=row.id, field="theme", value=value
    )
    return {}


def resolve_ingredient_ids(db: Session, drug_product_id: str | None) -> list[str]:
    """Endpoint #1 only. `None`/unmatched `drug_product_id` -> `[]` (K2 plan
    §1.3 fact 2, §8: valid medication, no approved knowledge — 200 empty,
    never 404/500). Ordered primary-first (`is_primary` desc, then id) so
    `_pick_usage_row` can deterministically pick one row for the
    single-object `usage` field on a combination product — every OTHER
    category still merges across every returned ingredient (§2.3),
    unaffected by this ordering; `is_primary` is never used to exclude an
    ingredient."""
    if not drug_product_id:
        return []
    rows = (
        db.query(DrugProductIngredient.drug_ingredient_id)
        .filter(DrugProductIngredient.drug_product_id == drug_product_id)
        .order_by(
            DrugProductIngredient.is_primary.desc(), DrugProductIngredient.drug_ingredient_id
        )
        .all()
    )
    return [row.drug_ingredient_id for row in rows]


#  Live-schema correction to K2 plan §1.3 fact 4 / §2.3, found while
#  implementing Slice 1: the plan claims "locale"/"audience" are part of
#  the business key on all 5 knowledge tables. Verified directly against
#  `app/models/drug_knowledge_content.py` — only `DrugUsage` and
#  `DrugPatientEducation` actually declare those columns.
#  `DrugSideEffect`/`DrugMonitoring`/`DrugContraindication` have neither, so
#  there is structurally no doctor-audience/patient-audience duplicate row
#  to leak for those 3 tables — every approved row already applies to both
#  audiences and (today) the single authored locale. Filtering by
#  locale/audience is only meaningful, and only applied, for the 2 models
#  that actually carry those fields.
_LOCALE_AUDIENCE_AWARE_MODELS = (DrugUsage, DrugPatientEducation)


def _filtered(db: Session, model_cls, ingredient_id: str, *, audience: str, locale: str = "vi"):
    """K2 plan §2.3 — locale/audience filter applied at the route/service
    layer, since `list_current_for_ingredient` (K1.6) does not filter by
    either, for the models that carry those fields."""
    rows = knowledge_retrieval.list_current_for_ingredient(db, model_cls, ingredient_id)
    if model_cls not in _LOCALE_AUDIENCE_AWARE_MODELS:
        return rows
    return [r for r in rows if r.locale == locale and r.audience == audience]


def _pick_usage_row(db: Session, ingredient_ids: list[str], *, audience: str):
    """At most one `usage` row (single-object contract, §6.1/§6.2) even
    when a combination product resolves to multiple ingredients — the
    first ingredient (already primary-first ordered by
    `resolve_ingredient_ids`) with an approved usage row wins."""
    for ingredient_id in ingredient_ids:
        rows = _filtered(db, DrugUsage, ingredient_id, audience=audience)
        if rows:
            return rows[0]
    return None


def _merged(db: Session, model_cls, ingredient_ids: list[str], *, audience: str) -> list:
    """§2.3 combination-product rule: merge, never intersect, never
    primary-only."""
    merged: list = []
    for ingredient_id in ingredient_ids:
        merged.extend(_filtered(db, model_cls, ingredient_id, audience=audience))
    return merged


def _reference_out(reference) -> ReferenceOut | None:
    """Map one `DrugReference` row to `ReferenceOut`, or `None` if its
    `source_type` fails ADR-15 §E's fail-soft check (never fabricates,
    never substitutes — invariant 2)."""
    if reference.source_type not in _SOURCE_TYPE_VALUES:
        _log_vocabulary_drift(
            knowledge_table="drug_references",
            row_id=reference.id,
            field="source_type",
            value=reference.source_type,
        )
        return None
    return ReferenceOut(
        publisher=reference.publisher,
        title=reference.title,
        source_type=reference.source_type,
        url=reference.url,
        document_identifier=reference.document_identifier,
        publication_date=reference.publication_date,
        source_version=reference.source_version,
    )


def _batch_references_out(
    db: Session, model_cls, row_ids: list[str]
) -> dict[str, list[ReferenceOut]]:
    """K2 plan §7 — every `row_id` is always server-resolved from rows this
    same request already fetched through the approved+audience/locale
    filter, never client-supplied. One query per knowledge-item category
    (`list_references_for_batch`, K1.6), not one query per row — avoids the
    N+1 the per-row `list_references_for` form would produce for a doctor
    endpoint response with many approved rows. `list_references_for_batch`
    already returns every requested id as a key (empty list if no
    citations), so no id is ever silently dropped, and its own ordering
    (`knowledge_row_id`, then `publication_date desc`, then `id`) is
    preserved exactly — this function only filters and maps, it never
    reorders."""
    references_by_row = knowledge_retrieval.list_references_for_batch(db, model_cls, row_ids)
    return {
        row_id: [out for ref in references if (out := _reference_out(ref)) is not None]
        for row_id, references in references_by_row.items()
    }


def build_patient_response(
    db: Session, ingredient_ids: list[str]
) -> PatientMedicationKnowledgeOut:
    """K2 plan §6.1. `ingredient_ids` already resolved by
    `resolve_ingredient_ids` (empty list -> every category empty/null,
    §6.3). `patient_context`/`condition_type` never appear here at all —
    not read, not mapped (invariant 6)."""
    usage_row = _pick_usage_row(db, ingredient_ids, audience="patient")
    usage = None
    if usage_row is not None:
        usage = PatientUsageOut(
            content=usage_row.content,
            last_reviewed_at=usage_row.last_reviewed_at,
            **_evidence_kwargs(usage_row, knowledge_table="drug_usage"),
        )

    education_out = [
        PatientEducationItemOut(
            content=row.content,
            last_reviewed_at=row.last_reviewed_at,
            **_theme_kwargs(row),
            **_evidence_kwargs(row, knowledge_table="drug_patient_education"),
        )
        for row in _merged(db, DrugPatientEducation, ingredient_ids, audience="patient")
    ]
    side_effects_out = [
        PatientSideEffectOut(
            label=row.label,
            description=row.description,
            last_reviewed_at=row.last_reviewed_at,
            **_evidence_kwargs(row, knowledge_table="drug_side_effects"),
        )
        for row in _merged(db, DrugSideEffect, ingredient_ids, audience="patient")
    ]
    monitoring_out = [
        PatientMonitoringOut(
            guidance=row.guidance,
            last_reviewed_at=row.last_reviewed_at,
            **_evidence_kwargs(row, knowledge_table="drug_monitoring"),
        )
        for row in _merged(db, DrugMonitoring, ingredient_ids, audience="patient")
    ]
    contraindications_out = [
        PatientContraindicationOut(
            condition_detail=row.condition_detail,
            last_reviewed_at=row.last_reviewed_at,
            **_evidence_kwargs(row, knowledge_table="drug_contraindications"),
        )
        for row in _merged(db, DrugContraindication, ingredient_ids, audience="patient")
    ]

    return PatientMedicationKnowledgeOut(
        knowledge_vocabulary_version=KNOWLEDGE_VOCABULARY_VERSION,
        usage=usage,
        patient_education=education_out,
        side_effects=side_effects_out,
        monitoring=monitoring_out,
        contraindications=contraindications_out,
        safety_notice=_PATIENT_SAFETY_NOTICE,
    )


def build_doctor_response(db: Session, drug_ingredient_id: str) -> DoctorIngredientKnowledgeOut:
    """K2 plan §6.2. Single ingredient — no combination-product merge,
    business key already caps `usage` at one approved row."""
    usage_rows = _filtered(db, DrugUsage, drug_ingredient_id, audience="doctor")
    usage = None
    if usage_rows:
        row = usage_rows[0]
        usage = DoctorUsageOut(
            content=row.content,
            source=row.source,
            version=row.version,
            last_reviewed_at=row.last_reviewed_at,
            **_evidence_kwargs(row, knowledge_table="drug_usage"),
        )

    education_out = [
        DoctorEducationItemOut(
            content=row.content,
            source=row.source,
            version=row.version,
            last_reviewed_at=row.last_reviewed_at,
            **_theme_kwargs(row),
            **_evidence_kwargs(row, knowledge_table="drug_patient_education"),
        )
        for row in _filtered(db, DrugPatientEducation, drug_ingredient_id, audience="doctor")
    ]

    # References are batch-loaded ONCE per category (not once per row) —
    # avoids the N+1 a per-row list_references_for call inside each
    # comprehension below would produce. Fetch this category's approved
    # rows first, batch-load references for all of them together, then map.
    side_effect_rows = _filtered(db, DrugSideEffect, drug_ingredient_id, audience="doctor")
    side_effect_refs = _batch_references_out(db, DrugSideEffect, [r.id for r in side_effect_rows])
    side_effects_out = [
        DoctorSideEffectOut(
            concept_code=row.concept_code,
            label=row.label,
            description=row.description,
            source=row.source,
            version=row.version,
            last_reviewed_at=row.last_reviewed_at,
            references=side_effect_refs[row.id],
            **_evidence_kwargs(row, knowledge_table="drug_side_effects"),
        )
        for row in side_effect_rows
    ]

    monitoring_rows = _filtered(db, DrugMonitoring, drug_ingredient_id, audience="doctor")
    monitoring_refs = _batch_references_out(db, DrugMonitoring, [r.id for r in monitoring_rows])
    monitoring_out = [
        DoctorMonitoringOut(
            parameter=row.parameter,
            patient_context=row.patient_context,
            guidance=row.guidance,
            source=row.source,
            version=row.version,
            last_reviewed_at=row.last_reviewed_at,
            references=monitoring_refs[row.id],
            **_evidence_kwargs(row, knowledge_table="drug_monitoring"),
        )
        for row in monitoring_rows
    ]

    contraindication_rows = _filtered(
        db, DrugContraindication, drug_ingredient_id, audience="doctor"
    )
    contraindication_refs = _batch_references_out(
        db, DrugContraindication, [r.id for r in contraindication_rows]
    )
    contraindications_out = [
        DoctorContraindicationOut(
            condition_type=row.condition_type,
            condition_key=row.condition_key,
            condition_detail=row.condition_detail,
            source=row.source,
            version=row.version,
            last_reviewed_at=row.last_reviewed_at,
            references=contraindication_refs[row.id],
            **_evidence_kwargs(row, knowledge_table="drug_contraindications"),
        )
        for row in contraindication_rows
    ]

    return DoctorIngredientKnowledgeOut(
        knowledge_vocabulary_version=KNOWLEDGE_VOCABULARY_VERSION,
        usage=usage,
        patient_education=education_out,
        side_effects=side_effects_out,
        monitoring=monitoring_out,
        contraindications=contraindications_out,
        safety_notice=_DOCTOR_SAFETY_NOTICE,
    )
