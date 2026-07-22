"""Read-only Approved Medication Knowledge Retrieval Contract (K1.6).

Sits between K1.5's write path (`knowledge_repository.py`: `approve_row`/
`retire_row`, the only way a row ever reaches `status='approved'`) and a
future K2 API route (not built here — EC-08 stays satisfied, see
docs/medication-management/MEDICATION_K1_6_KNOWLEDGE_RETRIEVAL_IMPLEMENTATION_PLAN.md).

**This module is the only sanctioned read surface for the 5 ADR-13
knowledge tables.** Any future consumer (a K2 API route, ADR-07's
context-builder enhancement, an internal script) must call through these
functions — never issue its own `db.query(DrugUsage)`/`select(DrugSideEffect)`
directly. Enforced the same way K1's dormancy has always been enforced: a
grep for the 5 table names across `app/api`/`app/ai`/`frontend/src` must
return zero hits, forever, until a K2 GO explicitly authorizes a route.

Terminology: this module uses "approved" / "current approved" throughout —
never "published". `knowledge_repository.list_published()` predates this
module, is not touched here (no defect found in it), and is not the
precedent for naming here.

Retrieval invariants (plan §2):
1. Only `status='approved'` rows are ever returned — hardcoded, never a
   caller-overridable parameter.
2. `draft`/`clinical_review`/`deprecated`/`retired` rows are never returned.
3. Deterministic per full business key (the DB's own partial unique index
   guarantees this) — this module does not assume it and silently pick a
   winner if it is ever violated; see `MultipleApprovedRowsError`.
4. No history/audit-trail read surface — out of scope (ADR-13: "internal
   authoring/QA surface, out of scope for K0-K3").
5. No effective-date/scheduling semantics — not backed by schema.
6. Fail closed on inconsistency: never silently return an arbitrary row
   when more than one 'approved' row exists for one business key.

Every public function takes primitive identifiers only (`drug_ingredient_id:
str`, business-key values as plain strings, `model_cls`) — never a
caller-supplied ORM row. This sidesteps the entire class of
identity-map-staleness bugs K1.5 spent 4 review rounds fixing on the write
side: there is no caller-supplied-row trust boundary to defend on the read
side, because there is no caller-supplied row at all. Every query in this
module still wraps in `db.no_autoflush` and calls `.populate_existing()`
regardless (same read-side habit as `_lock_canonical_row`/
`check_specialty_completeness` in `knowledge_repository.py`), so a row
already dirty-in-memory elsewhere in the same session can never be returned
stale, and this module's own reads never trigger an unintended flush of
unrelated pending session state.

No RBAC check in this module itself (matches `list_published`/
`check_specialty_completeness` — ADR-13 already establishes "approved" ==
cleared for general consumption; caller-identity gating is deferred to a
future K2 API route layer, out of scope here).

No mutation, no commit, ever — this module only ever issues SELECTs.

Caveat (Codex Round 1, P2-5): `.populate_existing()` protects against a row
already dirty-in-memory being returned *stale* (see above) — but the same
mechanism can, as a side effect, silently discard a caller's own
*legitimate*, not-yet-flushed in-memory edit to that same row if it is
still pending elsewhere in the same session when one of this module's
reads happens to touch it (reproduced directly: an unflushed `row.content =
"..."` edit was overwritten back to the persisted value after a call to
`get_current_by_business_key` on that same row). This is the same
trade-off K1.5 already accepted for `_lock_canonical_row`/
`check_specialty_completeness` (a `SessionLocal` with `autoflush=False`,
so nothing is ever silently persisted — only the in-memory, unflushed
attribute is refreshed) — K1.6 reuses that established pattern rather than
inventing a different one. No active call path exercises this today
(module is fully dormant); a future K2 route mixing an uncommitted
knowledge-content write with a K1.6 read in the same session/request
should be aware of it.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.drug_knowledge_core import DrugIngredient
from app.models.drug_knowledge_references import DrugReference, KnowledgeReferenceLink
from app.services.knowledge_repository import (
    _BUSINESS_KEY_FIELDS,
    KNOWLEDGE_TABLE_NAME,
    KnowledgeModel,
)


class KnowledgeRetrievalError(Exception):
    """Base for this module's domain exceptions."""


class MultipleApprovedRowsError(KnowledgeRetrievalError):
    """More than one 'approved' row was found for a business key — should be
    structurally impossible given the partial unique index (see
    `drug_knowledge_content.py`), but this module verifies it at read time
    anyway (defense-in-depth, matching K1.5's own invariant-#1 philosophy)
    rather than trusting the constraint blindly. May look like dead code to
    a future reviewer since the index is supposed to make it unreachable —
    it exists so a data-integrity violation is never silently resolved by
    picking a row."""


class UnknownBusinessKeyFieldError(KnowledgeRetrievalError):
    """Caller passed a business-key filter kwarg that isn't part of this
    model's actual business key — fails closed rather than silently
    building a filter that matches nothing, or (worse) something wrong."""


class MissingBusinessKeyFieldError(KnowledgeRetrievalError):
    """Caller's business-key filter is missing a field this model's
    business key requires — fails closed rather than silently querying a
    partial key, which could match more than the caller intended."""


class UnsupportedKnowledgeModelError(KnowledgeRetrievalError):
    """`model_cls` is not one of the 5 ADR-13 knowledge models this module
    supports — OR isn't even a class at all. Every public function raises
    this SAME exception type for any such input — before Codex Round 1
    (P2-1), a non-empty call with an unsupported-but-hashable class raised
    a bare `KeyError` (not part of this module's declared exception
    taxonomy), while `get_current_batch`/`list_references_for_batch`
    called with an EMPTY id list skipped validation entirely and silently
    returned `{}`. Before Codex Round 2 (P2-1 follow-up), a non-class,
    non-hashable input (a list, a dict) ALSO leaked a bare `TypeError` from
    the dict membership check, since `_require_supported_model` didn't
    check `isinstance(model_cls, type)` first. `_require_supported_model`
    is called first, before any other logic (including the empty-input
    early return), in every public function, so every one of these failure
    modes now raises this same exception, with the same deterministic,
    memory-address-free message shape (never a bare instance `repr()`,
    which SQLAlchemy/Python's default would render with a non-deterministic
    `<... object at 0x...>` for anything other than a class)."""


def _require_supported_model(model_cls: object) -> None:
    """Fails closed with `UnsupportedKnowledgeModelError` for ANY input
    that isn't one of the 5 supported model classes — a non-class value
    (list, dict, a plain `object()`, an instance of a supported OR
    unrelated model), an unrelated real ORM class, or a genuinely
    unsupported class all raise the same way. `isinstance(model_cls, type)`
    is checked FIRST and unconditionally rules out every non-class input —
    including non-hashable ones (a list/dict would otherwise raise a raw,
    uncaught `TypeError` from the `in` check below) — before the dict
    membership check ever runs, so that check only ever receives an
    actual, hashable class object. The message uses only short names
    (`type(model_cls).__name__` for the received type, `model_cls.__name__`
    for a real-but-unsupported class) — never `repr()` on an arbitrary
    instance, which embeds a non-deterministic memory address, and never a
    fully-qualified internal module path beyond what a plain class/type
    name already conveys."""
    supported_names = sorted(m.__name__ for m in _BUSINESS_KEY_FIELDS)
    if not isinstance(model_cls, type):
        raise UnsupportedKnowledgeModelError(
            "Expected one of the 5 supported knowledge model classes "
            f"({', '.join(supported_names)}), got a value of type "
            f"{type(model_cls).__name__!r} instead of a class."
        )
    if model_cls not in _BUSINESS_KEY_FIELDS:
        raise UnsupportedKnowledgeModelError(
            f"{model_cls.__name__!r} is not one of the 5 supported "
            f"knowledge model classes: {', '.join(supported_names)}."
        )


def _validate_business_key_filter(model_cls: type, business_key_filter: dict[str, object]) -> None:
    required = set(_BUSINESS_KEY_FIELDS[model_cls])
    given = set(business_key_filter)
    unknown = given - required
    if unknown:
        raise UnknownBusinessKeyFieldError(
            f"{model_cls.__name__}: unknown business-key field(s) {sorted(unknown)}. "
            f"This model's business key is {sorted(required)}."
        )
    missing = required - given
    if missing:
        raise MissingBusinessKeyFieldError(
            f"{model_cls.__name__}: business-key filter is missing required "
            f"field(s) {sorted(missing)}. This model's business key is "
            f"{sorted(required)}."
        )


def _secondary_key_columns(model_cls: type) -> tuple[str, ...]:
    """This model's own business-key columns, excluding `drug_ingredient_id`
    — used as the deterministic ordering tiebreaker for list/batch reads.
    Derived from `_BUSINESS_KEY_FIELDS` (single source of truth, shared with
    the write path) rather than a second hand-maintained mapping, so the two
    can never drift apart."""
    return tuple(f for f in _BUSINESS_KEY_FIELDS[model_cls] if f != "drug_ingredient_id")


def get_current_by_business_key(
    db: Session, model_cls: type[KnowledgeModel], **business_key_filter: object
) -> KnowledgeModel | None:
    """The one 'approved' row for this exact business key, or `None` if no
    approved row exists for it — `None` represents a normal, expected
    "not currently approved" outcome here, never an error condition; this
    module always uses this convention (never raises a not-found exception
    for a single-row lookup) so callers have one consistent contract to
    handle.

    Raises `UnsupportedKnowledgeModelError` if `model_cls` isn't one of the
    5 supported models. Raises `UnknownBusinessKeyFieldError`/
    `MissingBusinessKeyFieldError` if `business_key_filter` doesn't exactly
    match this model's business key. Raises `MultipleApprovedRowsError` if
    the query ever returns more than one row (invariant 6)."""
    _require_supported_model(model_cls)
    _validate_business_key_filter(model_cls, business_key_filter)
    with db.no_autoflush:
        rows = (
            db.query(model_cls)
            .filter_by(status="approved", **business_key_filter)
            .populate_existing()
            .all()
        )
    if len(rows) > 1:
        raise MultipleApprovedRowsError(
            f"{model_cls.__name__}: {len(rows)} 'approved' rows found for "
            f"business key {business_key_filter!r} — expected at most 1."
        )
    return rows[0] if rows else None


def list_current_for_ingredient(
    db: Session, model_cls: type[KnowledgeModel], drug_ingredient_id: str
) -> list[KnowledgeModel]:
    """Every 'approved' row for one ingredient (e.g. all approved side
    effects for one ingredient). Deterministic order: by this table's own
    secondary business-key columns (e.g. `drug_side_effects` orders by
    `concept_code`; `drug_monitoring` by `parameter`, `patient_context`) — a
    stable, meaningful tiebreaker already covered by the existing partial
    index's trailing columns, no new index needed.

    Raises `UnsupportedKnowledgeModelError` if `model_cls` isn't one of the
    5 supported models."""
    _require_supported_model(model_cls)
    order_columns = [getattr(model_cls, field) for field in _secondary_key_columns(model_cls)]
    with db.no_autoflush:
        return (
            db.query(model_cls)
            .filter_by(status="approved", drug_ingredient_id=drug_ingredient_id)
            .populate_existing()
            .order_by(*order_columns)
            .all()
        )


def list_current_for_drug_class(
    db: Session, model_cls: type[KnowledgeModel], drug_class_id: str
) -> list[KnowledgeModel]:
    """Every 'approved' row across all ingredients whose
    `drug_ingredients.drug_class_id` DIRECTLY equals `drug_class_id`.

    Scope is deliberately non-recursive: `drug_classes.parent_class_id`
    hierarchy (sub-classes) is NOT walked/included here — an ingredient
    belongs to exactly one class row via a plain FK, and this function
    joins on that single FK only. A hierarchical rollup (all ingredients
    under a class OR any of its descendant classes) is a different,
    separate query shape this function does not attempt; if that is ever
    needed it is a new, explicitly-scoped function, not an implicit
    behavior change here.

    Joins through `DrugIngredient` (`ix_drug_ingredients_drug_class_id`),
    ordered by ingredient `name_inn` then this table's own business-key
    tiebreaker.

    Raises `UnsupportedKnowledgeModelError` if `model_cls` isn't one of the
    5 supported models."""
    _require_supported_model(model_cls)
    order_columns = [getattr(model_cls, field) for field in _secondary_key_columns(model_cls)]
    with db.no_autoflush:
        return (
            db.query(model_cls)
            .join(DrugIngredient, DrugIngredient.id == model_cls.drug_ingredient_id)
            .filter(model_cls.status == "approved", DrugIngredient.drug_class_id == drug_class_id)
            .populate_existing()
            .order_by(DrugIngredient.name_inn, *order_columns)
            .all()
        )


def get_current_batch(
    db: Session, model_cls: type[KnowledgeModel], drug_ingredient_ids: list[str]
) -> dict[str, list[KnowledgeModel]]:
    """Approved rows for MULTIPLE ingredients in one query (`IN (...)` on
    the same partial index) — the shape ADR-07's future context-builder
    enhancement needs to avoid N+1 queries across a patient's active
    medication list. Designed for realistic batch sizes (typically well
    under 100 ingredients) — not validated or chunked for arbitrarily large
    `drug_ingredient_ids` lists.

    Every requested `drug_ingredient_id` is present as a dict key (empty
    list if it has no approved rows for this table) — never silently
    omitted, so callers can safely index without a fallback. Duplicate
    ingredient ids in the input collapse to a single output key (documented
    behavior, not left implicit) — the caller never gets two entries for
    the same id.

    Fails the WHOLE batch (raises `MultipleApprovedRowsError` before
    returning anything) if any single business key within the batch's
    results has more than one 'approved' row — a data-integrity violation
    must never be silently absorbed into a batch result that otherwise
    looks fine.

    Raises `UnsupportedKnowledgeModelError` if `model_cls` isn't one of the
    5 supported models — checked FIRST, even when `drug_ingredient_ids` is
    empty (Codex Round 1, P2-1: the empty-input early return used to skip
    this check entirely, silently returning `{}` for an unsupported
    `model_cls` — indistinguishable from "no approved knowledge exists")."""
    _require_supported_model(model_cls)
    unique_ids = list(dict.fromkeys(drug_ingredient_ids))
    result: dict[str, list[KnowledgeModel]] = {ingredient_id: [] for ingredient_id in unique_ids}
    if not unique_ids:
        return result

    business_key_fields = _BUSINESS_KEY_FIELDS[model_cls]
    order_columns = [getattr(model_cls, field) for field in _secondary_key_columns(model_cls)]
    with db.no_autoflush:
        rows = (
            db.query(model_cls)
            .filter(model_cls.status == "approved", model_cls.drug_ingredient_id.in_(unique_ids))
            .populate_existing()
            .order_by(model_cls.drug_ingredient_id, *order_columns)
            .all()
        )

    seen_keys: set[tuple[object, ...]] = set()
    for row in rows:
        key = tuple(getattr(row, field) for field in business_key_fields)
        if key in seen_keys:
            raise MultipleApprovedRowsError(
                f"{model_cls.__name__}: more than one 'approved' row found for "
                f"business key {dict(zip(business_key_fields, key, strict=True))} "
                "within a batch retrieval."
            )
        seen_keys.add(key)
        result[row.drug_ingredient_id].append(row)
    return result


def list_references_for(
    db: Session, model_cls: type[KnowledgeModel], row_id: str
) -> list[DrugReference]:
    """**Identity-based provenance lookup** — citations for `(model_cls,
    row_id)`, regardless of that row's current lifecycle status or even
    whether it still exists. This is a deliberate contract decision (Codex
    Round 1, P1-1 → PTH review: downgraded from a defect to an explicit
    design choice, Option A): this function does NOT verify the referenced
    row is `status='approved'`, does NOT verify the row exists at all, and
    NEVER fabricates a citation for an existing link (an empty list means
    no link exists for that identity, nothing more).

    **The caller is responsible for first resolving an approved/current
    row** — via `get_current_by_business_key`/`list_current_for_ingredient`/
    `list_current_for_drug_class`/`get_current_batch` — before calling this
    function with that row's `id`. This module's own "approved-only"
    invariants (§ module docstring, invariants 1-2) apply to those 5
    functions; `list_references_for`/`list_references_for_batch` are
    intentionally NOT part of that guarantee, since their entire purpose is
    to resolve citations FOR an already-identified row, not to indepen-
    dently rediscover or re-validate which rows are current. A future K2
    API route (or any other consumer) that calls this function directly
    with an externally-supplied `row_id`, without first proving that id
    came from one of the approved-only lookups above, would surface
    citations for non-approved or nonexistent content — that misuse is the
    CALLER's responsibility to avoid, not something this function guards
    against.

    Kept separate from the read functions above (not auto-joined) so
    callers who don't need citations don't pay the extra query — matches
    this codebase's existing pattern of keeping specialty-review and
    reference-linking as separate concerns from the core row fetch.
    Deliberately does not expose reviewer identity /
    `knowledge_review_specialties` rows — internal-only per the knowledge
    template doc's field-visibility table.

    Raises `UnsupportedKnowledgeModelError` if `model_cls` isn't one of the
    5 supported models."""
    _require_supported_model(model_cls)
    table_name = KNOWLEDGE_TABLE_NAME[model_cls]
    with db.no_autoflush:
        return (
            db.query(DrugReference)
            .join(
                KnowledgeReferenceLink,
                KnowledgeReferenceLink.drug_reference_id == DrugReference.id,
            )
            .filter(
                KnowledgeReferenceLink.knowledge_table == table_name,
                KnowledgeReferenceLink.knowledge_row_id == row_id,
            )
            .populate_existing()
            .order_by(DrugReference.publication_date.desc(), DrugReference.id)
            .all()
        )


def list_references_for_batch(
    db: Session, model_cls: type[KnowledgeModel], row_ids: list[str]
) -> dict[str, list[DrugReference]]:
    """Batch form of `list_references_for` — same **identity-based
    provenance lookup** contract (see `list_references_for`'s docstring):
    does not verify any `row_id`'s status or existence, caller is
    responsible for only ever passing ids already resolved through one of
    this module's approved-only lookups.

    One query for citations across MULTIPLE rows of the same model, so a
    consumer fetching references for every row in a `get_current_batch`/
    `list_current_for_ingredient` result isn't forced into an N+1 query per
    row. Every requested `row_id` is present as a dict key (empty list if
    it has no citations) — never silently omitted. Duplicate `row_id`s in
    the input collapse to a single output key, same convention as
    `get_current_batch`. Designed for realistic batch sizes (a patient's
    active-medication list worth of rows, typically well under 100) — not
    validated or chunked for arbitrarily large `row_ids` lists.

    Raises `UnsupportedKnowledgeModelError` if `model_cls` isn't one of the
    5 supported models — checked before the empty-input early return, same
    reasoning as `get_current_batch`."""
    _require_supported_model(model_cls)
    unique_ids = list(dict.fromkeys(row_ids))
    result: dict[str, list[DrugReference]] = {row_id: [] for row_id in unique_ids}
    if not unique_ids:
        return result

    table_name = KNOWLEDGE_TABLE_NAME[model_cls]
    with db.no_autoflush:
        rows = (
            db.query(KnowledgeReferenceLink.knowledge_row_id, DrugReference)
            .join(DrugReference, KnowledgeReferenceLink.drug_reference_id == DrugReference.id)
            .filter(
                KnowledgeReferenceLink.knowledge_table == table_name,
                KnowledgeReferenceLink.knowledge_row_id.in_(unique_ids),
            )
            .populate_existing()
            .order_by(
                KnowledgeReferenceLink.knowledge_row_id,
                DrugReference.publication_date.desc(),
                DrugReference.id,
            )
            .all()
        )
    for row_id, reference in rows:
        result[row_id].append(reference)
    return result
