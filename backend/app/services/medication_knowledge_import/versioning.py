"""Idempotency: business-key derivation, artifact hashing, and version-action
resolution for the A1b knowledge importer.

Pure logic + read-only DB queries — no writes anywhere in this module. See
docs/medication-management/MEDICATION_PHASE_A1B_ORCHESTRATOR_IMPLEMENTATION_PLAN.md
§3 for the full design and its revision history.
"""

from __future__ import annotations

import enum
import hashlib
import json

from sqlalchemy.orm import Session

from app.models.drug_knowledge_content import (
    DrugContraindication,
    DrugMonitoring,
    DrugPatientEducation,
    DrugSideEffect,
    DrugUsage,
)
from app.services.medication_knowledge_import.schema import KnowledgeFile, ReferenceEntry

# knowledge_type -> ORM row class. Distinct from schema.CONTENT_MODEL_BY_TYPE
# (which maps to the *content* Pydantic model, not the DB row class).
MODEL_BY_KNOWLEDGE_TYPE: dict[str, type] = {
    "usage": DrugUsage,
    "patient_education": DrugPatientEducation,
    "side_effect": DrugSideEffect,
    "monitoring": DrugMonitoring,
    "contraindication": DrugContraindication,
}

# Per-type business key, per the original A1 plan's §4 table — column names
# in the exact order business_key_for() below produces the tuple.
_BUSINESS_KEY_FIELDS: dict[str, tuple[str, ...]] = {
    "usage": ("drug_ingredient_id", "locale", "audience"),
    "patient_education": ("drug_ingredient_id", "theme", "locale", "audience"),
    "side_effect": ("drug_ingredient_id", "concept_code"),  # not level — F1 removed it
    "monitoring": ("drug_ingredient_id", "parameter", "patient_context"),
    "contraindication": ("drug_ingredient_id", "condition_type", "condition_key"),
}


class LegacyArtifactHashUnavailableError(ValueError):
    """LEGACY_ARTIFACT_HASH_UNAVAILABLE — raised when a non-'retired' row for
    a business key has `artifact_hash IS NULL`. Its immutability cannot be
    verified against the incoming file, and this module refuses to guess:
    never resolved as NEW_DRAFT, never NO_OP, never a content-only fallback
    comparison, never an overwrite. Manual remediation (backfill a real
    hash, or retire the row) is required before this business key can be
    imported again. A 'retired' row with a NULL hash does not raise this —
    only non-retired history is considered at all (see known_versions_for)."""


def business_key_for(knowledge_file: KnowledgeFile, ingredient_id: str) -> tuple:
    """Per-type business key. `ingredient_id` is `provenance.
    resolve_medication_identity(...)`'s resolved DrugIngredient.id — this
    function itself never touches the database."""
    metadata = knowledge_file.metadata
    content = knowledge_file.typed_content()
    knowledge_type = metadata.knowledge_type

    if knowledge_type == "usage":
        return (ingredient_id, metadata.locale, metadata.audience)
    if knowledge_type == "patient_education":
        return (ingredient_id, content.theme, metadata.locale, metadata.audience)
    if knowledge_type == "side_effect":
        return (ingredient_id, content.concept_code)
    if knowledge_type == "monitoring":
        return (ingredient_id, content.parameter, content.patient_context)
    if knowledge_type == "contraindication":
        return (ingredient_id, content.condition_type, content.condition_key)
    # unreachable — schema.py's Literal type already closes this
    raise ValueError(f"unknown knowledge_type {knowledge_type!r}")


def _reference_identity_key(ref: ReferenceEntry) -> tuple:
    """Matches F1's own two-tiered citation identity exactly (see
    app/models/drug_knowledge_references.py) — the document-identifier
    branch when present, else the publisher/title/publication_date
    fallback, both including accessed_at."""
    if ref.document_identifier:
        return (ref.document_identifier, ref.source_version, ref.accessed_at.isoformat())
    return (
        ref.publisher,
        ref.title,
        ref.publication_date.isoformat(),
        ref.source_version,
        ref.accessed_at.isoformat(),
    )


def _canonicalize_references(references: list[ReferenceEntry]) -> list[tuple]:
    """Sorted so reordering the `references:` list in a YAML file never
    manufactures a spurious version conflict — but an actual reference
    addition/removal/identity change always does, since the sorted key
    list itself changes."""
    return sorted(_reference_identity_key(ref) for ref in references)


def artifact_hash(knowledge_file: KnowledgeFile) -> str:
    """SHA-256 hex digest (64 characters) over the FULL authoring artifact
    — not just type-specific content fields (PTH round-6 P1 fix: an
    earlier design named this `content_hash` and hashed content fields
    only, excluding references and provenance; that let an author change a
    reference or its supporting provenance under an unchanged version and
    have the importer silently classify it NO_OP).

    Included: knowledge_type, type-specific content fields, locale,
    audience, references (canonicalized + sorted, order-independent),
    review_metadata.source/evidence_level/reviewed_at, specialty_codes
    (sorted), ai_generated, disclaimer.acknowledged.

    Excluded: authored_by, the source file's path, any runtime timestamp,
    database-generated IDs, status/lifecycle fields — none of these change
    what the artifact IS, only how/when/by whom it was produced.
    """
    metadata = knowledge_file.metadata
    content = knowledge_file.typed_content()
    review_metadata = knowledge_file.review_metadata

    payload = {
        "knowledge_type": metadata.knowledge_type,
        "content": content.model_dump(mode="json"),
        "locale": metadata.locale,
        "audience": metadata.audience,
        "references": _canonicalize_references(knowledge_file.references),
        "source": review_metadata.source,
        "evidence_level": review_metadata.evidence_level,
        "reviewed_at": review_metadata.reviewed_at.isoformat(),
        "specialty_codes": sorted(review_metadata.specialty_codes),
        "ai_generated": review_metadata.ai_generated,
        "disclaimer_acknowledged": knowledge_file.disclaimer.acknowledged,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class VersionAction(enum.Enum):
    NEW_DRAFT = "new_draft"  # new business key, or new version + new artifact
    NO_OP_ALREADY_IMPORTED = "no_op"  # same key, same version, same artifact hash
    REJECT_VERSION_CONFLICT = "reject"  # same key, same version, DIFFERENT artifact hash
    WARN_PROCEED_REPEATED_ARTIFACT = "warn_proceed"  # same key, new version, but artifact hash
    # matches an existing (any-status, non-retired) version


def resolve_version_action(
    known_versions: list[tuple[str, str]],
    version: str,
    artifact_hash_value: str,
) -> VersionAction:
    """Pure decision, no DB access, no writes — operates on an already-
    fetched list of (version, artifact_hash) pairs. Kept DB-free so the
    same function proves both the DB-seeded case (known_versions_for) and
    the batch-local case (orchestrator._resolve_phase1's sequential fold)
    without duplicating the 4-rule matrix twice."""
    exact_version_match = next((h for v, h in known_versions if v == version), None)
    if exact_version_match is not None:
        return (
            VersionAction.NO_OP_ALREADY_IMPORTED
            if exact_version_match == artifact_hash_value
            else VersionAction.REJECT_VERSION_CONFLICT
        )
    if any(h == artifact_hash_value for _, h in known_versions):
        return VersionAction.WARN_PROCEED_REPEATED_ARTIFACT
    return VersionAction.NEW_DRAFT


def known_versions_for(
    db: Session, knowledge_type: str, business_key: tuple
) -> list[tuple[str, str]]:
    """Read-only query — fetches version + artifact_hash for EVERY
    non-'retired' row matching this business key, not just the most recent
    one (the decision matrix's "matches an existing version" and "same
    version string" rules both require checking the FULL non-retired
    history, since a match can be to an older version, not only the
    latest one).

    Fails closed: raises LegacyArtifactHashUnavailableError if any
    matching non-retired row has `artifact_hash IS NULL` — never silently
    NEW_DRAFT, never NO_OP, never a content-only fallback comparison,
    never an overwrite. A 'retired' row with a NULL hash does not trigger
    this — retired rows are excluded from the query entirely, same as any
    other retired row's version history.
    """
    model_cls = MODEL_BY_KNOWLEDGE_TYPE[knowledge_type]
    fields = _BUSINESS_KEY_FIELDS[knowledge_type]
    filters = dict(zip(fields, business_key, strict=True))

    rows = (
        db.query(model_cls.version, model_cls.artifact_hash)
        .filter(model_cls.status != "retired")
        .filter_by(**filters)
        .all()
    )

    known: list[tuple[str, str]] = []
    for version, hash_value in rows:
        if hash_value is None:
            raise LegacyArtifactHashUnavailableError(
                f"LEGACY_ARTIFACT_HASH_UNAVAILABLE: a non-retired "
                f"{model_cls.__tablename__} row for business key {business_key!r} "
                f"(version={version!r}) has artifact_hash IS NULL — its "
                "immutability cannot be verified against this import. Manual "
                "remediation required: backfill a real hash for that row, or "
                "retire it, before this business key can be imported again."
            )
        known.append((version, hash_value))
    return known
