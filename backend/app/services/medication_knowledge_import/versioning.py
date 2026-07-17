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


_REFERENCE_ARTIFACT_FIELDS = (
    "publisher",
    "title",
    "source_type",
    "url",
    "document_identifier",
    "publication_date",
    "source_version",
    "accessed_at",
)


def _reference_artifact(ref: ReferenceEntry) -> dict:
    """The FULL authored reference representation — every field an author
    can change, not just the subset F1's citation identity uses to find/
    reuse a `DrugReference` row (PTH round-1 P1 fix: hashing only the
    identity fields let an author silently change `url`, `source_type`, or
    — on the document-identifier branch — `publisher`/`title`/
    `publication_date` under an unchanged version, and the importer would
    classify it NO_OP since the identity fields alone hadn't moved. This is
    the exact same class of bug that motivated switching from
    `content_hash` to `artifact_hash` in the first place — see that
    function's own docstring)."""
    return {
        "publisher": ref.publisher,
        "title": ref.title,
        "source_type": ref.source_type,
        "url": str(ref.url) if ref.url is not None else None,
        "document_identifier": ref.document_identifier,
        "publication_date": ref.publication_date.isoformat(),
        "source_version": ref.source_version,
        "accessed_at": ref.accessed_at.isoformat(),
    }


def _reference_sort_key(artifact: dict) -> tuple:
    """`(is_none, value)` per field so `None` (only possible for
    `document_identifier`) sorts deterministically without ever comparing
    `None` to `str` — Python raises TypeError on that comparison directly."""
    return tuple((artifact[field] is None, artifact[field]) for field in _REFERENCE_ARTIFACT_FIELDS)


def _canonicalize_references(references: list[ReferenceEntry]) -> list[dict]:
    """Sorted so reordering the `references:` list in a YAML file never
    manufactures a spurious version conflict — but an actual reference
    addition/removal/or ANY authored-field change always does, since each
    reference's full artifact (not just its identity fields) is part of
    the sort key and the hashed payload alike."""
    artifacts = [_reference_artifact(ref) for ref in references]
    return sorted(artifacts, key=_reference_sort_key)


def artifact_hash(knowledge_file: KnowledgeFile) -> str:
    """SHA-256 hex digest (64 characters) over the FULL authoring artifact
    — not just type-specific content fields (PTH round-6 P1 fix: an
    earlier design named this `content_hash` and hashed content fields
    only, excluding references and provenance; that let an author change a
    reference or its supporting provenance under an unchanged version and
    have the importer silently classify it NO_OP).

    Included: knowledge_type, type-specific content fields, locale,
    audience, references — EVERY authored field per reference (publisher,
    title, source_type, url, document_identifier, publication_date,
    source_version, accessed_at; canonicalized + sorted, order-independent
    — not just the subset F1's citation identity uses for DB dedup, see
    `_reference_artifact`'s own docstring), review_metadata.source/
    evidence_level/reviewed_at, specialty_codes (sorted), ai_generated,
    disclaimer.acknowledged.

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
    without duplicating the 4-rule matrix twice.

    Considers the FULL SET of hashes recorded under `version`, not just
    the first match (PTH round-1 P1 fix): this schema has no unique
    constraint on (business_key, version) — append-only plus a real
    concurrent-import race can leave two rows sharing the same version
    string with two DIFFERENT hashes. Picking only the first row found
    would make the NO_OP-vs-REJECT outcome depend on unspecified query
    ordering, and could silently NO_OP an import even though a genuine
    artifact conflict already exists under that version."""
    same_version_hashes = {h for v, h in known_versions if v == version}
    if same_version_hashes:
        return (
            VersionAction.NO_OP_ALREADY_IMPORTED
            if same_version_hashes == {artifact_hash_value}
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
