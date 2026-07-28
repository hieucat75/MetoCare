"""Repository/service layer for the 5 ADR-13 knowledge tables.

Full lifecycle write path (K1.5 + Slice 0): `create_draft`/
`submit_for_review` (K1-S3) plus `approve_row`/`reject_row`/`retire_row`
(K1.5 + Slice 0) together implement every transition `validate_transition`
allows — draft -> clinical_review -> {approved -> deprecated (automatic,
on supersession) -> retired} | rejected (terminal). `approve_row`/
`reject_row`/`retire_row` are gated by
`can_approve_knowledge`/`assert_can_approve_knowledge` (an interim
role-based check — see their docstrings; no dedicated Clinical Advisor
role exists yet, ADR-13 OQ-7/OQ-8).

Slice 0 (docs/medication-management/
MEDICATION_KNOWLEDGE_SLICE0_ORIGIN_PROVENANCE_FLAGS_IMPLEMENTATION_PLAN.md)
adds: the `rejected` terminal status + `reject_row`; an origin-awareness
guard in `approve_row` requiring complete AI-generation provenance before
an `origin='ai_synthesized'` row can be approved
(`_assert_ai_provenance_complete`, `AIProvenanceIncompleteError`); and a
`knowledge_lifecycle_transitions` history row recorded by every transition
function, inside the same transaction.

`drug_interactions` is out of scope — not one of the 5 tables this module
touches (deferred to its own ADR-02-compliant PR, per K1-M01/K1-S2).

No API route, no frontend, no AI wiring touches this module yet (K1
dormancy discipline: a write path existing here does not mean anything
calls it — that is a separate, later, explicitly-gated phase, K2+).
"""

from __future__ import annotations

import datetime as dt
from typing import TypeVar

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.system_actors import is_system_actor
from app.models.drug_knowledge_ai_generation import KnowledgeAIGeneration
from app.models.drug_knowledge_content import (
    DrugContraindication,
    DrugMonitoring,
    DrugPatientEducation,
    DrugSideEffect,
    DrugUsage,
)
from app.models.drug_knowledge_core import DrugClass, DrugIngredient
from app.models.drug_knowledge_governance import ClinicalSpecialty, KnowledgeReviewSpecialty
from app.models.drug_knowledge_lifecycle_transition import KnowledgeLifecycleTransition

KnowledgeModel = TypeVar(
    "KnowledgeModel",
    DrugUsage,
    DrugPatientEducation,
    DrugSideEffect,
    DrugMonitoring,
    DrugContraindication,
)

# Maps each of the 5 in-scope model classes to its table name — must match
# KNOWLEDGE_TABLES in drug_knowledge_governance.py (that tuple is the DB
# CHECK constraint's source of truth; this dict is this module's own,
# kept in sync by hand since the two files can't share a live import
# without a circular dependency).
KNOWLEDGE_TABLE_NAME: dict[type, str] = {
    DrugUsage: "drug_usage",
    DrugPatientEducation: "drug_patient_education",
    DrugSideEffect: "drug_side_effects",
    DrugMonitoring: "drug_monitoring",
    DrugContraindication: "drug_contraindications",
}

# ADR-13: "No transition ever skips clinical_review — a draft row can never
# become approved directly, even by an admin." Only these pairs are legal.
#
# ("clinical_review", "rejected") — Slice 0 §B2.3: the modeled destination
# for a clinical_review row a reviewer declines. 'rejected' is terminal —
# no transition out of it exists in this table, so a rejected row can
# never be silently mutated back to 'reviewed'/'approved'; the only way
# to supersede it is a brand-new draft row through the normal
# create_draft -> submit_for_review -> approve_row path (ADR-13
# append-only discipline, unchanged).
_ALLOWED_TRANSITIONS = {
    ("draft", "clinical_review"),
    ("clinical_review", "approved"),
    ("clinical_review", "rejected"),
    ("approved", "deprecated"),
    ("deprecated", "retired"),
}


class TransitionError(ValueError):
    """Raised when a lifecycle status transition violates ADR-13."""


class AIProvenanceIncompleteError(ValueError):
    """Raised by `approve_row` when an `origin='ai_synthesized'` row has no
    complete, non-superseded, successful `KnowledgeAIGeneration` record
    (Slice 0 §B2.3). Distinct from `TransitionError` (an illegal *status*
    transition) and `KnowledgeApprovalAuthorizationError` (wrong actor) —
    this is specifically "the actor and status transition are both legal,
    but this AI-authored row's provenance is not proven complete enough to
    approve.\""""


# "Every transition records actor, timestamp, reason code and PHI-free
# rationale" is a binding PTH implementation instruction (2026-07-27,
# Medication Knowledge Slice 0 final checkpoint) — not text quoted from
# MEDICATION_KNOWLEDGE_SLICE0_ORIGIN_PROVENANCE_FLAGS_IMPLEMENTATION_PLAN.md
# (that plan's own §B3 names only three migrations and predates this
# instruction). See docs/medication-management/adrs/
# ADR-13-KNOWLEDGE-CONTENT-LIFECYCLE.md, Amendment 1, for the authorizing
# record of `_record_transition`/`knowledge_lifecycle_transitions`.
#
# Applied as an OPTIONAL, backward-compatible addition to every existing
# transition function (submit_for_review, approve_row, retire_row) so
# none of K1.5's existing call sites/tests need to change. Callers that
# don't care about a specific reason get this generic, still-honest
# default; reject_row (new in Slice 0, no legacy callers to preserve)
# requires a real reason_code/rationale explicitly — a rejection should
# always say why.
_DEFAULT_REASON_CODE = "standard_transition"
_DEFAULT_RATIONALE = "Routine ADR-13 lifecycle transition."
_AUTO_DEPRECATION_REASON_CODE = "auto_deprecated_superseded"
_AUTO_DEPRECATION_RATIONALE = (
    "Automatically deprecated: a newer approved row now exists for the same business key."
)


def _record_transition(
    db: Session,
    model_cls: type,
    *,
    knowledge_row_id: str,
    from_status: str,
    to_status: str,
    actor_id: str,
    actor_role: str | None,
    reason_code: str,
    rationale: str,
    now: dt.datetime,
) -> None:
    """Append one lifecycle-transition history row, inside the caller's own
    open transaction (no independent commit here — same discipline as
    `_deprecate_superseded`). Never called outside a transition function's
    own try/except block; a failure here rolls back the whole transition,
    same as any other write in that block."""
    db.add(
        KnowledgeLifecycleTransition(
            knowledge_table=KNOWLEDGE_TABLE_NAME[model_cls],
            knowledge_row_id=knowledge_row_id,
            from_status=from_status,
            to_status=to_status,
            actor_id=actor_id,
            actor_role=actor_role,
            reason_code=reason_code,
            rationale=rationale,
            transitioned_at=now,
        )
    )


def validate_transition(
    current_status: str,
    new_status: str,
    *,
    authored_by: str,
    actor_user_id: str,
    specialty_complete: bool = False,
) -> None:
    """Pure validation of one ADR-13 lifecycle transition. Raises
    TransitionError if illegal; returns None if legal. Does not touch the
    database or mutate any row — callers are responsible for applying the
    transition only after this passes.
    """
    if (current_status, new_status) not in _ALLOWED_TRANSITIONS:
        raise TransitionError(
            f"Illegal transition {current_status!r} -> {new_status!r}. "
            f"Allowed transitions: {sorted(_ALLOWED_TRANSITIONS)}."
        )
    if new_status == "approved":
        # ADR-13: "status_changed_by (the approver) may never equal
        # authored_by (who wrote/last edited the row)."
        if actor_user_id == authored_by:
            raise TransitionError(
                "Self-approval is blocked: the approver cannot be the same "
                "identity as the row's authored_by. (ADR-13 provides a "
                "logged, PTH-approved override for this — not implemented "
                "in K1-S3.)"
            )
        if not specialty_complete:
            raise TransitionError(
                "Cannot approve: not every specialty required by this "
                "ingredient's drug_class has a recorded review "
                "(knowledge_review_specialties row)."
            )


def build_draft(
    model_cls: type[KnowledgeModel],
    *,
    authored_by: str,
    artifact_hash: str | None = None,
    **fields: object,
) -> KnowledgeModel:
    """Pure construction — no DB interaction at all. Always `status='draft'`
    (A1b orchestrator plan §7: draft-only, enforced by construction, never
    a runtime flag).

    `artifact_hash` defaults to `None` for backward compatibility with
    every caller that predates the A1b orchestrator (K1-S3's own tests,
    `create_draft` below). The A1b orchestrator itself always passes a real
    64-character SHA-256 hash here — enforced at the orchestrator's own
    call site (plan §3), not by this function's signature, since this is a
    *shared* primitive used by both the orchestrator and `create_draft`'s
    legacy callers and must not reject either."""
    now = dt.datetime.now(dt.UTC)
    return model_cls(
        authored_by=authored_by,
        status="draft",
        status_changed_by=authored_by,
        status_changed_at=now,
        artifact_hash=artifact_hash,
        **fields,
    )


def add_draft(db: Session, row: KnowledgeModel) -> None:
    """`db.add(row)` + `db.flush()`. Never commits, never rolls back (A1b
    orchestrator plan §2a) — flushing surfaces constraint violations
    immediately at the point of the failing row while leaving the caller's
    transaction open and reversible. The caller (a batch transaction owner
    such as `orchestrator.import_batch`, or `create_draft` below) is solely
    responsible for committing or rolling back."""
    db.add(row)
    db.flush()


def create_draft(
    db: Session,
    model_cls: type[KnowledgeModel],
    *,
    authored_by: str,
    **fields: object,
) -> KnowledgeModel:
    """Insert a new row with status='draft'. Always an INSERT — this is the
    only way to create OR "edit" content in this module: editing existing
    content means calling this again with the same business-key fields and
    new content, producing a second row, never an UPDATE of the first
    (ADR-13 append-only; verified by test_create_new_version_does_not_overwrite).

    A thin, backward-compatible wrapper over `build_draft`/`add_draft` (A1b
    orchestrator plan §2a) — external signature and behavior unchanged for
    every existing caller. `orchestrator.py` never calls this; it calls
    `build_draft`/`add_draft` directly so it can own the batch transaction
    itself (this function commits, which a multi-row batch cannot allow).
    """
    row = build_draft(model_cls, authored_by=authored_by, **fields)
    try:
        add_draft(db, row)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    return row


def submit_for_review(
    db: Session,
    row: KnowledgeModel,
    *,
    actor_user_id: str,
    reason_code: str = _DEFAULT_REASON_CODE,
    rationale: str = _DEFAULT_RATIONALE,
) -> KnowledgeModel:
    """draft -> clinical_review. ADR-13: any authenticated content author
    may do this — no specialty or self-approval check applies here (those
    only gate clinical_review -> approved, which this module never performs).

    Uses an atomic UPDATE ... WHERE status = 'draft' (matching this
    codebase's existing optimistic-concurrency convention in
    app/services/medication.py) rather than validate-then-write against the
    in-memory `row.status` — Codex review correctly flagged that two
    concurrent callers could otherwise both pass validation against a
    stale in-memory read and both commit, silently double-transitioning
    a row.

    `reason_code`/`rationale` (Slice 0, optional/backward-compatible —
    every existing caller keeps working unmodified) are recorded to
    `knowledge_lifecycle_transitions` alongside this transition.
    """
    validate_transition(
        row.status, "clinical_review", authored_by=row.authored_by, actor_user_id=actor_user_id
    )
    model_cls = type(row)
    now = dt.datetime.now(dt.UTC)
    result = db.execute(
        update(model_cls)
        .where(model_cls.id == row.id, model_cls.status == "draft")
        .values(status="clinical_review", status_changed_by=actor_user_id, status_changed_at=now)
    )
    if result.rowcount != 1:
        db.rollback()
        raise TransitionError(
            f"Row {row.id!r} was not in 'draft' status at commit time — "
            "another transition won the race. Re-fetch and re-check before retrying."
        )
    try:
        _record_transition(
            db,
            model_cls,
            knowledge_row_id=row.id,
            from_status="draft",
            to_status="clinical_review",
            actor_id=actor_user_id,
            actor_role=None,
            reason_code=reason_code,
            rationale=rationale,
            now=now,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    return row


# --- Interim RBAC gate (K1.5) -----------------------------------------
#
# No dedicated Clinical Advisor role exists yet (ADR-13 OQ-7/OQ-8 both
# "Pending PTH" per ARCHITECTURE_DECISION_INDEX.md). MEDICAL_REVIEWER is
# deliberately NOT used here: app/core/rbac.py documents it as
# "read-only — bypass read checks, blocked on writes elsewhere"
# (rbac.py:7) — reusing it for an approval WRITE would silently grant a
# capability that role was never audited for, platform-wide. This
# constant is the single place that decision lives; revisit it the
# moment a real Clinical Advisor role/identity is established (OQ-7).
_APPROVAL_CAPABLE_ROLES = frozenset({"internal_admin", "super_admin"})


class KnowledgeApprovalAuthorizationError(ValueError):
    """Raised when actor_role lacks approve/retire capability. Distinct
    from TransitionError (an illegal *state* transition) so a future API
    layer can map this to 403 and TransitionError to 409/400 separately."""


def can_approve_knowledge(actor_role: str) -> bool:
    """The ONE place the interim approval-capable role set is named
    (PTH review, 2026-07-17, non-negotiable invariant #2 — see
    MEDICATION_K1_5_APPROVAL_WORKFLOW_IMPLEMENTATION_PLAN.md §3.4/§3.5).
    No other function in this module, and no future caller (a K2+ API
    route, a script, anything), may inline its own
    `actor_role in {...}` comparison — always call this predicate (or
    assert_can_approve_knowledge below) instead. When a real Clinical
    Advisor role is established (ADR-13 OQ-7), only this function's body
    changes; approve_row/retire_row/every other caller stay untouched.

    A pure boolean predicate (not just the raising assert below) so a
    future read-only caller — e.g. an API route deciding whether to show
    an "Approve" button — can query capability without triggering an
    exception."""
    return actor_role in _APPROVAL_CAPABLE_ROLES


def assert_can_approve_knowledge(actor_role: str) -> None:
    if not can_approve_knowledge(actor_role):
        raise KnowledgeApprovalAuthorizationError(
            f"actor_role={actor_role!r} is not authorized to approve or "
            f"retire knowledge content. Allowed: {sorted(_APPROVAL_CAPABLE_ROLES)}."
        )


def assert_actor_is_not_system(actor_user_id: str) -> None:
    """Slice 0 (app/core/system_actors.py — 'Callers that need to assert a
    value is NOT a system actor, e.g. a self-approval check, should use
    this'). `assert_can_approve_knowledge` alone only checks `actor_role`,
    which this module never authenticates itself — it trusts whatever
    string a caller supplies. `validate_transition`'s self-approval check
    (`actor_user_id == authored_by`) only catches a system actor approving
    ITS OWN row; it does not catch a *different* reserved system-actor
    identity being passed as `actor_user_id` to approve/reject/retire
    someone else's (or its own, under a different reserved string) row.
    This is a second, independent identity check — never a real human
    `actor_user_id` collides with a `SystemActor` value (they are drawn
    from disjoint namespaces: real user ids vs. `system:*` strings), so
    this never rejects a real human approver."""
    if is_system_actor(actor_user_id):
        raise KnowledgeApprovalAuthorizationError(
            f"actor_user_id={actor_user_id!r} is a reserved system-actor "
            "identity. System/AI actors may never approve, reject, or "
            "retire knowledge content — only a real, authenticated human "
            "actor may perform this action."
        )


# --- Business-key lookup for auto-deprecation ---------------------------
#
# Mirrors medication_knowledge_import/versioning.py's _BUSINESS_KEY_FIELDS
# exactly (ADR-13 "Per-Table Business Key & Uniqueness Policy"). Kept as
# this module's own copy, same convention as KNOWLEDGE_TABLE_NAME above
# (the two files can't share a live import without a circular dependency;
# keep in sync by hand if either ever changes).
_BUSINESS_KEY_FIELDS: dict[type, tuple[str, ...]] = {
    DrugUsage: ("drug_ingredient_id", "locale", "audience"),
    DrugPatientEducation: ("drug_ingredient_id", "theme", "locale", "audience"),
    DrugSideEffect: ("drug_ingredient_id", "concept_code"),
    DrugMonitoring: ("drug_ingredient_id", "parameter", "patient_context"),
    DrugContraindication: ("drug_ingredient_id", "condition_type", "condition_key"),
}

# The partial unique index name per model (k1_m01_knowledge_schema — NOT
# added by K1.5, see plan §3.3). Used only to recognize, by name, the ONE
# specific IntegrityError this module is entitled to remap into the
# TransitionError taxonomy (Codex round-1 finding P1-3) — every other
# IntegrityError (a CHECK violation, an FK violation, an unrelated unique
# constraint) must surface completely unmodified, never silently absorbed
# into a business-logic exception type it doesn't actually represent.
_APPROVED_KEY_CONSTRAINT_NAME: dict[type, str] = {
    DrugUsage: "uq_drug_usage_approved_key",
    DrugPatientEducation: "uq_drug_patient_education_approved_key",
    DrugSideEffect: "uq_drug_side_effects_approved_key",
    DrugMonitoring: "uq_drug_monitoring_approved_key",
    DrugContraindication: "uq_drug_contraindications_approved_key",
}


def _is_approved_key_violation(exc: IntegrityError, model_cls: type) -> bool:
    """True iff `exc` is DEFINITIVELY a violation of THIS model's own
    approved-key partial unique index, verified via the underlying DB
    driver's own structured diagnostics (psycopg's `exc.orig.diag.
    constraint_name` on Postgres) — never by searching the rendered
    exception string.

    Codex round-2 P2-1: the original implementation matched the
    constraint name as a substring of `str(exc)` — but SQLAlchemy's
    rendered `IntegrityError` includes the bound SQL parameters (e.g.
    `[parameters: ('approved', ..., 'reviewer-1', ...)]`). A caller
    passing `actor_user_id="uq_drug_usage_approved_key"` made the
    string-match implementation misclassify an UNRELATED CHECK-constraint
    violation (missing provenance fields) as a lost approval race —
    reproduced directly: a CHECK failure became a `TransitionError`
    purely because that string happened to appear in a bound parameter,
    not because it was the actual constraint that fired. Exact structured
    lookup makes this class of false positive (and any false negative)
    impossible.

    SQLite's driver (`sqlite3.IntegrityError`) exposes no equivalent
    structured diagnostics — `exc.orig` there has no `.diag` attribute at
    all — so on SQLite this always returns False. There is no reliable
    signal to parse there, and guessing would risk the same
    misclassification this fix exists to prevent; never mapping on SQLite
    is the safe default, not a gap (the real, load-bearing proof of the
    mapping is the Postgres integration test, against the real driver)."""
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    constraint_name = getattr(diag, "constraint_name", None)
    if constraint_name is None:
        return False
    return constraint_name == _APPROVED_KEY_CONSTRAINT_NAME[model_cls]


def _deprecate_superseded(
    db: Session, row: KnowledgeModel, *, actor_user_id: str, now: dt.datetime
) -> int:
    """ADR-13: "approved -> deprecated: automatic when a newer approved
    row exists for the same business key — the old row is never deleted
    or edited." This is non-negotiable invariant #1 (PTH review,
    2026-07-17, plan §3.5): at most one approved row per business key at
    any instant. Must be called only from inside approve_row's own
    transaction (no independent commit here), and BEFORE that transaction's
    own approve UPDATE (see approve_row's inline comment — calling this
    after would transiently violate the partial unique index within the
    same uncommitted transaction, since the index is not deferred), so a
    crash or rollback between deprecating the old row and approving the
    new one is impossible — either both happen or neither does. The
    partial unique index on `status='approved'` is a second, independent
    backstop if this function is ever bypassed
    (verified directly by test_partial_unique_index_backstop_rejects_
    second_approved_row, plan §4.3 — the invariant is enforced twice, not
    trusted to one layer). Expected rowcount is 0 or 1 (the unique index
    caps live approved rows at 1 per business key); if it is ever >1
    (e.g. a pre-existing integrity violation), this still correctly
    deprecates all of them — fail-open here is safe, since deprecating
    extra approved rows only reduces exposure, never increases it."""
    model_cls = type(row)
    fields = _BUSINESS_KEY_FIELDS[model_cls]
    key_filters = [getattr(model_cls, f) == getattr(row, f) for f in fields]
    result = db.execute(
        update(model_cls)
        .where(model_cls.status == "approved", model_cls.id != row.id, *key_filters)
        .values(status="deprecated", status_changed_by=actor_user_id, status_changed_at=now)
        .returning(model_cls.id)
    )
    # Slice 0: record one transition-history row per row actually
    # deprecated by this statement (ordinarily 0 or 1 — see docstring
    # above for the >1 fail-open case). `superseded_ids` is derived from
    # this UPDATE's own `.returning()` clause — not a separate preceding
    # SELECT — so it is provably exactly the set of rows this statement
    # itself mutated, never a stale snapshot a concurrent transaction
    # could have raced between "select" and "update" (2026-07-27
    # final-checkpoint fix: the prior SELECT-then-UPDATE version could, in
    # principle, record deprecation history for a row this statement
    # never actually touched). Uses the fixed auto-deprecation reason,
    # never a caller-supplied one — this is always a system consequence
    # of approving a newer row, never a discretionary human decision with
    # its own stated reason.
    superseded_ids = [r[0] for r in result.fetchall()]
    for superseded_id in superseded_ids:
        _record_transition(
            db,
            model_cls,
            knowledge_row_id=superseded_id,
            from_status="approved",
            to_status="deprecated",
            actor_id=actor_user_id,
            actor_role=None,
            reason_code=_AUTO_DEPRECATION_REASON_CODE,
            rationale=_AUTO_DEPRECATION_RATIONALE,
            now=now,
        )
    return len(superseded_ids)


def _lock_canonical_row(db: Session, model_cls: type, row_id: str) -> KnowledgeModel:
    """Resolve the real, currently-committed row by id, locked FOR UPDATE
    (Codex round-1 finding P1-1). `approve_row`/`retire_row` must never
    trust any field on the caller-supplied `row` object other than its
    identity (`row.id`, used only to locate the row) — a detached or
    spoofed object with the right id but forged `authored_by`/business-key/
    `status` fields must not be able to influence self-approval, specialty-
    completeness, or deprecation-target checks. Every check downstream of
    this call reads the canonical row this function returns, never the
    caller's original object.

    Codex round-2 finding P1-1: a plain `SELECT ... FOR UPDATE` is NOT
    enough — if the row is already present in this Session's identity map
    (the ordinary case: a caller loaded it via `db.get()` earlier in the
    same session, then mutated an attribute in memory without persisting
    it), SQLAlchemy's default querying behavior returns the SAME cached
    Python object *without* overwriting already-loaded attributes from the
    fresh query result. Combined with this codebase's `SessionLocal`
    (`autoflush=False`, `app/core/database.py`), a caller-side in-memory
    mutation (e.g. `row.authored_by = "forged-author"`) would silently
    survive this "reload" and defeat the self-approval check — reproduced
    directly against the pre-fix code (`approve_row` incorrectly
    succeeded and persisted the forged value). `populate_existing=True`
    forces SQLAlchemy to unconditionally overwrite every already-loaded
    attribute on the identity-mapped object from this query's actual
    result row — the caller's in-memory mutation is discarded, not
    flushed (no `db.add()`/`db.merge()` involved, and `SessionLocal`
    already never autoflushes regardless). This is the ONLY change from
    the round-1 fix; `with_for_update` is unchanged.

    FOR UPDATE also gives a second benefit: it serializes concurrent
    approvers targeting the SAME row on this very statement (Postgres) —
    a second caller's SELECT...FOR UPDATE for the same id genuinely blocks
    here until the first transaction ends, ahead of and independent of the
    atomic-UPDATE rowcount check further down. SQLite does not support
    FOR UPDATE; SQLAlchemy's SQLite dialect silently omits the clause
    there (single-writer file locking makes it moot), so this is safe to
    issue unconditionally for both dialects.

    Fails closed (raises TransitionError) if the row does not exist —
    never returns None for the caller to accidentally dereference."""
    canonical = db.get(model_cls, row_id, populate_existing=True, with_for_update=True)
    if canonical is None:
        raise TransitionError(f"Row {row_id!r} does not exist.")
    return canonical


def _reject_if_pending_delete(db: Session, canonical: KnowledgeModel) -> None:
    """Fail closed if the CANONICAL row (the object `_lock_canonical_row`
    just resolved by id — never the caller-supplied `row` argument itself)
    has been marked for deletion in this session.

    Codex round-4 (finding: Codex round-3's own fix checked the wrong
    object): the round-3 version of this check ran on the caller-supplied
    `row` argument, BEFORE `_lock_canonical_row` was even called. That is
    exactly the anti-pattern every OTHER check in `approve_row`/
    `retire_row` was already hardened against (Codex round-1/2 P1-1): a
    caller can pass a DETACHED object sharing a real row's `id` but never
    itself touched by `db.delete()`. Reproduced directly against the
    round-3 code: `db.delete(real_row)` (unflushed) on the genuine
    identity-mapped object, then `approve_row(db, spoofed, ...)` where
    `spoofed = DrugUsage(id=real_row.id, ...)` was never added to `db` —
    `spoofed in db.deleted` and `sa_inspect(spoofed).deleted` were both
    `False`, so the round-3 check passed, `approve_row` returned
    `status='approved'`, and the session's still-pending `DELETE` on the
    real object fired regardless at `db.commit()` time — the row was
    gone from a fresh session despite the "successful" approval. Fixed by
    moving this check to run on `canonical` — the same object
    `_lock_canonical_row` resolved BY ID via the identity map — so it is
    the genuine, currently-tracked instance regardless of what object
    (real, detached, or spoofed) the caller happened to pass in. A
    detached caller-supplied object is a normal, supported case (only its
    `.id` is ever used, here and everywhere else in these two functions)
    — this check does not require or assume the caller's object is
    attached to `db` at all.

    Two checks, matching the two points in a session's lifecycle this can
    be observed at:
    - `canonical in db.deleted`: `session.delete()` called (on this same
      canonical object, via any reference to it) but not yet flushed
      (this `SessionLocal` has `autoflush=False`, so this is the common
      case — the check this module's own regression tests exercise).
    - `sa_inspect(canonical).deleted`: the DELETE already flushed within
      the CURRENT still-open transaction (pending commit) by some earlier
      statement in this same session.

    Does not special-case a transient, pending, or detached CALLER object
    — that is irrelevant here, since this function never receives the
    caller's object at all anymore, only the canonical one resolved by id.
    """
    if canonical in db.deleted or sa_inspect(canonical).deleted:
        raise TransitionError(
            f"Row {canonical.id!r} is marked for deletion in this session "
            "and cannot be approved or retired."
        )


def _assert_ai_provenance_complete(
    db: Session, model_cls: type, canonical: KnowledgeModel
) -> None:
    """Slice 0 §B2.3. No-op for any row whose ORIGIN (read from `canonical`
    — the re-fetched, session-locked row, never a caller-supplied field,
    same discipline as every other check in this module) is not
    `ai_synthesized`. For an `ai_synthesized` row, requires a
    `KnowledgeAIGeneration` that: targets this exact row
    (`knowledge_table`+`target_row_id`), succeeded
    (`generation_status='succeeded'`), is not superseded
    (`superseded_by_generation_id IS NULL`), and carries complete
    provenance (`model_identifier`, `prompt_template_id`,
    `prompt_template_version` all present) — raises
    `AIProvenanceIncompleteError` otherwise. A generation record
    existing is necessary but never sufficient to approve on its own:
    the human-actor gate (`assert_can_approve_knowledge`, checked before
    this function is ever reached) still independently applies."""
    if canonical.origin != "ai_synthesized":
        return
    table_name = KNOWLEDGE_TABLE_NAME[model_cls]
    # 2026-07-27 final-checkpoint fix: multiple qualifying generations can
    # legitimately exist for the same row (retries each leave their own
    # record, per the append-only design) — without an explicit ordering,
    # `.first()` picks an arbitrary one (implementation-defined query-plan
    # behavior, not a real contract), so approval could pass or fail
    # depending on which happened to come back first. Ordering by
    # `created_at` descending makes the MOST RECENT qualifying attempt
    # authoritative, deterministically — the natural "the latest retry is
    # the one that counts" semantics.
    generation = (
        db.query(KnowledgeAIGeneration)
        .filter_by(
            knowledge_table=table_name,
            target_row_id=canonical.id,
            generation_status="succeeded",
        )
        .filter(KnowledgeAIGeneration.superseded_by_generation_id.is_(None))
        .order_by(KnowledgeAIGeneration.created_at.desc())
        .first()
    )
    if generation is None or not (
        generation.model_identifier
        and generation.prompt_template_id
        and generation.prompt_template_version
    ):
        raise AIProvenanceIncompleteError(
            f"Row {canonical.id!r} has origin='ai_synthesized' but no complete, "
            "non-superseded successful generation record exists — refusing to approve."
        )


def approve_row(
    db: Session,
    row: KnowledgeModel,
    *,
    actor_user_id: str,
    actor_role: str,
    reason_code: str = _DEFAULT_REASON_CODE,
    rationale: str = _DEFAULT_RATIONALE,
) -> KnowledgeModel:
    """clinical_review -> approved (ADR-13). Atomically approves this row
    AND deprecates any prior approved row sharing its business key, in one
    transaction — see _deprecate_superseded's docstring for why these must
    not be split across two commits.

    Slice 0 provenance guard (§B2.3): an `origin='ai_synthesized'` row may
    only be approved when a complete, non-superseded, successful
    `KnowledgeAIGeneration` record exists for it — see the check inside
    the transaction below. This is in ADDITION to, not instead of, the
    existing human-actor gate (`assert_can_approve_knowledge`): AI/system
    actors were already structurally unable to approve anything (the
    closed `_APPROVAL_CAPABLE_ROLES` set never includes one), so this
    guard's whole job is proving the AI-authored row's OWN provenance is
    complete enough for the human approver to be approving something real.

    Only `row.id` from the caller-supplied `row` argument is trusted (to
    locate the row); every check (self-approval, specialty completeness,
    business key, current status, pending-delete state) reads the
    canonical row this function re-fetches from the DB via `db` itself
    (Codex round-1 P1-1) — never a caller-supplied field, and never a
    stale or spoofed value.

    Caller-object precondition (Codex round-4): `row` may be transient,
    pending, or fully DETACHED from `db` (or from any session at all) —
    that is a normal, supported case, since only `row.id` is ever read
    from it. `canonical` is always resolved via `db.get(...)` on `db`
    itself, so it is always attached to `db` specifically — every state
    check performed on `canonical` (including the pending-delete guard)
    reflects `db`'s own session state, never a different session's
    bookkeeping, even if `row` happens to be attached elsewhere.

    The entire function — including the canonical-row fetch, the specialty
    check, and transition validation, not just the final UPDATE/commit —
    runs inside one transaction boundary: any exception at any point
    rolls back and never leaves the session mid-transaction (Codex
    round-1 P1-2; plan §5's own stated invariant).
    """
    model_cls = type(row)
    now = dt.datetime.now(dt.UTC)
    try:
        # Codex round-3 P1-3 (classified false positive — see
        # MEDICATION_K1_5_COMPLIANCE_REVIEW.md §Codex Round-3 Fixes): this
        # was already a pure-Python check with no DB interaction, so
        # calling it before the `try:` never actually left the session
        # mid-transaction. Moved inside anyway, as defensive hardening,
        # so it stays inside this function's one transaction boundary
        # even if a future change ever makes it perform a DB read.
        assert_can_approve_knowledge(actor_role)
        assert_actor_is_not_system(actor_user_id)
        # Only `row.id` is ever read from the caller-supplied `row` here —
        # canonical is resolved by id FIRST, and every check after this
        # point (including the pending-delete guard) reads canonical, never
        # `row` itself (Codex round-4: round-3's pending-delete check ran
        # on `row` before canonical existed — see
        # _reject_if_pending_delete's docstring for the bypass that fixed).
        canonical = _lock_canonical_row(db, model_cls, row.id)
        _reject_if_pending_delete(db, canonical)
        _assert_ai_provenance_complete(db, model_cls, canonical)

        # Specialty completeness is re-checked against the DB at write time
        # (never trusts a caller-supplied bool) — the same reasoning as
        # every other check in this module: a stale or spoofed value must
        # not be able to force an approval.
        specialty_complete = check_specialty_completeness(db, canonical)
        validate_transition(
            canonical.status,
            "approved",
            authored_by=canonical.authored_by,
            actor_user_id=actor_user_id,
            specialty_complete=specialty_complete,
        )

        # Deprecate any prior approved row for this business key BEFORE
        # approving the new one (not after, despite the plan's narrative
        # ordering) — the partial unique index on status='approved' is not
        # deferred, so if the new row's approval UPDATE ran first, the
        # statement itself would transiently leave two 'approved' rows for
        # the same business key (the not-yet-deprecated old one and the
        # freshly-approved new one) and the index would reject it
        # immediately, before _deprecate_superseded ever got a chance to
        # run. Deprecating first avoids that transient double-approved
        # state entirely. Atomicity (invariant #1) is unaffected either
        # way: if the approve UPDATE below loses its race (rowcount != 1),
        # the whole transaction is rolled back, undoing the deprecation
        # too — so this is still all-or-nothing, just reordered.
        _deprecate_superseded(db, canonical, actor_user_id=actor_user_id, now=now)
        result = db.execute(
            update(model_cls)
            .where(model_cls.id == canonical.id, model_cls.status == "clinical_review")
            .values(status="approved", status_changed_by=actor_user_id, status_changed_at=now)
        )
        if result.rowcount != 1:
            raise TransitionError(
                f"Row {canonical.id!r} was not in 'clinical_review' status at "
                "commit time — another transition won the race. Re-fetch and "
                "re-check before retrying."
            )
        # Codex round-2 P2-2: refresh BEFORE commit, not after. The bulk
        # `UPDATE` above (Core-style, via db.execute) does not sync its
        # new values back onto `canonical`'s Python attributes on its
        # own — refresh is still needed so the returned object correctly
        # reflects the new status. But `SessionLocal` defaults to
        # `expire_on_commit=True` (unchanged here, per instruction not to
        # touch global session config), so refreshing — or any other
        # query — *after* `db.commit()` would autobegin a brand new
        # transaction that this function then returns while still open,
        # contradicting plan §5's "never leaves the session
        # mid-transaction" — reproduced directly against the pre-fix
        # code: `db.in_transaction()` was True immediately after a
        # successful approve_row call. Refreshing here, while still
        # inside the same open (uncommitted) transaction, sees our own
        # just-executed UPDATE and requires no second transaction.
        _record_transition(
            db,
            model_cls,
            knowledge_row_id=canonical.id,
            from_status="clinical_review",
            to_status="approved",
            actor_id=actor_user_id,
            actor_role=actor_role,
            reason_code=reason_code,
            rationale=rationale,
            now=now,
        )
        db.refresh(canonical)
        db.commit()
    except Exception as exc:
        db.rollback()
        # Codex round-1 P1-3: two DIFFERENT clinical_review rows can both
        # pass every in-process check above (each is individually a valid
        # clinical_review -> approved transition) and only collide at the
        # DB's partial unique index — a legitimate lost concurrency race,
        # same category as the rowcount!=1 case above, but arriving as a
        # raw IntegrityError instead of a TransitionError. Map ONLY that
        # specific, identified constraint violation into the same
        # TransitionError taxonomy plan §7 already specifies for "lost
        # optimistic-concurrency race" — chained with `from exc` so the
        # original IntegrityError is never actually discarded, just
        # re-typed. Any other IntegrityError (a CHECK violation, an FK
        # violation, a genuinely different unique constraint) is NOT this
        # module's to reinterpret — it must propagate completely
        # unmodified, since silently reclassifying an unrelated
        # programmer/data error as "someone else won a race" would hide
        # the real problem.
        if isinstance(exc, IntegrityError) and _is_approved_key_violation(exc, model_cls):
            raise TransitionError(
                f"Row {row.id!r} lost a concurrent approval race for its "
                "business key (partial unique index "
                f"{_APPROVED_KEY_CONSTRAINT_NAME[model_cls]!r})."
            ) from exc
        raise
    return canonical


def retire_row(
    db: Session,
    row: KnowledgeModel,
    *,
    actor_user_id: str,
    actor_role: str,
    reason_code: str = _DEFAULT_REASON_CODE,
    rationale: str = _DEFAULT_RATIONALE,
) -> KnowledgeModel:
    """deprecated -> retired (ADR-13, manual). The exact grace period
    between deprecation and retirement is an operational/process decision,
    not a code constraint ("a K1.5 operational decision, not architectural"
    per ADR-13) — this function does not check how long the row has been
    deprecated; if PTH wants a minimum-wait policy enforced later, that is
    a follow-up change to this function, not assumed here.

    Same canonical-row-resolution and whole-function transaction-boundary
    discipline as approve_row (Codex round-1 P1-1/P1-2; round-4
    caller-object precondition — see approve_row's docstring) — only
    `row.id` is trusted from the caller-supplied object, which may be
    transient or fully detached from any session. No partial unique index
    applies to 'retired' status, so unlike approve_row there is no
    IntegrityError to remap here (P1-3 is approve_row-specific).
    """
    model_cls = type(row)
    now = dt.datetime.now(dt.UTC)
    try:
        # See approve_row's matching comments (Codex round-3 P1-3
        # defensive hardening; Codex round-4 pending-delete guard checks
        # canonical, resolved first, never the caller-supplied `row`).
        assert_can_approve_knowledge(actor_role)
        assert_actor_is_not_system(actor_user_id)
        canonical = _lock_canonical_row(db, model_cls, row.id)
        _reject_if_pending_delete(db, canonical)
        validate_transition(
            canonical.status,
            "retired",
            authored_by=canonical.authored_by,
            actor_user_id=actor_user_id,
        )
        result = db.execute(
            update(model_cls)
            .where(model_cls.id == canonical.id, model_cls.status == "deprecated")
            .values(status="retired", status_changed_by=actor_user_id, status_changed_at=now)
        )
        if result.rowcount != 1:
            raise TransitionError(
                f"Row {canonical.id!r} was not in 'deprecated' status at "
                "commit time — another transition won the race. Re-fetch and "
                "re-check before retrying."
            )
        # See approve_row's matching comment (Codex round-2 P2-2): refresh
        # must happen before commit, inside the same open transaction —
        # never after, since `expire_on_commit=True` would otherwise make
        # any post-commit access autobegin a new transaction this
        # function then returns while still open.
        _record_transition(
            db,
            model_cls,
            knowledge_row_id=canonical.id,
            from_status="deprecated",
            to_status="retired",
            actor_id=actor_user_id,
            actor_role=actor_role,
            reason_code=reason_code,
            rationale=rationale,
            now=now,
        )
        db.refresh(canonical)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return canonical


def reject_row(
    db: Session,
    row: KnowledgeModel,
    *,
    actor_user_id: str,
    actor_role: str,
    reason_code: str,
    rationale: str,
) -> KnowledgeModel:
    """clinical_review -> rejected (Slice 0 §B2.3). Structurally identical
    to `retire_row`: same canonical-row resolution, same
    transaction-boundary discipline, same `assert_can_approve_knowledge`
    gate — no partial-unique-index interaction needed, since a rejected
    row was never approved and can never collide with the
    `status='approved'` partial unique index.

    Unlike `submit_for_review`/`approve_row`/`retire_row`,
    `reason_code`/`rationale` are REQUIRED (no default) — this is a new
    call site with no legacy callers to preserve, and a reviewer
    declining content should always be required to state why. Both must
    be PHI-free (no patient content, no free-text clinical detail beyond
    a short workflow rationale) — same discipline as
    `app/services/audit.py`'s `details` field.

    No origin-awareness guard is needed here (unlike `approve_row`) —
    rejecting is always safe regardless of a row's origin; there is no
    provenance-completeness precondition for declining content."""
    model_cls = type(row)
    now = dt.datetime.now(dt.UTC)
    try:
        assert_can_approve_knowledge(actor_role)
        assert_actor_is_not_system(actor_user_id)
        canonical = _lock_canonical_row(db, model_cls, row.id)
        _reject_if_pending_delete(db, canonical)
        validate_transition(
            canonical.status,
            "rejected",
            authored_by=canonical.authored_by,
            actor_user_id=actor_user_id,
        )
        result = db.execute(
            update(model_cls)
            .where(model_cls.id == canonical.id, model_cls.status == "clinical_review")
            .values(status="rejected", status_changed_by=actor_user_id, status_changed_at=now)
        )
        if result.rowcount != 1:
            raise TransitionError(
                f"Row {canonical.id!r} was not in 'clinical_review' status at "
                "commit time — another transition won the race. Re-fetch and "
                "re-check before retrying."
            )
        _record_transition(
            db,
            model_cls,
            knowledge_row_id=canonical.id,
            from_status="clinical_review",
            to_status="rejected",
            actor_id=actor_user_id,
            actor_role=actor_role,
            reason_code=reason_code,
            rationale=rationale,
            now=now,
        )
        db.refresh(canonical)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return canonical


def record_specialty_review(
    db: Session,
    *,
    knowledge_table: str,
    knowledge_row_id: str,
    specialty_id: str,
    reviewed_by: str,
) -> KnowledgeReviewSpecialty:
    """Record that one specialty has reviewed one knowledge row. Does not
    itself transition anything to 'approved' — see module docstring."""
    review = KnowledgeReviewSpecialty(
        knowledge_table=knowledge_table,
        knowledge_row_id=knowledge_row_id,
        specialty_id=specialty_id,
        reviewed_by=reviewed_by,
        reviewed_at=dt.datetime.now(dt.UTC),
    )
    db.add(review)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(review)
    return review


def check_specialty_completeness(db: Session, row: KnowledgeModel) -> bool:
    """True iff every specialty code in the row's ingredient's drug_class
    .required_specialties has at least one knowledge_review_specialties row
    for this exact row. Pure read — does not mutate anything.

    Fails closed (returns False), never raises, if the ingredient, its
    class, or a referenced specialty is missing — Codex review correctly
    flagged that `db.get()` returning None would otherwise crash with an
    AttributeError on the next attribute access. Production FKs prevent
    the ingredient/class case in practice, but `knowledge_review_specialties
    .specialty_id` is not FK-enforced against a live row being deleted
    later, so this stays defensive rather than trusting the constraint.

    Codex round-3 P1-2 / round-4: every `db.get()` call below passes
    `populate_existing=True` — without it, if `DrugIngredient`/`DrugClass`/
    `ClinicalSpecialty` were already present in this session's identity map
    (the realistic case: some earlier code in the same request/session
    loaded one, then mutated an attribute in memory without persisting it
    — `SessionLocal` has `autoflush=False`, so this is never silently
    flushed), `db.get()` would return the SAME cached, dirty Python object
    instead of querying the DB — letting an in-memory-only
    `DrugClass.required_specialties`, `DrugIngredient.drug_class_id`, or
    `ClinicalSpecialty.code` mutation silently decide this gate.
    `populate_existing=True` forces an unconditional reload of every
    already-loaded attribute from the actual persisted row (same
    technique as `_lock_canonical_row`) with no `db.add()`/`db.merge()`
    and no flush of anything — the caller's in-memory mutation is
    discarded, never persisted. The `ClinicalSpecialty` lookup further
    below was the last of the three missing this in round 3 — reproduced
    directly: forging an already-attached `ClinicalSpecialty.code` in
    memory (never flushed) flipped this gate's result away from the real,
    persisted code's actual match/mismatch, in both directions (a
    matching persisted code forged to a non-matching one incorrectly
    returned incomplete; a non-matching persisted code forged to the
    required one incorrectly returned complete — the latter would have
    let an approval bypass a specialty review that never actually
    happened).
    """
    model_cls = type(row)
    table_name = KNOWLEDGE_TABLE_NAME[model_cls]

    ingredient = db.get(DrugIngredient, row.drug_ingredient_id, populate_existing=True)
    if ingredient is None:
        return False
    drug_class = db.get(DrugClass, ingredient.drug_class_id, populate_existing=True)
    if drug_class is None:
        return False
    required_codes = set(drug_class.required_specialties or [])
    if not required_codes:
        return True

    reviewed = (
        db.query(KnowledgeReviewSpecialty)
        .filter_by(knowledge_table=table_name, knowledge_row_id=row.id)
        .all()
    )
    reviewed_codes = set()
    for r in reviewed:
        specialty = db.get(ClinicalSpecialty, r.specialty_id, populate_existing=True)
        if specialty is None:
            # A dangling knowledge_review_specialties.specialty_id (not
            # FK-enforced) means this row's review data is not trustworthy
            # — fail closed immediately rather than silently ignoring the
            # bad reference and evaluating completeness on the rest
            # (Codex round-2: skipping it could let an unrelated dangling
            # row coexist with valid required-specialty reviews and still
            # return True, understating the actual data-integrity problem).
            return False
        reviewed_codes.add(specialty.code)

    return required_codes.issubset(reviewed_codes)


def list_published(
    db: Session,
    model_cls: type[KnowledgeModel],
    **business_key_filter: object,
) -> list[KnowledgeModel]:
    """Query intended for future patient-facing consumption (not wired to any
    API yet — K1 dormancy, see module docstring) — filters status='approved'
    unconditionally, matching ADR-13's "GET /medications/{id}/knowledge
    filters status='approved' unconditionally — not a parameter clients can
    override" rule. Since K1.5, `approve_row` is a real write path, so this
    can genuinely return rows once something calls it; before K1.5 it always
    returned an empty list because nothing could reach 'approved' at all.
    """
    return (
        db.query(model_cls)
        .filter_by(status="approved", **business_key_filter)
        .all()
    )
