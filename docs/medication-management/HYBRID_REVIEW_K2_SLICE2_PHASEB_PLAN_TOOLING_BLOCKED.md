# HYBRID_REVIEW_K2_SLICE2_PHASEB_PLAN_TOOLING_BLOCKED

**This is NOT a completed independent Codex review.** Three consecutive `codex exec` runs against `docs/medication-management/MEDICATION_K2_SLICE2_EXTERNAL_INGESTION_IMPLEMENTATION_PLAN.md` each performed substantial real investigation (reading the target plan in full, the Slice 0 plan in full, every cited model/service/migration/CI file, and in two runs a live `sqlite3` reproduction of a schema defect) but **none produced a final synthesized report** — all three stalled on a local Codex CLI defect (§D) before emitting a `turn.completed` event. Per explicit instruction, no fourth attempt was made.

This document instead separates what Codex itself directly verified against the repository (§A) from what Claude independently verified afterward to close the gap (§B), states plainly what the 15 mandatory review areas were **not** conclusively covered (§C), documents the exact tooling failure (§D), and gives the minimal corrections the plan needs (§E) with a final verdict (§F).

**No code was written. No migrations were created. No PR was opened. Nothing was deployed. The implementation plan itself was not modified in this task.**

---

## A. Findings Directly Produced or Verified by Codex Before the Tooling Failure

Across the three runs, Codex's own transcripts (tool calls + its own narrated interim conclusions, captured verbatim in the streamed JSONL before each stall) directly produced the following, all later independently confirmed by Claude in §B:

1. **A1 — SQLite foreign keys are not enabled by the current engine.** Codex ran `rg -n 'PRAGMA foreign_keys|foreign_keys=ON|ForeignKey.*ondelete|event\.listens_for.*connect' backend/app backend/tests backend/alembic` (run 3) and concluded in its own narration: *"SQLite foreign keys are not enabled by the current engine setup, so the plan's claimed cross-engine `ON DELETE RESTRICT` protection is false."*

2. **A2 — The plan's SQLite `content_hash` CHECK repeats an embedded-NUL weakness Slice 0 already found and fixed.** Codex's own narration (run 3): *"the plan's SQLite hash CHECK repeats an embedded-NUL weakness that Slice 0 already fixed."* This followed Codex reading `backend/alembic/versions/k2_s0_round3_hardening.py` in full.

3. **A3 — A live `sqlite3` reproduction (run 1) demonstrating a NULL-admits-invalid-row gap in the plan's own CHECK-constraint pattern.** Codex constructed and ran, against an in-memory SQLite database, the plan's exact `duplicate_of_artifact_id` and target-XOR CHECK constraints (verbatim from plan §3.3), then executed:
   ```sql
   INSERT INTO t(status, target_type, ingredient_id) VALUES ('staged', NULL, 'ingredient-1');
   ```
   and confirmed the row was accepted rather than rejected. Codex's own narration immediately after (run 3, which independently re-derived the same class of defect via direct file reading rather than re-running the repro): *"the proposed NULL-sensitive CHECKs admit invalid rows under SQL three-valued logic."*

4. **A4 — Missing-source attempts are not representable with the proposed non-null `source_id`.** Codex's own narration (run 3): *"missing-source attempts are not representable with the proposed non-null `source_id`."* This followed Codex reading plan §2 (architecture diagram) and §3.3 (schema) together.

5. **A5 — Confirmed factual claims in the plan.** Across all three runs, Codex read `backend/app/core/system_actors.py` and `backend/app/core/feature_flags.py` in full and its own narration (run 3) states: *"The plan's claimed actor and flag reservations are confirmed in current source."* — i.e. Codex itself verified the plan's claim that `SystemActor.MEDICATION_INGESTION` and `FeatureFlag.MEDICATION_EXTERNAL_SOURCE_INGESTION` already exist and require no new code.

None of the three runs reached a point where Codex assigned formal P0/P1/P2 severities, produced the required output shape (Sources Inspected / Verdict / Finding Counts / Findings / Corrections / Accepted Risks), or covered mandatory review areas 3, 6 (fully), 9, 10, 11, 12, 14, 15 in its own words before stalling.

---

## B. Findings Independently Verified by Claude Against Repository Files

Claude re-derived and independently confirmed A1–A4 by direct file reads (not by trusting Codex's narration), and additionally covers review areas Codex's transcripts show it never reached before stalling.

### B1 (confirms A1) — SQLite FK enforcement is off codebase-wide, not just for Slice 2

- `backend/app/core/database.py:23-32` (`_make_engine`): for a `sqlite` URL, `connect_args = {"check_same_thread": False}` only. No `PRAGMA foreign_keys=ON`, no `sqlalchemy.event.listens_for(engine, "connect")` handler.
- `grep -rn "PRAGMA foreign_keys\|foreign_keys.*ON\|event.listens_for.*connect" backend/app backend/tests backend/alembic` → **zero matches** anywhere in the codebase.
- SQLite disables foreign-key enforcement by default per connection unless `PRAGMA foreign_keys=ON` is explicitly issued. Since it is issued nowhere, **every `ON DELETE RESTRICT` FK in this codebase — Slice 0's and the plan's proposed Slice 2 ones alike — is a no-op on SQLite as currently configured.**
- **This is a pre-existing, codebase-wide gap, not one newly introduced by the Slice 2 plan.** However, the plan (`§4.2`, line ~234; `§18`, line ~522) explicitly claims `ON DELETE RESTRICT` as the mechanism satisfying PTH's own required invariant "referenced targets cannot be hard-deleted into orphaning," and the plan's own test matrix (`§15`, line ~478, "Orphan prevention... `integration`") does not mark this test PostgreSQL-only. As written, that test would pass on PostgreSQL and **silently pass-but-not-actually-verify on SQLite** (the DELETE would succeed, the orphan would occur, and no assertion failure would result unless the test explicitly checks dialect).
- **Structural comparison that sharpens this finding:** Slice 0 itself does *not* rely on bare FK `RESTRICT` for its own analogous "no orphan / no hard delete" guarantee — `k2_s0_round3_hardening.py` Guard 7 (lines 490-527) adds explicit `BEFORE DELETE`/`BEFORE TRUNCATE` triggers on all 5 knowledge content tables specifically because FK-level protection was judged insufficient. The Slice 2 plan's reliance on bare FK `RESTRICT` alone is inconsistent with the precedent the very codebase it claims to mirror already established.

### B2 (confirms A2) — The plan's proposed SQLite hash CHECK is the exact pre-fix pattern Slice 0 discovered was broken

- Plan `§3.5` (line ~213) proposes: `CHECK (length(content_hash) = 64 AND content_hash = lower(content_hash) AND content_hash NOT GLOB '*[^0-9a-f]*')`.
- `backend/alembic/versions/k2_s0_round3_hardening.py:249-273` documents, in detail, a real reproduced attack against exactly this pattern: *"SQLite's own string-matching internals stop at an embedded NUL (U+0000) byte, so a value like `"a" * 64 + "\x00" + "attacker-controlled garbage"` satisfies the 64-class GLOB pattern... reproduced directly via a real SQLAlchemy raw-SQL INSERT... the 87-byte value above was accepted and persisted verbatim... Ordinary `LENGTH(column)` cannot catch this either — SQLite's own `LENGTH()` on a TEXT value ALSO stops at the same embedded NUL and misreports 64."* The fix Slice 0 shipped combines `GLOB` with `LENGTH(CAST(column AS BLOB)) = 64` — a byte-length check immune to the embedded-NUL truncation that a plain `length()` (used by the Slice 2 plan) is not.
- **The plan's §3.5 claim — "reuses the exact validator pattern already shipped for `KnowledgeAIGeneration.input_hash`/`output_hash`" — is false as written.** It reuses an *earlier, already-superseded* version of that pattern (pre–Round 3.1), not the current one. The plan's own stated defense-in-depth rationale (ORM-level `re.fullmatch` as primary defense, DB CHECK as secondary) is a sound structure, but the DB-layer half of that structure is concretely broken in the same way Slice 0's was before its own fix.

### B3 (confirms A3) — The plan's target-XOR CHECK constraint is bypassable under SQL three-valued logic

Independently re-derived (not just trusting Codex's repro) by evaluating the plan's own proposed CHECK (`§3.3`, lines ~186-193) against the row `status='staged', target_type=NULL, target_drug_ingredient_id='x', target_drug_product_id=NULL`:

```
Branch 1: status='staged' (TRUE) AND target_type='drug_ingredient' (NULL = 'drug_ingredient' → NULL) AND ...  → TRUE AND NULL → NULL
Branch 2: status='staged' (TRUE) AND target_type='drug_product'    (NULL = 'drug_product'    → NULL) AND ...  → TRUE AND NULL → NULL
Branch 3: status != 'staged' → FALSE                                                                          → FALSE
Overall:  NULL OR NULL OR FALSE = NULL
```

A CHECK constraint evaluating to `NULL` (unknown) is treated as **passing**, not violated, in both PostgreSQL and SQLite (standard SQL three-valued-logic CHECK semantics). **A row with `status='staged'`, a populated `target_drug_ingredient_id`, but `target_type` left `NULL` is silently accepted** — directly contradicting the plan's own claimed invariant that "staged requires exactly one valid target" (including a non-null discriminator) and the review's required "exactly zero or one target may be populated... never both" XOR semantics. The plan's `duplicate_of_artifact_id` CHECK (lines ~176-181) does **not** have this flaw — it correctly uses `IS NULL`/`IS NOT NULL` predicates throughout, which are NULL-safe. The target-XOR CHECK is the one place the plan mixes NULL-unsafe `=` equality comparisons into a branch alongside NULL-only columns, which is what creates the gap.

### B4 (confirms A4) — `source_not_found`/`source_disabled` rejections cannot be persisted as written

- Plan `§3.3` line 148: `ingestion_attempts.source_id` is `String(36), FK → ingestion_sources.id, ON DELETE RESTRICT, NOT NULL`.
- Plan `§2` architecture diagram, lines 78-79: step 1 is *"resolve source_key → source row (source_not_found / source_disabled gate)"*, and only **after** that does step 2 run: *"INSERT ingestion_attempts (status='received')."*
- Plan `§8` line ~329 confirms the same ordering: *"Source resolution — `source_key` must exist... and be `enabled=True`... Checked first."*
- **Consequence:** if `source_key` does not resolve to any row at all (`source_not_found`), there is no valid `source_id` value to satisfy the column's `NOT NULL` FK constraint — so no `ingestion_attempts` row can be inserted for this case at all. Yet `source_not_found` is listed in the plan's closed `rejection_code` taxonomy (`§8`) as an achievable value on a `received → rejected` transition, and the CLI contract (`§7`) unconditionally promises `{"attempt_id", "status": "rejected", "rejection_code": "source_not_found", ...}` in its output shape. **As written, this specific rejection path cannot produce the attempt row (or the `attempt_id`) the plan's own CLI output contract requires.** `source_disabled` does not have this problem — a disabled source still has a valid `source_id` to reference, so that half of gate 1 is representable as written. This is a real gap, not a stylistic one: it directly undermines PTH's explicit "maintain fail-closed attempt lifecycle" requirement (§1 of the original decisions), since the one class of failure most likely to happen from a misconfigured caller (a typo'd `source_key`) is the one class the schema cannot actually record.

### B5 — Single Alembic head confirmed (no defect found)

Ran `alembic heads` directly against the repo (from `backend/`, using its project venv): **`k2_s0_round3_hardening (head)`** — exactly one head, matching the plan's claim (`§10`). An earlier automated regex-based cross-check by Claude produced a false positive suggesting 3 heads; that script had a parsing bug and is not trustworthy — the authoritative `alembic heads` CLI output is single-head, confirming **no migration-chain defect exists here.**

### B6 — CI hand-maintained test-file-list staleness confirmed as the plan describes

`grep -n "test_medication" .github/workflows/ci.yml` shows exactly 3 files (`test_medication_p0_migrations.py`, `test_medication_k1_knowledge_migration.py`, `test_medication_k1_s2_catalog_migration.py`) in the PostgreSQL job's explicit list. `ls backend/tests/integration/ | grep medication_k2` confirms 4 files exist on disk (`test_medication_k2_s0_origin_migration.py`, `test_medication_k2_s0_round3_hardening_postgres.py`, `test_medication_k2_slice1_postgres.py`, `test_medication_k2_widen_evidence_level_migration.py`) that are **not** in that list. This exactly matches the plan's own `§13` claim — **the plan is accurate here; no correction needed on this point**, only flagged for completeness since it was one of the 15 mandatory review areas.

### B7 — Naming/precedent inconsistencies not reached by Codex before stalling

- **B7a (P2):** Plan `§3.4` header states the new `ingestion_attempt_transitions` table is *"Same shape and enforcement idiom as Slice 0's `k2_s0_lifecycle_transitions` history table."* `k2_s0_lifecycle_transitions` is a **migration revision id**, not a table name — the actual table (`backend/app/models/drug_knowledge_lifecycle_transition.py:48`) is `knowledge_lifecycle_transitions`. Cosmetic, but worth fixing since a future implementer searching the codebase for a table literally named `k2_s0_lifecycle_transitions` will not find one.
- **B7b (P2):** Plan `§3.4` (line ~199) specifies `from_status` as **nullable**, "NULL for the initial `received` row." The actual precedent table, `KnowledgeLifecycleTransition` (`drug_knowledge_lifecycle_transition.py:57-58`), makes **both** `from_status` and `to_status` `NOT NULL` — because that codebase's convention is to never record a "creation" event as a transition at all (`create_draft` never calls `_record_transition`; only real transitions with a genuine prior status do). The Slice 2 plan's choice to record an explicit `None → received` transition (diagrammed at plan `§2` line 80) is a valid alternative design, but it diverges from the established precedent it claims to mirror, without calling out the divergence. Needs an explicit decision, not a silent difference.

---

## C. Review Areas Not Conclusively Covered

Of the 15 mandatory review areas in the original request, Codex's transcripts (before stalling) and this hybrid follow-up together give **strong coverage of areas 1, 2, 4, 5 (partially, via B3/B4), 13, 14, 15**, and **partial coverage of area 6** (B4 covers "when the attempt row is inserted" and the crash/stale-row question was addressed in the plan's own §16, independently judged internally consistent). The following remain **not conclusively covered** by either Codex or this hybrid pass, and should not be treated as clean:

- **Area 3 (source-kind vocabulary)** — the plan's proposed starter vocabulary (`§20`) was never compared against the review's suggested alternative (`regulatory_dataset`, `manufacturer_dataset`, `licensed_reference`, `curated_internal`, `operator_submission`) by either Codex or this pass. Left as an open item for PTH, as the plan itself already flags it as non-blocking.
- **Area 7 (dedup concurrency)** — the plan's savepoint design (`§5`) was read by Codex in all three runs but never adversarially tested (no live concurrent-insert repro was run, unlike the CHECK-constraint repro in A3). The design reasoning is sound on inspection, but "sound on inspection" is not the same bar as the PostgreSQL concurrency test the plan itself specifies as required (`§15`) — that test does not exist yet and was not run.
- **Area 9 (content validation semantics)** — read by Codex but no explicit pass/fail verdict was reached before stalling.
- **Area 10 (source enablement/payload caps)** — same.
- **Area 11 (actor/operator identity)** — A5 confirms the actor/flag *reservations* exist, but the CLI-cannot-override-actor claim (`§6`) was never tested against actual code, since no CLI code exists yet (correctly — Phase B produced no code). This is a plan-design review only, not a code review, and should be re-verified once Phase C code exists.
- **Area 12 (CLI contract/local-file security)** — read but not adversarially reviewed (TOCTOU, symlink handling, special-device rejection) by either Codex or this pass in detail.

None of these gaps are known defects — they are simply **unverified**, which is a materially different status than "reviewed and clean." Do not represent them as passed.

---

## D. Exact Codex CLI/Tooling Failures Encountered

- **Environment:** `codex-cli 0.144.1` (not on the skill's known-bad-version list, which currently only covers `0.120.0`–`0.120.2`).
- **Symptom (all 3 runs):** after extensive, real tool-call activity (each run performed 20-35 `rg`/`nl`/`sed`/`sqlite3`/`alembic` commands reading the actual target files), the process stopped emitting new `item.completed` events, never emitted a `turn.completed` event, and the stdout stream showed `Reading additional input from stdin...` — despite stdin being explicitly redirected from `/dev/null`.
- **Root-cause signal:** stderr in all 3 runs repeatedly logged, at increasing intervals over 10-15+ minutes: `` ERROR codex_models_manager::manager: failed to renew cache TTL: missing field `supports_reasoning_summaries` at line 86 column 5 `` — a schema-mismatch error in Codex's own local models-cache background refresh, unrelated to this review's prompt or repo content.
- **Mitigation attempted between run 2 and run 3:** renamed the stale cache file (`~/.codex/models_cache.json` → `.bak-stale-<timestamp>`) to force a clean regeneration. This measurably delayed the failure — run 3 got substantially further (completed the full 15-area file-reading pass, ran a live `sqlite3` repro, and checked `alembic heads`) before the *same* error resurfaced roughly 13 minutes in and the process again failed to reach `turn.completed`. **This confirms the defect is not a one-time stale-cache artifact but a recurring background failure in this Codex CLI build**, not fixable by a client-side cache clear alone.
- **Per explicit instruction, no fourth attempt was made.** The stale cache backup file remains at `~/.codex/models_cache.json.bak-stale-20260729145140` for anyone investigating the CLI bug further; it was not restored (a fresh cache will regenerate on next successful run).
- **Cost note:** three attempts plus verification consumed real API/tool budget (session cost crossed $10 and then $14 during this task) with no completed Codex-authored report to show for the CLI-side failures — flagging this so a decision can be made about whether to retry later (e.g. after a Codex CLI upgrade) rather than immediately.

---

## E. Minimal Plan Corrections Recommended

Ranked by what should block Phase C, based on the confirmed findings in §B (not on Codex's unfinished/unformalized severity judgments, which never completed):

1. **[Should block] Fix the target-XOR CHECK constraint (§B3, plan §3.3).** Replace the bare `target_type = 'drug_ingredient'` / `target_type = 'drug_product'` equality comparisons with NULL-safe forms (e.g. add explicit `target_type IS NOT NULL` guards to every branch, or use `IS NOT DISTINCT FROM` on PostgreSQL with an equivalent SQLite-safe construction). Add a regression test seeding exactly the row from §B3 and asserting the INSERT is rejected.
2. **[Should block] Fix the SQLite `content_hash` CHECK to match Slice 0's actual current pattern (§B2, plan §3.5).** Replace `length(content_hash) = 64` with `LENGTH(CAST(content_hash AS BLOB)) = 64` combined with the `GLOB` charset check, exactly as `k2_s0_round3_hardening.py:272` does. Update §3.5's prose claim to accurately describe what is being reused.
3. **[Should block] Resolve the `source_not_found` representability gap (§B4, plan §2/§3.3/§8).** Either (a) make `ingestion_attempts.source_id` nullable and add a CHECK that it is non-null except when `rejection_code IN ('source_not_found', ...)`, or (b) record the raw submitted `source_key` string on the attempt row separately from the resolved `source_id` FK so a `source_not_found` attempt can still be persisted with a null FK but a preserved audit trail of what was requested. Update the CLI contract (§7) and diagram (§2) to match whichever is chosen.
4. **[Should block, scoped to test correctness] Mark the orphan-prevention test PostgreSQL-only, or add an explicit application/trigger-level guard for SQLite (§B1, plan §15/§18).** As written the test would not actually exercise the claimed protection on SQLite, since FK enforcement is off there codebase-wide. Cheapest fix: mark the test `@pytest.mark.postgres_only` (matching the codebase's existing integration-test dialect convention) and add one line to §11/§18 stating explicitly that orphan prevention is PostgreSQL-only until a codebase-wide SQLite FK-enforcement fix lands (tracked separately, not blocking Slice 2, since it's pre-existing and shared with Slice 0).
5. **[Hardening, not blocking] Fix the §3.4 naming reference (§B7a)** — cite `knowledge_lifecycle_transitions` (the actual table) rather than `k2_s0_lifecycle_transitions` (the migration revision id).
6. **[Hardening, not blocking] Make an explicit decision, not a silent divergence, on the nullable-`from_status` design (§B7b)** — either justify diverging from the `KnowledgeLifecycleTransition` precedent (nullable `from_status` for the creation event) or align with it (don't record a creation transition; the row's `received` status is implicit from its existence, same as the existing table's convention).
7. **[Verification gap, not a defect] Before Phase C sign-off, actually run the PostgreSQL concurrency test the plan already specifies (§C, area 7)** rather than relying on design-review-only confidence in the savepoint logic.

---

## F. Final Verdict

**NOT READY FOR PHASE C — INDEPENDENT CODEX REVIEW INCOMPLETE.**

Three confirmed, concretely-evidenced correctness/security defects (§B1-B4) were found in the plan as written — one of them (§B3, the target-XOR CHECK) is a genuine data-integrity hole that would let a `staged` row be created with no target-type discriminator, contradicting the plan's own central invariant; one (§B2) is a rediscovery of a vulnerability this very codebase already found and fixed elsewhere; one (§B4) means the plan's own CLI output contract cannot be honored for its most likely real-world failure case. None of these were formally triaged to P0/P1/P2 by Codex, because Codex never finished — but based on Claude's independent verification against the actual repository, B3 and B4 in particular should be treated as blocking (equivalent to P1, arguably P0 for B3 given it defeats a stated non-negotiable invariant), not deferrable hardening.

Separately and independently of plan quality: the review process itself did not complete as instructed. Three attempts at obtaining Codex's own independent, formally-graded review all failed on a reproducible Codex CLI defect (§D), not on anything about this plan or this repository. That process failure is reported honestly here rather than concealed, per instruction — **this document is not a substitute for the independent Codex review that was requested, only the closest honest approximation obtainable given the tooling failure.**

Implementation work performed in this task: **none.** No application code was written. No migrations were created. No PR was opened. Nothing was deployed. The implementation plan document itself was not modified.
