# Medication Knowledge — Phase A1b Orchestrator Implementation Plan

**Date:** 2026-07-17
**Status:** 🟡 **Planning GO — implementation NOT GO.** This document is itself
subject to review/approval before any `versioning.py`/`orchestrator.py` code
is written. Phase B authoring has not started and is not authorized by this
plan.
**Depends on (both merged):**
- PR #128 — F1 schema completion (`drug_references`, `knowledge_reference_links`,
  `drug_side_effects.frequency`/`action_level` split) → `main` @ `cc4d6c1`
- PR #129 — F2 specialty seed (7-code `clinical_specialties` vocabulary) →
  `main` @ `b2c4f26`
- PR #130 — A1a schema alignment (importer contract matches the F1 schema) →
  `main` @ `659e542`

**Supersedes/extends:**
- `MEDICATION_PHASE_A_PR_A1_IMPLEMENTATION_PLAN.md` §4 (idempotency), §6
  (preview), §7 (test matrix), §8 (PR split), §9 (risks) — this document goes
  deeper on the orchestrator/versioning piece specifically; where the two
  disagree, this document is the more current one for A1b.
- `MEDICATION_PHASE_A_BLOCKING_FINDINGS.md` — Findings 1 and 2 are now
  **✅ Resolved** (see that file's updated status section). This plan is the
  direct unblock of both.

**Unblocked-per-original-gate:** the earlier plan (§8) explicitly said A1b
"must not persist knowledge content while references would be silently
dropped or specialty validation silently bypassed," gated on Finding 1 and
Finding 2. Both are now closed. This plan is the next step, not a new
decision to start A1b — the decision to start A1b was already made when F1/F2
were approved; this document is the *how*.

---

## 0. Scope of this document

Planning only. No code in this PR/commit. The deliverable is this plan; the
next deliverable (a separate PR, after this plan is approved) is
`versioning.py` + `orchestrator.py` + reference-persistence helpers +
their tests.

Everything below locks the 13 invariants PTH specified, each as its own
numbered section with: the rule, why, the concrete design, and the test(s)
that will prove it.

---

## 1. Batch load/validate before write

**Rule:** every file in a batch is loaded, schema-validated, business-rule
validated, and identity/specialty-resolved *before* any database write is
attempted for *any* file in the batch.

**Design — two phases, matching the already-Accepted plan (§4 of the A1
plan) exactly, extended to cover A1b's new resolution steps:**

**Phase 1 — pure, no writes (except read-only DB lookups):**
For each file in the batch, in order:
1. `loader.load_file(path)` → raw dict
2. `KnowledgeFile.model_validate(raw)` → typed, schema-valid object
3. `validators.validate_business_rules(knowledge_file)` → list of errors
   (specialty-code structural check, duplicate-reference-in-file check)
4. `provenance.resolve_medication_identity(db, name_inn)` → real
   `DrugIngredient` row, or `IdentityResolutionError`
5. For every `specialty_codes` entry: `provenance.check_specialty_exists(db, code)`
   — **new for A1b**: now meaningful, since F2 seeded the table. A code that
   passes A1a's structural allowlist check but fails this DB-existence check
   is a batch error (see §6, fail-closed).
6. `versioning.resolve_version_action(db, ...)` (new module, §3 below) — a
   **read-only** decision against current DB state: `NEW_DRAFT` / `NO_OP` /
   `REJECT_VERSION_CONFLICT` / `WARN_PROCEED`. `REJECT_VERSION_CONFLICT` is
   collected as a batch error, same severity as a schema/validation failure
   — not silently skipped, not treated as "that file's problem alone."

Each file's outcome is either a fully-resolved `ImportPlan` (validated
content + resolved ingredient id + resolved specialty ids + version action)
or a list of errors. Nothing is written to the database in this phase.

**Phase 2 — write, only entered if Phase 1 produced zero errors across the
entire batch** (see §2 for the transaction, §7 for what "zero errors" means
under partial failure).

**Rejected alternative:** validate-and-write file-by-file (stream
processing). Rejected because it cannot satisfy §7's whole-batch rollback
requirement without either (a) a running transaction held open across
however long Phase 1 validation of *later* files takes (bad — long-held
locks, and a later file's failure would still need to undo earlier files'
commits, i.e. you'd need the two-phase design anyway), or (b) accepting
partial-batch writes, which PTH's own §7 test matrix already forbids
(`test_rollback_partial_batch_failure` in the original plan).

**Tests:** `test_medication_knowledge_import_orchestrator.py::test_valid_batch_produces_import_plans_no_writes`,
`::test_phase1_never_calls_db_add_or_commit` (assert via a Session spy/mock
that `add`/`commit` are never called during Phase 1, only queries).

---

## 2. Transaction boundary

**Rule:** one batch = one transaction. All-or-nothing.

**Design:** matches K1-S2's own migration-write pattern and the existing
plan's §4 language exactly: Phase 2 opens exactly one `db` transaction
(the same `Session` used for Phase 1's read-only queries — no new
connection), performs every write for every `ImportPlan` in the batch
(`create_draft` calls + reference find-or-create + link creation, §4/§5),
then commits **once** at the end. Any exception anywhere in Phase 2 —
expected (a constraint violation we didn't predict) or unexpected (a bug) —
triggers `db.rollback()` before re-raising, mirroring
`knowledge_repository.create_draft`'s own existing
`try: db.commit() except: db.rollback(); raise` convention (reused, not
reinvented — `orchestrator.py` should call the existing `create_draft`, not
duplicate its commit/rollback logic).

**Explicit non-goal:** per-file sub-transactions / savepoints inside the
batch. A single flat transaction is sufficient and simpler; savepoints would
only matter if partial-batch-success were an acceptable outcome, which §7
already rules out.

**Single caller-visible outcome shape:** `orchestrator.import_batch(...)`
returns a `BatchResult` (dataclass) with `success: bool`,
`errors: list[FileError]` (empty iff `success`), `written: list[WrittenRow]`
(empty iff `not success` or `dry_run`), `dry_run: bool`. The caller (a CLI
script, never a route — see §12) gets one object to inspect, not a partial
mix of "some worked."

**Tests:** `test_batch_write_is_atomic_across_files` (N files, force an
exception on write of file K via a monkeypatched `create_draft` that raises
on the Kth call → assert zero rows across all 5 knowledge tables + zero
`drug_references`/`knowledge_reference_links` rows after rollback, on both
SQLite and Postgres per §11).

---

## 3. Idempotency by business key + content hash

**Rule:** re-running the same file (or an equivalent file) must never create
a duplicate draft. Reuses the exact 4-way decision matrix already specified
and PTH-approved in the original plan §4 — restated here as the concrete
`versioning.py` contract A1b implements:

**New module `versioning.py`:**

```python
def business_key_for(knowledge_type: str, ingredient_id: str, content: BaseModel) -> tuple:
    """Per-type business key, per the original plan's §4 table:
    usage: (ingredient_id, locale, audience)
    patient_education: (ingredient_id, theme, locale, audience)
    side_effect: (ingredient_id, concept_code)   # NOT (..., level, ...) — F1 removed level
    monitoring: (ingredient_id, parameter, patient_context)
    contraindication: (ingredient_id, condition_type, condition_key)
    """

def content_hash(knowledge_type: str, content: BaseModel) -> str:
    """SHA-256 over the type-specific content fields ONLY (never provenance/
    metadata fields) — same technique as this session's own K1-S2 catalog
    checksum verification. Field set per type is fixed and explicit (no
    reliance on dict ordering)."""

class VersionAction(enum.Enum):
    NEW_DRAFT = "new_draft"                    # new business key, or new version + new content
    NO_OP_ALREADY_IMPORTED = "no_op"            # same key, same version, same content hash
    REJECT_VERSION_CONFLICT = "reject"          # same key, same version, DIFFERENT content hash
    WARN_PROCEED_REPEATED_CONTENT = "warn_proceed"  # same key, new version, but content hash
                                                     # matches an existing (any-status, non-retired) version

def resolve_version_action(
    db: Session, model_cls: type, business_key: tuple, version: str, content_hash_value: str
) -> VersionAction:
    """Pure decision (read-only query), no writes. Looks up the most recent
    non-'retired' row for this business key."""
```

**Fail-closed on `REJECT_VERSION_CONFLICT`:** this is a batch error (§1),
never a silent skip and never a silent overwrite — "a version string is a
promise that its content is fixed" (original plan §4, unchanged).

**Tests:** `test_medication_knowledge_import_versioning.py` — one test per
`VersionAction` outcome, plus the concurrency test already specified in the
original plan §7 (two importer invocations racing the same business key;
worst case is a harmless duplicate draft row, proven bounded, not
eliminated — no distributed locking, matching the accepted single-writer
operational constraint).

---

## 4. New version creates a new row, never overwrites history

**Rule:** `NEW_DRAFT` and `WARN_PROCEED_REPEATED_CONTENT` both mean "call
`create_draft`" — an INSERT. There is no code path in `orchestrator.py` that
calls `UPDATE` against a knowledge-content row's fields. (The one existing
`UPDATE` in this codebase's knowledge stack, `submit_for_review`'s
status-only atomic transition, is untouched by A1b — orchestrator never
calls it; see §6.)

**Design:** `orchestrator.py` reuses `knowledge_repository.create_draft`
unchanged (no new "upsert" helper is added to that module — adding one
would be the exact overwrite footgun this invariant forbids). Old rows for
the same business key are left byte-for-byte untouched; the new row is a
sibling, not a replacement. This is the same guarantee K1-S3's own
`test_create_new_version_does_not_overwrite` already proves at the
`create_draft` level — A1b's tests prove it at the batch/orchestrator level
on top.

**Tests:** `test_version_bump_creates_sibling_row_old_row_unchanged`
(asserts old row's `id`, `created_at`, and content fields are bit-identical
before/after a version-bump import).

---

## 5. Persist structured references and links

**Rule:** every reference in a knowledge file's `references:` list becomes a
real `drug_references` row (reused if an equivalent one already exists) and
a real `knowledge_reference_links` row joining it to the new draft. This is
the actual "A1b must not persist knowledge content while references would be
silently dropped" gate from Finding 1 — now buildable since F1 (#128) exists.

**Design — find-or-create, using F1's two-tiered identity (not a naive
INSERT that could race the partial unique indexes):**

1. If `reference.document_identifier` is set: query
   `drug_references WHERE document_identifier = :doc_id AND source_version = :v AND accessed_at = :d`.
2. Else: query
   `drug_references WHERE publisher = :p AND title = :t AND publication_date = :pd AND source_version = :v AND accessed_at = :d`.
3. If found, reuse its `id`. If not, INSERT a new `DrugReference` row inside
   the same open transaction (§2) — a genuine race here (two batches citing
   the same new reference concurrently) is the same accepted class of risk
   as §3's business-key race; not solved with locking, bounded to "harmless
   duplicate reference row," which is itself dedup-able later since the
   partial unique index still prevents a *third* duplicate.
4. INSERT a `KnowledgeReferenceLink` row: `knowledge_table` = the model's
   table name (reusing `knowledge_repository.KNOWLEDGE_TABLE_NAME`),
   `knowledge_row_id` = the new draft row's id, `drug_reference_id` = the
   resolved reference id.

**Never a placeholder / never re-serialized into `source: VARCHAR(255)`:**
the existing `source` column on each knowledge row is still populated from
`review_metadata.source` (unchanged, still useful as an at-a-glance summary
per the original plan §3) — but it is not where reference persistence
*lives*. `drug_references`/`knowledge_reference_links` are the real,
queryable relation Finding 1 required.

**Fail-closed:** if reference persistence fails for any reason mid-batch
(FK violation, unexpected constraint hit), the whole-batch rollback (§2)
applies — a knowledge row is never left committed without its references.

**Tests:** `test_reference_persisted_and_linked_to_new_draft`,
`test_reference_reused_not_duplicated_across_two_items_same_citation`,
`test_reference_reused_across_different_access_dates_creates_two_rows`
(exercises F1's `accessed_at`-inclusive identity directly at the
orchestrator level, not just the migration level).

---

## 6. Specialty validation from DB

**Rule:** `orchestrator.py` checks every declared `specialty_codes` entry
against real `clinical_specialties` rows via
`provenance.check_specialty_exists(db, code)` — not just A1a's structural
Python allowlist (`validators.ALLOWED_SPECIALTY_CODES`), which only proves
"this is a plausible code," not "this code exists as reviewable metadata."

**Fail-closed:** an unknown/inactive code is a batch error (§1), collected
alongside schema/validation errors — never silently dropped from the file's
`specialty_codes` list, never silently accepted.

**Not in scope for A1b:** actually recording a specialty's *review*
(`record_specialty_review`, K1-S3) — that's a separate action taken by a
Clinical Advisor after content is drafted, not something the importer does.
A1b only validates that a *declared* specialty code is real; it does not
create `knowledge_review_specialties` rows.

**Tests:** `test_unknown_specialty_code_rejected_at_db_level` (a code that
passes the A1a structural allowlist — i.e. one of the 7 — but has been
deactivated (`is_active=False`) in the test's seed fixture, proving this is
a genuine DB check and not a re-implementation of the Python allowlist).

---

## 7. Draft-only — absolutely never create `approved`

**Rule:** restated from the original plan §9's strongest risk, re-affirmed
explicitly here because A1b is the PR that actually writes rows.

**Design (enforced by construction, not by a runtime flag):**
- `orchestrator.py` calls `knowledge_repository.create_draft` exclusively.
  It never calls `submit_for_review` (which only ever targets
  `'clinical_review'`, never `'approved'`, per K1-S3's own scope lock — but
  A1b doesn't call it at all, since nothing in the importer flow submits
  content for review; that's a separate human action after drafting).
- `orchestrator.py` never imports or calls `validate_transition` with any
  target other than none at all — it doesn't need to call it, since
  `create_draft` always hardcodes `status="draft"`.
- No new "bulk approve" or "auto-approve trusted sources" helper is added
  anywhere in this PR, ever, under any flag.

**CI/PR-diff stop gate (mandatory, same mechanism as the original plan
§7/§9):** the A1b PR's review (Codex + compliance + architecture, all
mandatory per this project's standing convention) must explicitly grep the
diff for the string `"approved"` and for any `validate_transition` call —
zero occurrences outside test fixtures that assert the *rejection* of an
approved-targeting attempt. Every test in the new test files also asserts
`status='approved'` count is 0 across all 5 tables at teardown, matching
K1-S3's `test_zero_approved_rows_exist_anywhere` convention exactly.

---

## 8. Fail-closed if identity/reference/specialty is invalid

**Rule:** three independent fail-closed gates, all already individually
designed above — restated together here since PTH called them out as one
invariant:

| Check | Failure mode | Where | Behavior |
|---|---|---|---|
| Medication identity | `name_inn` doesn't resolve to a real `drug_ingredients` row | `provenance.resolve_medication_identity` | Raises `IdentityResolutionError` → batch error (§1). Never creates a placeholder ingredient. |
| Reference | malformed shape | already A1a's job (schema.py, PR #130) | Rejected before Phase 1 even reaches provenance checks. |
| Reference | valid shape but persistence hits an unexpected constraint (e.g. concurrent write raced past the find step) | §5's find-or-create, inside the write transaction | Whole-batch rollback (§2) — never partially persists a knowledge row without its reference. |
| Specialty | code doesn't exist / is inactive in `clinical_specialties` | `provenance.check_specialty_exists` | Batch error (§1), same severity as any other validation failure. |

None of these three has a "proceed anyway with a warning" path — that
distinction is reserved for `WARN_PROCEED_REPEATED_CONTENT` (§3), which is
about re-citing *already-valid, already-resolved* content under a new
version string, a fundamentally different situation from an invalid
identity/reference/specialty.

---

## 9. Preview / dry-run

**Rule:** `orchestrator.import_batch(..., dry_run=True)` runs the complete
Phase 1 pipeline (§1) — including the read-only version-action resolution
(§3) and the read-only reference find-or-create *lookup* (§5, query only,
no INSERT) — and returns the same `BatchResult` shape, but never opens the
write transaction and never calls `db.add`/`db.commit` anywhere.

**Distinct from PR-A1c's content preview/diff renderer** (original plan
§6, unbuilt, separate future PR) — that renderer answers "what would this
knowledge item *mean* as rendered content" (Markdown, for a human reviewer
to read). This orchestrator-level dry-run answers a different question:
"what would this batch *do* to the database" — how many new drafts, how
many no-ops, how many reference rows reused vs. created, which files would
be rejected and why. Both are useful; neither substitutes for the other.
This plan does not build A1c's renderer.

**Report shape:** `BatchResult.dry_run = True`, `written = []` (nothing was
actually written), plus a new `planned: list[PlannedWrite]` field populated
only in dry-run mode, describing what Phase 2 *would* have done per file
(`NEW_DRAFT` / `NO_OP` / reference reused-vs-created counts).

**Tests:** `test_dry_run_reports_plan_without_writing`
(assert zero rows in every table touched, `planned` non-empty, matches what
a subsequent non-dry-run call with identical input actually writes).

---

## 10. Rollback and partial-failure behavior

**Rule:** already the core design of §1/§2 — restated as its own explicit
test-matrix commitment since PTH called it out separately.

**The two distinct failure classes, both zero-write:**
1. **Phase 1 validation failure** (any file in the batch fails schema,
   business-rule, identity, specialty, or version-conflict checks) → the
   entire batch never reaches Phase 2. Zero writes, full stop, `BatchResult.success = False`
   with every file's errors listed (not just the first failing file — batch
   validation collects everything, per the existing "validate everything,
   report everything" convention).
2. **Phase 2 write failure** (an unexpected exception during the write
   transaction — a bug, a race that slipped past §3/§5's read-then-write
   window, a constraint violation not predicted by Phase 1's checks) →
   `db.rollback()`, zero rows survive across every table touched
   (`drug_usage`/`drug_patient_education`/`drug_side_effects`/
   `drug_monitoring`/`drug_contraindications`, `drug_references`,
   `knowledge_reference_links`), exception re-raised or wrapped into
   `BatchResult.success = False` with the underlying error surfaced (not
   swallowed).

**No partial-success outcome exists in this design.** A batch either fully
succeeds or fully fails — this is a deliberate simplicity choice consistent
with the "single-writer, human-run batch tool" operational model (original
plan §4's concurrency section), not a distributed system requiring partial
retry semantics.

**Tests:** `test_rollback_partial_batch_failure` (already in the original
plan's §7 test matrix, restated here as owned by A1b specifically) — batch
of N files where file K fails at *each* of: schema validation, identity
resolution, specialty check, version conflict, and (separately) an
unexpected Phase 2 exception — one test per failure point, each asserting
zero rows across all 7 tables (5 knowledge + 2 reference tables).

---

## 11. SQLite / PostgreSQL parity

**Rule:** every orchestrator/versioning test that touches the database runs
against both dialects, matching this codebase's established convention
(unit-style tests against the SQLite `db` fixture per `tests/conftest.py`;
anything asserting real-Postgres-specific behavior — partial unique index
interaction, concurrent transaction behavior — as `pytest.mark.integration`
against `POSTGRES_TEST_URL`).

**Specific parity risks this PR must test, not just assume:**
- F1's two-tiered citation identity (`uq_drug_references_by_document_identifier`,
  `uq_drug_references_by_title`) is implemented as partial unique indexes
  with `postgresql_where=`/`sqlite_where=` — §5's find-or-create logic must
  be proven to behave identically on both (a duplicate that Postgres's
  partial index catches must also be caught on SQLite, and vice versa —
  this session's own F1 rehearsal already exercises this at the migration
  level; A1b's tests exercise it at the application/orchestrator level).
- Batch transaction rollback behavior (§2/§10) — SQLite's DDL is
  non-transactional in general, but this PR only performs DML (INSERT),
  which is transactional on both dialects; still worth an explicit
  regression test given this session's own round-2 Codex finding on F1's
  migration guard (a DDL-ordering bug that only manifested because SQLite
  DDL isn't transactional) — the same class of assumption must not be
  silently carried into A1b's DML-only write path without verifying it.

**Tests:** every test file in this PR (`test_medication_knowledge_import_versioning.py`,
`test_medication_knowledge_import_orchestrator.py`,
`test_medication_knowledge_import_references.py`) runs its full suite
against SQLite (default `db` fixture) and has a `pytest.mark.integration`
parallel suite against Postgres for the parts that touch F1's partial
unique indexes specifically.

---

## 12. Zero API / frontend / AI wiring

**Rule:** unchanged from the original plan §7/§9. `orchestrator.py` is
called by a CLI script or CI job, never a route. No file under
`medication_knowledge_import/` (or the new `versioning.py`, wherever it
lands in that package) may be imported by anything under `backend/app/api/`,
`frontend/`, or `backend/app/ai/`.

**CI/PR-diff stop gate:** the A1b PR's diff must touch zero files under
`frontend/`, zero files under `backend/app/api/`, zero files under
`backend/app/ai/`, and zero files under the pre-existing
`backend/app/knowledge/` package (the live AI-narrative-adjacent package —
different status enum, different purpose, must never be confused with
this batch-import package per the original plan §9's first risk row).

---

## 13. Zero real clinical content

**Rule:** unchanged from every prior K1/A1a PR in this program. Every test
fixture in A1b's test files is synthetic (`test-ingredient-synthetic`,
fabricated publisher/title/citation strings, placeholder specialty codes)
— never real drug names beyond what's already in the 41-entry test catalog
seed, never real clinical facts, never content that could be mistaken for
authored Phase B material. Phase B authoring itself is explicitly **not
started** by this plan or by A1b's implementation — A1b builds the pipe,
Phase B (a separate, later, PTH-gated decision) puts real content through it.

---

## 14. Module layout (for the implementation PR, not built here)

```
backend/app/services/medication_knowledge_import/
  loader.py          # existing (A1a)
  schema.py          # existing (A1a, now F1-aligned per #130)
  validators.py       # existing (A1a)
  provenance.py       # existing (A1a) — check_specialty_exists now meaningful (F2 seeded)
  versioning.py        # NEW — §3, §4: business_key_for, content_hash, VersionAction, resolve_version_action
  orchestrator.py      # NEW — §1, §2, §9, §10: import_batch(db, paths, dry_run=...) -> BatchResult
  references.py        # NEW — §5: find_or_create_reference, link_reference_to_row
                        #       (kept separate from versioning.py — different concern,
                        #        different DB tables, independently testable)
```

`knowledge_repository.py` (K1-S3, existing) is imported by `orchestrator.py`
for `create_draft` and `KNOWLEDGE_TABLE_NAME` — not modified. No new function
is added to `knowledge_repository.py` by A1b; all new write logic lives in
the three new modules above, keeping K1-S3's own scope lock (draft-only,
already-reviewed) undisturbed.

---

## 15. Test file plan

| File | Covers |
|---|---|
| `test_medication_knowledge_import_versioning.py` | §3, §4 — all 4 `VersionAction` outcomes, concurrency race (bounded harmless-duplicate), business-key derivation per type, content-hash stability/sensitivity |
| `test_medication_knowledge_import_references.py` | §5, §8 — find-or-create both identity branches, reuse vs. new-row creation, `accessed_at` differentiation at the app level, fail-closed on unexpected persistence error |
| `test_medication_knowledge_import_orchestrator.py` | §1, §2, §6, §7, §9, §10, §12 — end-to-end valid batch, specialty DB-check rejection, zero-approved-rows assertion on every test, dry-run report accuracy, whole-batch rollback per failure point, CI/PR-diff checks for API/frontend/AI/`app/knowledge/` isolation |
| `tests/integration/test_medication_a1b_orchestrator_postgres.py` | §11 — Postgres-specific partial-unique-index parity for reference dedup, real-transaction rollback proof |

Total new test count target: comparable density to F1 (23 integration +
unit) and A1a (41 unit) — exact count TBD at implementation time, not fixed
by this plan.

---

## 16. What this plan does NOT authorize

- No `versioning.py`, `orchestrator.py`, or `references.py` code — this PR
  is the plan only.
- No Phase B content authoring.
- No API route, frontend screen, or AI wiring of any kind.
- No change to `knowledge_repository.py`'s existing scope lock (still
  draft-only; still no `approved`-reaching path).
- No new ADR — this plan implements decisions already made in ADR-13 and
  the two Accepted findings (Finding 1/2), it does not introduce a new
  architectural decision.

## 17. GO / NO-GO

| Item | Status |
|---|---|
| A1b planning | ✅ **GO** (this document) |
| A1b implementation (`versioning.py` + `orchestrator.py` + `references.py` + tests) | 🔴 **NOT GO** — awaits PTH + Codex + compliance + architecture review of this plan |
| Phase B authoring | 🔴 **NOT GO** — separate, later gate |
