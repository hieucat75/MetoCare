# Medication Knowledge — Phase A1b Orchestrator Implementation Plan

**Date:** 2026-07-17 (revised same day — round 2 PTH review, round 3 Codex
re-verification of the round-2 fix)
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
`db.commit()` or `db.rollback()`. Three additional gaps Codex's round-3
review found in the illustrative code below, now fixed:

**Session precondition (Codex round-3 P1):** `import_batch` requires a
`Session` with **no active pending work at entry** — no uncommitted
`db.new`/`db.dirty`/`db.deleted`. This is checked and enforced, not just
documented, because the sole-ownership guarantee (`import_batch` is the
only committer/rollbacker) only holds if the transaction it ends actually
began with this invocation — a `Session` handed in with someone else's
pending changes would have those changes silently committed or rolled back
too. The production entrypoint (a CLI script) constructs one fresh
`Session` per invocation and disposes it after — this precondition simply
makes that contract explicit and fail-fast rather than assumed:

```python
def import_batch(db: Session, paths: list[Path], *, dry_run: bool = False) -> BatchResult:
    if db.new or db.dirty or db.deleted:
        raise ValueError(
            "import_batch requires a Session with no pending work at entry — "
            "pass a fresh Session per invocation, never a shared/long-lived one."
        )
    ...
```

**Every return path explicitly closes the transaction (Codex round-3 P1):**
the earlier illustrative code returned early on validation errors or
`dry_run` without an explicit `db.rollback()`. Even though nothing was
written, the read-only queries already opened a transaction (SQLAlchemy
autobegin) — leaving it open past `import_batch`'s return is a resource
leak on the caller's `Session`, not merely untidy. Every return path below
now closes it.

**NO_OP plans must not reach `build_draft`/`add_draft` (Codex round-3 P1):**
the earlier illustrative code looped over every `ImportPlan` unconditionally
— an already-imported file (`NO_OP_ALREADY_IMPORTED`) would still get a new
draft row, directly violating idempotency (§3). Fixed by checking
`plan.version_action` before writing.

**Locked failure-contract (Codex round-3 P2):** `import_batch` never raises
for an anticipated failure — Phase 1 validation errors and Phase 2 write
failures both return `BatchResult(success=False, ...)`, not an exception.
The earlier draft's "re-raised or wrapped" hedge in §10 is retracted; only a
genuinely unanticipated interpreter-level failure outside `except
Exception`'s scope (e.g. `KeyboardInterrupt`) propagates, matching normal
Python behavior — nothing in this design special-cases that.

```python
def import_batch(db: Session, paths: list[Path], *, dry_run: bool = False) -> BatchResult:
    if db.new or db.dirty or db.deleted:
        raise ValueError("import_batch requires a fresh Session with no pending work.")

    plans_or_errors = _resolve_phase1(db, paths)  # reads only, §1 — sequential fold, §3
    if any_errors(plans_or_errors):
        db.rollback()  # close the read-only transaction; nothing was written
        return BatchResult(success=False, errors=collect_errors(plans_or_errors), written=[], dry_run=dry_run)
    if dry_run:
        db.rollback()  # close the read-only transaction; dry-run never writes
        return BatchResult(success=True, errors=[], written=[], dry_run=True, planned=build_plan_report(plans_or_errors))

    written = []
    try:
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
    except Exception as exc:
        db.rollback()
        return BatchResult(success=False, errors=[str(exc)], written=[], dry_run=False)
    return BatchResult(success=True, errors=[], written=written, dry_run=False)
```

(Illustrative code — exact signatures finalized at implementation time; the
commit/rollback ownership, the session precondition, the every-path
`rollback()`, the `NO_OP` skip, and the never-raises contract shown here are
all **locked**, not illustrative.)

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
1. Import 3 files in one batch, all valid per Phase 1.
2. Files 1 and 2 reach `add_draft` and are flushed (visible in-transaction,
   not yet committed).
3. Before file 3's reference persistence flushes, the test pre-seeds a
   colliding `drug_references` row via a **separate** session/connection,
   under the exact citation identity file 3's own reference resolves to
   (matching F1's two-tiered partial unique index, not a FK). File 3's
   `find_or_create_reference` genuinely queries first (finds nothing, since
   the colliding row was inserted by another session and isn't visible to
   this one without a fresh read after the other session commits) and then
   flushes an insert that raises a real `IntegrityError` against the unique
   index — the actual code path, not a stand-in exception. **Chosen over an
   FK-violation trigger deliberately:** this codebase's SQLite test fixture
   does not enable `PRAGMA foreign_keys=ON` (verified — `backend/app/core/
   database.py`/`tests/conftest.py` set no such pragma), so an FK-violation
   trigger would silently succeed on SQLite instead of raising, and this
   test must produce identical behavior on both dialects (§11). A unique-
   index violation is enforced natively by both SQLite and Postgres
   regardless of any pragma, making it the reliable, dialect-agnostic choice.
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
proves the session precondition above: calling `import_batch` with a
`Session` that already has pending `db.new`/`db.dirty` raises `ValueError`
immediately, before touching any file.

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
    known_versions: list[tuple[str, str]],  # [(version, content_hash), ...] — see below for where this comes from
    version: str, content_hash_value: str,
) -> VersionAction:
    """Pure decision, no DB access, no writes — operates on an already-
    fetched list of (version, content_hash) pairs. Kept DB-free so the same
    function proves both the DB-seeded case and the batch-local case below
    without duplicating the 4-rule matrix twice."""
    exact_version_match = next((h for v, h in known_versions if v == version), None)
    if exact_version_match is not None:
        return VersionAction.NO_OP_ALREADY_IMPORTED if exact_version_match == content_hash_value \
            else VersionAction.REJECT_VERSION_CONFLICT
    if any(h == content_hash_value for _, h in known_versions):
        return VersionAction.WARN_PROCEED_REPEATED_CONTENT
    return VersionAction.NEW_DRAFT


def known_versions_for(db: Session, model_cls: type, business_key: tuple) -> list[tuple[str, str]]:
    """Read-only query — fetches version + content-hash-equivalent-fields
    for EVERY non-'retired' row matching this business key, not just the
    most recent one (Codex round-3 P1 fix: the decision matrix's "matches
    an existing version" and "same version string" rules both require
    checking the FULL non-retired history, since a match can be to an
    older version, not only the latest one)."""
```

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
independently**, threading one evolving `batch_index: dict[tuple, list[tuple[str, str]]]`
(business key → known versions) through the whole batch:

```python
def _resolve_phase1(db: Session, paths: list[Path]) -> list[ImportPlan | list[FileError]]:
    batch_index: dict[tuple, list[tuple[str, str]]] = {}
    results = []
    for path in paths:
        # ... loader/schema/validators/provenance steps (§1) unchanged ...
        business_key = business_key_for(knowledge_type, ingredient_id, content)
        version = review_metadata.version
        hash_value = content_hash(knowledge_type, content)

        known = batch_index.get(business_key)
        if known is None:
            known = known_versions_for(db, model_cls, business_key)  # DB-seeded, once per key
            batch_index[business_key] = known

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
original plan §7 (two importer invocations racing the same business key;
worst case is a harmless duplicate draft row, proven bounded, not
eliminated — no distributed locking, matching the accepted single-writer
operational constraint), plus two new tests for the round-3 fixes:
- `test_content_hash_match_against_older_non_latest_version` — seed v1 and
  v2 for a business key, then import v1's exact content again under a new
  version string v3 → asserts `WARN_PROCEED_REPEATED_CONTENT` (proves
  `known_versions_for` checks the full non-retired history, not just the
  most recent row — the earlier draft's "most recent row only" design
  would have missed this).
- `test_batch_local_duplicate_new_business_key_no_op` /
  `test_batch_local_duplicate_new_business_key_conflict_rejected` — two
  files in one batch share a business key with zero DB rows; identical
  content under the same version → second file resolves `NO_OP`; differing
  content under the same version → second file resolves
  `REJECT_VERSION_CONFLICT` and the whole batch fails (§1/§10) — proves the
  batch-local fold, not just the DB-seeded path.

**Why this race is harmless but §5's reference race (below) is not:**
knowledge-content tables have no DB-level uniqueness constraint on business
key — ADR-13's append-only model *intentionally* allows multiple draft rows
to coexist for the same business key (that is what version history is). A
race here produces two informationally-redundant rows, which is a real but
accepted operational cost, not a constraint violation. `drug_references`,
by contrast, **does** have a real partial unique index on citation identity
— a race there hits an actual `IntegrityError`, not a benign duplicate, and
is handled accordingly (§5: whole-batch rollback, not "accept the
duplicate"). Do not generalize this section's "harmless duplicate" language
to §5; the two tables have different constraint shapes and therefore
different correct race behaviors.

---

## 4. New version creates a new row, never overwrites history

**Rule:** `NEW_DRAFT` and `WARN_PROCEED_REPEATED_CONTENT` both mean
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
3. Else: query
   `drug_references WHERE publisher = :p AND title = :t AND publication_date = :pd AND source_version = :v AND accessed_at = :d`.
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
`test_concurrent_reference_race_loser_rolls_back_entire_batch` (two real
sessions, both find-nothing then both insert the same citation identity;
assert the loser's `IntegrityError` triggers a full rollback of that
batch's own drafts/references, the winner's single row survives, and no
duplicate row exists — run on both SQLite and Postgres per §11),
`test_two_files_same_batch_new_reference_reused_via_batch_cache` (two
files in one batch cite an identical brand-new citation; assert exactly
one `DrugReference` row is created — proves the batch-local cache prevents
the deterministic-not-a-race unique-index rejection that would otherwise
occur, since neither file's independent find-query would see the other's
unflushed insert), `test_duplicate_reference_within_file_creates_one_link`
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
distinction is reserved for `WARN_PROCEED_REPEATED_CONTENT` (§3), which is
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
  incidental:** the race-losing transaction's `IntegrityError` (§5) must
  fire identically on both dialects — `test_concurrent_reference_race_loser_rolls_back_entire_batch`
  (§5) runs on both SQLite and Postgres, asserting the same outcome (loser
  rolls back, winner's single row survives, zero duplicates) on each.
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
  versioning.py        # NEW — §3, §4: business_key_for, content_hash, VersionAction, resolve_version_action
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

---

## 15. Test file plan

| File | Covers |
|---|---|
| `test_medication_knowledge_import_versioning.py` | §3, §4 — all 4 `VersionAction` outcomes, full-non-retired-history content-hash matching (not most-recent-only), batch-local duplicate/conflict resolution across sibling files, concurrency race (bounded harmless-duplicate — distinct from §5's reference race, see §3's explicit distinction), business-key derivation per type, content-hash stability/sensitivity |
| `test_medication_knowledge_import_references.py` | §5, §8 — find-or-create both identity branches, reuse vs. new-row creation, `accessed_at` differentiation at the app level, batch-local reference cache (same-batch reuse, no spurious unique-index rejection), idempotent link creation (duplicate DB identity within one file), fail-closed on unexpected persistence error, `test_concurrent_reference_race_loser_rolls_back_entire_batch` |
| `test_medication_knowledge_import_orchestrator.py` | §1, §2, §6, §7, §9, §10, §12 — end-to-end valid batch, `test_import_batch_requires_fresh_session` (session precondition), `test_batch_rollback_uses_real_write_path_not_mock` (commit-ownership spy + every-return-path transaction closure, §2a), NO_OP plans never reach `build_draft` (no duplicate on re-import), specialty DB-check rejection, zero-approved-rows assertion on every test, dry-run report accuracy including batch-local reference cache simulation, whole-batch rollback per failure point (never raises — always `BatchResult`), CI/PR-diff checks for API/frontend/AI/`app/knowledge/` isolation |
| `test_knowledge_repository.py` (existing, K1-S3) | §2a, §14 — regression suite proving `create_draft`'s external behavior is unchanged after the `build_draft`/`add_draft` refactor; no new tests needed here, existing tests must simply keep passing |
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
| A1b implementation (`versioning.py` + `orchestrator.py` + `references.py` + tests) | 🔴 **NOT GO** — awaits PTH + Codex + compliance + architecture review of this plan |
| Phase B authoring | 🔴 **NOT GO** — separate, later gate |
