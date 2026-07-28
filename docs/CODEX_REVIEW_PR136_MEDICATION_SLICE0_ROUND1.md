# Codex Review — PR #136 (Round 1) — Medication Knowledge Slice 0

**Reviewer:** Codex (read-only, `model_reasoning_effort=high`, `codex exec -s read-only`)
**Date:** 2026-07-28
**Branch:** `feat/medication-knowledge-slice0-provenance`
**Base:** `main@e8ae3d8`
**Head SHA reviewed:** `f44e516`
**Scope:** full PR diff (22 files, +5501/-89), custom focus brief covering 8 risk gates
(migration safety, lifecycle integrity, origin/provenance, system actor, feature flags,
API/authorization, transactionality, test credibility). Explicitly instructed not to
treat green CI as sufficient.

---

## VERDICT: **BLOCK MERGE**

**P1 (critical, blocks merge):** 6
**P2 (advisory):** 3

---

## Findings

1. **[P1] `origin` and `authored_by` are not immutable after persistence.**
   Both are ordinary writable columns (`drug_knowledge_content.py:124`,
   `drug_knowledge_content.py:141`). The `origin` validator checks only vocabulary and
   the AI/status combination; it does not reject changing an existing valid origin to
   another valid origin (`drug_knowledge_content.py:158`). There is no corresponding
   guard for `authored_by`. A persisted approved row can therefore be reattributed from
   `human_authored` to `source_extracted` or have its author replaced through ORM or
   SQL, silently rewriting historical identity. Enforce write-once semantics at the
   persistence boundary, not merely during construction.

2. **[P1] The lifecycle matrix is bypassable and not enforced as a single fail-closed
   source of truth.**
   The legal pairs exist only in `_ALLOWED_TRANSITIONS` (`knowledge_repository.py:85`).
   The content model validator merely admits any canonical status
   (`drug_knowledge_content.py:180`), while the history table checks `from_status` and
   `to_status` independently (`drug_knowledge_lifecycle_transition.py:98`).
   Consequently, direct ORM/SQL can change a human-authored row from `draft` to
   `approved` without history, and can insert impossible audit pairs such as
   `draft → retired`. A database trigger/event or sealed mutation API is needed if this
   foundation is expected to fail closed.

3. **[P1] Neither "append-only" table is actually append-only.**
   Both models expose normal mutable ORM attributes, with no database trigger,
   permission restriction, or ORM persistence hook preventing updates/deletes. The
   downgrade guard protects only dropping the table, not overwriting evidence. The
   tests merely grep one service module (`test_knowledge_repository.py:2730`), and
   another test directly mutates immutable prompt provenance and commits it
   (`test_knowledge_repository.py:2516`). Thus model identity, hashes, prompts, actors,
   timestamps, transition rationale, and statuses can all be rewritten by any session
   with model access.

4. **[P1] The SystemActor "closed set" is forgeable and the human-actor gate is
   bypassable.**
   `is_system_actor()` returns false for every unregistered value, including
   `system:attacker` (`system_actors.py:41`). `assert_actor_is_not_system()` rejects
   only those recognized enum members (`knowledge_repository.py:391`). Therefore an
   unregistered `system:*` identity supplied with `internal_admin` passes as human and
   can approve/reject/retire. `created_by` is also an unrestricted string
   (`drug_knowledge_ai_generation.py:139`); the migration tests themselves successfully
   store the unregistered `system:test` actor
   (`test_medication_k2_s0_origin_migration.py:309`). Reject the reserved namespace
   unless the value is a registered actor, and validate all system-attributed fields.

5. **[P1] A rejected, wrongly attributed, or stale AI generation can authorize
   approval.**
   The approval query filters only target, `generation_status='succeeded'`, and lacks a
   supersession pointer (`knowledge_repository.py:653`). It does not require:
   - `origin='ai_synthesized'`;
   - a registered AI system actor in `created_by`;
   - an admissible `review_status`;
   - `output_hash` or source evidence;
   - the latest generation attempt to have succeeded.

   Thus `review_status='rejected'`, `origin='human_authored'`, arbitrary `created_by`,
   empty evidence and null output hash can still qualify. A newer failed retry is
   ignored, allowing an older success despite the comment claiming the latest retry is
   authoritative. Approval also changes only the knowledge row and lifecycle history
   (`knowledge_repository.py:770`); it never marks the chosen generation `promoted`, so
   provenance remains `pending` after approval. The authoritative generation selection,
   validation, promotion, and reviewer linkage must be one transaction.

6. **[P1] Human reviewer attribution is not tied to the approving actor.**
   The database requires only that `reviewed_by` be non-null
   (`drug_knowledge_content.py:91`). Draft construction accepts arbitrary fields
   (`knowledge_repository.py:206`), and approval updates only
   `status_changed_by`/`status_changed_at`, leaving the pre-supplied reviewer untouched
   (`knowledge_repository.py:773`). A draft can therefore claim a system actor or
   unrelated user reviewed it, while another human approves it. Validate reviewer
   identity and explicitly define whether it must equal the approver or a recorded
   specialty reviewer.

7. **[P2] Polymorphic history/provenance rows can be orphaned, and the migration tests
   demonstrate it.**
   `knowledge_row_id` has no physical FK or service-level resolution constraint
   (`drug_knowledge_lifecycle_transition.py:49`). The PostgreSQL test inserts an
   ingredient ID while declaring `knowledge_table='drug_side_effects'`, rather than
   referencing a side-effect row, and succeeds
   (`test_medication_k2_s0_origin_migration.py:328`). The same risk applies to non-null
   AI generation targets. Add service/database validation and a test proving non-null
   targets resolve to the declared table.

8. **[P2] The rejected-status downgrade does not account for retained lifecycle
   history.**
   The lifecycle migration, which precedes the content-status widening, already
   permits `rejected` history (`k2_s0_lifecycle_transitions.py:62`). The later
   downgrade checks only current content rows
   (`k2_s0_add_rejected_status.py:70`). If a rejected content row was deleted or
   directly reclassified while its history remains, downgrade succeeds and leaves
   history containing a lifecycle state that the five content tables can no longer
   represent. Include lifecycle history in the downgrade guard or reorder the
   vocabulary migration.

9. **[P2] Several guardrail tests do not exercise the claimed guard.**
   PostgreSQL lifecycle constraint tests only inspect `pg_constraint` text instead of
   causing a real violation (`test_medication_k2_s0_origin_migration.py:664`). Unit
   tests accept either ORM `ValueError` or DB `IntegrityError`, so they generally stop
   before reaching the database (`test_knowledge_repository.py:2680`). The append-only
   tests inspect only `knowledge_repository.py`, not persistence behavior or other
   modules. The populated migration round trip does not reload and assert that the row
   and all preexisting fields survived re-upgrade
   (`test_medication_k2_s0_origin_migration.py:431`).

---

## Verified from the diff (not findings)

- All seven medication flags — existing retrieval plus six new flags — default OFF.
- No new endpoint, AI-provider call, background execution, frontend exposure, or
  prompt-history API appears in the diff.
- Normal lifecycle service paths do place status and transition-history writes in the
  same transaction.
- The semantic correctness of classifying every legacy row as `human_authored` cannot
  be proven from this diff alone; the migration is mechanically deterministic and
  complete, but the historical-writer evidence it relies on is outside the supplied
  changes.

---

## Disposition

Fix Round 1 tracked in-branch. See finding-by-finding closure table in the follow-up
commit/PR description once fixes land. Codex Round 2 will explicitly re-check all nine
findings above plus regressions from any new persistence hooks/triggers/transaction
changes.
