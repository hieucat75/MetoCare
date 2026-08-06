# INDEPENDENT_REVIEW_K2_SLICE2_PHASEB_PLAN_ROUND2

**Reviewer identity/environment:** Claude (Sonnet 5), acting in an independent-reviewer role for this task — not the author of the plan or of Fix Round 1 within this task's own instructions. No Codex CLI was invoked for this round (not requested; the prior three attempts against the pre-fix plan all failed on a reproducible local Codex CLI defect, documented in `HYBRID_REVIEW_K2_SLICE2_PHASEB_PLAN_TOOLING_BLOCKED.md` §D). This document is **not** a Codex review and is named accordingly.

**Methodology note on independence:** the plan under review and the hybrid review were both produced by Claude in this same overall session, in earlier turns. This round re-read the complete current plan file fresh (not from memory), re-verified every load-bearing factual claim directly against the actual repository (not against the author's own change report, which this task's instructions explicitly said not to trust), and actively searched for defects not already caught by the hybrid review — three were found (§5, P1-2 and P1-3, and the downgrade-ordering issue P1-1), which is direct evidence this pass was not a rubber stamp of prior work.

---

## 1. Reviewer identity/environment

See above. Tools used: direct file reads (`Read`) of the plan and cited repository files, and targeted `grep`/`sed` shell inspection (`Bash`) of the actual current repository state — no reliance on the plan's own change report or the hybrid review's conclusions as a substitute for direct verification.

## 2. Exact sources inspected

- `docs/medication-management/MEDICATION_K2_SLICE2_EXTERNAL_INGESTION_IMPLEMENTATION_PLAN.md` — full file, both halves (lines 1–505 and 506–815), read fresh in this task.
- `docs/medication-management/HYBRID_REVIEW_K2_SLICE2_PHASEB_PLAN_TOOLING_BLOCKED.md` — read as context in a prior turn of this session; treated as context only, not as approval, per instruction.
- `backend/app/core/feature_flags.py` — lines 53, 88 (flag registration + default) — re-verified fresh via `grep` in this task.
- `backend/app/core/system_actors.py` — lines 28, 34, 41, 77 (`SystemActor` enum, `MEDICATION_INGESTION` member, `is_system_actor`, `assert_no_forged_system_actor`) — re-verified fresh via `grep` in this task.
- `backend/app/services/knowledge_repository.py`, `backend/app/api/deps_medication_knowledge.py` — grepped fresh for any `"ingestion"` string — zero matches, confirming zero coupling.
- `backend/app/models/drug_knowledge_ai_generation.py` — line 80 (`class KnowledgeAIGeneration`) — location re-confirmed fresh.
- `backend/app/models/_mixins.py` — lines 21–22 (`UUIDPrimaryKey`, `default=_uuid`) — read fresh in this task; this is the source of finding P2-1 below.
- `backend/alembic/versions/` — grepped fresh for `CREATE TRIGGER` combined with `drug_ingredients`/`drug_products`, and for `trg_drug_ingredients`/`trg_drug_products` name prefixes — zero matches in both cases (source of the "trigger names are collision-safe" confirmation in review area 5).
- `backend/alembic/versions/k2_s0_round3_hardening.py` — read in full in an earlier turn of this session (lines 1–635, including the `downgrade()` function at lines 533–635 and its "Guard 5 non-emptiness check — MUST run before any other statement" comment at lines 537–559); re-cited here from that earlier direct read, not from the plan's own paraphrase of it — this is the source of finding P1-1 below.
- `find backend -iname "*ingestion*"` — zero results, confirming no Slice 2 application code, migration, or test file exists anywhere in the repository.

## 3. Verdict

**NOT READY — PLAN FIXES REQUIRED.**

Zero P0 findings. **Three P1 findings** — the gate in this task's instructions requires zero P1 before Phase C can be authorized, so this alone is dispositive regardless of P2 disposition. Five P2 findings, none yet dispositioned by PTH.

## 4. P0/P1/P2 counts

- **P0: 0**
- **P1: 3**
- **P2: 5**

## 5. Findings with evidence

### P1-1 — Migration 2's downgrade doesn't state the exact statement-ordering requirement that its own cited precedent proves is necessary

- **Severity:** P1
- **Plan section / line range:** §10, line 577 ("Migration 2's downgrade additionally drops the two new orphan-prevention triggers... no data-loss guard is needed for this specific step, since dropping a trigger cannot destroy a row").
- **Repository evidence:** `backend/alembic/versions/k2_s0_round3_hardening.py:537-559` — the exact precedent this plan cites elsewhere (§3.6, §10) for its trigger-based orphan-prevention design. That function's `downgrade()` puts its populated-data emptiness check (`SELECT COUNT(*) FROM knowledge_ai_generations`) as the **literal first statement**, before any `DROP CONSTRAINT`/`DROP TRIGGER`, with an explicit comment: *"MUST run before any other statement in this function... on SQLite, every DDL statement below is independently auto-committed the instant it runs (SQLite has no transactional DDL) — if the check ran later... a refused downgrade would still leave the database durably de-hardened... Reproduced directly: upgrade to head, insert one... row, attempt this downgrade — with the check running late, `sqlite_master` showed the... triggers already gone even though the refusal fired."*
- **Concrete failure scenario:** migration 2's `downgrade()` has two independent-sounding steps per the plan's own §10 text — the table-drop preflight ("before dropping any table...") and the trigger-drop ("Migration 2's downgrade additionally drops the two... triggers"). If a Phase C implementer writes these in the order the prose lists them (or in any order that isn't "emptiness check absolutely first"), and the emptiness check on `ingestion_attempts` runs *after* the `DROP TRIGGER` statements for `drug_ingredients`/`drug_products`, then a refused downgrade (because `ingestion_attempts` is populated) still leaves the orphan-prevention triggers gone on SQLite — because SQLite has no transactional DDL, exactly as the cited precedent already reproduced and documented once. The result: a database stamped at a valid, "guards active" migration head that has, in fact, lost its only real SQLite orphan-prevention mechanism (§3.6 already establishes the trigger, not the FK, is the *only* real enforcement on SQLite) — silently.
- **Expected invariant:** "no valid stamped revision exists with protections temporarily absent" (this task's Review Area 11) and "no temporary de-hardening while stamped at a valid head" (the plan's own §1 non-goals table language, borrowed from the original Phase A decisions).
- **What the plan currently says:** §10 describes the emptiness check and the trigger-drop as if they were two independent facts about migration 2's downgrade, without stating their required relative order.
- **Minimal correction:** add one explicit sentence to §10: "As with `k2_s0_round3_hardening.py`'s own downgrade, the populated-data emptiness check against `ingestion_attempts` must be the literal first statement in migration 2's `downgrade()` function, before any `DROP TRIGGER`/`DROP CONSTRAINT` statement — SQLite's non-transactional DDL means a later-positioned check leaves the database durably de-hardened even when the downgrade is correctly refused."

### P1-2 — No CHECK constraint enforces `artifact_id = duplicate_of_artifact_id` when both are set, despite the design requiring them to always agree

- **Severity:** P1
- **Plan section / line range:** §3.3 CHECK block, lines 209–247 (no such constraint present); §3.3 invariant matrix, lines 253–259 (both columns independently marked `NOT NULL` on the `duplicate_existing` rows, with no stated or enforced relationship between their *values*); §5 illustrative code, lines 411–421 (`artifact, disposition = _persist_or_find_artifact(...)` followed by `artifact_id=artifact.id` — in the `duplicate_existing` branch, `artifact` is the *existing* row returned by the dedup lookup, so by construction `artifact_id` and `duplicate_of_artifact_id` are always meant to be the same value).
- **Repository evidence:** not applicable to a not-yet-built table — this is a schema-design gap in the plan itself, evaluated against the plan's own stated design intent (§5's code shows both fields are populated from the same `artifact` object in the duplicate case) and against this task's own explicit instruction (Review Area 4: *"duplicate_of_artifact_id references the correct source-scoped artifact"* and *"Check whether duplicate_of_artifact_id and artifact_id point to the same existing artifact"*).
- **Concrete failure scenario:** a bug in a future implementation, or a direct raw-SQL/tooling error, could set `artifact_id` to artifact A and `duplicate_of_artifact_id` to artifact B (a *different* row) on the same `unresolved`/`staged` attempt row — every CHECK constraint in §3.3 would still pass (each column's own NOT NULL-ness is independently satisfied), producing a row that claims "this attempt's bytes are artifact A" and "...and it's a duplicate of artifact B" simultaneously — self-contradictory, silently accepted by the database. §15's test matrix has no row that would catch this, because no invariant currently forbids it.
- **Expected invariant:** per this task's Review Area 4, `duplicate_of_artifact_id` must reference the same artifact `artifact_id` already identifies, whenever both are populated — a plain, no-subquery, same-row CHECK constraint (`duplicate_of_artifact_id IS NULL OR duplicate_of_artifact_id = artifact_id`), which is fully expressible in standard SQL without needing a trigger.
- **What the plan currently says:** the two columns are each independently constrained (§3.3, lines 225–229 for `duplicate_of_artifact_id`'s relationship to `disposition`; the artifact-linkage CHECK at lines 217–220 for `artifact_id`'s relationship to `status`) but never compared to each other.
- **Minimal correction:** add to §3.3's CHECK block:
  ```sql
  -- duplicate_of_artifact_id, when set, must reference the same artifact artifact_id already does
  CHECK (duplicate_of_artifact_id IS NULL OR duplicate_of_artifact_id = artifact_id)
  ```
  and add a corresponding row to §15's test matrix: direct raw-SQL INSERT with `artifact_id` and `duplicate_of_artifact_id` pointing at two different, both-valid artifacts → assert rejection.

### P1-3 — No CHECK constraint enforces `rejection_detail IS NULL` when `status != 'rejected'`

- **Severity:** P1
- **Plan section / line range:** §3.3 CHECK block, lines 209–247 (covers `rejection_code` at lines 210–214, but no equivalent constraint for `rejection_detail`, listed as a column at line 197).
- **Repository evidence:** schema-design gap, evaluated against this task's own explicit instruction (Review Area 4: *"non-rejected forbids rejection_code and rejection_detail"* — the plan implements only the first half of this compound requirement).
- **Concrete failure scenario:** a `staged` or `unresolved` row could carry an arbitrary, non-NULL `rejection_detail` string with no database-level objection — semantically nonsensical (a successfully-staged attempt has no "rejection" to detail), and a real information-hygiene concern given `rejection_detail` is explicitly designed to hold free-text-adjacent content (§8: "a short, sanitized human-readable reason string") that the plan otherwise goes to some lengths to keep tightly scoped and redaction-safe. Leaving it unconstrained on non-rejected rows means the one field in this schema explicitly designed to carry semi-free-text has no DB-level guarantee it's ever actually empty when it's supposed to be.
- **Expected invariant:** identical shape to the already-present `rejection_code` CHECK, just extended to cover `rejection_detail` too.
- **What the plan currently says:** only `rejection_code`'s presence/absence is tied to `status`; `rejection_detail` is described in prose (§3.3, §8) as "sanitized/redacted" and bounded to 500 chars, but never tied to `status` at the DB layer at all.
- **Minimal correction:** extend the existing CHECK, e.g.:
  ```sql
  CHECK (status = 'rejected' OR rejection_detail IS NULL)
  ```
  (Can be merged into the existing `rejection_code` CHECK as a single combined constraint, or kept separate — either is fine; the point is that today neither exists for `rejection_detail`.)

### P2-1 — §5's illustrative code doesn't state that `attempt.id` must be generated client-side before building dependent transition rows

- **Severity:** P2
- **Plan section / line range:** §5, lines 397–452 (illustrative `submit_artifact`/`_build_transition_history` pseudocode); explicitly labeled "exact code is a Phase C artifact, not Phase B" (line 398), which is why this is P2 (documentation/clarity for illustrative code) rather than P1 (a defect in something meant to ship as-is).
- **Repository evidence:** `backend/app/models/_mixins.py:21-22` — `class UUIDPrimaryKey: id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)`. This is a **client-side Python default** (`default=`, not `server_default=`), which SQLAlchemy does not eagerly apply to an in-memory object's attribute at construction time — the default is resolved when the INSERT statement is generated, at flush. `attempt.id` accessed immediately after `IngestionAttempt(...)` construction, before any `session.flush()`, would be `None` unless the caller explicitly passes `id=...`.
- **Concrete failure scenario:** `_build_transition_history(attempt)` (line 423) needs `attempt.id` to populate `IngestionAttemptTransition.attempt_id` (`NOT NULL`, §3.4). If a Phase C implementer follows the illustrative code literally — relying on the column-level default rather than explicitly generating the UUID in the service function — every transition row would be constructed with `attempt_id=None`, failing the `NOT NULL` constraint at flush time. This is not silent data corruption (it fails loudly with an `IntegrityError`, likely caught quickly in the very first integration test run) but it is a real gap in code meant to guide Phase C implementation.
- **Expected invariant:** the illustrative pseudocode should not model a pattern that doesn't actually work against this codebase's own established `UUIDPrimaryKey` convention.
- **What the plan currently says:** §5's code implicitly assumes `attempt.id` is available at construction time, with no comment addressing this.
- **Minimal correction:** add a one-line comment to §5's illustrative code (or prose immediately preceding it): "`attempt`'s `id` must be generated explicitly in the service layer (e.g. `id=str(uuid.uuid4())`) before constructing dependent `IngestionAttemptTransition` rows — `UUIDPrimaryKey`'s `default=` is a client-side default that SQLAlchemy resolves at flush time, not at object construction, so it is not available via attribute access beforehand."

### P2-2 — No CHECK constraint (or stated invariant) that `completed_at >= created_at`

- **Severity:** P2
- **Plan section / line range:** §3.3, line 203 (`completed_at` column description states "`created_at` and `completed_at` are always equal" as a design fact, but no constraint enforces it).
- **Repository evidence:** schema-design gap; low severity since these are audit/observability timestamps, not identity or integrity-bearing FKs — unlike P1-2/P1-3, getting these slightly inconsistent wouldn't corrupt any downstream logic, only muddy an audit trail.
- **Concrete failure scenario:** a future code change (not even necessarily a bug — e.g. a well-intentioned future refactor that separates "attempt opened" from "attempt resolved" in time, which §3.3's own prose explicitly anticipates as a *possible future direction*) could silently violate the "always equal" invariant with nothing at the DB layer to notice or prevent it.
- **Expected invariant:** `completed_at >= created_at` at minimum (weaker than "always equal," but cheap, defensible insurance against an actually-nonsensical state — completion before creation).
- **What the plan currently says:** states the equality as a design fact in prose only.
- **Minimal correction:** add `CHECK (completed_at >= created_at)` to §3.3's CHECK block.

### P2-3 — §3.5's illustrative SQLite `GLOB` pattern is written as shorthand, not the literal pattern or a stated "illustrative" caveat

- **Severity:** P2
- **Plan section / line range:** §3.5, line 299 — `` `CHECK (content_hash GLOB '[0-9a-f][0-9a-f][0-9a-f]...(×64)' AND LENGTH(CAST(content_hash AS BLOB)) = 64)` ``.
- **Repository evidence:** `backend/alembic/versions/k2_s0_round3_hardening.py:272` shows the actual literal pattern is dynamically generated: `` condition = f"{column} GLOB '{'[0-9a-f]' * 64}' AND LENGTH(CAST({column} AS BLOB)) = 64" `` — a real 64-repetition string, not literal `...` characters in the SQL itself.
- **Concrete failure scenario:** low — the plan does correctly cite the real function and file/line as the actual precedent to reuse, so a competent Phase C implementer would go read the real code rather than copy the shorthand literally. But the shorthand as written, if pasted directly into a migration file, would be syntactically broken SQL (a literal `...` and `(×64)` are not valid GLOB pattern syntax).
- **Expected invariant:** illustrative SQL in a plan document should either be genuinely copy-pasteable or explicitly marked as shorthand.
- **What the plan currently says:** presents the shorthand inline as if it were the CHECK expression, without an explicit "illustrative, not literal" flag.
- **Minimal correction:** either spell out the real 64-repetition pattern, or add "(shorthand — see the cited function for the literal, programmatically-generated 64-character pattern)" immediately after it.

### P2-4 — §3.6 doesn't name the PostgreSQL trigger function(s) for the new orphan-prevention triggers, asymmetrically with the SQLite trigger names it does give

- **Severity:** P2
- **Plan section / line range:** §3.6, lines 317–329 — the SQLite trigger is named explicitly (`trg_drug_ingredients_no_orphan_ingestion`), but the PostgreSQL side is only described as "a function+trigger pair in the same style as `k2_s0_round3_hardening.py`'s `fn_knowledge_content_no_hard_delete`," without giving explicit names.
- **Repository evidence:** confirmed via fresh grep (this review, §2) that no `drug_ingredients`/`drug_products` trigger currently exists on either dialect, so there is no actual collision risk today — this finding is about documentation completeness, not a real naming conflict.
- **Concrete failure scenario:** none functionally — a Phase C implementer would simply have to invent PostgreSQL function names themselves, which is a minor, low-risk gap, not a defect.
- **Expected invariant:** parity of specificity between the two dialects' illustrative naming, matching the plan's otherwise-high level of exactness elsewhere.
- **What the plan currently says:** names the SQLite trigger explicitly; leaves the PostgreSQL function/trigger names to be inferred "in the same style as."
- **Minimal correction:** name them explicitly, e.g. `fn_drug_ingredients_no_orphan_ingestion` / `trg_drug_ingredients_no_orphan_ingestion` and the `drug_products` equivalents, following the one-function-per-guarded-table convention `fn_knowledge_content_no_hard_delete` already establishes (that precedent uses one shared function for all 5 knowledge tables, parameterized via `TG_TABLE_NAME` — Slice 2's two orphan-prevention triggers could similarly share one function, or use two dedicated ones; either is fine, but the plan should say which).

### P2-5 — No stated validation posture (or explicit non-validation rationale) for `triggered_by_user_id`

- **Severity:** P2
- **Plan section / line range:** §7, line 499 — `--triggered-by-user-id | no | human identity, recorded verbatim, never actor-validated`.
- **Repository evidence:** none directly applicable — this is a documentation-completeness gap, evaluated against this task's explicit Review Area 10 instruction to review "initiating user validation."
- **Concrete failure scenario:** none functional (this is a pure audit field, never used for authorization decisions per §6) — but its absence of stated rationale leaves an ambiguity: is it *intentionally* free-text/unvalidated (a deliberate scope decision, consistent with Slice 2 not building any user-registry integration), or is it an oversight that a Phase C implementer might "fix" by adding an FK to a users table that doesn't obviously belong in this dormant, internal-only slice?
- **Expected invariant:** every field whose validation posture this task's review explicitly asked about should have a stated, deliberate rationale, matching the rigor already given to `executing_actor` (§6) and every other actor/identity field in this plan.
- **What the plan currently says:** states the field is unvalidated but not why, or that this is deliberate.
- **Minimal correction:** add one sentence to §6 or §7: "`triggered_by_user_id` is intentionally unvalidated free-text, not FK-constrained against any user table — Slice 2 has no dependency on, or coupling to, any user-identity system, consistent with its otherwise-total isolation from the rest of the application; it exists purely as an audit convenience, never consulted for authorization."

## 6. Required corrections

Ranked by blocking status:

1. **[Blocking, P1]** Add the explicit downgrade-ordering statement to §10 (P1-1).
2. **[Blocking, P1]** Add the `duplicate_of_artifact_id = artifact_id` CHECK to §3.3, plus a corresponding test row in §15 (P1-2).
3. **[Blocking, P1]** Add the `rejection_detail` non-rejected-forbids-value CHECK to §3.3 (P1-3).
4. **[Hardening, P2]** Add the client-side-UUID-generation note to §5's illustrative code (P2-1).
5. **[Hardening, P2]** Add `CHECK (completed_at >= created_at)` to §3.3 (P2-2).
6. **[Hardening, P2]** Fix or flag the §3.5 GLOB shorthand as illustrative (P2-3).
7. **[Hardening, P2]** Name the PostgreSQL trigger/function(s) explicitly in §3.6 (P2-4).
8. **[Hardening, P2]** State the `triggered_by_user_id` validation-posture rationale (P2-5).

## 7. Accepted/deferred P2 risks

None of the 5 P2 items have been explicitly accepted, fixed, or deferred by PTH yet — per this task's own gate ("every P2 explicitly accepted, fixed or deferred by PTH"), none can be treated as closed until PTH makes that call. All 5 are cheap, single-sentence-to-single-CHECK-constraint fixes; none appear to warrant a genuine "accept as-is" disposition on their merits, but that determination belongs to PTH, not this review.

## 8. Unreviewed areas, if any

- **Review Area 9's "duplicate-key policy" for JSON:** reviewed and found **not applicable** — Slice 2 never persists or acts on parsed JSON content (only proves parseability, per §1's non-goals), so `json.loads`'s last-value-wins behavior on duplicate keys has no effect on anything Slice 2 does or stores; `raw_content` is unaffected regardless. Not a gap, explicitly checked and closed.
- **Review Area 9's "maximum rows/columns/field length" for CSV:** reviewed and found **not separately needed** — the existing overall payload-size cap (5 MiB / source-configured limit, §3.1, §8) already bounds total `csv.reader` work; no unbounded-resource-consumption path exists independent of that cap.
- **Everything else in the 13 review areas and the required-source-inspection list** was directly inspected in this round (§2) or in the immediately preceding turns of this same session with fresh, independent re-verification of the load-bearing claims in this round (feature flag, actor registry, Slice 1 isolation, `UUIDPrimaryKey` convention, absence of any Slice 2 code, trigger-name collision risk). No review area was skipped.

## 9. Confirmation that no implementation work occurred

Confirmed. This task performed only reads (`Read`, `Bash` grep/inspection commands) and one `Write` (this review document itself). No application code was written. No migration was created or modified. The implementation plan (`MEDICATION_K2_SLICE2_EXTERNAL_INGESTION_IMPLEMENTATION_PLAN.md`) was **not** modified in this task. No PR was opened. Nothing was deployed. Phase C was not begun.

---

**Verdict recap: NOT READY — PLAN FIXES REQUIRED.** 3 P1 findings must be resolved (all three are small, precisely-scoped CHECK-constraint/ordering additions, not architectural rework) and PTH must explicitly disposition the 5 P2 findings before this plan can pass the stated gate (zero P0, zero P1, every P2 dispositioned).

K2 SLICE 2 — FRESH INDEPENDENT PLAN REVIEW COMPLETE.
