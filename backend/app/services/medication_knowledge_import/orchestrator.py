"""Batch import orchestrator for A1b — ties loader → schema → validators →
provenance → versioning → knowledge_repository/references together into one
all-or-nothing batch operation.

See docs/medication-management/MEDICATION_PHASE_A1B_ORCHESTRATOR_IMPLEMENTATION_PLAN.md
for the full design and its revision history. The invariants this module
locks (do not weaken any of these without a new plan revision):

- One batch = one transaction = one commit, all-or-nothing (§2).
- Every file is loaded/validated/resolved before any write (§1).
- `NO_OP_ALREADY_IMPORTED` plans never reach `build_draft`/`add_draft` (§3).
- Append-only — only `build_draft`/`add_draft` (INSERT), never UPDATE (§4).
- `import_batch` is the only function in this call graph allowed to call
  `db.commit()`/`db.rollback()` (§2a).
- Import/content failures always return `BatchResult`; the one exception
  is the fresh-session precondition, a programmer-contract violation,
  which raises `ValueError` immediately (§2a).
- Whole-batch rollback on any Phase 2 failure (§10).
- No API route, no frontend, no AI wiring imports this module.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.services.knowledge_repository import add_draft, build_draft
from app.services.medication_knowledge_import import loader, provenance, validators
from app.services.medication_knowledge_import import versioning as v
from app.services.medication_knowledge_import.references import (
    citation_identity_key,
    find_existing_reference,
    find_or_create_reference,
    link_reference_to_row,
)
from app.services.medication_knowledge_import.schema import KnowledgeFile, ReferenceEntry


@dataclass
class FileError:
    """One file's (or, for a whole-batch write failure, the batch's own)
    error. `file=None` marks a failure not tied to a single file — a
    Phase 2 write failure after Phase 1 already passed every file."""

    file: Path | None
    message: str


@dataclass
class ImportPlan:
    """One file's fully-resolved Phase 1 outcome — nothing written yet."""

    path: Path
    model_cls: type
    knowledge_type: str
    fields: dict
    authored_by: str
    artifact_hash: str
    version_action: v.VersionAction
    references: list[ReferenceEntry]


@dataclass
class WrittenRow:
    path: Path
    model_cls: type
    row_id: str


@dataclass
class PlannedWrite:
    """Dry-run-only report of what Phase 2 *would* do for one file."""

    path: Path
    version_action: v.VersionAction


@dataclass
class BatchResult:
    success: bool
    errors: list[FileError] = field(default_factory=list)
    written: list[WrittenRow] = field(default_factory=list)
    dry_run: bool = False
    planned: list[PlannedWrite] | None = None


def _build_row_fields(knowledge_file: KnowledgeFile, ingredient_id: str) -> dict:
    """Maps a validated authoring file onto the exact kwargs `build_draft`
    needs for its knowledge_type — locale/audience only for the two types
    that actually have those columns (usage, patient_education); the other
    three types have no locale/audience dimension in their own schema."""
    metadata = knowledge_file.metadata
    content = knowledge_file.typed_content()
    review_metadata = knowledge_file.review_metadata
    knowledge_type = metadata.knowledge_type

    fields: dict = {
        "drug_ingredient_id": ingredient_id,
        "source": review_metadata.source,
        "version": review_metadata.version,
        "evidence_level": review_metadata.evidence_level,
        "last_reviewed_at": dt.datetime.combine(
            review_metadata.reviewed_at, dt.time.min, tzinfo=dt.UTC
        ),
    }

    if knowledge_type == "usage":
        fields.update(locale=metadata.locale, audience=metadata.audience, content=content.body)
    elif knowledge_type == "patient_education":
        fields.update(
            theme=content.theme,
            locale=metadata.locale,
            audience=metadata.audience,
            content=content.body,
        )
    elif knowledge_type == "side_effect":
        fields.update(
            concept_code=content.concept_code,
            label=content.label,
            frequency=content.frequency,
            action_level=content.action_level,
            description=content.description,
        )
    elif knowledge_type == "monitoring":
        fields.update(
            parameter=content.parameter,
            patient_context=content.patient_context,
            guidance=content.guidance,
        )
    elif knowledge_type == "contraindication":
        fields.update(
            condition_type=content.condition_type,
            condition_key=content.condition_key,
            condition_detail=content.condition_detail,
        )
    else:
        # unreachable — schema.py's Literal type already closes this
        raise ValueError(f"unknown knowledge_type {knowledge_type!r}")
    return fields


def _resolve_phase1(db: Session, paths: list[Path]) -> list[ImportPlan | FileError]:
    """Phase 1 (plan §1): pure except for read-only DB lookups. Zero writes.
    Processes files sequentially — not independently in parallel — folding
    each file's own version-action outcome into `batch_index` before the
    next file's resolution runs (plan §3's batch-local fold), namespaced by
    `(model_cls, business_key)` so different knowledge types can never
    cross-contaminate each other's version history."""
    batch_index: dict[tuple, list[tuple[str, str]]] = {}
    results: list[ImportPlan | FileError] = []

    for path in paths:
        try:
            raw = loader.load_file(path)
            knowledge_file = KnowledgeFile.model_validate(raw)
        except (loader.LoaderError, ValidationError) as exc:
            results.append(FileError(file=path, message=str(exc)))
            continue

        business_errors = validators.validate_business_rules(knowledge_file)
        if business_errors:
            results.append(FileError(file=path, message="; ".join(business_errors)))
            continue

        try:
            ingredient = provenance.resolve_medication_identity(
                db, knowledge_file.metadata.medication_identity.name_inn
            )
        except provenance.IdentityResolutionError as exc:
            results.append(FileError(file=path, message=str(exc)))
            continue

        unknown_specialties = [
            code
            for code in knowledge_file.review_metadata.specialty_codes
            if not provenance.check_specialty_exists(db, code)
        ]
        if unknown_specialties:
            results.append(
                FileError(
                    file=path,
                    message=(
                        f"unknown or inactive specialty code(s): {unknown_specialties!r} "
                        "— not a real, active clinical_specialties row"
                    ),
                )
            )
            continue

        knowledge_type = knowledge_file.metadata.knowledge_type
        model_cls = v.MODEL_BY_KNOWLEDGE_TYPE[knowledge_type]
        business_key = v.business_key_for(knowledge_file, ingredient.id)
        index_key = (model_cls, business_key)
        version = knowledge_file.review_metadata.version
        hash_value = v.artifact_hash(knowledge_file)

        known = batch_index.get(index_key)
        if known is None:
            try:
                known = v.known_versions_for(db, knowledge_type, business_key)
            except v.LegacyArtifactHashUnavailableError as exc:
                results.append(FileError(file=path, message=str(exc)))
                continue
            batch_index[index_key] = known

        action = v.resolve_version_action(known, version, hash_value)
        if action is v.VersionAction.REJECT_VERSION_CONFLICT:
            results.append(
                FileError(
                    file=path,
                    message=(
                        f"version conflict: business_key={business_key!r} "
                        f"version={version!r} already exists with different content/"
                        "references/provenance — a version string is a promise its "
                        "artifact is fixed"
                    ),
                )
            )
            continue

        # Fold this file's own outcome into the index so a LATER file in
        # this same batch sees it too — this is what closes the batch-local
        # gap (plan §3).
        known.append((version, hash_value))

        results.append(
            ImportPlan(
                path=path,
                model_cls=model_cls,
                knowledge_type=knowledge_type,
                fields=_build_row_fields(knowledge_file, ingredient.id),
                authored_by=knowledge_file.review_metadata.authored_by,
                artifact_hash=hash_value,
                version_action=action,
                references=knowledge_file.references,
            )
        )

    return results


def _build_dry_run_report(db: Session, plans: list[ImportPlan]) -> list[PlannedWrite]:
    """Dry-run reference resolution (plan §9) — same cache-then-DB-query
    logic as `find_or_create_reference`, but a cache miss stores a planned
    placeholder instead of inserting, so a second file in the same batch
    citing the same brand-new reference correctly reports reuse instead of
    double-counting a create. Never calls `find_or_create_reference` itself
    (that function may insert) — uses the read-only `find_existing_reference`
    query directly."""
    ref_cache: dict[tuple, str] = {}
    for plan in plans:
        for ref in plan.references:
            cache_key = citation_identity_key(ref)
            if cache_key in ref_cache:
                continue
            existing = find_existing_reference(db, ref)
            placeholder = f"planned:{len(ref_cache)}"
            ref_cache[cache_key] = existing.id if existing is not None else placeholder
    return [PlannedWrite(path=plan.path, version_action=plan.version_action) for plan in plans]


def import_batch(db: Session, paths: list[Path], *, dry_run: bool = False) -> BatchResult:
    """The one entrypoint. See module docstring for the invariants this
    function locks. `db` must be a fresh `Session` with no transaction
    already in progress — a caller violating that is a programmer-contract
    bug, not an import outcome, and gets a `ValueError` raised immediately,
    before any file is touched."""
    if db.in_transaction():
        raise ValueError(
            "import_batch requires a fresh Session with no transaction already "
            "open — pass a fresh Session per invocation, never a shared/long-lived one."
        )

    try:
        results = _resolve_phase1(db, paths)
        errors = [r for r in results if isinstance(r, FileError)]
        if errors:
            db.rollback()  # close the read-only transaction; nothing was written
            return BatchResult(success=False, errors=errors, written=[], dry_run=dry_run)

        plans = [r for r in results if isinstance(r, ImportPlan)]

        if dry_run:
            planned = _build_dry_run_report(db, plans)
            db.rollback()  # close the read-only transaction; dry-run never writes
            return BatchResult(success=True, errors=[], written=[], dry_run=True, planned=planned)

        written: list[WrittenRow] = []
        ref_cache: dict[tuple, str] = {}
        for plan in plans:
            if plan.version_action is v.VersionAction.NO_OP_ALREADY_IMPORTED:
                continue  # already imported — no draft, no reference writes
            row = build_draft(
                plan.model_cls,
                authored_by=plan.authored_by,
                artifact_hash=plan.artifact_hash,
                **plan.fields,
            )
            add_draft(db, row)  # add + flush, no commit
            for ref in plan.references:
                ref_id = find_or_create_reference(db, ref, batch_cache=ref_cache)
                link_reference_to_row(db, row, ref_id)  # add + flush, no commit; idempotent
            written.append(WrittenRow(path=plan.path, model_cls=plan.model_cls, row_id=row.id))

        db.commit()  # the ONE commit for the whole batch
        return BatchResult(success=True, errors=[], written=written, dry_run=False)
    except Exception as exc:
        db.rollback()
        return BatchResult(
            success=False,
            errors=[FileError(file=None, message=str(exc))],
            written=[],
            dry_run=dry_run,
        )
