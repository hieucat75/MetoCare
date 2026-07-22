# MetoCare Medication — K1.6 Implementation Plan
## Approved Medication Knowledge Retrieval and Consumption Contract

**Status:** DRAFT — planning checkpoint, not yet approved for implementation.
**Date:** 2026-07-21
**Depends on:** K1.5 (PR #133, merged `ed99dfc`) — `approve_row`/`retire_row` write path, real `status='approved'` rows now reachable.
**Branch:** none created yet.
**Code changes:** none made yet.

---

## 0. Naming note — where this sits in the existing roadmap

No document in the repo uses the literal string "K1.6." The existing roadmap (`MEDICATION_K1_5_APPROVAL_WORKFLOW_IMPLEMENTATION_PLAN.md` §2, Phase 5) names the *next* milestone **"K2 — Knowledge API Exposure"**, gated by **EC-08** ("No public/internal API route reads from or writes to the new knowledge tables... requires its own separate GO").

K1.6, as scoped in this plan, is **narrower than and prior to K2**: it builds the internal repository-layer *read contract* (plain Python functions over SQLAlchemy) that a future K2 API route would call — but it wires **no route, no schema, no dependency injection, nothing FastAPI-visible**. EC-08 stays satisfied after K1.6. This plan explicitly does not ask for or assume a K2 GO.

No new ADR is required — this plan implements what ADR-13 already accepted (the "API impact" read invariant), it does not decide anything ADR-13 left open.

---

## 1. Current-state audit

### 1.1 Governing ADR — ADR-13 (Accepted, 2026-07-15)

The binding rule, verbatim:

> "**API impact:** `GET /medications/{id}/knowledge` (per the K0 API design) filters `status = 'approved'` unconditionally at the query layer — this is not a parameter clients can override. Draft/in-review content is visible only through an internal authoring/QA surface, out of scope for K0–K3."

Lifecycle: `draft → clinical_review → approved → deprecated (automatic) → retired (manual)`. Append-only — editing approved content always creates a new row; the old row is deprecated, never mutated/deleted. No transition skips `clinical_review`.

No effective-date / `valid_from`/`valid_to` concept exists in the accepted schema — "current" is defined purely as `status = 'approved'`, guaranteed unique per business key by a partial unique index. K1.6 must not invent scheduled/future-effective semantics not backed by schema.

Knowledge content carries **no `patient_id`/`clinic_id` column anywhere** — per ADR-01: "Public reference data. Không cần encrypt." This is global reference content, not PHI, not tenant-scoped.

### 1.2 Existing code already built for this

- `knowledge_repository.list_published(db, model_cls, **business_key_filter)` (K1-S3) already does `db.query(model_cls).filter_by(status="approved", **business_key_filter).all()` — safe by construction (kwargs can't override the hardcoded `status="approved"`), already tested, **called by nothing** (confirmed dormant, K1.5 compliance review, zero hits in `app/api`/`app/ai`/`frontend/src`).
- `DrugReference` + `KnowledgeReferenceLink` (PR #128, `app/models/drug_knowledge_references.py`) — structured citation tables, **already populated** by the A1b orchestrator's `references.py` (`find_or_create_reference`/`link_reference_to_row`), indexed on `(knowledge_table, knowledge_row_id)`. This was not part of K1.5's scope but is directly relevant to K1.6's "provenance/evidence metadata" requirement — I hadn't accounted for these tables before reading them directly; they change the read contract's shape (see §3.2).
- `KnowledgeReviewSpecialty` — internal governance metadata (which specialty reviewed a row). Per `MEDICATION_KNOWLEDGE_TEMPLATE_V1.md` §4's field-visibility table, this is **internal-only, never patient-facing** — the read contract should not expose it.

### 1.3 Schema — exact current business keys (verified directly from `app/models/drug_knowledge_content.py`, not from ADR-13's original table, which was superseded for two tables without a formal amendment)

| Table | Business key (unique among `status='approved'`) | Partial unique index |
|---|---|---|
| `drug_usage` | `(drug_ingredient_id, locale, audience)` | `uq_drug_usage_approved_key` |
| `drug_patient_education` | `(drug_ingredient_id, theme, locale, audience)` | `uq_drug_patient_education_approved_key` |
| `drug_side_effects` | `(drug_ingredient_id, concept_code)` — **not** `(..., level, concept_code)`; `level` was dropped and split into `frequency`+`action_level` by `k1_a1b_f1_schema_complete` | `uq_drug_side_effects_approved_key` |
| `drug_monitoring` | `(drug_ingredient_id, parameter, patient_context)` | `uq_drug_monitoring_approved_key` |
| `drug_contraindications` | `(drug_ingredient_id, condition_type, condition_key)` | `uq_drug_contraindications_approved_key` |

Every one of these partial unique indexes is `WHERE status = 'approved'` over exactly the business key — this is simultaneously the DB-level uniqueness guarantee **and** the ideal query index for "get current approved row."

`drug_ingredients.drug_class_id` already has a plain index (`ix_drug_ingredients_drug_class_id`) — supports the drug-class read path without a new index.

Alembic head: `k1_a1b_artifact_hash` (single head). No migration touches any of the 5 knowledge tables' indexes beyond what's listed above.

### 1.4 Existing read/API conventions to stay consistent with

From `app/services/medication.py`/`app/api/v1/routes/patients.py`/`medications.py`:
- List responses: `(total: int, items: list[Model])` tuple, `total` from a separate `count()` query, not `len(items)`.
- `limit`/`offset` clamped server-side (`limit = min(limit, 100)`), independent of any route-level clamp.
- Platform-global reference data (the `/medications/suggest` drug-catalog autocomplete) uses `require_roles(...)` at the **route** layer, not an ownership check — the closer precedent for this subsystem than patient-scoped reads.

### 1.5 Anticipated future consumers (so the contract is shaped for real needs)

- **ADR-07 (AI Knowledge Source, Proposed, Gate 3):** names a planned `_build_medications_with_knowledge()` context-builder enhancement needing, per medication, a `knowledge` sub-object (`common_use`, `caution_summary`, `requires_monitoring`, `evidence_note`) sourced via a `fetch_drug_knowledge(drug_product_id)`-shaped call — explicitly for **multiple concurrent medications in one context-assembly pass** → this is the concrete motivation for a **batch** retrieval function.
- **Frontend placeholders** (`SideEffectsCard`, `InteractionsCard`, `UsageInstructionsCard`) are pre-built, called with `[]` today, waiting for a backend contract. Their prop shapes do **not** exactly match the DB enums (`SideEffectsCard`'s `common/uncommon/urgent` vs the DB's `frequency: common/uncommon/rare/unknown` + `action_level: self_monitor/contact_clinician/urgent_medical_help`) — this mismatch is **already known and documented** (`MEDICATION_KNOWLEDGE_TEMPLATE_V1.md` §9.5, PTH-pending). K1.6 does not attempt to resolve it — that's a K2/frontend-contract decision.
- **ADR-14 (Patient Context Resolution, K4):** explicitly requires the Context Engine to stay a **separate domain** from the plain knowledge read contract — quotes PTH directly: *"Knowledge không nên trộn Context."* K1.6's contract must stay patient-neutral; any personalization is K4's job, layered on top, never merged into this module's queries.

---

## 2. Retrieval invariants

1. **Only `status='approved'` rows are ever returned.** Hardcoded in every query — never a parameter a caller can override (same safety property `list_published` already has).
2. **Never `draft`/`clinical_review`/`deprecated`/`retired`.**
3. **Deterministic per full business key** — guaranteed by the DB's own partial unique index. The read layer must not *assume* this and silently pick a winner if it's ever violated (see invariant 6).
4. **Version history / superseded rows:** correctly invisible to "current" reads. Since `approve_row` deprecates the prior row in the *same* atomic transaction as the new approval, a reader can never observe zero or two "approved" rows for one business key mid-transition — Postgres MVCC + K1.5's own atomicity guarantee this. K1.6 does **not** expose a history/audit-trail read surface — that's explicitly out of scope (ADR-13: "internal authoring/QA surface, out of scope for K0–K3").
5. **Effective-date semantics:** not supported by schema, not invented here. "Approved" = immediately effective.
6. **Fail closed on inconsistency.** If a query for one business key's approved rows ever returns more than one row (should be structurally impossible given the partial unique index, but K1.5's own defense-in-depth philosophy — "the invariant is enforced twice, not trusted to one layer" — applies here too): raise a domain exception, **never** silently return the first/last/arbitrary row.

---

## 3. Required read contracts

Proposed module: **`backend/app/services/knowledge_retrieval.py`** (new file, separate from `knowledge_repository.py` — read path and write path are different concerns, and keeping them in one file would push it past a reasonable size). `knowledge_repository.py` is **not modified** — no defect was found in it, so per your instruction it stays untouched.

### 3.1 Exceptions

```python
class KnowledgeRetrievalError(Exception):
    """Base for this module's domain exceptions."""

class MultipleApprovedRowsError(KnowledgeRetrievalError):
    """More than one 'approved' row was found for a business key — should be
    structurally impossible given the partial unique index, but this module
    verifies it at read time anyway (defense-in-depth, matching K1.5's own
    invariant-#1 philosophy) rather than trusting the constraint blindly."""

class UnknownBusinessKeyFieldError(KnowledgeRetrievalError):
    """Caller passed a business-key filter kwarg that isn't part of this
    model's actual business key — fails closed rather than silently
    building a filter that matches nothing, or (worse) something wrong."""

class MissingBusinessKeyFieldError(KnowledgeRetrievalError):
    """Caller's business-key filter is missing a field this model's
    business key requires — added during implementation per PTH's
    original sign-off (a free-form kwargs dict must fail closed on a
    missing field, not just an unknown one)."""

class UnsupportedKnowledgeModelError(KnowledgeRetrievalError):
    """`model_cls` is not one of the 5 supported ADR-13 knowledge models —
    added in Codex Round 2 (finding P2-1): every public function now
    raises this SAME exception for an unsupported model_cls, including the
    two batch functions called with an empty id list, which previously
    skipped validation entirely and silently returned `{}`."""
```

`None` (not an exception) represents "no approved row exists" for a single-row lookup — a normal, expected outcome, not an error condition.

### 3.2 Functions

```python
def get_current_by_business_key(
    db: Session, model_cls: type[KnowledgeModel], **business_key_filter: object,
) -> KnowledgeModel | None:
    """The one 'approved' row for this exact business key, or None.
    Validates business_key_filter's keys against _BUSINESS_KEY_FIELDS[model_cls]
    (fails closed with UnknownBusinessKeyFieldError on a typo'd/wrong field —
    never silently ignores it). Raises MultipleApprovedRowsError if the query
    ever returns >1 row (invariant 6)."""

def list_current_for_ingredient(
    db: Session, model_cls: type[KnowledgeModel], drug_ingredient_id: str,
) -> list[KnowledgeModel]:
    """Every 'approved' row for one ingredient (e.g. all approved side
    effects). Deterministic order: by this table's own secondary
    business-key columns (e.g. drug_side_effects orders by concept_code;
    drug_monitoring by parameter, patient_context) — a stable, meaningful
    tiebreaker already covered by the existing partial index's trailing
    columns, no new index needed."""

def list_current_for_drug_class(
    db: Session, model_cls: type[KnowledgeModel], drug_class_id: str,
) -> list[KnowledgeModel]:
    """Every 'approved' row across all ingredients in one drug class. Joins
    through DrugIngredient (ix_drug_ingredients_drug_class_id), ordered by
    ingredient name_inn then this table's own business-key tiebreaker."""

def get_current_batch(
    db: Session, model_cls: type[KnowledgeModel], drug_ingredient_ids: list[str],
) -> dict[str, list[KnowledgeModel]]:
    """Approved rows for MULTIPLE ingredients in one query (IN (...) on the
    same partial index) — the shape ADR-07's future context-builder
    enhancement needs to avoid N+1 queries across a patient's active
    medication list. Every requested ingredient_id is present as a dict key
    (empty list if it has no approved rows for this table) — never silently
    omitted, so callers can safely index without a fallback."""

def list_references_for(db: Session, model_cls: type[KnowledgeModel], row_id: str) -> list[DrugReference]:
    """**Identity-based provenance lookup** — citations for `(model_cls,
    row_id)`, via KnowledgeReferenceLink (ix_knowledge_reference_links_row).
    Empty list if none exist — never fabricates a citation. Kept separate
    from the functions above (not auto-joined) so callers who don't need
    citations don't pay the extra query — matches this codebase's existing
    pattern of keeping specialty-review and reference-linking as separate
    concerns from the core row fetch."""

def list_references_for_batch(db: Session, model_cls: type[KnowledgeModel], row_ids: list[str]) -> dict[str, list[DrugReference]]:
    """Batch form of list_references_for — one query for citations across
    multiple rows of the same model, so a consumer fetching references for
    every row in a get_current_batch/list_current_for_ingredient result
    isn't forced into an N+1 query per row."""
```

**Implementation note (post-Codex-Round-1, superseding this section's original signature):** `list_references_for`/`list_references_for_batch` take `(model_cls, row_id)` — a primitive identifier, not the ORM `row` object this section originally specified. This is a deliberate hardening applied during implementation (PTH review requirement #3: every public function must take primitive identifiers only, never a caller-supplied ORM row) — the signature above reflects the actual, shipped code, not the pre-implementation draft.

**Provenance contract decision (Codex Round 1, finding P1-1 → PTH review, Option A):** `list_references_for`/`list_references_for_batch` are an **identity-based provenance lookup** — they do NOT verify that `row_id` refers to a currently `approved` row, or that it exists at all. This was initially flagged as a possible defect (the module is named an "Approved... Retrieval Contract"), then downgraded to a documented design choice: the caller is responsible for first resolving an approved/current row via one of the other 5 functions before calling either of these two with that row's id. This module's "approved-only" invariants (§2) apply to `get_current_by_business_key`/`list_current_for_ingredient`/`list_current_for_drug_class`/`get_current_batch` only — not to the two provenance-lookup functions, whose entire purpose is resolving citations FOR an already-identified row, not independently re-validating which rows are current.

Deliberately **not** exposed here: reviewer identity / `knowledge_review_specialties` rows (internal-only per the template doc's field-visibility table), any history/audit query, any effective-dating parameter.

Every function takes **primitive identifiers only** (`drug_ingredient_id: str`, business-key values as plain strings) — never a caller-supplied ORM object. This sidesteps the entire class of identity-map-staleness bugs K1.5 spent 4 review rounds fixing on the write side: there is no "caller-supplied row" trust boundary to defend on the read side, because there's no caller-supplied row at all. Every `SELECT`/`Query` in this module still uses `.populate_existing()` regardless, so a row already dirty-in-memory elsewhere in the same session can never be returned stale (same technique as `_lock_canonical_row`, applied here as a read-side habit, not because a caller object is trusted).

---

## 4. Consumption boundary

- **`knowledge_retrieval.py` is the only sanctioned read surface.** Any future consumer (K2 API route, ADR-07's context-builder enhancement, an internal script) calls through these functions — never issues its own `db.query(DrugUsage)`/`select(DrugSideEffect)` directly. Stated explicitly in the new module's own docstring, enforced the same way K1's dormancy has always been enforced: `grep -rln "drug_usage\|drug_patient_education\|drug_side_effects\|drug_monitoring\|drug_contraindications" app/api app/ai frontend/src` must return zero hits, forever, until a K2 GO explicitly authorizes a route.
- **Boundary vs. domain service vs. adapter:** `knowledge_retrieval.py` is the repository/domain layer (talks SQLAlchemy directly). A future K2 API route is a thin adapter translating HTTP → these function calls → a response schema. A future K4 Context Engine (ADR-14) is a *separate* domain service that itself calls into this module (never bypasses it) and layers personalization on top — this module never reaches into Context Engine concerns.
- **Subsystem stays dormant after K1.6** — same as K1.5: a read path existing here does not mean anything calls it.
- **`list_published` is left as-is.** It is not a defect (it correctly filters `status='approved'` unconditionally, per ADR-13) — just superseded in practice by the richer functions above. I'm not touching its file or docstring in K1.6, per your instruction not to change K1.5 without a real defect; if you'd like it formally marked deprecated later, that's a separate, explicitly-approved documentation change to `knowledge_repository.py`.

---

## 5. Security and clinical safety

- **Tenant/user scope:** none needed — no `patient_id`/`clinic_id` column exists on any of the 5 tables (global reference content, confirmed ADR-01).
- **RBAC for internal reads:** **no role check inside `knowledge_retrieval.py` itself.** ADR-13 already establishes "approved" == cleared for general consumption; the repository layer's job is the query-level invariant (status filter), not caller identity. This mirrors `list_published`/`check_specialty_completeness` (no `actor_role` parameter today). Any future API-route-level RBAC (which authenticated roles may call the eventual endpoint) is deliberately deferred to K2 — out of scope here, matches "không mở API."
- **Provenance mandatory:** `list_references_for` surfaces `DrugReference` citations; the read side never fabricates one if none exists (fails closed to an empty list, not a guess).
- **Stale/retired knowledge:** never returned by any function in this module. A future audit/QA surface (if ever needed) would be a separate, explicitly-scoped module with its own RBAC gate — not folded into this one.
- **No silent fallback:** `MultipleApprovedRowsError` exists specifically so a data-integrity violation is never silently resolved by picking a row.
- **No caller-supplied ORM state:** every function signature takes primitives only (§3.2) — structurally prevents the write-side's entire K1.5 bug class from having an analogue here.

---

## 6. Database behavior

- **`get_current_by_business_key`** — exact match against the table's own partial unique index (`uq_<table>_approved_key`). O(log n) index scan, at most one row can ever match.
- **`list_current_for_ingredient`** — prefix scan on the same partial index (`drug_ingredient_id` is its leading column); the index's own trailing columns give free, meaningful, deterministic ordering with no extra sort step or new index.
- **`list_current_for_drug_class`** — two-hop join (`ix_drug_ingredients_drug_class_id` → per-table partial index), both sides already indexed.
- **`get_current_batch`** — `IN (...)` scan on the same partial index; efficient for realistic batch sizes (a patient's active-medication list, typically well under 100 ingredients).
- **`list_references_for`** — uses `ix_knowledge_reference_links_row (knowledge_table, knowledge_row_id)`, already the exact lookup direction needed.
- **No index exists for "history ordered by `status_changed_at`"** — not needed, since K1.6 doesn't expose history. If a future QA/audit surface needs it, that slice adds `(drug_ingredient_id, status_changed_at DESC)` then, not now.

**Migration decision: none required.** Every read path this plan proposes is already fully supported by indexes that exist today. This matches the roadmap's own independent prediction for the eventual K2 phase ("Migration: None expected (pure read API over existing tables)").

---

## 7. Test plan

**SQLite unit (`backend/tests/test_knowledge_retrieval.py`):**
- `get_current_by_business_key`: happy path; zero-approved-rows → `None`; multiple historical versions (draft/clinical_review/approved/deprecated/retired coexisting over time) → only the approved one returned; unknown business-key kwarg → `UnknownBusinessKeyFieldError`; a direct-ORM-bypass double-approved-row (same technique as K1.5's `TestPartialUniqueIndexBackstop`) → `MultipleApprovedRowsError`, not a silent pick.
- `list_current_for_ingredient` / `list_current_for_drug_class`: multiple approved rows, correct set, correct exclusion of non-approved rows and cross-ingredient/cross-class rows; **deterministic ordering** — assert identical order across repeated runs and across randomized insertion order.
- `get_current_batch`: multiple ingredients in one call, correct per-ingredient grouping; an ingredient with zero approved rows still present with an empty list; duplicate ingredient_ids in input handled sanely (documented + tested behavior, not left implicit).
- `list_references_for`: zero, one, and many-to-many (one reference cited by multiple rows) cases.
- **Identity-map staleness:** an attached, dirty (unflushed) row with a forged in-memory `status='approved'` (on an actually-draft row) must never appear in results — proves `.populate_existing()` is actually applied, not just documented.
- **Dormancy boundary:** `grep` check, 0 hits in `app/api`/`app/ai`/`frontend/src` for the new module's functions.

**PostgreSQL integration (`backend/tests/integration/test_medication_k1_6_knowledge_retrieval_postgres.py`):**
- **Concurrent approve/read visibility:** real threads — one committing `approve_row` (paused mid-transaction via the same monkeypatch technique K1.5's race tests use), one concurrently calling `get_current_by_business_key` — assert the reader only ever observes the pre- or post-transition single approved row, never zero or two.
- **Query-plan sanity (new for K1.6):** `EXPLAIN` the actual queries and assert the partial unique index / `ix_drug_ingredients_drug_class_id` is chosen by the planner — catches a future rewrite that accidentally defeats the index, since nothing else in this program has needed this class of check yet.
- **Partial-unique-index backstop, read side:** bypass the service layer, insert two real `approved` rows directly (same technique as K1.5), assert `get_current_by_business_key` raises `MultipleApprovedRowsError` against the real constraint, not a hypothetical.

---

## 8. Scope exclusions

No UI. No public API route. No AI integration. No Phase B clinical content. No bulk ingestion. **No change to K1.5** (`knowledge_repository.py`/its tests untouched — no defect found). No history/audit-trail read surface. No effective-dating/scheduling logic. No new RBAC primitive (deferred to K2's route layer). No migration.

---

## 9. Files expected to change

**New only — zero diff to any existing file:**
- `backend/app/services/knowledge_retrieval.py`
- `backend/tests/test_knowledge_retrieval.py`
- `backend/tests/integration/test_medication_k1_6_knowledge_retrieval_postgres.py`
- `docs/medication-management/MEDICATION_K1_6_KNOWLEDGE_RETRIEVAL_IMPLEMENTATION_PLAN.md` (this file)
- (post-implementation, separate step) `docs/medication-management/MEDICATION_K1_6_COMPLIANCE_REVIEW.md`

---

## 10. Risks

1. **Naming/roadmap mismatch** — "K1.6" isn't a roadmap-named milestone; the existing docs call the API-wiring phase "K2." Mitigation: this plan explicitly frames K1.6 as pre-K2, non-overlapping with EC-08.
2. **Scope-creep temptation** — easy to "just add a thin route for testing." Mitigated by the same dormancy grep check used throughout K1/K1.5, run at every review round.
3. **Frontend shape mismatch** (`SideEffectsCard`'s enum vs. DB's `frequency`/`action_level`) — pre-existing, already documented, PTH-pending. K1.6 does not attempt to resolve it.
4. **`MultipleApprovedRowsError` may look like dead code** to a future reviewer, since the partial unique index is supposed to make it unreachable — noting this reasoning up front (defense-in-depth, same philosophy as K1.5's own invariant #1) so a future review round doesn't flag it as decorative without understanding why it's there.
5. **`get_current_batch`'s "empty list vs. omit" semantics** for an ingredient with no approved rows — a minor decision point; this plan defaults to "always present, empty list if none" (safer for callers doing dict lookups) and documents it rather than blocking on a formal decision.
6. **Performance** — no concern identified at current/expected data volumes; revisit only if real content scales far beyond the Phase 4 pilot.

---

## 11. Acceptance gates

- 0 P0/P1/P2 across all Codex-style adversarial review rounds (same process K1.5 used) before merge.
- Full SQLite + PostgreSQL test suite green.
- Zero migration (`alembic heads` unchanged, single head).
- Zero hits for the new module anywhere in `app/api`/`app/ai`/`frontend/src` (dormancy).
- Zero diff to `knowledge_repository.py`/`test_knowledge_repository.py` unless a genuine defect is found and separately approved.
- Compliance review doc written, same rigor as K1.5's.
- Explicit PTH sign-off before merge.

## 12. Sequence

1. **This checkpoint** — PTH reviews and approves (or requests changes to) this plan.
2. Create branch (name TBD at approval time, e.g. `feat/medication-k1-6-knowledge-retrieval-contract`).
3. TDD: `get_current_by_business_key` first (red → green), then the remaining four functions, one at a time.
4. PostgreSQL integration tests (concurrency, query-plan sanity, backstop).
5. Self-review + adversarial Codex-style review rounds until 0 P0/P1.
6. Compliance review doc.
7. PTH sign-off → commit → PR → merge (same governance flow as PR #133).
8. **Stop.** Do not proceed to K2 (API wiring) without a separate, explicit GO.

---

## Verdict: **READY TO IMPLEMENT K1.6**

ADR-13 is Accepted and unambiguous on the governing invariant; every proposed read path is already covered by existing indexes (no migration); the write-side (K1.5) needs no changes (no defect found); no new ADR is required (this plan implements what ADR-13 already decided, it doesn't decide anything new). The only open items (batch empty-list default, frontend enum reconciliation) are either resolved with a documented, reversible default in this plan or explicitly deferred to a later, separately-scoped decision — neither blocks starting implementation.

Waiting at this planning checkpoint for your approval before any branch or code is created.
