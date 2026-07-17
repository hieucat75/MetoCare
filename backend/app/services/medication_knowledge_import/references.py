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


def _citation_identity_key(ref: ReferenceEntry) -> tuple:
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


def find_or_create_reference(
    db: Session,
    ref: ReferenceEntry,
    *,
    batch_cache: dict[tuple, str],
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
    `import_batch` invocations.

    Never commits/rolls back — `add()` + `flush()` only.
    """
    cache_key = _citation_identity_key(ref)
    cached_id = batch_cache.get(cache_key)
    if cached_id is not None:
        return cached_id

    if ref.document_identifier:
        existing = (
            db.query(DrugReference)
            .filter_by(
                document_identifier=ref.document_identifier,
                source_version=ref.source_version,
                accessed_at=ref.accessed_at,
            )
            .one_or_none()
        )
    else:
        # document_identifier IS NULL is required, not optional: F1's own
        # title-based partial unique index only applies under that same
        # condition — without it here, a reference with no
        # document_identifier could wrongly match and reuse a row that
        # DOES have one set (if the other fields happen to coincide).
        existing = (
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

    if existing is not None:
        batch_cache[cache_key] = existing.id
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
    batch_cache[cache_key] = new_reference.id
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
