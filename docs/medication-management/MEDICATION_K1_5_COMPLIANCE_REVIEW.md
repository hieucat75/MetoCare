# MetoCare Medication — K1.5 Compliance Review

**Version:** 1.5 (implementation session, post-Codex-review-round-4 fixes)
**Date:** 2026-07-21
**PR scope:** K1.5 — Clinical Review & Approval Write Path (`approve_row`, `retire_row`, RBAC gate)
**Branch:** `feat/medication-k1-5-approval-workflow`
**Baseline:** `main` @ `988e8f85cfd8a93819165fdc0f42fb44c8dfc683` (A1b orchestrator, PR #132)
**Reviewer:** Implementer self-review + four independent Codex CLI review rounds. **PTH sign-off has NOT yet run** — this document is an implementation-session checkpoint artifact per the plan's own governance gate (§9.4), not a merge-readiness record.

**PTH checkpoint review round 1 (2026-07-20):** both deviations reported in v1.0 approved. Gates A (real two-distinct-row PostgreSQL concurrency test) and B (transaction ownership verified against plan §5) closed in v1.1.

**Codex review round 1 (2026-07-20):** 0 P0, 3 P1, 3 P2. All 6 findings independently re-verified against source and accepted. All 6 fixed in v1.2 — see §Codex Round-1 Fixes.

**Codex review round 2 (2026-07-20):** 0 P0, 1 P1, 3 P2, 2 P3. All 6 findings independently **reproduced against the running code** (not taken on faith — each has a captured repro output) and accepted. All 6 fixed in this revision — see §Codex Round-2 Fixes. Round 2 caught real gaps in round 1's own fixes and in this document's own claims (see that section) — round 1's "PASS" self-assessments were not sufficient on their own.

**Codex review round 3 (2026-07-21):** 0 P0, 2 P1, 2 P2, 2 P3 — 7 findings total, 6 accepted and 1 (P1-3) classified as a **false positive** after independent reproduction failed to reproduce it from a clean session. All 6 accepted findings fixed in v1.4 — see §Codex Round-3 Fixes.

**Codex review round 4 (2026-07-21):** 1 P1, 1 P2, 3 P3 — reviewed round 3's own fixes by direct, independent reproduction (not taken on faith). Found that round 3's own P1-1 fix (the pending-delete guard) checked the WRONG object — a spoofed/detached caller argument bypassed it, reproduced directly against the round-3 code. All 5 findings fixed in this revision (v1.5) — see §Codex Round-4 Fixes.

---

## Codex Round-1 Fixes

### P1-1 — Canonical row re-fetch (FOR UPDATE), not caller-supplied fields

**Was:** `approve_row`/`retire_row` read `row.status`, `row.authored_by`, and (via `check_specialty_completeness`/`_deprecate_superseded`) `row.drug_ingredient_id`/business-key fields directly off the caller-supplied object. A detached/spoofed object sharing a real row's `id` but forging those other fields could bypass self-approval/specialty checks.

**Fix (v1.2):** new helper `_lock_canonical_row(db, model_cls, row_id)` — `SELECT ... FOR UPDATE` by id, fails closed (`TransitionError`) if the row doesn't exist. **Superseded by a stronger fix in round 2** — see §Codex Round-2 Fixes P1-1 below; a plain `FOR UPDATE` alone turned out not to be sufficient.

### P1-2 — Whole-function transaction boundary

**Was:** `assert_can_approve_knowledge`, `check_specialty_completeness`, `validate_transition` ran *before* the `try:` block, so a pre-write validation failure could leave the session mid-transaction.

**Fix:** the canonical-row fetch, specialty check, and `validate_transition` all moved inside the same `try/except Exception: db.rollback(); raise` block that already wrapped the DB writes.

**Test:** `TestApproveRow.test_session_usable_after_validation_failure`.

### P1-3 — Approved-key `IntegrityError` mapped to `TransitionError`; nothing else is

**Was:** two candidate rows racing to approve the same business key had the loser see a raw Postgres `IntegrityError` instead of the `TransitionError` plan §7 specifies for "lost optimistic-concurrency race."

**Fix (v1.2):** matched the constraint name as a substring of `str(exc)`. **Superseded by a stronger fix in round 2** — see §Codex Round-2 Fixes P2-1 below; string-matching turned out to be exploitable via bound SQL parameters.

### P2-1 — Same-row Postgres "concurrent" test was actually sequential

**Was:** `TestConcurrentApproveRaceUnderRealPostgresIsolation` called `approve_row` for session A synchronously to completion *before* ever calling it for session B — no threads at all.

**Fix (v1.2):** rewritten with two real `threading.Thread`s racing the same row, aligned via a `threading.Barrier`, relying on `approve_row`'s own `FOR UPDATE` for overlap. **Further hardened in round 2** — a Barrier alone doesn't *prove* contention occurred; see §Codex Round-2 Fixes P2-3, which adds a second, independent test that verifies real lock-wait state via `pg_stat_activity`.

### P2-2 — Approve/retire smoke coverage for the other 4 models

**Was:** every K1.5 behavioral and Postgres test used `DrugUsage` exclusively.

**Fix:** new `TestApproveRetireAcrossAllKnowledgeModels` (SQLite), parametrized over all 5 models: happy-path approve → same-business-key supersession → retire; different-business-key rows do NOT supersede each other. 10 tests. **Extended in round 2** — see §Codex Round-2 Fixes P3-1, which adds per-secondary-field coverage this class didn't have.

### P2-3 — Stale docstrings

**Was:** module docstring still said "There is no function anywhere in this module that can set a row's status to 'approved'"; `list_published`'s docstring said it "always returns an empty list."

**Fix:** module docstring rewritten to describe the full K1.5 lifecycle write path and the K1-dormancy distinction. `list_published`'s docstring updated.

---

## Codex Round-2 Fixes

Round 2 reviewed the round-1 fixes themselves and found that three of them — P1-1's canonical-row fetch, P1-3's constraint-name matching, and P2-1's same-row concurrency test — were each insufficient in a way round 1's own tests did not (and structurally could not) catch. Each finding below was **independently reproduced against the actual running code** before being accepted, not accepted on Codex's assertion alone.

### P1-1 — `SELECT ... FOR UPDATE` alone does not defeat identity-map staleness

**Was:** if the row was already present in the calling session's identity map (the realistic case — a caller loaded it via `db.get()` earlier in the same session) and a caller mutated an attribute in memory without persisting it (`SessionLocal` has `autoflush=False`, `app/core/database.py:37`, so this is never silently flushed), `_lock_canonical_row`'s plain `SELECT ... FOR UPDATE` returned the SAME cached Python object *without* overwriting the already-loaded, dirty attribute — SQLAlchemy's default querying behavior.

**Reproduced directly** against the pre-fix code:
```
session autoflush: False
after in-memory mutation, row.authored_by = forged-author
approved forged-author approved
fresh-session authored_by: forged-author   status: approved
```
`approve_row` incorrectly succeeded and even **persisted** the forged `authored_by` on commit — a self-approval bypass plus a data-integrity corruption, not just a validation gap.

**Fix:** `_lock_canonical_row` now uses `db.get(model_cls, row_id, populate_existing=True, with_for_update=True)`. `populate_existing=True` forces SQLAlchemy to unconditionally overwrite every already-loaded attribute on the identity-mapped object from the fresh query result — the in-memory mutation is discarded, never flushed (no `db.add()`/`db.merge()` involved). Re-verified the exact same repro now shows the canonical value winning:
```
canonical.authored_by after populate_existing reload: author-1
```

**Tests (new):** `TestApproveRow.test_ignores_forged_authored_by_on_attached_identity_mapped_object`, `test_ignores_forged_status_preventing_double_approval`, `test_ignores_forged_secondary_business_key_field`, `test_ignores_forged_drug_ingredient_id_for_specialty_gate` — four variants (authored_by, status, a secondary business-key field, drug_ingredient_id), all on an ATTACHED object (the round-1 test only covered a genuinely detached one, which the identity-map bug didn't affect).

### P2-1 — Constraint-name string matching was exploitable via bound SQL parameters

**Was:** `_is_approved_key_violation` matched the constraint name as a substring of `str(exc)` — but SQLAlchemy's rendered `IntegrityError` includes the bound SQL parameters (`[parameters: ('approved', ..., 'reviewer-1', ...)]`). A caller passing `actor_user_id="uq_drug_usage_approved_key"` made an UNRELATED `CHECK`-constraint violation (missing provenance) misclassify as a lost approval race.

**Reproduced directly** against the pre-fix code:
```
TransitionError : Row '...' lost a concurrent approval race for its business key (partial unique index 'uq_drug_usage_approved_key').
has __cause__: (sqlite3.IntegrityError) CHECK constraint failed: ck_drug_usage_approved_invariants
[parameters: ('approved', ..., 'uq_drug_usage_approved_key', ..., 'clinical_review')]
```

**Fix:** `_is_approved_key_violation` now reads the underlying Postgres driver's own structured diagnostics — `exc.orig.diag.constraint_name` (psycopg3) — and requires an EXACT match against the current model's own constraint name. Verified live against a real partial-unique-index violation:
```
exc type: IntegrityError
exc.orig type: UniqueViolation
diag.constraint_name: uq_drug_usage_approved_key
```
SQLite's driver exposes no equivalent structured signal (`exc.orig` has no `.diag`), so on SQLite this now always returns `False` — no guessing, no fallback string search. The real, load-bearing proof of the mapping is the Postgres integration test against the real driver; SQLite only proves the "must not remap" direction.

**Tests:** `TestApproveRow.test_unrelated_integrity_error_is_not_remapped` (SQLite, unchanged from round 1, still valid — a different, non-approved-key constraint, never remapped). New: `TestConstraintMappingUsesStructuredDiagnostics.test_deceptive_actor_id_does_not_cause_false_positive_remap` (Postgres) — passes `actor_user_id="uq_drug_usage_approved_key"` against a CHECK-constraint failure and asserts the raw `IntegrityError` still propagates unmapped, with `exc.orig.diag.constraint_name == "ck_drug_usage_approved_invariants"`.

### P2-2 — Success path autobegan a new transaction after commit

**Was:** `db.refresh(canonical)` ran *after* `db.commit()`, outside the `try`. `SessionLocal`'s `expire_on_commit=True` default (unchanged) means any post-commit query — including this refresh — autobegins a new transaction. Reproduced directly:
```
approved.status: approved
in_transaction after approve_row returns: True
```
The refresh was also unreachable by the function's own rollback handling, since it ran after the `except` block.

**Fix:** `db.refresh(canonical)` moved to run *before* `db.commit()`, inside the same `try` block, in the same still-open transaction (it correctly sees the function's own just-executed `UPDATE`). Commit is now the last DB operation of the success path in both `approve_row` and `retire_row`. No change to `SessionLocal`'s global configuration.

**Tests (new):** `TestApproveRow.test_session_has_no_open_transaction_after_successful_approve`, `TestRetireRow.test_session_has_no_open_transaction_after_successful_retire` — assert `not db.in_transaction()` immediately after a successful call, and that the returned object's status/attributes are still correct.

### P2-3 — Same-row race test's outcome-only assertions don't prove real contention

**Was:** the round-1-hardened same-row test (real threads + `Barrier`) could pass under 100% sequential execution with zero actual lock contention — the final outcome (one success, one `TransitionError`, count=1) is identical either way, so the test doesn't distinguish "genuine overlap" from "thread A happened to finish first."

**Fix:** new, additional test `TestSameRowRaceProvesRealLockContention` — pauses thread A (via monkeypatching `_lock_canonical_row`, keyed on `db.info["test_thread"]`) immediately after it acquires its `FOR UPDATE` lock, then polls a **third, independent monitoring connection** against `pg_stat_activity`/`pg_locks` until it observes a backend genuinely in `wait_event_type = 'Lock'` state on the `drug_usage` relation — the actual DB-level proof of contention, not an inference from timing — before releasing thread A. **Verified the test actually tests what it claims**: temporarily set `with_for_update=False` in `_lock_canonical_row` and re-ran this test — it correctly **failed** ("thread B never appeared genuinely blocked... within the timeout"), then reverted and re-confirmed green (diff-verified identical to the pre-experiment file). The original Barrier-only test is kept alongside this one, not replaced — it remains a valid (if weaker) outcome-correctness check.

### P3-1 — Business-key coverage only ever varied `drug_ingredient_id`

**Was:** `TestApproveRetireAcrossAllKnowledgeModels`'s non-supersession test only varied the ingredient; the supersession test kept every secondary field identical. If `_BUSINESS_KEY_FIELDS` were reduced to `("drug_ingredient_id",)` for any model, no existing test would notice.

**Fix:** new `TestBusinessKeyFieldsAreFullyEnforced`, parametrized over all (model, secondary field) pairs — 10 cases across the 5 models (`DrugUsage`: locale, audience; `DrugPatientEducation`: theme, locale, audience; `DrugSideEffect`: concept_code; `DrugMonitoring`: parameter, patient_context; `DrugContraindication`: condition_type, condition_key). Each builds two rows sharing the same ingredient but differing in exactly one secondary field and asserts neither supersedes the other. **Verified the tests actually catch the regression they're meant to**: temporarily reduced every model's `_BUSINESS_KEY_FIELDS` to `("drug_ingredient_id",)` and re-ran — all 10/10 new tests failed as expected; reverted and re-confirmed byte-identical to the pre-experiment file, full suite green again.

### P3-2 — This document itself

Corrected in this revision: the P1-3/error-taxonomy sections' description of the constraint-matching mechanism (now structured diagnostics, not string search); Gate A's synchronization description (a bounded `time.sleep(1.0)` pause backing a monkeypatch-based synchronization point — a real, working technique for the two-distinct-row case, but not by itself a proof of blocking, which is why P2-3 above adds a `pg_stat_activity`-verified test for the same-row case); Gate B's "`IntegrityError` is never caught by name" claim (false since the P1-3/round-2 fix — it IS caught, by `isinstance`, for the one specific structurally-verified case; corrected below); the Codex-review-status footer (now reflects two completed rounds, not zero).

---

## Codex Round-3 Fixes

Round 3 reviewed the round-2 revision (v1.3) itself. 7 findings; 6 accepted, 1 (P1-3) independently re-verified and classified as a **false positive** — reproduction from a clean session did not confirm the reported behavior. Each accepted finding below was fixed and covered by new regression tests; the false-positive finding was investigated and documented rather than "fixed."

### P1-1 — A deleted ORM object could appear approved, then be deleted at commit

**Was:** neither `approve_row` nor `retire_row` checked whether the caller-supplied `row` object had already had `db.delete(row)` called on it. `_lock_canonical_row`'s `populate_existing=True` re-fetch only overwrites column *attributes* from the DB — it does nothing to the session's own "this object is scheduled for deletion" bookkeeping (`Session.deleted` / the object's post-flush `deleted` instance state). A caller that deleted a row and then, in the same session, called `approve_row`/`retire_row` on that same object would see every check pass (the row is still physically present and unchanged — nothing has told Postgres to delete it yet) and get back a result reporting `status='approved'`/`'retired'`, only for the session's own pending `DELETE` to fire regardless at `db.commit()` time — silently deleting the row the function had just reported as approved.

**Fix:** new helper `_reject_if_pending_delete(db, row)`, called as the first statement inside both `approve_row`'s and `retire_row`'s existing `try:` block (so a rejection here rolls back through the same `except Exception: db.rollback(); raise` path already in place). Checks two conditions, covering both points in a session's lifecycle this is observable at:
- `row in db.deleted` — `session.delete()` called but not yet flushed (this codebase's `SessionLocal` has `autoflush=False`, so this is the common case).
- `sa_inspect(row).deleted` — the `DELETE` already flushed within the current still-open transaction (pending commit) by an earlier statement in the same session.

Deliberately does **not** special-case a transient, pending, or detached caller object beyond this — those already fail closed via `_lock_canonical_row`'s existing "row does not exist" path: a transient or not-yet-flushed pending object's id will not resolve to any real persisted row, and a detached object's attachment state is irrelevant since only its `id` is ever used to re-fetch the row fresh. No scope broadened beyond the reported finding.

**Tests (new):** `TestApproveRow.test_rejects_row_marked_for_deletion_not_yet_flushed`, `test_rejects_row_already_flushed_as_deleted`; `TestRetireRow` — same two, mirrored. Each: load row → `db.delete(row)` (optionally `db.flush()`) → call the operation → assert `TransitionError` → assert `not db.in_transaction()` → assert, from a **fresh** `SessionLocal()` session, the row still exists with its original, unchanged status.

### P1-2 — The specialty gate trusted dirty identity-map state

**Was:** `check_specialty_completeness` looked up `DrugIngredient`/`DrugClass` via plain `db.get(...)` (no `populate_existing`). If either was already present in the session's identity map (the realistic case — some earlier code in the same session loaded one, then mutated an attribute in memory without persisting it; `autoflush=False` means this is never silently flushed), `db.get()` returns the SAME cached, dirty Python object without querying the DB at all — the exact identity-map staleness class of bug the round-2 P1-1 fix (`_lock_canonical_row`) already closed for the row itself, but this gate's own two lookups were never updated to match.

**Fix:** both `db.get(DrugIngredient, ...)` and `db.get(DrugClass, ...)` calls in `check_specialty_completeness` now pass `populate_existing=True` — same technique as `_lock_canonical_row`, no `db.add()`/`db.merge()`, no flush of anything, `autoflush=False` unchanged. Forces an unconditional reload of every already-loaded attribute from the actual persisted row; a caller's in-memory-only mutation is discarded, never trusted, never persisted.

**Tests (new):** `TestSpecialtyCompleteness.test_ignores_forged_required_specialties_on_attached_drug_class` (forges an attached `DrugClass.required_specialties` from `['cardiology']` to `[]` in memory — gate still correctly reports incomplete), `test_ignores_forged_drug_class_id_on_attached_ingredient` (forges an attached `DrugIngredient.drug_class_id` to point at an unrelated lenient class — gate still correctly evaluates against the real, strict class). Both assert, from a fresh session, that the forged mutation was never persisted.

### P1-3 — Authorization failure outside the rollback boundary — **FALSE POSITIVE**

**Reported:** `assert_can_approve_knowledge` ran before `approve_row`'s `try:` block, allegedly risking an authorization failure leaving the session mid-transaction, outside the function's own rollback boundary.

**Independent reproduction (this revision):** starting from a clean session with `db.in_transaction() is False`, calling `approve_row(..., actor_role=<unauthorized>)` raises `KnowledgeApprovalAuthorizationError` and leaves `db.in_transaction()` at `False` — unchanged. `assert_can_approve_knowledge`/`can_approve_knowledge` are pure Python (a single `frozenset` membership test) and perform **no** database operation of any kind — there is no DB statement for a "leaked mid-transaction" state to consist of. The finding did not reproduce.

**Disposition:** kept classified as a false positive, per explicit instruction — not "fixed." As defensive hardening only (not a bug fix, since nothing reproduced), `assert_can_approve_knowledge(actor_role)` was moved to be the first statement inside the same `try:` block in both `approve_row` and `retire_row`, so it stays inside this function's one transaction boundary even if a future change ever makes it perform a DB read. This is a no-op for current behavior.

**Test (new):** `TestApproveRow.test_unauthorized_call_from_clean_session_leaves_no_open_transaction` / `TestRetireRow` (mirrored) — clean-baseline regression: from a session with `db.in_transaction() is False`, an unauthorized-role call raises the expected error and `db.in_transaction()` remains `False` afterward.

### P2-1 — The rollback-atomicity test was fake-green

**Was:** `test_rolls_back_deprecation_when_second_statement_fails` built `prior_approved` and `target` with **different** business keys (`self._submitted_row(db)` called twice, each creating its own fresh ingredient). The REAL `_deprecate_superseded` call made as part of approving `target` therefore matched zero rows sharing `prior_approved`'s business key — it never touched `prior_approved` at all. The "corruption" the monkeypatch injected was a second, unrelated raw `UPDATE` against `target` directly; the assertion `prior_approved.status == "approved"` after rollback passed trivially regardless of whether rollback worked correctly, since nothing real had ever changed `prior_approved` in the first place. The test proved nothing about atomicity.

**Fix:** `prior_approved` and `target` now share the **exact same** business key (same `drug_ingredient_id`, `locale`, `audience`). `target`'s own `approve_row` call now genuinely reaches `_deprecate_superseded`, which for real finds and deprecates `prior_approved` (unmodified production logic, not a monkeypatch stand-in). The monkeypatch's only remaining job is forcing the SECOND statement (`target`'s own approve `UPDATE`) to fail deterministically, by flipping `target`'s real DB status to `'retired'` via a raw `UPDATE ... execution_options={"synchronize_session": False}` immediately after the real deprecation runs — so `approve_row`'s atomic `UPDATE ... WHERE status = 'clinical_review'` correctly matches 0 rows and raises `TransitionError`.

**Assertions (fresh session, post-rollback):** `prior_approved` remains `'approved'` (the real deprecation was rolled back); `target` remains `'clinical_review'` (both the corrupting `UPDATE` and the failed approve attempt were rolled back); `not db.in_transaction()`.

**Break-test performed and reverted:** temporarily commented out the `db.rollback()` line in `approve_row`'s `except` block, re-ran this one test — it correctly **failed** (`AssertionError` on `not db.in_transaction()`, i.e. it caught the break at the very first thing that would go wrong). Reverted via `cp` from a pre-edit backup and diff-verified byte-identical to the pre-experiment source (`diff` reported no differences) before re-confirming green.

### P2-2 — The authorization matrix was incomplete

**Was:** every unauthorized-role test in this module used a single hard-coded role (`"patient"`); no test exercised `doctor`, `clinic_admin`, `medical_reviewer`, `ai_service`, an unrecognized string, or `None`; no test proved `approve_row` and `retire_row` share the same gate rather than each independently re-implementing an equivalent check; the only end-to-end happy-path role exercised was `internal_admin` — `super_admin` (the other approval-capable role) was never actually driven through `approve_row`/`retire_row`, only through the pure `validate_transition` unit tests.

**Fix:** new `TestApprovalAuthorizationMatrix` — parametrized `can_approve_knowledge`/`assert_can_approve_knowledge` coverage across `internal_admin`, `super_admin`, `medical_reviewer`, `doctor`, `patient`, `clinic_admin`, `ai_service` (every `UserRole` value), an unrecognized string, and `None`. A source-inspection test (`test_approve_row_and_retire_row_both_gate_through_assert_can_approve_knowledge`, mirroring this doc's own existing invariant-#2 grep technique) proves both `approve_row` and `retire_row` call the exact same `assert_can_approve_knowledge(actor_role)` gate rather than each needing independent full-matrix coverage. `TestApproveRow.test_rejects_unauthorized_role`/`TestRetireRow.test_rejects_unauthorized_role` expanded from one hard-coded role to the same 7-value parametrization, end-to-end. New `test_every_capable_role_can_approve_end_to_end`/`test_every_capable_role_can_retire_end_to_end` cover the `super_admin` happy path for both functions, previously untested end-to-end.

### P3-1 — Concurrency-race test synchronization relied on a fixed sleep

**Was:** `TestConcurrentApproveTwoDistinctRowsRaceForSameBusinessKey` synchronized thread B (holding row1's lock) and thread C (racing for it) via a bounded `time.sleep(1.0)` grace period after B's lock-acquired signal — a real, working technique in practice, but not a proof of contention, and inherently either too short (flaky on a slower/loaded machine) or too long (needlessly slow) rather than actually observing the DB state.

**Fix:** replaced the fixed sleep with the same technique `TestSameRowRaceProvesRealLockContention` already used (round-2 P2-3): a third, independent monitoring connection polls `pg_stat_activity`/`pg_locks` (bounded 0.05s interval sleeps, 10s monotonic deadline) until it observes a backend genuinely in `wait_event_type = 'Lock'` state on the `drug_usage` relation, with a clear timeout-diagnostic assertion message, before releasing thread B. Release happens in a `finally` block regardless of whether the polling assertion passes, so both threads are always joined and cleaned up rather than hanging.

**Stability check:** the race-test subset (`-k "race or Race"`, 3 tests) run 8 consecutive times against a freshly recreated database — 8/8 passed, 0 flakes.

### P3-2 — No `NOWAIT`/lock-timeout on the `FOR UPDATE` lock

**Disposition:** recorded as **non-blocking technical debt**, not fixed in this slice, per explicit instruction — `_lock_canonical_row`'s `SELECT ... FOR UPDATE` has no `NOWAIT` and no production `lock_timeout` is set, so a pathological caller holding the lock indefinitely could make a concurrent approver hang rather than fail fast. Test-level timeouts already bound every concurrency test (`thread.join(timeout=30)`, `Barrier(...).wait(timeout=10)`, the new poll's 10s monotonic deadline) so CI cannot hang indefinitely; this is an operational/production-hardening concern, not a test gap. No code change made for this finding. Tracked alongside this document's existing technical-debt list (§5-question governance answers, item 4).

---

## Codex Round-4 Fixes

Round 4 reviewed round 3's own fixes by direct, independent reproduction — writing standalone throwaway scripts to actually exercise the suspected gaps against the real running code, not accepting the round-3 self-report on faith. This caught a genuine bypass in round 3's own P1-1 fix (the thing round 3 explicitly set out to close) and a genuine gap in round 3's own P1-2 fix (the thing round 3 explicitly set out to close), both classified P1/P2 and fixed here; three additional P3 test/documentation hardening items were also accepted.

### P1 — `_reject_if_pending_delete` checked the WRONG object — round 3's own P1-1 fix was bypassable

**Was:** round 3's `_reject_if_pending_delete(db, row)` ran BEFORE `_lock_canonical_row`, checking `row in db.deleted` / `sa_inspect(row).deleted` on the CALLER-SUPPLIED `row` argument — exactly the anti-pattern every OTHER check in `approve_row`/`retire_row` was already hardened against since round 1/2 (a caller can pass a DETACHED object sharing a real row's `id` but never itself touched by `db.delete()`).

**Reproduced directly** against the round-3 code (throwaway script, not a permanent test at the time): loaded a real row, `db.delete(real_row)` (unflushed), then called `approve_row(db, spoofed, ...)` where `spoofed = DrugUsage(id=real_row.id, ...)` was a genuinely detached object never added to `db`:
```
row in db.deleted: True
spoofed in db.deleted: False
approve_row returned: approved <uuid>
fresh session sees row: None
```
`retire_row` reproduced identically (`retired <uuid>` returned, row gone from a fresh session). The compliance doc itself (v1.4, the line now corrected below) also contained a factually incorrect claim asserting this case "already fail[s] closed via `_lock_canonical_row`'s existing 'row does not exist' path" — false, because the DELETE hadn't been flushed yet, so the row still physically existed and `_lock_canonical_row` found it.

**Fix:** `_reject_if_pending_delete` now takes `canonical` (the object `_lock_canonical_row` resolved by id), not `row`. Both `approve_row` and `retire_row` now resolve `canonical = _lock_canonical_row(db, model_cls, row.id)` FIRST, then call `_reject_if_pending_delete(db, canonical)` — matching the "only `row.id` is ever trusted; every check reads canonical" invariant this file already establishes for every other property. No `merge()`, no re-add, no resurrection of the row — canonical is a plain re-fetch, exactly as `_lock_canonical_row` always did.

**Side effect discovered while fixing:** for the ALREADY-FLUSHED-delete case specifically, `_lock_canonical_row`'s own `db.get()` now returns `None` (raising "does not exist") BEFORE `_reject_if_pending_delete` even runs — because once a DELETE is flushed within the same open transaction, the row is genuinely gone from that transaction's own view, regardless of which object reference is checked. This is still fully fail-closed (same `TransitionError`, same rollback, same row-preserved-in-a-fresh-session guarantee), just via a different message than the still-unflushed case. The existing round-3 regression tests for the flushed case (`test_rejects_row_already_flushed_as_deleted`, both functions) had their `match=` updated from `"marked for deletion"` to `"does not exist|marked for deletion"` to reflect this — their assertions on rollback/row-preservation are unchanged.

**Break-test performed and reverted:** temporarily restored the round-3 ordering (`_reject_if_pending_delete(db, row)` before `_lock_canonical_row`) — the new spoofed-object regression tests for the UNFLUSHED case failed exactly as expected (`Failed: DID NOT RAISE TransitionError`) on both `approve_row` and `retire_row`; the flushed-case tests still passed (expected — orthogonally caught by the existence check regardless of ordering). Reverted via a clean backup copy, diff-verified byte-identical, re-confirmed green.

**Tests (new):** `TestApproveRow`/`TestRetireRow` — `test_rejects_spoofed_object_when_real_row_has_unflushed_pending_delete`, `test_rejects_spoofed_object_when_real_row_already_flushed_as_deleted` (4 tests total). Each: load a real row, `db.delete(real_row)` (optionally `db.flush()`), construct a DETACHED object sharing the real row's `id` (never added to `db`), call the operation with the spoofed object, assert `TransitionError`, assert `not db.in_transaction()`, assert a fresh session still sees the row with its original status. The pre-existing round-3 tests (same-object case) are kept unmodified in intent — only the flushed-case `match=` pattern was widened.

### P2 — `ClinicalSpecialty.code` still had the identity-map staleness round 3's own P1-2 fix was meant to close

**Was:** round 3's P1-2 fix added `populate_existing=True` to the `DrugIngredient`/`DrugClass` lookups in `check_specialty_completeness`, but the THIRD `db.get()` call in the same function — `db.get(ClinicalSpecialty, r.specialty_id)`, resolving each recorded review's specialty — was left unchanged, with the exact same staleness exposure.

**Reproduced directly**: recorded a genuine, matching specialty review (`check_specialty_completeness` → `True`), then forged the already-attached `ClinicalSpecialty.code` in memory (never flushed) to a non-matching value:
```
attached_specialty.code (forged, in-memory): totally-different-code-never-required
fresh-session persisted code: cardiology-24e7e771   (the real, still-matching code)
check_specialty_completeness after forging ClinicalSpecialty.code: False
```
The gate incorrectly flipped from complete to incomplete based on the forged in-memory value. The reverse direction is compliance-sensitive: forging an unrelated, ALREADY-reviewed-but-wrong specialty's code to MATCH the actually-required code could let an approval bypass a specialty review that never really happened.

**Fix:** `db.get(ClinicalSpecialty, r.specialty_id, populate_existing=True)` — same technique as the other two lookups in this function. No `merge()`, no flush of dirty values, `autoflush=False` unchanged.

**Break-test performed and reverted:** temporarily removed `populate_existing=True` from this one call — both new regression tests failed exactly as expected (`assert True is False` / `assert False is True`, the forged value winning over the persisted one). Reverted via the same clean backup, diff-verified byte-identical, re-confirmed green.

**Tests (new):** `TestSpecialtyCompleteness.test_ignores_forged_matching_specialty_code_forged_to_mismatch` (persisted code matches, attached code forged to a non-matching value → gate stays `True`) and `test_ignores_forged_mismatching_specialty_code_forged_to_match` (persisted code does NOT match, attached code forged to the required value → gate stays `False`, approval not bypassed).

### P3 — Cross-session semantics, now resolved as a structural side effect of the P1 fix

Round 4's review raised a design concern: `sa_inspect(row).deleted` reflects whichever session `row` currently happens to be attached to, which could differ from `db` if a caller passed an object loaded in a different session. Since the P1 fix now makes `_reject_if_pending_delete` operate on `canonical` — which is ALWAYS resolved via `db.get(...)` on `db` itself, and therefore always attached to `db` specifically, never any other session — this concern no longer applies: every state check this function performs is now guaranteed to reflect `db`'s own session bookkeeping. Documented explicitly in `approve_row`'s docstring (the "Caller-object precondition" paragraph) rather than adding a same-session assertion — a detached caller-supplied `row` remains a normal, fully supported case (only `.id` is ever read from it), consistent with the existing threat model for every other property this module defends (authored_by, status, business key, drug_ingredient_id).

### P3 — Pending-delete tests did not cover the spoofed-object threat model (now closed by the P1 fix's own tests)

The round-3 pending-delete regression tests only ever exercised the "same object" case, unlike every sibling test for other caller-supplied properties in this file (`test_ignores_spoofed_fields_on_caller_supplied_object` and friends). This gap is closed by the 4 new tests added under the P1 fix above, which follow the established spoofed-object pattern exactly.

### P3 — PostgreSQL lock-contention polls filtered by relation only, not by the specific waiting backend

**Was:** both `TestSameRowRaceProvesRealLockContention` (round 2) and the two-distinct-row race test's polling (round 3's own P3-1 fix) queried `pg_stat_activity` filtered only by `l.relation = 'drug_usage'::regclass AND a.wait_event_type = 'Lock'` — matching ANY backend blocked on that relation, not necessarily the specific thread under test. Low likelihood of a false positive in the current dedicated-throwaway-DB, sequential-test-file setup, but not hermetically scoped to the transaction actually being verified.

**Fix:** each test's genuinely-waiting thread (thread B in the same-row test, thread C in the two-distinct-row test) now captures its own `pg_backend_pid()` directly from its own connection, immediately after creating its session and before doing anything that could block, and publishes it to the main thread via a dedicated `threading.Event`. The monitoring poll then filters `pg_stat_activity` by `a.pid = :pid AND a.wait_event_type = 'Lock' AND a.state = 'active'` — pinned to that EXACT backend, no relation-name filter needed since the pid alone is already precise. Monotonic deadline, bounded 0.05s–0.1s poll intervals, and `finally`-guaranteed release/cleanup are all unchanged from round 3.

**Stability check:** the race-test subset (`-k "race or Race"`, 3 tests) run 8 consecutive times against a freshly recreated database with the pid-pinned polling — 8/8 passed, 0 flakes.

### P3-2 (unchanged from round 3) — No `NOWAIT`/lock-timeout

Round 4 confirmed this remains correctly classified as non-blocking technical debt, per explicit instruction not to change production lock semantics in this slice. No new code change.

---

## Scope lock verification

| Requirement | Status | Evidence |
|---|---|---|
| `clinical_review → approved` write path | ✅ | `approve_row()`, `app/services/knowledge_repository.py` |
| `deprecated → retired` write path | ✅ | `retire_row()`, same file |
| `approved → deprecated` automatic on supersession | ✅ | `_deprecate_superseded()`, called from inside `approve_row`'s own transaction |
| RBAC via single named abstraction | ✅ | `can_approve_knowledge()` / `assert_can_approve_knowledge()` — grep-verified (see §Invariant #2 below) |
| No new Alembic migration | ✅ | `alembic heads` reports single head `k1_a1b_artifact_hash` (unchanged) |
| No new/changed DB schema | ✅ | Partial unique indexes (`uq_drug_usage_approved_key` etc.) already existed from `k1_m01_knowledge_schema` |
| No API route | ✅ | No file under `app/api/` touched |
| No frontend | ✅ | `frontend/` untouched |
| No AI wiring | ✅ | No file under `app/ai`/context-builder touched |
| Dormancy preserved | ✅ | `grep -rln "knowledge_repository" ../frontend/src app/api app/ai` → zero hits |
| No real clinical content | ✅ | All test fixtures use synthetic placeholder strings |
| Self-approval override mechanism | ✅ not built | Out of scope per plan §3.2, not touched |
| `CLINICAL_ADVISOR` role / `UserRole` enum change | ✅ not built | `app/models/user.py` untouched |

## Non-negotiable invariants (plan §3.5) — enforcement + evidence

**#1 — At most one `approved` row per business key, at any instant, enforced two independent ways** (deviation from plan's exact statement order — **PTH-approved**):
- Service-layer: `approve_row` calls `_deprecate_superseded()` and its own approve `UPDATE` inside **one** `try/except Exception: db.rollback(); raise` block, both before `db.commit()`. Verified: `TestApproveRow.test_auto_deprecates_prior_approved_row_same_business_key` (SQLite).
- DB-layer backstop: the pre-existing partial unique index (`uq_drug_usage_approved_key`, `k1_m01_knowledge_schema`, NOT added by this slice). Verified independently of the service layer — direct `INSERT` bypassing `approve_row` entirely — by `TestPartialUniqueIndexBackstop` against **real PostgreSQL**.
- Deprecating BEFORE approving (not after, despite the plan's narrative ordering) avoids a transient double-`approved` state that would trip the non-deferred partial unique index. Atomicity is unaffected — a losing race still rolls back the whole transaction.

**#2 — RBAC only through `can_approve_knowledge()`:** `grep -n "actor_role" backend/app/services/knowledge_repository.py` shows exactly one role-set comparison (`return actor_role in _APPROVAL_CAPABLE_ROLES`, inside `can_approve_knowledge`'s own body); every other match is a type annotation, a delegating call, or docstring/error text.

**#3 — Lifecycle fails closed on illegal/duplicate/reverse transitions:** `approved → approved` and `retired → approved` both explicitly tested and rejected (`test_rejects_double_approval`, `test_rejects_approval_of_retired_row`).

## Gate A — real two-distinct-row PostgreSQL concurrency race (production path)

**Test:** `TestConcurrentApproveTwoDistinctRowsRaceForSameBusinessKey`, `tests/integration/test_medication_k1_5_approval_workflow_postgres.py`.

**Concurrency model:** a plain `threading.Barrier` alone was insufficient (measured empirically — 10/10 repeat runs of a Barrier-only version resulted in both threads succeeding, since local Postgres is fast enough that thread B's entire transaction can complete before thread C's first statement is even sent). The working mechanism: `repo._deprecate_superseded` is instrumented via `monkeypatch` so thread B's call pauses — *after* genuinely acquiring Postgres's row-level lock on the pre-existing approved row inside its still-open transaction — until thread C's own conflicting statement has had time to reach Postgres and physically block on that lock. **Round-3 update:** this used to be confirmed via a bounded `time.sleep(1.0)` grace period after the lock-acquired signal — a real, working technique, but not itself a proof of blocking (P3-1 above). Now confirmed the same way the companion same-row test already was (P2-3): a third, independent monitoring connection polls `pg_stat_activity`/`pg_locks` until it observes a backend genuinely blocked on the `drug_usage` relation, with a monotonic deadline and bounded poll interval, before releasing thread B. `approve_row` itself and its exact statement sequence are unmodified.

**Race result (deterministic across repeated runs):** exactly one thread succeeds; the loser raises `TransitionError` with `__cause__` being the real Postgres `IntegrityError` naming `uq_drug_usage_approved_key` (verified via structured `exc.orig.diag.constraint_name` matching, per the P2-1 round-2 fix — not string search). Never zero, never two approved rows (verified from a third, uninvolved session). The old approved row is deprecated exactly once; the loser's own row is untouched at `clinical_review`.

**Kept, not replaced:** `TestPartialUniqueIndexBackstop` (direct bypass `INSERT`) remains as an additional, lower-level proof.

## Gate B — transaction ownership verified against the frozen plan

**Exact plan text** (`MEDICATION_K1_5_APPROVAL_WORKFLOW_IMPLEMENTATION_PLAN.md`, §5, quoted verbatim):

> `approve_row` and `retire_row` each own their own transaction end-to-end ... the function itself calls `db.commit()` (success) or `db.rollback()` (any failure) and never leaves the session mid-transaction either way.
>
> `approve_row` specifically owns **two** UPDATE statements ... inside **one** transaction ... wrapped in one `try/except Exception: db.rollback(); raise` ... a failure in the second UPDATE must not leave the first one committed.

**Verdict:** the plan explicitly makes `approve_row`/`retire_row` themselves the transaction boundary — matches the implementation. No code change made for this reason; instead:

- **Deterministic (non-threaded) rollback proof:** `TestApproveRow.test_rolls_back_deprecation_when_second_statement_fails` (SQLite) — forces the second statement to fail via a monkeypatched `_deprecate_superseded` that corrupts the target row's real DB status mid-transaction (updated in round 2 to work correctly with the `populate_existing` canonical-fetch fix — a caller-side stale-object trick no longer reaches the write statements at all, since the canonical fetch now always wins).
- **Success-path proof (round 2):** `test_session_has_no_open_transaction_after_successful_approve`/`_retire` — `not db.in_transaction()` immediately after a successful call, closing the gap the original Gate B verification missed (it only checked failure paths).
- **Why `except Exception: db.rollback(); raise` is the right boundary here:** `approve_row` performs multiple DB statements that must succeed or fail together, and per plan §5 this function *is* the transaction owner with no outer caller-owned transaction to defer to — a narrower `except` would risk leaving the session broken on a non-`IntegrityError`/`TransitionError` failure (a driver-level disconnect, for instance).
- **`IntegrityError` handling is precise, not swallowed:** it IS caught, by `isinstance`, but only to check one exact, structurally-verified condition (`_is_approved_key_violation`, per the P2-1 round-2 fix) — if true, it is re-typed via `raise TransitionError(...) from exc` (the original stays reachable via `__cause__`, never discarded); if false, the bare `raise` re-raises it completely unmodified. Verified by `test_unrelated_integrity_error_is_not_remapped` and `test_deceptive_actor_id_does_not_cause_false_positive_remap` (the negative cases) and by Gate A's race test (the positive case, checked via `__cause__`).

## Error taxonomy (plan §7)

| Error | Raised by | Meaning |
|---|---|---|
| `TransitionError` (existing) | `validate_transition`, `submit_for_review`, `approve_row`, `retire_row` | Illegal transition, self-approval, incomplete specialty, or lost concurrency race |
| `KnowledgeApprovalAuthorizationError` (new) | `assert_can_approve_knowledge` | Actor's role lacks approve/retire capability |

`approve_row` maps exactly one specific case — an `IntegrityError` whose underlying Postgres driver diagnostics (`exc.orig.diag.constraint_name`) EXACTLY match the current model's own approved-key partial unique index — into `TransitionError(...) from exc`. This is a precise, structurally-verified check (round-2 P2-1 fix), not a string search; SQLite has no equivalent structured signal and the mapping never fires there. Every other `IntegrityError` propagates completely unmodified — verified by `test_unrelated_integrity_error_is_not_remapped` (SQLite, a different constraint), `test_deceptive_actor_id_does_not_cause_false_positive_remap` (Postgres, an adversarial bound-parameter value), and `TestPartialUniqueIndexBackstop` (proves the constraint itself still fires for a real violation).

## Transaction ownership (plan §5)

`approve_row` and `retire_row` each own their transaction end-to-end. As of the round-2 P2-2 fix, `db.refresh()` runs *before* `db.commit()` (inside the same open transaction), so `db.commit()` is the last DB operation of the success path in both functions — verified by `not db.in_transaction()` immediately after a successful call. Neither function is called from `orchestrator.import_batch`'s own transaction.

## Test coverage

| Layer | File | Tests | Result |
|---|---|---|---|
| Unit (SQLite) | `backend/tests/test_knowledge_repository.py` | Round-4 additions: spoofed-object pending-delete guard (4, `approve_row`+`retire_row`), `ClinicalSpecialty` identity-map (2) — plus every round-1/2/3 test, unmodified except two `match=` widenings (see P1 fix above) | **116/116 passed** (was 110/110 in v1.4) |
| Integration (real PostgreSQL) | `backend/tests/integration/test_medication_k1_5_approval_workflow_postgres.py` | Same-row race (Barrier); same-row race with `pg_stat_activity`-verified lock contention, now pid-pinned (round-4); two-distinct-row race, now pid-pinned (round-4); partial-unique-index backstop; deceptive-actor-id constraint-mapping proof | **5/5 passed**, race-test subset stable across **8/8** repeat runs against a freshly recreated database |
| Regression (related Postgres, medication knowledge) | 7 files under `tests/integration/`, run individually against a freshly recreated `mcp_test` database each | 35+14+24+23+8+5+5 = **114/114 passed**, 0 failed |
| Regression | Full backend suite, `-m "not integration"` | **3173 passed, 11 skipped, 114 deselected, 0 failed** | Includes `test_zero_approved_rows_exist_anywhere` (both copies) still passing unmodified |

**Self-verification of new tests' rigor:** round-2's `TestSameRowRaceProvesRealLockContention` fails when `with_for_update` is disabled; `TestBusinessKeyFieldsAreFullyEnforced` (10/10 cases) fails when `_BUSINESS_KEY_FIELDS` is reduced to `drug_ingredient_id` only; round-3's rebuilt `test_rolls_back_deprecation_when_second_statement_fails` fails when `approve_row`'s `db.rollback()` is temporarily disabled; round-4's 4 new spoofed-object pending-delete tests fail (unflushed case only, as expected) when the round-3 check-ordering is temporarily restored; round-4's 2 new `ClinicalSpecialty` tests fail when `populate_existing=True` is temporarily removed from that one lookup. All break-test experiments reverted and diff-verified byte-identical to the pre-experiment source before re-confirming green.

### Pre-existing test-isolation limitation (not a K1.5 regression)

Running the whole `tests/integration/` directory together in one pytest session produces failures from cross-file contamination between test files sharing one live Postgres database in the same run — each file's `migrated_schema` fixture assumes exclusive DB ownership. Independently corroborated by `.github/workflows/ci.yml`'s own job, which only ever runs 3 of these 7 files together. Not touched here (pre-existing, unrelated to K1.5, fixing shared-fixture conventions is out of scope). K1.5's own regression check runs each related file individually against a fresh database instead (see table above).

### Deviation #2: test isolation for the shared session-scoped SQLite fixture — **PTH-approved**

`tests/conftest.py::db` is a plain session on a session-scoped SQLite file with no per-test rollback. `TestApproveRow`/`TestRetireRow`/the new round-2 test classes all use an `autouse` cleanup fixture (snapshot row ids before the test, delete everything created at teardown) rather than editing the two pre-existing `test_zero_approved_rows_exist_anywhere` regression tests, keeping their literal "still passes unmodified" exit criterion true.

## Lint / type checks

- `ruff check .`: all clean, 0 issues.
- No mypy/pyright configured in this repo (consistent with every prior K1/A1b slice).
- `alembic heads`: single head, `k1_a1b_artifact_hash`, unchanged.

## 5-question governance answers

1. **Which ADR?** ADR-13 — implements the previously-unreachable `clinical_review → approved`, `approved → deprecated`, `deprecated → retired` write paths.
2. **Which Exit Criterion?** Closes the gap named in `MEDICATION_K1_S3_COMPLIANCE_REVIEW.md`'s own technical-debt note (#4b).
3. **Scope expansion?** No — no migration, no API, no frontend, no AI, no real content, no new role.
4. **Technical debt?** (a) `_BUSINESS_KEY_FIELDS` duplicates `medication_knowledge_import/versioning.py`'s own copy by hand (documented in-code). (b) Self-approval override mechanism remains unbuilt (deliberately, plan §3.2). (c) No minimum grace period between `deprecated`/`retired` enforced (deliberately, ADR-13). (d) **(Round 3/4, P3-2, unchanged)** `_lock_canonical_row`'s `SELECT ... FOR UPDATE` has no `NOWAIT` and no production `lock_timeout` is configured — a caller holding the lock indefinitely could make a concurrent approver hang rather than fail fast. Deliberately not added in this slice (not required by the frozen plan); test-level timeouts already bound every concurrency test so CI itself cannot hang.
5. **Rollback loss?** N/A at schema level (no migration). Service level: both functions roll back fully on any failure, verified by the concurrency tests and `test_rejects_double_approval`.

## Codex review status

**Four rounds complete:**
- Round 1 (2026-07-20): 0 P0, 3 P1, 3 P2 — all 6 fixed (v1.2).
- Round 2 (2026-07-20): 0 P0, 1 P1, 3 P2, 2 P3 — all 6 fixed (v1.3), including corrections to three of round 1's own fixes that round 2 found insufficient.
- Round 3 (2026-07-21): 0 P0, 2 P1, 2 P2, 2 P3 — 6 of 7 accepted and fixed (v1.4); 1 (P1-3) independently investigated and classified as a false positive (did not reproduce from a clean session).
- Round 4 (2026-07-21): 1 P1, 1 P2, 3 P3 — all 5 fixed (this revision, v1.5), including a correction to round 3's own P1-1 fix (the pending-delete guard checked the wrong object — a spoofed/detached argument bypassed it) and round 3's own P1-2 fix (one of three `db.get()` lookups in the same function was left without `populate_existing=True`). Both were reproduced directly against the round-3 code before being accepted, not taken on faith.

**Verdict: READY FOR CODEX REVIEW ROUND 5.** Zero unresolved P0/P1/P2 from rounds 1–4; the sole open item (P3-2, `NOWAIT`/lock-timeout) remains explicitly recorded as non-blocking technical debt, not a defect requiring a fix in this slice. Per this program's standing convention (§9.4), a Codex round with 0 new P0/P1 and explicit PTH sign-off are still required before merge. **No commit/PR/merge has happened.**
