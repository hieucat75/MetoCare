# Codex Review — PR #136 (Round 2) — Medication Knowledge Slice 0

**Reviewer:** Codex (read-only, `model_reasoning_effort=high`, `codex exec -s read-only`)
**Date:** 2026-07-28
**Branch:** `feat/medication-knowledge-slice0-provenance`
**Base:** `main@e8ae3d8`
**Head SHA reviewed:** `ce44e63` (the 4 commits landed after Round 1, before this
round's own fixes)
**Scope:** full PR diff (base `main` vs. that head), explicitly re-checking all 9
Round 1 findings against source (not taking the fix commits' claims at face value)
plus a targeted regression hunt over the new triggers/transactions/concurrency code.

---

## VERDICT (as delivered): **BLOCK MERGE**

Codex found that the Round 1 fixes substantially improved the service layer, but
identified **6 new/still-open P1 findings** and **3 P2 findings**, including one
severe regression the fix itself introduced.

---

## Findings (as delivered by Codex)

1. **[P1] PostgreSQL cannot promote any AI generation.** `knowledge_ai_generations.
   input_source_ids`/`generation_params` were plain `json` (no equality operator in
   Postgres), but the new append-only trigger compared them with `IS DISTINCT FROM`.
   Every UPDATE against the table — including the one legitimate `pending →
   promoted` transition — failed with `operator does not exist: json = json`.
   **Independently reproduced directly against the real `mcp_test` database before
   fixing** (see Disposition below).
2. **[P1] Lifecycle matrix still not fully enforced at the DB boundary.**
   `knowledge_lifecycle_transitions` constrained `from_status`/`to_status`
   independently, so raw SQL could still insert an impossible pair (`draft →
   retired`). Also noted: a legal content-table status UPDATE via raw SQL does not
   itself force a corresponding history row (accepted as a documented residual
   limitation — see Remaining Risks).
3. **[P1] The AI append-only trigger omitted `id` from its immutable-column list.**
   (Codex's related claim that `updated_at` was also wrongly omitted is incorrect —
   `updated_at` is expected to change on every legitimate UPDATE via
   `TimestampMixin`'s own `onupdate=func.now()`, including the review_status
   promotion; including it in the immutable check would have broken the legitimate
   path. Only the `id` omission was a real gap.)
4. **[P1] Reviewer identity could still be rewritten after approval.** `approve_row`
   correctly bound `reviewed_by=actor_user_id` at approval time, but nothing
   prevented a later UPDATE from replacing it with a different value while
   `status='approved'` was preserved.
5. **[P1] "Latest generation" selection remains ambiguous under `created_at` ties.**
   Accepted as a genuine limitation, but not fixed in this round — see Remaining
   Risks (already a tracked, PTH-visible follow-up from the original PR description,
   requiring a server-governed sequence mechanism out of this round's scope).
6. **[P1] Provenance-completeness check accepts structurally weak hashes** (no
   length/format validation beyond non-empty). Accepted as a real but out-of-
   original-Round-1-scope hardening suggestion — not fixed this round (see
   Remaining Risks).
7. **[P1] System-actor closed set not enforced across all persistence paths.** The
   DB `CHECK` on `created_by` only rejected the *forged* `system:` namespace, not
   an ordinary human string, for a column documented as always machine-authored.
   `authored_by` on the 5 content tables had no reserved-namespace validation at
   all.
8. **[P2] Polymorphic integrity is checked only at INSERT time** — no guard against
   later deleting the target row out from under an existing history/generation
   reference. Accepted as a real, deferred limitation (no legitimate DELETE path
   exists for content rows today — see Remaining Risks).
9. **[P2] Guardrail tests still don't exercise real migration triggers** for the
   unit-test suite (by design — `tests/conftest.py`'s `db` fixture uses
   `Base.metadata.create_all()`, not Alembic, so DB triggers never apply there; the
   *actual* trigger-level tests live in the migration test files, which Codex's own
   note did not fully credit). The one concrete, actionable part of this finding —
   the new populated round-trip test comparing only a hand-picked column subset —
   was valid and fixed this round.
10. **[P2] The review-status trigger blocks the documented `promoted → superseded`
    supersession lifecycle.** Accepted as correct for current scope: no code in
    Slice 0 ever performs that transition (the model's own docstring reserves
    supersession logic for Slice 3, "not built in Slice 0") — fixing this now would
    reopen part of the append-only guarantee before the logic that would use it
    correctly exists. Deferred, tracked as a Slice 3 dependency.

## Round-1 closure table (as delivered by Codex, before this round's fixes)

| # | Codex-reported verdict |
|---|---|
| 1 | CLOSED |
| 2 | PARTIALLY CLOSED |
| 3 | PARTIALLY CLOSED |
| 4 | PARTIALLY CLOSED |
| 5 | STILL OPEN |
| 6 | PARTIALLY CLOSED |
| 7 | CLOSED |
| 8 | CLOSED |
| 9 | PARTIALLY CLOSED |

---

## Disposition — fixes applied after this round, in-branch

All 6 P1 findings above that were within this round's reasonable scope were fixed
and independently verified directly against the real `mcp_test` PostgreSQL database
(not just re-run through pytest) immediately after this review:

- **Finding 1 (JSON/JSONB):** changed `input_source_ids`/`generation_params` to
  `JSONB` on Postgres (model + the original `k2_s0_ai_generation_history` migration,
  safe since unmerged/undeployed). Verified: a real `INSERT` + `UPDATE ...
  review_status = 'promoted'` now succeeds on Postgres (previously raised `operator
  does not exist: json = json`).
- **Finding 2 (impossible pairs):** added a portable `CHECK` constraint on
  `knowledge_lifecycle_transitions` requiring `(from_status || '->' || to_status)`
  to be one of the 5 legal pairs. Verified: a raw `draft → retired` INSERT is now
  rejected with `ck_knowledge_lifecycle_transitions_pair`.
- **Finding 3 (`id` omission):** added `id` to `_AI_GENERATION_IMMUTABLE_COLUMNS`.
- **Finding 4 (reviewed_by mutation):** extended the content-guard trigger so
  `reviewed_by`, once non-null, is write-once (same discipline as
  `origin`/`authored_by`). Verified: setting `reviewed_by` from `NULL` succeeds;
  changing an already-set `reviewed_by` now raises.
- **Finding 7a (created_by too permissive):** tightened the `knowledge_ai_generations
  .created_by` CHECK to require an exact registered `SystemActor` value
  unconditionally (not merely "not a forged `system:*` string"). Verified: an
  ordinary human string for `created_by` is now rejected by
  `ck_knowledge_ai_generations_created_by_system_namespace`.
- **Finding 7b (authored_by unchecked):** added `assert_no_forged_system_actor`
  validation to `KnowledgeLifecycleMixin.authored_by` (lenient — rejects only a
  forged/unregistered `system:*` value, since `authored_by` legitimately holds a
  registered `SystemActor` for `ai_synthesized` rows).
- **Finding 9 (round-trip column subset):** the populated round-trip test now
  compares `SELECT *` (every column) instead of a hand-picked subset.

**Deliberately not fixed this round** (findings 5, 6, 8, 10 above) — each is either
an already-tracked, PTH-visible follow-up from the original PR description, out of
this round's scope, or gated on future Slice 3 work that doesn't exist yet. See the
"Remaining risks" section of the final Fix Round report for the full reasoning per
item.

A full automated Codex Round 3 re-review of this delta was not run: the task
instruction that authorized this round asked to run Round 2 and then stop before
merge to report — it did not ask for an open-ended number of rounds. Every fix
above was instead independently, directly verified against the real PostgreSQL
database (raw SQL reproduction of the failure before the fix, and of the passing
behavior after), which is the same standard of evidence Codex Round 2 itself used
to substantiate its findings. This is noted transparently as a manual-verification
gap rather than a Codex-reviewed one, for PTH to weigh when deciding whether a
further automated round is warranted before merge.
