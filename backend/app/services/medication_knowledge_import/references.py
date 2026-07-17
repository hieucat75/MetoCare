"""Structured reference persistence for the A1b knowledge importer.

Find-or-create against F1's `drug_references`/`knowledge_reference_links`
tables (app/models/drug_knowledge_references.py), using F1's own two-tiered
citation identity exactly. Never commits/rolls back — `db.add()` +
`db.flush()` only; the caller (`orchestrator.import_batch`) owns the batch
transaction. See
docs/medication-management/MEDICATION_PHASE_A1B_ORCHESTRATOR_IMPLEMENTATION_PLAN.md
§5 for the full design and its revision history.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.drug_knowledge_references import DrugReference, KnowledgeReferenceLink
from app.services.knowledge_repository import KNOWLEDGE_TABLE_NAME, KnowledgeModel
from app.services.medication_knowledge_import.schema import ReferenceEntry


def citation_identity_key(ref: ReferenceEntry) -> tuple:
    """The batch-local cache key AND the discriminator for which DB query
    branch to run. Explicitly prefixed by branch name ("document_identifier"
    vs "title") so the two branches can never collide even if their other
    field values happen to overlap — a document-identifier-keyed reference
    and a title-keyed reference are never the same cache slot."""
    if ref.document_identifier:
        return (
            "document_identifier",
            ref.document_identifier,
            ref.source_version,
            ref.accessed_at,
        )
    return (
        "title",
        ref.publisher,
        ref.title,
        ref.publication_date,
        ref.source_version,
        ref.accessed_at,
    )


class ReferenceIdentityMetadataConflictError(ValueError):
    """REFERENCE_IDENTITY_METADATA_CONFLICT — raised when a `DrugReference`
    row matches this file's citation identity (PTH round-2 P1 fix), but
    its other authored fields (publisher/title/source_type/url/
    publication_date) differ from what the incoming file actually wrote.
    F1's citation identity is deliberately narrower than the full authored
    artifact (see `versioning.artifact_hash`'s own docstring), so a
    version bump that changes e.g. `url` while keeping the same DOI would
    otherwise silently reuse a reference row whose stored fields no
    longer match what this version's artifact_hash claims — the knowledge
    row would assert one artifact while the DB relationship it links to
    holds another. Never silently reused, never updated in place, never
    inserted as a second row that would violate F1's own unique identity
    index — fails the whole batch closed instead. Manual remediation
    (retire the stale row, or correct the newer file back to the
    original's metadata) is required before this citation can be
    imported again."""


def reference_artifact(ref: ReferenceEntry) -> dict:
    """Normalized dict of every authored reference field — the full
    comparison unit for `ReferenceIdentityMetadataConflictError`, both
    against a persisted `DrugReference` row (`_reference_metadata_matches`)
    and against another `ReferenceEntry` seen earlier in the SAME batch
    (the `batch_cache` value in `find_or_create_reference` and
    `orchestrator._build_dry_run_report`). Exported (no underscore)
    because both this module and `orchestrator.py` need it."""
    return {
        "publisher": ref.publisher,
        "title": ref.title,
        "source_type": ref.source_type,
        "url": str(ref.url) if ref.url is not None else None,
        "document_identifier": ref.document_identifier,
        "publication_date": ref.publication_date,
        "source_version": ref.source_version,
        "accessed_at": ref.accessed_at,
    }


def _drug_reference_artifact(existing: DrugReference) -> dict:
    """Same field set as `reference_artifact`, read off a persisted row."""
    return {
        "publisher": existing.publisher,
        "title": existing.title,
        "source_type": existing.source_type,
        "url": existing.url,
        "document_identifier": existing.document_identifier,
        "publication_date": existing.publication_date,
        "source_version": existing.source_version,
        "accessed_at": existing.accessed_at,
    }


def _reference_metadata_matches(existing: DrugReference, ref: ReferenceEntry) -> bool:
    """True iff `existing` (already matched on citation identity) also
    matches every OTHER authored field of `ref`. Citation identity alone
    guarantees equality on some fields already (e.g. document_identifier/
    source_version/accessed_at on that branch) — checking all 8 fields
    here is simply defensive, not redundant-but-wrong, since the fields
    the identity query does NOT cover are exactly the ones that can
    silently drift (see `ReferenceIdentityMetadataConflictError`)."""
    return _drug_reference_artifact(existing) == reference_artifact(ref)


def find_existing_reference_or_raise_conflict(
    db: Session, ref: ReferenceEntry
) -> DrugReference | None:
    """`find_existing_reference` plus the identity/metadata consistency
    check (PTH round-2 P1 fix). Returns `None` if no row matches the
    citation identity at all (a genuine new reference — safe to create).
    Raises `ReferenceIdentityMetadataConflictError` if a row DOES match
    the identity but its other authored fields differ. Read-only — used
    by both `find_or_create_reference` (real write path) and
    `orchestrator._build_dry_run_report` (dry-run), so a conflict is
    detected identically in both, never surfacing only on the real run
    after a dry-run reported success."""
    existing = find_existing_reference(db, ref)
    if existing is not None and not _reference_metadata_matches(existing, ref):
        raise ReferenceIdentityMetadataConflictError(
            f"REFERENCE_IDENTITY_METADATA_CONFLICT: an existing drug_references "
            f"row matches this file's citation identity {citation_identity_key(ref)!r} "
            "but its publisher/title/source_type/url/publication_date differ from "
            "what this file authored — refusing to silently reuse a reference row "
            "under stale metadata."
        )
    return existing


def find_existing_reference(db: Session, ref: ReferenceEntry) -> DrugReference | None:
    """Read-only lookup only — the query half of `find_or_create_reference`,
    using F1's two-tiered citation identity exactly. Exposed separately
    (not inlined) so `orchestrator.py`'s dry-run mode (plan §9) can reuse
    the exact same lookup logic without ever inserting — dry-run must
    never call `find_or_create_reference` itself, since that function may
    `add()`+`flush()` a new row."""
    if ref.document_identifier:
        return (
            db.query(DrugReference)
            .filter_by(
                document_identifier=ref.document_identifier,
                source_version=ref.source_version,
                accessed_at=ref.accessed_at,
            )
            .one_or_none()
        )
    # document_identifier IS NULL is required, not optional: F1's own
    # title-based partial unique index only applies under that same
    # condition — without it here, a reference with no document_identifier
    # could wrongly match and reuse a row that DOES have one set (if the
    # other fields happen to coincide).
    return (
        db.query(DrugReference)
        .filter_by(
            publisher=ref.publisher,
            title=ref.title,
            publication_date=ref.publication_date,
            source_version=ref.source_version,
            accessed_at=ref.accessed_at,
            document_identifier=None,
        )
        .one_or_none()
    )


def find_or_create_reference(
    db: Session,
    ref: ReferenceEntry,
    *,
    batch_cache: dict[tuple, tuple[str, dict]],
) -> str:
    """Find-or-create one `DrugReference` row for one authoring-file
    reference entry, using F1's two-tiered citation identity exactly.
    Returns the resolved `DrugReference.id`.

    Checks `batch_cache` first: two files in the same batch citing an
    identical brand-new reference is a deterministic, avoidable duplicate
    insert (neither file's independent find-query would see the other's
    unflushed insert), not a genuine race — it must be resolved from the
    cache, not by hitting the cross-batch unique-index-rejection path this
    function also participates in for true races between separate
    `import_batch` invocations. `batch_cache` values are `(id, artifact)`
    pairs, not bare ids (PTH round-2 P1 fix, same-batch case): a cache HIT
    still re-checks the incoming reference's full artifact against what
    was cached, so two files in the SAME batch sharing a citation identity
    but disagreeing on another authored field raise the same conflict a
    cross-batch DB-query mismatch would — the batch-local cache is a
    dedup optimization, not an escape hatch from the consistency check.

    Identity/metadata consistency (PTH round-2 P1 fix): a row matching
    citation identity but disagreeing on another authored field (url,
    source_type, or — on the fallback branch — the fields the identity
    query doesn't cover) raises `ReferenceIdentityMetadataConflictError`
    rather than silently reusing stale metadata, updating the row in
    place, or inserting a second row that would violate F1's own unique
    identity index.

    Never commits/rolls back — `add()` + `flush()` only.
    """
    cache_key = citation_identity_key(ref)
    incoming_artifact = reference_artifact(ref)
    cached = batch_cache.get(cache_key)
    if cached is not None:
        cached_id, cached_artifact = cached
        if cached_artifact != incoming_artifact:
            raise ReferenceIdentityMetadataConflictError(
                f"REFERENCE_IDENTITY_METADATA_CONFLICT: an earlier file in this "
                f"SAME batch already resolved citation identity {cache_key!r} with "
                "different authored metadata (publisher/title/source_type/url/"
                "publication_date) — refusing to silently share one reference row "
                "across two disagreeing authored artifacts within one batch."
            )
        return cached_id

    existing = find_existing_reference_or_raise_conflict(db, ref)
    if existing is not None:
        batch_cache[cache_key] = (existing.id, incoming_artifact)
        return existing.id

    new_reference = DrugReference(
        publisher=ref.publisher,
        title=ref.title,
        source_type=ref.source_type,
        url=str(ref.url) if ref.url is not None else None,
        document_identifier=ref.document_identifier,
        publication_date=ref.publication_date,
        source_version=ref.source_version,
        accessed_at=ref.accessed_at,
    )
    db.add(new_reference)
    # Surfaces a real IntegrityError immediately if a concurrent writer
    # already committed this exact identity — plan §5's corrected race
    # semantics treat this as a whole-batch failure, not a recoverable
    # duplicate.
    db.flush()
    batch_cache[cache_key] = (new_reference.id, incoming_artifact)
    return new_reference.id


def link_reference_to_row(db: Session, row: KnowledgeModel, drug_reference_id: str) -> None:
    """Find-or-create the `KnowledgeReferenceLink` joining `row` to the
    reference identified by `drug_reference_id` — not a bare insert. A1a's
    file-level duplicate-reference validator keys on
    (publisher, title, publication_date), not F1's actual
    document-identifier-first identity: a file can have two `references:`
    entries that look different to A1a but resolve to the SAME
    `DrugReference` row here. Without this idempotency check, that would
    then try to insert a second, duplicate link for the identical
    (knowledge_table, knowledge_row_id, drug_reference_id) tuple, hitting
    `uq_krl_no_duplicate_link` needlessly.

    Never commits/rolls back — `add()` + `flush()` only.
    """
    knowledge_table = KNOWLEDGE_TABLE_NAME[type(row)]
    existing = (
        db.query(KnowledgeReferenceLink)
        .filter_by(
            knowledge_table=knowledge_table,
            knowledge_row_id=row.id,
            drug_reference_id=drug_reference_id,
        )
        .one_or_none()
    )
    if existing is not None:
        return

    link = KnowledgeReferenceLink(
        knowledge_table=knowledge_table,
        knowledge_row_id=row.id,
        drug_reference_id=drug_reference_id,
    )
    db.add(link)
    db.flush()
