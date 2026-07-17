# Medication Knowledge — Phase A1b Orchestrator Implementation Plan

**Date:** 2026-07-17 (revised same day — round 2 PTH review, rounds 3-6
Codex re-verification, round 7 PTH re-review + follow-up Codex pass, round
8 PTH re-review of the migration nullability/legacy-row policy)
**Status:** 🟡 **Planning GO — implementation NOT GO.** This document is itself
subject to review/approval before any `versioning.py`/`orchestrator.py` code
is written. Phase B authoring has not started and is not authorized by this
plan.

**Round-2 revision note (PTH review):** found one P1 (transaction-ownership
architectural conflict — an earlier version said "reuse `create_draft`
unchanged" while also requiring one-commit-per-batch; those two claims
contradict each other, since `create_draft` commits internally) and two P2s
(SQLAlchemy transaction-lifecycle wording that implied a fresh transaction
opens after Phase 1, and an incorrect "harmless duplicate reference row"
framing for a race that a working unique index should never actually
allow). All three fixed in §2 (rewritten, now §2a/§2b) and §5 (race
semantics corrected). §14's module-layout claim that `knowledge_repository.py`
would be untouched also corrected.

**Round-3 revision note (Codex re-verification of the round-2 fix, run
proactively per this project's standing "Codex/compliance/architecture
review sạch" gate):** the round-2 fix was directionally correct but still
had 6 P1s and 4 P2s Codex caught — all fixed in this revision:
- **P1** every Phase 1 early-return path (validation errors, dry-run) now
  explicitly closes the transaction instead of leaving it open (§2a).
- **P1** `import_batch` now requires and checks a fresh `Session` with no
  pending work at entry — otherwise the sole-ownership guarantee doesn't
  hold (§2a).
- **P1** the illustrative write loop now explicitly skips `NO_OP` plans
  before calling `build_draft`/`add_draft` — the round-2 draft would have
  still written a duplicate for an already-imported file (§2a).
- **P1** version-action resolution is now a **sequential, batch-local fold**
  across the whole batch, not independent per-file DB queries — two files
  in one batch sharing a brand-new business key now correctly resolve
  against each other, not just against DB history (§3).
- **P1** `known_versions_for` now queries the **full non-retired history**
  for a business key, not just the most recent row — the decision matrix's
  own "matches an existing version" rule requires this (§3).
- **P1** the stale `create_draft`-committing recipe still living in
  `MEDICATION_PHASE_A_PR_A1_IMPLEMENTATION_PLAN.md` (§4/table/PR-split) is
  now marked superseded, pointing at this document, instead of standing as
  a competing instruction.
- **P2** the reference-race test's SQLite trigger switched from an FK
  violation (this codebase's SQLite fixture does not enable
  `PRAGMA foreign_keys=ON`, so it would silently not fire) to a unique-index
  violation (enforced natively on both dialects) (§2a).
- **P2** reference persistence now checks a **batch-local cache** before
  querying the DB — two files in one batch citing the same brand-new
  reference is a deterministic outcome, not a race, and must not hit the
  same unique-index-rejection path §5 designed for genuine cross-batch
  races (§5, and simulated in dry-run too, §9).
- **P2** `link_reference_to_row` is now itself find-or-create (idempotent),
  since A1a's file-level duplicate-reference validator keys on
  publisher/title/date, not F1's actual document-identifier-first identity
  — a file can have two references that look different to A1a but resolve
  to the same DB row here (§5).
- **P2** the write-failure outcome contract is locked to "never raises,
  always returns `BatchResult`" — the round-2 draft's "re-raised or wrapped"
  hedge in §10 is retracted.

**Round-4 revision note (Codex re-verification of the round-3 fix):** the
round-3 fix was directionally correct but still had 4 P1s and 4 P2s:
- **P1** the session-precondition check (`db.new`/`db.dirty`/`db.deleted`)
  didn't catch a session with an already-open transaction but no pending
  ORM changes (e.g. after a bare `SELECT`) — tightened to check
  `db.in_transaction()` (§2a).
- **P1** Phase 1 ran outside the `try` block in the illustrative code, so an
  ordinary exception during loading/lookup would propagate uncaught and
  leave its transaction open — the entire function body is now inside one
  `try` (§2a).
- **P1** the batch-local version-resolution index (§3) was keyed on
  business key alone, which can collide across different knowledge types
  (`monitoring`/`contraindication` business keys are both 3-element string
  tuples) — namespaced by `(model_cls, business_key)` (§3).
- **P1** §5's reference fallback query (no `document_identifier`) didn't
  exclude rows that *do* have one set, risking a wrong-identity match —
  added the `document_identifier IS NULL` condition, mirroring F1's own
  partial index exactly (§5).
- **P2** `BatchResult.errors` was typed `list[FileError]` but a Phase 2
  failure returned a raw string — wrapped into `FileError` consistently (§2a).
- **P2** the reference-race test (and §2a's own rollback test) described a
  fuzzy "isn't visible without a fresh read" race that isn't a reliable,
  dialect-portable trigger — both rewritten to use explicit, deterministic
  ordering instead of implied concurrency timing (§2a, §5).
- **P2** the "harmless duplicate" claim for the draft-row race (§3) was
  overbroad — narrowed to identical-content races only; a same-version,
  differing-content race is a real, documented, undefended gap in the
  single-writer assumption, not "harmless" (§3).
- **P2** the original A1 plan's Verdict table and out-of-scope list still
  described Finding 1/2 as unresolved/deferred in several places beyond the
  one line already fixed in round 2 — added an explicit superseding note
  rather than silently editing the dated historical record.

**Round-5 revision note (Codex re-verification of the round-4 fix — no
P1s this round, 3 P2s, all in test descriptions rather than the design
itself):**
- the "ordered collision" reference-race test (§5) and the transaction-
  ownership rollback test (§2a) both had the *same* flaw: they had a
  separate session insert+commit a colliding row while the batch's own
  session already held SQLite's file-level write lock from earlier
  flushes — SQLite would raise `OperationalError: database is locked`
  there instead of letting the separate session commit, so the described
  trigger wasn't actually reachable on that dialect. Both rewritten to use
  a same-session, same-transaction "bypass the normal dedup path"
  technique (a deliberate second insert under an identity already
  occupied by an earlier flushed-but-uncommitted row in the *same*
  transaction) — a defense-in-depth trigger, not a race reproduction,
  fully deterministic on both dialects with no locking/ordering concerns.
- `test_import_batch_requires_fresh_session` only tested pending
  `db.new`/`db.dirty` state, which the *superseded* round-3 check would
  also have caught — added the actual distinguishing case (a session that
  ran a bare `SELECT`, leaving new/dirty/deleted empty but
  `db.in_transaction()` true) so the test actually regression-tests the
  round-4 tightening.
- the §3 concurrency-test description still read as endorsing "same
  business key racing" generically as harmless — restricted its scope to
  identical-content races explicitly, matching the narrowed claim the
  round-4 fix already made in the surrounding prose.

**Round-6 revision note (Codex re-verification of the round-5 test
rewrites — 2 P2s, both precise test-correctness catches, no design
flaws):**
- `test_two_files_same_batch_new_reference_reused_via_batch_cache`'s
  premise was wrong: sequential same-session processing means file 1's
  reference is already flushed (and query-visible) by the time file 2
  runs — its "exactly one row" assertion would pass identically with the
  batch-local cache removed. Added a query-count assertion (zero
  additional DB queries for file 2) as what actually proves the cache is
  the mechanism, not incidental same-session visibility.
- The §11 dialect-parity summary still said "winner's single row
  survives" for the round-5-redesigned same-transaction test — but a full
  rollback of one transaction undoes both the legitimate and duplicate
  inserts together; there is no persisting winner there (that framing
  belongs only to the optional cross-session true-concurrency variant).

**Round-7 revision note (PTH re-review of the round-6 revision — one
final P1, one wording fix):**
- **P1 — idempotency hash was ignoring references and provenance.** The
  design named the hash function `content_hash` and hashed only
  type-specific content fields. A concrete failure this enabled: import
  v1.0.0 with reference R1; author changes the reference to R2 but keeps
  version and content identical; re-import sees the same version + same
  content hash and classifies `NO_OP` — R2 is never persisted or linked,
  while the importer reports success. Fixed: renamed to `artifact_hash`
  and widened to cover `knowledge_type`, content fields, `locale`/
  `audience`, `references` (canonicalized via F1's own two-tiered identity,
  sorted before hashing so YAML reordering isn't load-bearing but identity
  changes are), `review_metadata.source`/`evidence_level`/`reviewed_at`,
  `specialty_codes` (sorted), `ai_generated`, and
  `disclaimer.acknowledged`. Excludes `authored_by`, file path, runtime
  timestamps, DB IDs, and status fields. `WARN_PROCEED_REPEATED_CONTENT`
  renamed to `WARN_PROCEED_REPEATED_ARTIFACT` throughout, matching the
  wider hash it now represents. Six new required tests added (§3):
  reference-only change, provenance-only change, reference/specialty
  reorder-is-no-op (×2), and new-version-same-content-new-reference
  actually persisting the reference.
- **Wording fix** — the "`import_batch` never raises" contract (§2a) was
  ambiguous against the session precondition, which itself deliberately
  raises `ValueError`. Reworded to distinguish two categories explicitly:
  *import/content failures* (Phase 1 validation, version conflicts, Phase
  2 write failures) always return `BatchResult`; *programmer-contract
  violations* (a non-fresh `Session`) raise `ValueError` immediately,
  before any file is processed, because that's a caller bug, not an
  import outcome. No code-design change, wording only.

**Round-7 follow-up (self-caught via one more targeted Codex pass on the
artifact_hash fix above — 1 P1, 2 P2, 1 P3, no design reversal, all
tightening the same fix):**
- **P1 — the artifact-hash design wasn't actually implementable as first
  written:** `known_versions_for` needs a comparable hash on a *later*
  invocation, but no knowledge table has an `artifact_hash` column and
  several hashed inputs (`specialty_codes`, `ai_generated`,
  `disclaimer.acknowledged`) have no other persistence path at all in the
  current schema. Fixed (§3, §14): `artifact_hash` is computed once at
  import time from the full in-memory `KnowledgeFile` and stored as a new
  column on each of the 5 knowledge tables — `known_versions_for` becomes
  a plain column read, no recomputation or joins needed. This adds one
  small, disclosed Alembic migration to A1b's scope (same review bar as
  F1/F2), corrected throughout §3/§14/§16/§17 rather than left implicit.
- **P2** the concurrency-test scope (§3) said "identical content" as the
  harmless-race boundary — no longer sufficient once the hash covers
  references/provenance too; tightened to "identical full artifact" in
  both the test description and the "harmless claim narrowed" paragraph.
- **P2** the illustrative code's caption still called the failure contract
  a blanket "never-raises contract" immediately next to a function that
  visibly raises `ValueError` for a bad session — annotated in place to
  point at the round-7 wording fix rather than read as still-unresolved.
- **P3** §3's own heading still said "content hash" — renamed to
  "artifact hash."

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
6. `versioning.resolve_version_action(db, batch_index, ...)` (new module, §3
   below) — a **read-only** decision against current DB state *and* against
   every earlier file already processed in this same batch (§3's round-3
   fix — Codex correctly caught that two files in one batch, checked only
   against the DB independently, can both resolve `NEW_DRAFT` for what is
   actually a duplicate-within-the-batch, or bypass `REJECT_VERSION_CONFLICT`
   entirely if the DB has no prior row at all): `NEW_DRAFT` / `NO_OP` /
   `REJECT_VERSION_CONFLICT` / `WARN_PROCEED`. `REJECT_VERSION_CONFLICT` is
   collected as a batch error, same severity as a schema/validation failure
   — not silently skipped, not treated as "that file's problem alone." Files
   are processed **in order** for this step specifically (not independently
   in parallel), each one's resolved action folded into `batch_index` before
   the next file's resolution runs — see §3 for the exact algorithm.

Each file's outcome is either a fully-resolved `ImportPlan` (validated
content + resolved ingredient id + resolved specialty ids + version action)
or a list of errors. Nothing is written to the database in this phase.

**Phase 1 and Phase 2 share one transaction, never two** (locked in §2 —
revised after PTH's round-2 review: SQLAlchemy's `Session` autobegins a
transaction on first use, so Phase 1's read-only queries already have one
open by the time Phase 1 finishes; there is no clean point to "start a new
transaction" after Phase 1 without first ending the one already open, which
this plan does not do). Phase 1 writing zero rows (above) is what makes
this safe **only if every return path explicitly ends that transaction**
(Codex round-3 fix, §2a) — "never committed" is not the same as "properly
closed"; an unclosed read-only transaction on a returned-but-still-open
`Session` can hold locks and lets a later, unrelated use of that `Session`
accidentally inherit or commit it.

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

**Rule:** one batch = one transaction = one commit. All-or-nothing.

**Revised after PTH's round-2 review — the earlier draft of this plan had
two real defects here, both fixed below:**

### 2a. Transaction ownership (P1 fix)

**The defect:** the earlier draft said "reuse `knowledge_repository.create_draft`
unchanged" for Phase 2's writes. `create_draft` commits internally
(`db.commit()` / `except: db.rollback(); raise`) — it is designed for a
single, standalone draft creation, not for participating in someone else's
multi-row transaction. If `orchestrator.py` called it once per file in a
loop, the first two drafts in a 3-file batch would already be **committed**
by the time the third file's error occurs — no rollback can undo an already
-committed transaction. This directly breaks "all-or-nothing."

**The fix — transaction ownership is now explicit and singular:**

> Low-level functions participating in a batch transaction must never call
> `commit()` or `rollback()`. Only the transaction owner (`import_batch`)
> may end the transaction.

`knowledge_repository.py` gains two new, commit-free primitives (this is a
change from an earlier draft of this plan, which claimed
`knowledge_repository.py` would not be touched — see the corrected §14):

- `build_draft(model_cls, *, authored_by, **fields) -> KnowledgeModel` — pure
  construction, no DB interaction at all.
- `add_draft(db: Session, row: KnowledgeModel) -> None` — `db.add(row)` +
  `db.flush()`. **Never commits, never rolls back.** Flushing (not
  committing) still surfaces constraint violations immediately at the point
  of the failing file, while leaving the transaction open and reversible.

`create_draft` itself **keeps its existing signature and behavior
unchanged** for its existing callers (K1-S3's own tests, any future
single-call use case) — it becomes a thin, backward-compatible wrapper:
`build_draft(...)` + `add_draft(db, row)` + `db.commit()` + `db.refresh(row)`,
wrapped in the same `try/except: db.rollback(); raise` it already has today.
K1-S3's existing tests must pass unchanged against this refactor — that is
itself a required regression test for the A1b implementation PR, not
optional.

`orchestrator.py` **never calls `create_draft`.** It calls `build_draft`/
`add_draft` directly, so no commit happens mid-batch. Same rule applies to
`references.py`'s `find_or_create_reference`/`link_reference_to_row` (§5):
`db.add()`/`db.flush()` only, never `commit()`/`rollback()`.

`import_batch` is the **only** function in this call graph allowed to call
`db.commit()` or `db.rollback()`. Four properties, all locked, all shown
together in the one code block below (an earlier revision of this plan had
a duplicate, drifted mini-snippet here — removed; there is now exactly one
illustrative code block for `import_batch`, immediately following):

- **Session precondition:** `import_batch` requires a `Session` with **no
  transactional state already in progress at entry**. This is checked and
  enforced, not just documented, because the sole-ownership guarantee
  (`import_batch` is the only committer/rollbacker) only holds if the
  transaction it ends actually began with this invocation — a `Session`
  handed in with someone else's already-open transaction (even one with no
  pending ORM-object changes, e.g. after a bare `SELECT`) would have that
  transaction silently committed or rolled back too. The production
  entrypoint (a CLI script) constructs one fresh `Session` per invocation
  and disposes it after — this precondition makes that contract explicit
  and fail-fast rather than assumed.
- **Every return path explicitly closes the transaction:** returning early
  on validation errors or `dry_run` without an explicit `db.rollback()`
  would leave the read-only transaction (SQLAlchemy autobegun by Phase 1's
  own queries) open past `import_batch`'s return — a resource leak on the
  caller's `Session`, not merely untidy.
- **`NO_OP` plans must not reach `build_draft`/`add_draft`:** looping over
  every `ImportPlan` unconditionally would still write a new draft row for
  an already-imported file (`NO_OP_ALREADY_IMPORTED`), directly violating
  idempotency (§3).
- **Locked failure-contract, precisely worded (PTH round-6 wording fix —
  the prior phrasing "never raises for an anticipated failure" was
  ambiguous against the session precondition, which itself is an anticipated,
  deliberately-raised check):** *import/content failures* — anything about
  the files being imported (Phase 1 validation, version conflicts, Phase 2
  write failures) — always return `BatchResult(success=False, ...)`, never
  an exception. *Programmer-contract violations* — a caller passing a
  non-fresh `Session`, i.e. the precondition above — raise `ValueError`
  immediately, before any file is processed, because that is a bug in the
  caller's own code, not an outcome of importing anything, and should fail
  loudly at the call site rather than surface as a misleading "no files
  succeeded" result. Only a genuinely unanticipated interpreter-level
  failure outside `except Exception`'s scope (e.g. `KeyboardInterrupt`)
  propagates beyond that, matching normal Python behavior.

**Codex round-4 fixes to the illustrative code, both real gaps in the
round-3 version:**
- **Session precondition was insufficient (P1):** `db.new`/`db.dirty`/
  `db.deleted` are all empty for a `Session` that already ran a `SELECT` (or
  had rows flushed and then, hypothetically, un-tracked) but still owns an
  open transaction — that session would pass the round-3 check and then
  have its pre-existing transaction committed/rolled back by
  `import_batch`, violating sole ownership. Fixed: check
  `db.in_transaction()` instead (or in addition to the new/dirty/deleted
  check, for defense in depth) — the exact SQLAlchemy call is finalized at
  implementation time against this codebase's actual session-autobegin
  behavior, but the **locked intent** is: reject any `Session` with *any*
  transactional state already in progress, not just pending ORM-object
  changes.
- **Phase 1 wasn't inside the same error boundary (P1):** the round-3 code
  called `_resolve_phase1` *before* the `try` block — an ordinary exception
  during loading or a DB lookup (not a validation *result*, an actual raised
  exception) would propagate uncaught, leaving its autobegun transaction
  open and breaking the just-locked "never raises" contract. Fixed: the
  entire function body, both phases, is inside one `try`.
- **Error type inconsistency (P2):** the round-3 code returned
  `errors=[str(exc)]` (a raw string) for a Phase 2 failure while
  `BatchResult.errors` is declared as `list[FileError]` everywhere else — a
  caller reading `FileError` fields uniformly for both phases would break
  only on write failures. Fixed: wrap into the same `FileError` type
  (`file=None` since a whole-batch write failure isn't tied to one file).

```python
def import_batch(db: Session, paths: list[Path], *, dry_run: bool = False) -> BatchResult:
    if db.in_transaction():
        raise ValueError(
            "import_batch requires a fresh Session with no transaction already "
            "open — pass a fresh Session per invocation, never a shared/long-lived one."
        )

    try:
        plans_or_errors = _resolve_phase1(db, paths)  # reads only, §1 — sequential fold, §3
        if any_errors(plans_or_errors):
            db.rollback()  # close the read-only transaction; nothing was written
            return BatchResult(success=False, errors=collect_errors(plans_or_errors), written=[], dry_run=dry_run)
        if dry_run:
            db.rollback()  # close the read-only transaction; dry-run never writes
            return BatchResult(success=True, errors=[], written=[], dry_run=True, planned=build_plan_report(plans_or_errors))

        written = []
        ref_cache: dict = {}
        for plan in plans_or_errors:
            if plan.version_action is VersionAction.NO_OP_ALREADY_IMPORTED:
                continue  # already imported — no draft, no reference writes
            row = build_draft(plan.model_cls, authored_by=plan.authored_by, **plan.fields)
            add_draft(db, row)                                    # add + flush, no commit
            for ref in plan.references:
                ref_id = find_or_create_reference(db, ref, batch_cache=ref_cache)  # §5 — batch-local cache first
                link_reference_to_row(db, row, ref_id)             # add + flush, no commit; idempotent, §5
            written.append(row)
        db.commit()                                                # the ONE commit for the whole batch
        return BatchResult(success=True, errors=[], written=written, dry_run=False)
    except Exception as exc:
        db.rollback()
        return BatchResult(success=False, errors=[FileError(file=None, message=str(exc))], written=[], dry_run=dry_run)
```

(Illustrative code — exact signatures finalized at implementation time; the
commit/rollback ownership, the session precondition (which *does* raise
`ValueError` — a programmer-contract violation, not an import/content
failure, per the round-7 wording fix below; this is the one intentional
exception to the "returns `BatchResult`" rule, not an inconsistency), the
every-path `rollback()`, the `NO_OP` skip, the single try/except spanning
both phases, the `FileError`-typed errors, and the import/content
never-raises contract shown here are all **locked**, not illustrative.)

### 2b. SQLAlchemy transaction lifecycle (locked)

**The defect:** the earlier draft said Phase 2 "opens exactly one `db`
transaction ... the same `Session` used for Phase 1's read-only queries" —
worded as if a fresh transaction begins after Phase 1 ends. SQLAlchemy's
`Session` autobegins a transaction on first statement execution, so Phase
1's own read-only queries already have one open; there is no clean "begin a
new one" point after Phase 1 without first explicitly ending the existing
one (and if we did, we would need to revalidate every Phase 1 decision
against a fresh read before writing, to close the race window — real
complexity this plan does not want to take on).

**Locked decision (PTH's stated preference, §2b of the review): one outer
transaction for the entire `import_batch` invocation.** Phase 1 runs inside
it read-only (writes zero rows — §1); Phase 2 writes inside the same,
already-open transaction; `import_batch` commits it exactly once at the
end, or rolls it back exactly once on any exception. For this tool's actual
operating profile (single-writer, human-run, batch sizes in the tens-to-
low-hundreds of files, not a high-throughput service) holding one
transaction open for the duration of one invocation is an accepted cost,
not a risk — the same judgment call the original plan already made for
"not building distributed locking" (§4/concurrency).

**Explicit non-goal:** per-file sub-transactions / savepoints inside the
batch. A single flat transaction is sufficient and simpler; savepoints would
only matter if partial-batch-success were an acceptable outcome, which §7
already rules out (see also §5's reference-race handling, which explicitly
rejects a savepoint-based per-reference retry for the same reason).

**Single caller-visible outcome shape:** `orchestrator.import_batch(...)`
returns a `BatchResult` (dataclass) with `success: bool`,
`errors: list[FileError]` (empty iff `success`), `written: list[WrittenRow]`
(empty iff `not success` or `dry_run`), `dry_run: bool`. The caller (a CLI
script, never a route — see §12) gets one object to inspect, not a partial
mix of "some worked."

**Tests (real implementation, not monkeypatch-only — PTH's explicit
round-2 requirement):**

`test_batch_rollback_uses_real_write_path_not_mock`:
1. Import 3 files in one batch, all valid per Phase 1. File 1's reference
   resolves to some citation identity X.
2. Files 1 and 2 reach `add_draft`/reference persistence and are flushed
   (visible in-transaction, not yet committed) — file 1's reference X is
   now a real, flushed (not committed) `DrugReference` row.
3. File 3's failure is triggered **within the same session/transaction, no
   cross-session ordering at all** (Codex round-5 correction — a round-4
   version of this test had a *separate* session insert+commit a colliding
   row while this batch's session already held an open write transaction
   from step 2's flushes; on SQLite's file-backed single-writer lock, that
   separate session would raise `OperationalError: database is locked`
   waiting on this transaction, never reaching its own commit — not a
   reliable, dialect-portable trigger). Fixed: file 3's test fixture is
   constructed so its own reference has the **same citation identity X**
   as file 1's already-flushed reference, and the test forces file 3's
   write path to skip the batch-local cache/find-or-create dedup (§5) that
   would normally correctly reuse X — simulating "if the application-level
   dedup had a bug for this one file, does the database constraint still
   catch it and does the whole batch still roll back correctly?" This is a
   **defense-in-depth** trigger, not a race reproduction: a direct second
   `add()`+`flush()` of a `DrugReference` under an identity already
   occupied by an earlier, uncommitted-but-flushed row in the *same*
   transaction still violates the partial unique index (Postgres and
   SQLite both enforce uniqueness against a session's own uncommitted-but-
   flushed rows, not only committed ones), raising a real `IntegrityError`
   — the actual code path, not a stand-in exception, fully deterministic
   on both dialects, no locking or ordering concerns. **Chosen over an
   FK-violation trigger deliberately:** this codebase's SQLite test fixture
   does not enable `PRAGMA foreign_keys=ON` (verified — `backend/app/core/
   database.py`/`tests/conftest.py` set no such pragma), so an FK-violation
   trigger would silently succeed on SQLite instead of raising, and this
   test must produce identical behavior on both dialects (§11). A
   unique-index violation is enforced natively by both SQLite and Postgres
   regardless of any pragma, making it the reliable, dialect-agnostic
   choice.
4. After the caught exception triggers exactly one `db.rollback()` (and
   `import_batch` returns `BatchResult(success=False, ...)` per the locked
   never-raises contract above — the test asserts the return value, not a
   raised exception), assert all 7 tables (5 knowledge + `drug_references` +
   `knowledge_reference_links`) have zero rows for this test's data — files
   1 and 2's flushed-but-uncommitted rows must be gone too, proving they
   were never independently committed.
5. A commit-call spy (wrapping `Session.commit`, e.g. via
   `event.listens_for(Session, "after_commit")` or a monkeypatch on the
   bound method with `wraps=`) asserts `commit()` was invoked **zero times**
   in this failing-batch test, and — in the companion all-valid-batch
   variant of this test — invoked **exactly once**, from `import_batch`'s
   own stack frame (assert via `inspect.stack()` or by asserting no
   `commit()` call is observed before `import_batch`'s loop over
   `plans_or_errors` completes).
6. Run this test on both SQLite and Postgres (§11) — the unique-index
   trigger and the rollback behavior must be identical on both.

A **second, dedicated test** (`test_import_batch_requires_fresh_session`)
proves the session precondition above — with two cases, not one (Codex
round-5 fix: a test that only supplies pending `db.new`/`db.dirty` would
still pass under the superseded round-3 check and doesn't actually
regression-test the round-4 tightening to `db.in_transaction()`):
1. A `Session` with pending `db.new`/`db.dirty` (e.g. an unflushed `add()`)
   raises `ValueError` immediately, before touching any file.
2. A `Session` that has only executed a bare read (e.g.
   `db.execute(sa.text("SELECT 1"))`) — leaving `db.new`/`db.dirty`/
   `db.deleted` all empty, but with `db.in_transaction()` now `True` via
   SQLAlchemy's autobegin — **also** raises `ValueError` immediately. This
   second case is the one that actually distinguishes the round-4 fix from
   the round-3 check it replaced; without it, the test suite would not
   catch a regression back to the weaker check.

---

## 3. Idempotency by business key + artifact hash

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

def artifact_hash(knowledge_file: KnowledgeFile, content: BaseModel) -> str:
    """SHA-256 over the FULL authoring artifact — not just type-specific
    content fields (PTH round-6 P1 fix: an earlier draft named this
    `content_hash` and hashed content fields only, excluding references and
    provenance. That let an author change a citation, or the reviewer
    metadata backing it, under an unchanged version+content and have the
    importer classify it NO_OP — silently dropping the reference/provenance
    change while reporting success. Renamed to `artifact_hash` because
    "content" no longer describes what's hashed).

    Included (this IS the artifact whose immutability a version string
    promises):
    - `knowledge_type`
    - type-specific content fields (unchanged from the original design)
    - `locale`, `audience`
    - `references`, canonicalized and order-independent (see below) —
      sorted before hashing so a YAML author reordering the `references:`
      list does not manufacture a spurious version change, but an actual
      reference addition/removal/identity change DOES change the hash
    - `review_metadata.source`, `review_metadata.evidence_level`,
      `review_metadata.reviewed_at`
    - `review_metadata.specialty_codes`, sorted (same reordering-independence
      reasoning as references)
    - `review_metadata.ai_generated`
    - `disclaimer.acknowledged`

    Excluded (these do not change what the artifact IS, only how/when/by
    whom it was produced):
    - `authored_by`
    - the source file's path
    - any runtime timestamp not explicitly listed above (`created_at` etc.)
    - database-generated IDs
    - `status`/lifecycle fields (draft never carries these at authoring time)

    **Reference canonicalization matches F1's own two-tiered identity
    exactly** (§5) — for each reference, the canonical key is
    `(document_identifier, source_version, accessed_at)` when
    `document_identifier` is set, else
    `(publisher, title, publication_date, source_version, accessed_at)`;
    the list of these keys is sorted before hashing, so reference order in
    the YAML file is never load-bearing but reference *identity* always is.
    """

class VersionAction(enum.Enum):
    NEW_DRAFT = "new_draft"                    # new business key, or new version + new artifact
    NO_OP_ALREADY_IMPORTED = "no_op"            # same key, same version, same artifact hash
    REJECT_VERSION_CONFLICT = "reject"          # same key, same version, DIFFERENT artifact hash
    WARN_PROCEED_REPEATED_ARTIFACT = "warn_proceed"  # same key, new version, but artifact hash
                                                      # matches an existing (any-status, non-retired) version

def resolve_version_action(
    known_versions: list[tuple[str, str]],  # [(version, artifact_hash), ...] — see below for where this comes from
    version: str, artifact_hash_value: str,
) -> VersionAction:
    """Pure decision, no DB access, no writes — operates on an already-
    fetched list of (version, artifact_hash) pairs. Kept DB-free so the same
    function proves both the DB-seeded case and the batch-local case below
    without duplicating the 4-rule matrix twice."""
    exact_version_match = next((h for v, h in known_versions if v == version), None)
    if exact_version_match is not None:
        return VersionAction.NO_OP_ALREADY_IMPORTED if exact_version_match == artifact_hash_value \
            else VersionAction.REJECT_VERSION_CONFLICT
    if any(h == artifact_hash_value for _, h in known_versions):
        return VersionAction.WARN_PROCEED_REPEATED_ARTIFACT
    return VersionAction.NEW_DRAFT


def known_versions_for(db: Session, model_cls: type, business_key: tuple) -> list[tuple[str, str]]:
    """Read-only query — fetches version + artifact_hash for EVERY
    non-'retired' row matching this business key, not just the most recent
    one (Codex round-3 P1 fix: the decision matrix's "matches an existing
    version" and "same version string" rules both require checking the
    FULL non-retired history, since a match can be to an older version, not
    only the latest one). A plain column read — see the storage design
    immediately below for why this doesn't need to recompute or join
    anything."""
```

**Storage design (Codex round-7 P1 fix — the round-6 draft said "requires
the artifact hash... to be stored per row at write time — an
implementation detail," which is not a real design; it hand-waved the one
piece that makes this section actually work):**

`artifact_hash` is computed **once, at import time, from the full in-memory
`KnowledgeFile`** — before anything is persisted — and the resulting
opaque hash string is stored as a **new, nullable column on each of the 5
knowledge tables**:

```python
artifact_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
```

**Nullable, not `NOT NULL` (PTH round-8 fix — the round-7 draft proposed
`nullable=False`, which cannot be safely added to a table that may already
have existing rows):** since several hashed inputs
(`specialty_codes`/`ai_generated`/`disclaimer.acknowledged`, per below)
have no independent persistence path, there is no way to backfill a real
`artifact_hash` for any row that existed before this migration. `NOT NULL`
would force one of: an empty-string placeholder, a hash of incomplete
data, a sentinel that looks like a valid hash, or a guessed reconstruction
— all of them mean the importer could later compare a *fabricated* hash
against a *real* one and reach a wrong `NO_OP`/`REJECT` conclusion for an
artifact that never actually existed. **The column stays nullable at the
schema level; immutability is enforced at the application level instead**
(below), matching how `source`/`version`/`evidence_level` etc. are already
nullable at the schema level with `ck_*_approved_invariants` enforcing
non-null only at `approved` — the same "schema allows, application-layer
gate enforces" split this codebase already uses elsewhere.

**Application-level rules (not a schema constraint):**
- `build_draft`, called only from `orchestrator.py`, **always** supplies a
  64-character SHA-256 `artifact_hash` — enforced by `orchestrator.py`
  itself (e.g. an assertion or a required, non-optional parameter with no
  default), not by the DB. Every row A1b's importer ever creates has a real
  hash.
- Existing/legacy callers of `create_draft`(K1-S3's own tests, any future
  non-importer caller) may continue to create rows with `artifact_hash =
  NULL` — those rows are not managed by the importer and the column
  simply doesn't apply to them. `create_draft`'s existing signature is
  unchanged (§2a); `artifact_hash` defaults to `None` for any caller that
  doesn't pass it, preserving 100% backward compatibility.
- **`known_versions_for` must fail closed on a `NULL` hash, never
  interpret it (PTH round-8 fix):** if any non-`retired` row for a
  business key has `artifact_hash IS NULL`, the entire batch touching that
  business key fails with a distinct, explicit error —
  `LEGACY_ARTIFACT_HASH_UNAVAILABLE` — stating plainly that this version's
  immutability cannot be verified and manual remediation is required.
  Explicitly forbidden as substitutes: silently resolving `NEW_DRAFT`;
  silently resolving `NO_OP`; comparing against a content-only subset as a
  fallback; overwriting the legacy row. A `retired` row with a `NULL` hash
  does **not** block — `known_versions_for` only considers non-`retired`
  history in the first place (§3, unchanged), so a retired legacy row is
  simply invisible to this check, same as any other retired row.
- **Remediation path (documented, not built by this plan):** once a
  human-run backfill/remediation process establishes real hashes (or
  explicitly retires the affected rows) and confirms zero remaining
  `NULL`-hash non-retired rows for any business key the importer will ever
  touch, a **separate, later migration** tightens the column to
  `NOT NULL` — that migration is not part of A1b, is not authorized by
  this plan, and requires its own review when proposed.

**This requires a new, small Alembic migration as part of A1b's own PR** —
a genuine, disclosed scope addition beyond `versioning.py`/`orchestrator.py`
/`references.py` (§14 corrected below), analogous in size and review bar to
F1/F2's own migrations (Codex + compliance + architecture review, same
gate). This is *not* optional: without a stored column, `known_versions_for`
has no way to obtain a comparable hash on a later importer invocation,
since several of the hashed inputs are not independently persisted
anywhere in the current schema even though they're always present in the
in-memory `KnowledgeFile` at import time:
- `specialty_codes` — validated (§6) but never persisted as a declared-set
  column anywhere; `knowledge_review_specialties` records actual *reviews*,
  not the file's *declared* list.
- `ai_generated` — validated (must be `False`) but not a column on any
  knowledge table.
- `disclaimer.acknowledged` — per the original A1 plan §3, deliberately has
  no DB column at all (a validation gate only).

None of that is a problem for computing the hash itself (it's computed from
the file, which has all these fields, before any of this matters) — it
would only be a problem if `known_versions_for` tried to *reconstruct* the
hash from persisted row state instead of reading a stored value. Storing
the opaque hash sidesteps that entirely — and it is exactly why the column
cannot be backfilled for pre-existing rows, hence nullable + fail-closed
above.

**`locale`/`audience` are included unconditionally** in the hash formula
above because they are always present on the in-memory `KnowledgeMetadata`
(every authoring file declares them, regardless of `knowledge_type`) —
this is independent of whether a given knowledge table happens to persist
them as its own columns (`drug_usage`/`drug_patient_education` do;
`drug_side_effects`/`drug_monitoring`/`drug_contraindications` don't,
since those types have no locale/audience dimension in their own business
key). The hash is computed from the artifact, not reconstructed from the
row, so this asymmetry across tables doesn't matter.

**Batch-local resolution (Codex round-3 P1 fix — the design above, taken
alone, is still wrong for a batch):** if two files in the *same* batch
share a business key that has zero rows in the DB today, each file's
`known_versions_for(db, ...)` independently returns `[]` (Phase 1 writes
nothing, so neither file's in-progress plan is visible to the other via a
DB query) — both would resolve `NEW_DRAFT`, and either both get written as
duplicates, or (worse) one has different content under the same version
string and `REJECT_VERSION_CONFLICT` never fires because there was no *DB*
row to conflict against.

**Fix:** `_resolve_phase1` processes files **sequentially, not
independently**, threading one evolving
`batch_index: dict[tuple, list[tuple[str, str]]]` through the whole batch,
**keyed by `(model_cls, business_key)`, not `business_key` alone** (Codex
round-4 P1 fix — `usage`, `monitoring`, and `contraindication` business keys
are all 3-element string tuples and can compare equal by coincidence across
different knowledge types for the same ingredient; without `model_cls` in
the key, a later file for a *different* table could wrongly inherit an
earlier file's version history and resolve `NO_OP`/`REJECT` against the
wrong table's data):

```python
def _resolve_phase1(db: Session, paths: list[Path]) -> list[ImportPlan | list[FileError]]:
    batch_index: dict[tuple[type, tuple], list[tuple[str, str]]] = {}
    results = []
    for path in paths:
        # ... loader/schema/validators/provenance steps (§1) unchanged ...
        business_key = business_key_for(knowledge_type, ingredient_id, content)
        index_key = (model_cls, business_key)   # namespaced by table — the round-4 fix
        version = review_metadata.version
        hash_value = artifact_hash(knowledge_file, content)  # full artifact — §3's round-6 fix

        known = batch_index.get(index_key)
        if known is None:
            known = known_versions_for(db, model_cls, business_key)  # DB-seeded, once per key
            batch_index[index_key] = known

        action = resolve_version_action(known, version, hash_value)
        if action is not VersionAction.REJECT_VERSION_CONFLICT:
            # fold this file's own outcome into the index so a LATER file
            # in the same batch sees it too — this is what closes the gap.
            known.append((version, hash_value))

        results.append(ImportPlan(..., version_action=action) if action != REJECT else errors_for(action))
    return results
```

A second file in the batch sharing the first file's new business key now
sees the first file's `(version, hash)` already folded into `known` — so an
identical repeat correctly resolves `NO_OP_ALREADY_IMPORTED` (against the
in-batch entry, not just the DB) and a same-version-different-content
repeat correctly resolves `REJECT_VERSION_CONFLICT`, even though neither
had a *pre-existing DB row* to conflict against. This is the same 4-rule
matrix, just fed a superset of "known versions" (DB history *and* earlier
files in this batch) instead of DB history alone.

**Fail-closed on `REJECT_VERSION_CONFLICT`:** this is a batch error (§1),
never a silent skip and never a silent overwrite — "a version string is a
promise that its content is fixed" (original plan §4, unchanged).

**Tests:** `test_medication_knowledge_import_versioning.py` — one test per
`VersionAction` outcome, plus the concurrency test already specified in the
original plan §7, **scope restricted to an identical full artifact** (Codex
round-5 fix, tightened further in round 7 — "identical content" alone is no
longer a sufficient boundary now that the hash covers the full artifact:
two imports can share identical content fields but differ in references or
provenance, producing *different* artifact hashes under the same version —
if those race, both inserts can succeed, which is exactly the
conflicting-version failure mode described below, not a harmless
duplicate): two importer invocations racing the same business key **and an
identical full artifact — same content, same references, same
provenance** — worst case is a harmless duplicate draft row, proven
bounded, not eliminated, no distributed locking, matching the accepted
single-writer operational constraint. A race with the same business
key/version but **any** difference in content, references, or provenance
(i.e. a different artifact hash) is a documented, undefended gap (see
"harmless claim narrowed" below) — not something this test claims to
bound, and not something a test should assert is "fine," since it isn't.
Plus two new tests for the round-3 fixes:
- `test_artifact_hash_match_against_older_non_latest_version` — seed v1 and
  v2 for a business key, then import v1's exact artifact again under a new
  version string v3 → asserts `WARN_PROCEED_REPEATED_ARTIFACT` (proves
  `known_versions_for` checks the full non-retired history, not just the
  most recent row — the earlier draft's "most recent row only" design
  would have missed this).
- `test_batch_local_duplicate_new_business_key_no_op` /
  `test_batch_local_duplicate_new_business_key_conflict_rejected` — two
  files in one batch share a business key with zero DB rows; identical
  artifact under the same version → second file resolves `NO_OP`; differing
  artifact under the same version → second file resolves
  `REJECT_VERSION_CONFLICT` and the whole batch fails (§1/§10) — proves the
  batch-local fold, not just the DB-seeded path.
- `test_batch_index_namespaced_by_model_not_just_business_key` (Codex
  round-4 P1) — two files for the *same ingredient*, different knowledge
  types (e.g. `monitoring` and `contraindication`), whose business-key
  tuples are constructed to be equal as plain tuples (same string values in
  the same positions) → assert both resolve `NEW_DRAFT` independently, each
  querying its own table's history, proving the batch index does not
  cross-contaminate across knowledge types.
- `test_reference_change_under_same_version_rejected` (PTH round-6 P1 —
  the actual bug report: an author changes a reference from R1 to R2 while
  keeping version and content-fields unchanged) → same business key, same
  version, content fields identical, but the `references:` list differs
  (R1 replaced by R2) → asserts `REJECT_VERSION_CONFLICT`, **not** `NO_OP` —
  proves `artifact_hash` actually changes when references change, closing
  the exact gap the earlier `content_hash` design had.
- `test_provenance_change_under_same_version_rejected` — same business key,
  version, and content, but `review_metadata.reviewed_at` (or
  `evidence_level`) differs → asserts `REJECT_VERSION_CONFLICT` — proves
  provenance fields are inside the hash, not just content.
- `test_reference_reorder_only_is_no_op` /
  `test_specialty_codes_reorder_only_is_no_op` — same business key,
  version, and content, but the `references:` list (respectively
  `specialty_codes:` list) is reordered with no actual change to the set of
  items → asserts `NO_OP_ALREADY_IMPORTED` — proves canonicalization/sorting
  before hashing prevents YAML reordering from manufacturing a spurious
  version conflict.
- `test_new_version_same_content_new_reference_persists` — new version
  string, content fields unchanged, but a new reference added → resolves
  `NEW_DRAFT` or `WARN_PROCEED_REPEATED_ARTIFACT` per the artifact rule (the
  hash differs because references differ, so this is never `NO_OP`), and
  the write phase actually persists the new reference row and links it to
  the new draft (§5) — proves the reference change survives into the DB,
  not just into the version-action decision.

**Nullable-column / legacy-row tests (PTH round-8 fix, required before A1b
implementation, not just recommended):**
- `test_migration_upgrade_with_existing_rows_does_not_fail` — run the new
  migration against a database seeded with pre-existing knowledge rows
  (simulating a table that already has content, even though K1 dormancy
  means this shouldn't happen in practice today — the migration itself
  must not assume it) → upgrade succeeds, every pre-existing row's
  `artifact_hash` is `NULL`, nothing else about those rows changes.
- `test_orchestrator_created_rows_always_have_hash` — any row written via
  `build_draft`/`add_draft` through `orchestrator.py` has a 64-character
  `artifact_hash` — never `NULL`, never empty string.
- `test_legacy_null_hash_blocks_whole_batch` — seed a non-`retired` row for
  a business key with `artifact_hash = NULL` (simulating a legacy or
  pre-migration row), then attempt to import a file targeting that same
  business key → the entire batch fails closed with
  `LEGACY_ARTIFACT_HASH_UNAVAILABLE` (or equivalent), zero writes across
  all 7 tables — asserts this is **not** silently resolved as `NEW_DRAFT`,
  **not** `NO_OP`, and does not fall back to any content-only comparison.
- `test_retired_null_hash_row_does_not_block` — same setup, but the
  `NULL`-hash row's status is `retired` → import proceeds normally
  (`known_versions_for` only considers non-`retired` rows, so the retired
  legacy row is invisible to the check, exactly as for any other retired
  row).
- `test_migration_has_no_fake_backfill` — a direct assertion against the
  migration's own `upgrade()`: no `UPDATE` statement, no default value
  other than the column's own `NULL` default, touches `artifact_hash` for
  any pre-existing row. This is a regression test for the migration file
  itself, not the application code, guarding against a future edit
  "helpfully" adding a backfill.
- SQLite/PostgreSQL upgrade+downgrade parity for the new column (§11):
  same nullable-column behavior, same legacy-row fail-closed behavior, on
  both dialects.
- Migration head remains single after this migration lands (same check as
  every prior K1/A1b migration in this program).
- Downgrade removes exactly the 5 new `artifact_hash` columns and nothing
  else — no data loss beyond the columns being introduced by this same
  migration, matching this program's established downgrade-safety
  convention (F1 §2a/§2b, restated here for the new migration).

**Why this race is harmless but §5's reference race (below) is not — and a
correction narrowing that claim (Codex round-4 P2):** knowledge-content
tables have no DB-level uniqueness constraint on business key — ADR-13's
append-only model *intentionally* allows multiple draft rows to coexist for
the same business key (that is what version history is). `drug_references`,
by contrast, **does** have a real partial unique index on citation identity
— a race there hits an actual `IntegrityError`, not a benign duplicate, and
is handled accordingly (§5: whole-batch rollback, not "accept the
duplicate"). Do not generalize this section's language to §5; the two
tables have different constraint shapes and therefore different correct
race behaviors.

**The "harmless" claim here is narrower than the round-3 wording implied,
and narrower still after round 7's widened hash:** it holds for two batches
racing the *same* business key, version, and **identical full artifact —
same content, same references, same provenance** (a genuine re-import of
the same file happening twice concurrently) — that produces two
informationally-redundant rows, a real but accepted operational cost. It
does **not** hold if two batches race the same business key and version
with **any** difference in content, references, or provenance (i.e. a
different `artifact_hash`): since there is no DB constraint to catch this
at the draft-row level, both inserts can succeed, leaving two rows that
both claim the same version string with conflicting artifacts — exactly the
situation `REJECT_VERSION_CONFLICT` exists to prevent, except the race
window means the check-then-insert isn't atomic across two separate
transactions (only within one batch, via §3's own batch-local fold above).
This is a real, undefended gap in the single-writer assumption, not merely
"duplicate rows" — documented here honestly rather than folded into the
same "harmless" bucket as the identical-artifact case.
Consistent with this plan's stated philosophy (§4/concurrency in the
original A1 plan, restated here): no distributed locking is built to close
this window; the mitigation is operational (this is a human-run,
single-writer tool — two people should not run the batch importer against
the same content concurrently), not a code-level guarantee.

---

## 4. New version creates a new row, never overwrites history

**Rule:** `NEW_DRAFT` and `WARN_PROCEED_REPEATED_ARTIFACT` both mean
"`build_draft` + `add_draft`" (§2a) — an INSERT. There is no code path in
`orchestrator.py` that calls `UPDATE` against a knowledge-content row's
fields. (The one existing `UPDATE` in this codebase's knowledge stack,
`submit_for_review`'s status-only atomic transition, is untouched by A1b —
orchestrator never calls it; see §6.)

**Design:** `orchestrator.py` calls the new commit-free `build_draft`/
`add_draft` primitives (§2a — not `create_draft` directly, since
`create_draft` commits and orchestrator must own the transaction). Neither
`build_draft` nor `add_draft` has any update capability — they only ever
construct and INSERT a new row — so no new "upsert" helper exists anywhere
in this design; adding one would be the exact overwrite footgun this
invariant forbids. Old rows for the same business key are left
byte-for-byte untouched; the new row is a sibling, not a replacement. This
is the same guarantee K1-S3's own `test_create_new_version_does_not_overwrite`
already proves at the `create_draft` level (and, per §2a, `create_draft`'s
own behavior is unchanged for its existing callers, so that existing test
keeps passing without modification) — A1b's tests prove the same guarantee
again at the batch/orchestrator level, using `build_draft`/`add_draft`
directly.

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

**Design — find-or-create, using F1's two-tiered identity. Race semantics
corrected after PTH's round-2 review — the earlier draft's "harmless
duplicate reference row" framing was wrong and is retracted below. Two
further gaps fixed after Codex's round-3 pass on the round-2 revision:**

1. Check the **batch-local cache first** (Codex round-3 P2 fix — a `dict`
   keyed on citation identity, threaded through the whole `import_batch`
   call, seeded empty at batch start): if this exact citation identity was
   already resolved earlier in *this same batch* (by an earlier file citing
   the same source), reuse that id directly — no DB query, no risk of a
   spurious "duplicate" reference row for something this batch itself
   already created two lines ago. Without this, two files in one batch
   citing the same brand-new reference would each independently run the
   find-query (both see nothing, since neither has flushed yet when both
   run their reads early), and the second one's insert would hit the exact
   §5-corrected unique-index rejection above — a fully deterministic,
   avoidable failure, not a genuine race, so it must not be handled the
   same way as a true cross-batch race.
2. If not in the batch-local cache: if `reference.document_identifier` is
   set, query
   `drug_references WHERE document_identifier = :doc_id AND source_version = :v AND accessed_at = :d`.
3. Else (no `document_identifier`), query
   `drug_references WHERE publisher = :p AND title = :t AND publication_date = :pd AND source_version = :v AND accessed_at = :d AND document_identifier IS NULL`
   — **the `document_identifier IS NULL` condition is required, not
   optional** (Codex round-4 P1 fix): F1's title-based partial unique index
   (`uq_drug_references_by_title`) itself only applies `WHERE
   document_identifier IS NULL` (§5 of the F1 migration). Without this same
   condition in the *query*, a reference with no `document_identifier`
   could wrongly match and reuse an existing row that *does* have one set
   (if publisher/title/publication_date/source_version/accessed_at happen
   to coincide) — silently attaching this item to the wrong citation
   identity, one that a human curator deliberately gave a stable
   identifier. The batch-local cache key (step 1) must make the same
   distinction — a document-identifier-keyed cache entry and a
   title-keyed cache entry for what look like overlapping fields are never
   the same cache slot.
4. If found (batch-local cache or DB query), reuse its `id` and **store it
   in the batch-local cache** so later files in this batch see it too. If
   not found anywhere, `add()` + `flush()` (never `commit()` — §2a) a new
   `DrugReference` row inside the batch's one open transaction, then store
   its freshly-flushed `id` in the batch-local cache.
5. `link_reference_to_row` is itself find-or-create, not a bare insert
   (Codex round-3 P2 fix): query
   `knowledge_reference_links WHERE knowledge_table = :t AND knowledge_row_id = :row_id AND drug_reference_id = :ref_id`
   first. **Why this matters even though A1a's structural validator already
   rejects duplicate references within one file:** A1a's duplicate check
   (`validators._validate_no_duplicate_references`, already merged in #130)
   keys on `(publisher, title, publication_date)` — a file with two
   `references:` entries sharing the same `document_identifier` but
   *differing* publisher/title spelling passes that structural check (they
   look different to it) yet resolves to the **same** `DrugReference` row
   here (correctly, per F1's document-identifier-first identity) — without
   this idempotency check, step 4 would then try to `add()` a second,
   duplicate `KnowledgeReferenceLink` for the identical
   `(knowledge_table, knowledge_row_id, drug_reference_id)` tuple, hitting
   `uq_krl_no_duplicate_link` needlessly. If found, skip (no-op, the link
   already exists); if not, `add()` + `flush()` a new
   `KnowledgeReferenceLink` row: `knowledge_table` = the model's table name
   (reusing `knowledge_repository.KNOWLEDGE_TABLE_NAME`), `knowledge_row_id`
   = the new draft row's id, `drug_reference_id` = the resolved reference id.

**Corrected race semantics (this is about a genuine *cross-batch* race —
two separate `import_batch` invocations in two separate transactions —
distinct from the batch-local, same-transaction, deterministic-not-a-race
case the cache above already eliminates):** the earlier draft claimed a
concurrent find-then-insert race would produce a "harmless duplicate
reference row," bounded by the partial unique index preventing "a third
duplicate." That is wrong — **if the unique index is doing its job, a
genuine duplicate row can never exist at all.** The real sequence under a
race is:

1. Two concurrent batches (in separate transactions) both query and both
   find nothing for the same citation identity.
2. Both `add()`+`flush()` an insert for what each believes is a new
   reference.
3. One transaction's flush succeeds.
4. The other transaction's flush raises a real `IntegrityError` against
   F1's partial unique index (`uq_drug_references_by_document_identifier`
   or `uq_drug_references_by_title`) — not a duplicate row, a **rejected**
   one.

**This is treated as a whole-batch failure, not a recoverable duplicate.**
Per this invariant's own fail-closed requirement, and consistent with §2's
single-transaction, no-savepoints design: the `IntegrityError` from step 4
propagates directly to `import_batch`'s exception handler exactly like any
other Phase 2 failure — the **entire losing batch rolls back**, including
any drafts and references it had already flushed for other files. There is
no per-reference savepoint-and-retry (that would be a legitimate future
optimization but is explicitly out of scope here, per §2b's non-goal on
savepoints) — the simplest correct behavior in this tool's single-writer
operating profile is: on a genuine citation-identity race, the batch that
loses fails outright, and re-running it afterward succeeds (this time the
find step sees the winner's already-committed row and reuses it). **A
duplicate citation-identity row never exists in the database at any point**
— the partial unique index's guarantee is upheld, not merely "usually"
upheld with a documented escape hatch.

**Dialect parity is load-bearing here, not incidental (see also §11):**
F1's two-tiered identity is implemented as partial unique indexes with
`postgresql_where=`/`sqlite_where=` on both dialects — the race-losing
transaction must raise an integrity-equivalent error on **both** SQLite and
PostgreSQL, surfaced identically through SQLAlchemy's dialect-normalized
`IntegrityError`. This must be proven by a real two-session concurrency
test on both dialects (§11), not assumed from the migration-level
rehearsal already done for F1 alone.

**Never a placeholder / never re-serialized into `source: VARCHAR(255)`:**
the existing `source` column on each knowledge row is still populated from
`review_metadata.source` (unchanged, still useful as an at-a-glance summary
per the original plan §3) — but it is not where reference persistence
*lives*. `drug_references`/`knowledge_reference_links` are the real,
queryable relation Finding 1 required.

**Fail-closed:** if reference persistence fails for any reason mid-batch
(FK violation, unique-index rejection per above, unexpected constraint
hit), the whole-batch rollback (§2) applies — a knowledge row is never left
committed without its references, and a reference row is never left
duplicated.

**Tests:** `test_reference_persisted_and_linked_to_new_draft`,
`test_reference_reused_not_duplicated_across_two_items_same_citation`,
`test_reference_reused_across_different_access_dates_creates_two_rows`
(exercises F1's `accessed_at`-inclusive identity directly at the
orchestrator level, not just the migration level),
`test_null_document_identifier_never_matches_a_row_that_has_one` (Codex
round-4 P1 — pre-seed a `drug_references` row *with* a
`document_identifier` whose publisher/title/publication_date/source_version
/accessed_at happen to match a new reference that has *no*
`document_identifier`; assert a **new** row is created, not a reuse of the
pre-seeded one — proves the title-branch query's
`document_identifier IS NULL` condition is present and doing its job).

**Reference-race test, corrected (Codex round-4 P2 — the round-3 wording
described a genuinely simultaneous two-session race, which is dialect-
inconsistent to test):** a real two-writer scenario behaves differently per
dialect — SQLite serializes writers at the file-lock level (a true race
there typically surfaces as `OperationalError: database is locked`, not the
unique-index `IntegrityError` this test needs), and even on PostgreSQL,
"both sessions find nothing" isn't deterministically reproducible under
READ COMMITTED without explicit synchronization in the test harness. Split
into two tests instead:
- `test_reference_race_loser_rolls_back_entire_batch` (dialect-neutral,
  runs on both SQLite and Postgres, **deterministic, not a true race** —
  same technique as §2a's rollback test): pre-seed a colliding
  `drug_references` row via a separate, already-committed session *before*
  the batch under test even starts its find-query. The batch's own find
  query correctly sees the pre-existing row (no race — it was committed
  before this batch began), so this specific test doesn't exercise the
  find-miss-then-insert-collides path; it is kept as a basic "reusing an
  existing row via the fallback query is dialect-consistent" check, not a
  race proof.
- `test_reference_unique_index_violation_rolls_back_entire_batch`
  (dialect-neutral, both SQLite and Postgres — **redesigned after Codex
  round-5**, single-session, no cross-session ordering at all): the
  round-4 version tried to have a *separate* session insert+commit a
  colliding row while the batch's own session held an open write
  transaction (from earlier files' `add_draft` flushes) — on SQLite,
  file-backed single-writer locking means that separate session would
  raise `OperationalError: database is locked` waiting for the batch's
  still-open transaction to release the lock, never reaching its own
  commit, so the test couldn't actually exercise the intended path on that
  dialect. Fixed by removing the cross-session element entirely: within
  the **same** batch/transaction, deliberately construct two references
  with identical citation identity and route the *second* one past
  `find_or_create_reference`'s own find-check (a direct `add()`+`flush()`
  of a second `DrugReference` with the same identity, bypassing the
  find-or-create wrapper — simulating "if the application-level find logic
  had a bug and let a duplicate through, does the DB constraint itself
  still catch it and does the batch still roll back correctly?"). This is
  a **defense-in-depth** test, not a race reproduction — it needs no
  locking, no ordering, no true concurrency, and is fully deterministic on
  both dialects, since a plain second insert under an already-unique
  identity always violates the partial index regardless of dialect or
  timing. Assert the resulting `IntegrityError` triggers a full rollback of
  the whole batch (drafts and references alike, including the first,
  legitimately-inserted reference), and that no duplicate reference row
  exists afterward.
- A **best-effort, Postgres-only** true-concurrency test (two real threads/
  connections, no artificial ordering, no bypassing find-or-create) may
  additionally be added at implementation time to validate real-world MVCC
  behavior under genuine concurrent load, but is explicitly **not** a
  required dialect-parity test — SQLite's single-writer file-locking model
  makes a "genuine simultaneous race between two separate batches" a
  fundamentally different, less meaningful scenario there than on
  Postgres (the defense-in-depth test above is what actually proves the
  invariant on both dialects; this one is extra assurance for Postgres's
  real concurrency model specifically).

`test_two_files_same_batch_new_reference_reused_via_batch_cache`
(**corrected after Codex round-6** — the earlier description's premise was
wrong: since both files are processed sequentially within the *same*
session/transaction, file 1's reference insert is already flushed by the
time file 2 runs, so a plain DB query — with no cache involved at all —
would already find and correctly reuse it; asserting "exactly one
`DrugReference` row" alone therefore passes identically whether or not the
batch-local cache exists, and does not actually regression-test the
cache). Fixed: two files in one batch cite an identical brand-new
citation; assert exactly one `DrugReference` row is created **and** assert,
via a query-count spy/mock on the `Session` (or an explicit call-count on
`find_or_create_reference`'s internal DB-query step), that file 2's
resolution issues **zero** additional `drug_references` queries — served
entirely from the batch-local cache populated by file 1, not from a
redundant (even if correct) DB round-trip. The row-count assertion alone
proves correctness; the query-count assertion is what actually proves the
cache is the mechanism, not incidental same-session flush visibility.

`test_duplicate_reference_within_file_creates_one_link`
(one file's `references:` list has two entries sharing a
`document_identifier` but different `publisher`/`title` — passes A1a's
structural duplicate check, which doesn't key on `document_identifier` —
assert exactly one `DrugReference` row and exactly one
`KnowledgeReferenceLink` row, proving `link_reference_to_row`'s own
idempotency check, not reliance on A1a's file-level validator, is what
prevents the duplicate link).

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
- `orchestrator.py` calls `build_draft`/`add_draft` exclusively (§2a) — both
  of which, like `create_draft` before the refactor, always hardcode
  `status="draft"`. It never calls `submit_for_review` (which only ever
  targets `'clinical_review'`, never `'approved'`, per K1-S3's own scope
  lock — but A1b doesn't call it at all, since nothing in the importer flow
  submits content for review; that's a separate human action after
  drafting).
- `orchestrator.py` never imports or calls `validate_transition` with any
  target at all — it doesn't need to, since `build_draft` always hardcodes
  `status="draft"`, the same guarantee `create_draft` already had before
  its §2a refactor.
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
distinction is reserved for `WARN_PROCEED_REPEATED_ARTIFACT` (§3), which is
about re-citing *already-valid, already-resolved* content under a new
version string, a fundamentally different situation from an invalid
identity/reference/specialty.

---

## 9. Preview / dry-run

**Rule:** `orchestrator.import_batch(..., dry_run=True)` runs the complete
Phase 1 pipeline (§1) — including the read-only version-action resolution
(§3, batch-local fold included) and the read-only reference find-or-create
*lookup* (§5, query only, no INSERT) — and returns the same `BatchResult`
shape, but never adds/flushes/commits anything, and closes the read-only
transaction before returning (§2a).

**The reference batch-local cache (§5) must be simulated in dry-run too,**
not skipped (Codex round-3 P2 fix): if dry-run's reference lookups run
independently per file (no shared cache), two files citing the same
brand-new reference would each report "would create" — overcounting new
references by one and misreporting what a subsequent real run would
actually do. Dry-run threads the same `batch_cache: dict` through its own
Phase-1-only pass, populated with a *planned, not-yet-flushed* id
placeholder on a cache miss (never a DB insert) — so the second file's
lookup correctly reports "would reuse (new-this-batch)" instead of "would
create."

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
a subsequent non-dry-run call with identical input actually writes),
`test_dry_run_reference_batch_cache_matches_real_run` (two files citing the
same brand-new reference, dry-run mode — assert `planned` reports exactly
one "would create" and one "would reuse (new-this-batch)," matching what
the same input actually produces when re-run without `dry_run`).

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
2. **Phase 2 write failure** (a cross-batch reference race per §5's
   corrected semantics, or a genuinely unanticipated constraint violation
   not predicted by Phase 1's checks) → `db.rollback()`, zero rows survive
   across every table touched (`drug_usage`/`drug_patient_education`/
   `drug_side_effects`/`drug_monitoring`/`drug_contraindications`,
   `drug_references`, `knowledge_reference_links`). **Locked outcome
   contract (Codex round-3 P2 fix — the earlier draft's "re-raised or
   wrapped" hedge is retracted):** `import_batch` never raises for this
   case either — it always returns `BatchResult(success=False, errors=[...])`
   with the underlying error message surfaced (not swallowed), exactly like
   a Phase 1 failure. The caller (a CLI script) inspects one return type for
   every anticipated failure mode; only a truly unanticipated
   interpreter-level condition outside `except Exception`'s scope would ever
   propagate, and that is ordinary Python behavior, not something this
   design special-cases.

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
- **§5's corrected reference-race behavior is dialect-load-bearing, not
  incidental:** the `IntegrityError` from a duplicate citation-identity
  insert (§5) must fire identically on both dialects —
  `test_reference_unique_index_violation_rolls_back_entire_batch` (§5,
  same-session defense-in-depth trigger, not true concurrency — see §5's
  note on why a genuinely simultaneous cross-session race is not portably
  testable) runs on both SQLite and Postgres, asserting the same outcome:
  **zero rows survive** for either the legitimate first reference or the
  duplicate-attempt second one (Codex round-6 fix — since both inserts are
  in the *same* transaction here, a full rollback undoes both together;
  there is no persisting "winner" in this test, unlike the optional
  cross-session true-concurrency variant below, where each side really is
  a separate transaction and one genuinely can commit while the other
  rolls back). A best-effort, Postgres-only true-concurrency variant (two
  real, separate transactions) is optional, not required for parity — that
  is the one where a winner's row surviving is the correct, expected
  outcome.
- **§2's commit-ownership rule is likewise tested on both dialects** —
  `test_batch_rollback_uses_real_write_path_not_mock` (§2a) runs on both
  SQLite and Postgres, since a commit/rollback ownership bug could in
  principle manifest differently under each dialect's own transaction
  semantics even though the application-level rule (only `import_batch`
  commits) is dialect-agnostic by design.
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
unique indexes specifically, plus the two dialect-load-bearing tests above.

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
  versioning.py        # NEW — §3, §4: business_key_for, artifact_hash, VersionAction, resolve_version_action
  orchestrator.py      # NEW — §1, §2, §9, §10: import_batch(db, paths, dry_run=...) -> BatchResult
  references.py        # NEW — §5: find_or_create_reference, link_reference_to_row
                        #       (kept separate from versioning.py — different concern,
                        #        different DB tables, independently testable)
```

**Correction from an earlier draft of this plan (P1 fix, §2a):**
`knowledge_repository.py` (K1-S3, existing) **is** modified by A1b — a
small, additive, backward-compatible refactor, not left untouched as an
earlier draft claimed:
- Adds `build_draft(model_cls, *, authored_by, **fields) -> KnowledgeModel`
  (pure construction) and `add_draft(db, row) -> None` (`add()` + `flush()`,
  never `commit()`/`rollback()`).
- `create_draft` is refactored to call `build_draft` + `add_draft` +
  `db.commit()` + `db.refresh()` internally — its external signature and
  behavior are **unchanged** for existing callers.
- `KNOWLEDGE_TABLE_NAME` is unchanged, still imported by `orchestrator.py`
  and now also by `references.py` (for the `knowledge_table` column on
  `KnowledgeReferenceLink`, §5).
- K1-S3's own existing test suite (`create_draft`, `submit_for_review`,
  `check_specialty_completeness`, etc.) must pass unmodified against this
  refactor — a required regression-proof for the A1b implementation PR,
  since this touches an already-reviewed, previously-"draft-only-locked"
  module.

All *new* write logic beyond `build_draft`/`add_draft` (versioning
decisions, reference find-or-create, transaction ownership) still lives in
the three new modules above — this refactor does not reopen K1-S3's
draft-only scope lock (§7 still holds: nothing added here can reach
`approved`).

**Additional correction (Codex round-7 P1 fix, §3):** A1b's scope also
includes **one small Alembic migration** — a **nullable** `artifact_hash`
column (`String(64)`, `nullable=True` — **not** `NOT NULL`, per PTH's
round-8 fix: see §3 for why a `NOT NULL` column cannot be safely added to
tables that may already have existing rows, since several hashed inputs
have no backfill path) added to each of the 5 knowledge tables
(`drug_usage`, `drug_patient_education`, `drug_side_effects`,
`drug_monitoring`, `drug_contraindications`). This was not disclosed in
earlier drafts of this plan, which implied A1b touches no schema. It's
required for §3's idempotency design to be implementable at all
(`known_versions_for` reads a stored value; several hashed inputs have no
other persistence path). Immutability for legacy `NULL`-hash rows is
enforced at the application layer (§3's fail-closed
`LEGACY_ARTIFACT_HASH_UNAVAILABLE` rule), not at the schema level — the
column itself stays permissive. Same review bar as F1/F2's migrations —
Codex + compliance + architecture, mandatory before merge.

---

## 15. Test file plan

| File | Covers |
|---|---|
| `test_medication_knowledge_import_versioning.py` | §3, §4 — all 4 `VersionAction` outcomes, full-non-retired-history artifact-hash matching (not most-recent-only), batch-local duplicate/conflict resolution across sibling files, concurrency race (bounded harmless-duplicate, identical-artifact only — distinct from §5's reference race, see §3's explicit distinction), business-key derivation per type, artifact-hash stability/sensitivity **including references and provenance, not just content fields** (reference-only change → reject, provenance-only change → reject, reference/specialty reorder → no-op, new-version-same-content-new-reference → persists) |
| `test_medication_knowledge_import_references.py` | §5, §8 — find-or-create both identity branches (including the `document_identifier IS NULL` fallback-query restriction), reuse vs. new-row creation, `accessed_at` differentiation at the app level, batch-local reference cache (same-batch reuse, no spurious unique-index rejection), idempotent link creation (duplicate DB identity within one file), fail-closed on unexpected persistence error, `test_reference_unique_index_violation_rolls_back_entire_batch` (deterministic ordering, both dialects) |
| `test_medication_knowledge_import_orchestrator.py` | §1, §2, §6, §7, §9, §10, §12 — end-to-end valid batch, `test_import_batch_requires_fresh_session` (session precondition), `test_batch_rollback_uses_real_write_path_not_mock` (commit-ownership spy + every-return-path transaction closure, §2a), NO_OP plans never reach `build_draft` (no duplicate on re-import), specialty DB-check rejection, zero-approved-rows assertion on every test, dry-run report accuracy including batch-local reference cache simulation, whole-batch rollback per failure point (never raises — always `BatchResult`), CI/PR-diff checks for API/frontend/AI/`app/knowledge/` isolation |
| `test_knowledge_repository.py` (existing, K1-S3) | §2a, §14 — regression suite proving `create_draft`'s external behavior is unchanged after the `build_draft`/`add_draft` refactor; no new tests needed here, existing tests must simply keep passing |
| `test_medication_a1b_artifact_hash_migration.py` (new, both dialects) | §3, §14 — nullable-column migration upgrade against pre-existing rows, no fake backfill, orchestrator-created rows always hashed, legacy `NULL`-hash non-retired row fails the whole batch closed (`LEGACY_ARTIFACT_HASH_UNAVAILABLE`), retired `NULL`-hash row doesn't block, single migration head, downgrade removes exactly the 5 new columns |
| `tests/integration/test_medication_a1b_orchestrator_postgres.py` | §11 — Postgres-specific partial-unique-index parity for reference dedup, real-transaction rollback proof, both dialect-load-bearing races (§2a's unique-index write-failure trigger, §5's reference race) run against real Postgres |

Total new test count target: comparable density to F1 (23 integration +
unit) and A1a (41 unit) — exact count TBD at implementation time, not fixed
by this plan.

---

## 16. What this plan does NOT authorize

- No `versioning.py`, `orchestrator.py`, or `references.py` code — this PR
  is the plan only.
- No `knowledge_repository.py` code either — §2a/§14 describe the required
  `build_draft`/`add_draft` addition as a locked *design decision*, not as
  code shipped in this PR. The actual diff lands in the implementation PR.
- No Alembic migration either — §3/§14's `artifact_hash` column addition is
  a locked design requirement, not a migration file shipped in this PR.
- No Phase B content authoring.
- No API route, frontend screen, or AI wiring of any kind.
- No change to `knowledge_repository.py`'s existing draft-only *scope lock*
  (still no `approved`-reaching path anywhere) — §2a's planned refactor adds
  two new commit-free primitives and makes `create_draft` a wrapper over
  them, but does not loosen that lock; K1-S3's own tests must keep passing
  unmodified as proof.
- No new ADR — this plan implements decisions already made in ADR-13 and
  the two Accepted findings (Finding 1/2), it does not introduce a new
  architectural decision.

## 17. GO / NO-GO

| Item | Status |
|---|---|
| A1b planning | ✅ **GO** (this document) |
| A1b implementation (`versioning.py` + `orchestrator.py` + `references.py` + the `artifact_hash` column migration + tests) | 🔴 **NOT GO** — awaits PTH + Codex + compliance + architecture review of this plan |
| Phase B authoring | 🔴 **NOT GO** — separate, later gate |
