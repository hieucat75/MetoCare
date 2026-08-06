# MEDICATION_K2_SLICE2_EXTERNAL_INGESTION_IMPLEMENTATION_PLAN

**Status:** PLAN — FIX ROUND 4 APPLIED (2026-07-29). Not yet authorized for Phase C. No code, no migrations, no PR, no deployment produced by this document.
**Date:** 2026-07-29 (original Phase B draft); **Fix Round 1:** hybrid-review blockers B1–B4; **Fix Round 2:** Round 2 Claude self-review's 3 P1 + 5 P2; **Fix Round 3:** true independent review's 3 P1 + 5 P2; **Fix Round 4:** this revision — Fix Round 3's own SQLite completeness mechanism was found invalid and is replaced with a structural simplification.
**Slice:** K2 Slice 2 — dormant external-source ingestion staging foundation
**Phase:** Phase B (this document). **Phase C remains unauthorized** — see § Review Status.
**Author context:** Written against the current `main` state after PR #136 (Slice 0) and PR #135 (K2 Slice 1) — both merged, both dormant behind feature flags.

---

## Review Status

- **Hybrid review: complete** (Fix Round 1). **Claude same-session adversarial self-review: complete, disclosed as not independent** (Fix Round 2). **True independent review: completed** — `TRUE_INDEPENDENT_REVIEW_K2_SLICE2_PHASEB_FINAL.md`, fresh-context, P0 0 / P1 3 / P2 5, verdict NOT READY. **Fix Round 3: completed**, resolving all 8 of those findings.
- **Fix Round 3 introduced (or, more precisely, retained without adequate scrutiny) an invalid SQLite deferred-FK assumption.** Its transition-history completeness mechanism relied on `PRAGMA defer_foreign_keys=ON` to permit a reversed (child-before-parent) insert order, reasoning that this gave PostgreSQL and SQLite symmetric enforcement. That reasoning was wrong: `PRAGMA defer_foreign_keys` only changes *when* an FK is checked — it does nothing if FK enforcement (`PRAGMA foreign_keys`) is off in the first place, which it is, everywhere, in this codebase (verified repeatedly across every review round). On SQLite specifically, Round 3's design permitted committing orphan transition rows that never had — and could never require — a real parent attempt row, since nothing would ever check.
- **Fix Round 4 resolves this** by removing the entire multi-row transition-history mechanism rather than attempting a fourth patch to it — see § Executive Summary and §3.4 (repurposed as the FK-posture lesson-learned record) below.
- **Phase C remains unauthorized.**
- **A focused independent verification remains required after Fix Round 4** — the same standing requirement as Fix Round 3 stated, now additionally covering the removal itself: confirming the simplified 3-table design genuinely has no analogous cross-row integrity gap of its own.

```
K2 SLICE 2 — PHASE B HYBRID REVIEW COMPLETE
K2 SLICE 2 — PHASE B ROUND 2 CLAUDE ADVERSARIAL SELF-REVIEW COMPLETE (NOT INDEPENDENT)
K2 SLICE 2 — PHASE B TRUE INDEPENDENT REVIEW COMPLETE (P0 0 / P1 3 / P2 5, NOT READY)
K2 SLICE 2 — PHASE B PLAN FIX ROUND 3 APPLIED
K2 SLICE 2 — PHASE B PLAN FIX ROUND 4 APPLIED (Round 3's SQLite deferred-FK mechanism was invalid — removed, replaced with structural simplification)
FOCUSED INDEPENDENT VERIFICATION REQUIRED — PHASE C NOT AUTHORIZED
```

---

## Executive Summary

Slice 2 adds a **dormant, non-networked, internal-only staging pipeline** that can accept locally-supplied bytes (via CLI or direct service call — never HTTP), hash and store them immutably, deduplicate per-source, and optionally associate them with an explicit canonical `drug_ingredient` or `drug_product`. It never touches the five ADR-13 knowledge content tables, never calls an AI provider, never fetches a remote URL, and ships fully OFF behind `MEDICATION_EXTERNAL_SOURCE_INGESTION` (already reserved by Slice 0, default `False`).

**Fix Round 4 — architectural decision and why:**

Round 3's design tried to make a 4-table model (with a separate, multi-row `ingestion_attempt_transitions` table) fully DB-integrity-provable on both dialects, using a reversed insert order and deferred FK checking to let a completeness trigger on the parent row validate its children after the fact. That mechanism is **invalid on SQLite**: deferring an FK check is meaningless when FK enforcement itself (`PRAGMA foreign_keys`) is never turned on anywhere in this codebase (confirmed, again, in this round — zero matches for `PRAGMA foreign_keys` anywhere in `backend/`). A raw-SQL caller (or a bug) could insert transition rows referencing an attempt id that is never subsequently created, and commit successfully — SQLite would never object, and the completeness trigger, which only exists on the *attempts* table, would simply never run.

**Fix Round 4 chooses the preferred option: remove `ingestion_attempt_transitions` entirely.** Slice 2's processing is synchronous and produces exactly one committed outcome per attempt — there was never an independently-observable "received" or "validated" state to audit in the first place (nothing else can query an attempt mid-processing; the whole operation is one atomic transaction). Every fact Fix Round 3's transition rows tried to preserve — that an attempt received bytes, was validated (or wasn't), and reached a terminal outcome — is already fully and unambiguously captured by the **immutable, insert-once `ingestion_attempts` row itself**: its `status`, `disposition`, `rejection_code`/`rejection_detail`, `artifact_id`, target FK, `created_at`, and `completed_at`. A separate history table added a second table's worth of cross-row/cross-table integrity obligations (ordinal gaplessness, pair-legality, chain continuity, completeness-vs-parent) to protect information that was already redundant with the parent row. Removing it doesn't lose auditability — it removes an entire class of defect (three P1-level rounds' worth, across Fix Rounds 2, 3, and now 4) that existed only to protect data nobody needed protected.

**Slice 2 is now a 3-table design:** `ingestion_sources`, `ingestion_artifacts`, `ingestion_attempts`. **`ingestion_attempts` itself is now also immutability-trigger-protected** (§3.3), matching `ingestion_artifacts` — since it is now the sole audit record, it gets the same no-UPDATE/no-DELETE/no-TRUNCATE treatment.

**All valid Fix Round 3 corrections are preserved unchanged:** revision IDs `k2s2_ingestion_core`/`k2s2_ingestion_guards` (both ≤32 chars); no CLI `--triggered-by-user-id` argument (CLI initiator always `NULL`); fixed executing actor; exact trigger timing/level/`TG_OP` documentation conventions; the pysqlite savepoint empirical-verification requirement; no overclaiming that FK-existence proves authentication.

**Migration count:** still 2 — `k2s2_ingestion_core`, `k2s2_ingestion_guards` — now with simpler content in migration 2 (no transition-history machinery).

**Verdict: NOT READY FOR PHASE C — FOCUSED INDEPENDENT VERIFICATION REQUIRED.**

---

## 1. Scope and Non-Goals

Unchanged from Fix Round 3.

---

## 2. Architecture and Data Flow

**Fix Round 4 — simplified back to a single, normal-order insert sequence; no more reversed order, no deferred FK, no separate transitions table.**

```
operator (human)                 registered source
      │                          (ingestion_sources row)
      │ invokes
      ▼
 CLI entrypoint
 app/jobs/
 medication_ingestion_submit.py
      │
      │ flag check FIRST — before SessionLocal() ever opens
      ▼
 [MEDICATION_EXTERNAL_SOURCE_INGESTION == False] ──► exit 2, no DB touched
      │ True
      ▼
 PRE-ATTEMPT GATE (§4.6) — source resolution only
      │
      ├─ resolve source_key → source row
      │      not found  → CLI exit 3, zero rows anywhere
      │      disabled   → CLI exit 3, zero rows anywhere
      │      found + enabled → continue
      ▼
 app/services/medication_ingestion_repository.py :: submit_artifact(...)
 ══ SINGLE ATOMIC OUTER TRANSACTION (§4.5) — all-or-nothing, normal insert order ══
      │
      ├─ 0. generate attempt_id = str(uuid.uuid4()) explicitly, in Python
      ├─ 1. technical validation gates, in order (§8)
      │      any failure → status='rejected', rejection_code=..., no artifact
      ├─ 2. all gates pass → SAVEPOINT-scoped dedup insert into ingestion_artifacts (§5)
      ├─ 3. target supplied? → status='staged' with target FK, or status='unresolved'
      └─ 4. INSERT the ONE terminal ingestion_attempts row (Fix Round 4:
             the only row this transaction ever writes to this table —
             no child rows, no completeness trigger needed, no ordering
             concern of any kind) → COMMIT the outer transaction once
      │
      ▼
 CLI prints JSON summary {attempt_id, status, disposition, rejection_code, artifact_id}, exit 0

 Any exception anywhere in steps 0-4 rolls back the WHOLE transaction — zero
 new rows anywhere. CLI exit 1. Retry always submits a brand-new attempt.
```

No component in this diagram is reachable from an HTTP request, a scheduler, or an AI call.

---

## 3. Final Table Schemas and Constraints

**Fix Round 4: three tables, not four.** `ingestion_attempt_transitions` is removed (§3.4 below is repurposed to record why, permanently, so this mistake is not repeated in a future slice).

### 3.1 `ingestion_sources`

Unchanged from Fix Round 2/3.

### 3.2 `ingestion_artifacts` (immutable)

Unchanged from Fix Round 2/3.

### 3.3 `ingestion_attempts` (insert-once, immutable — Fix Round 4: now also trigger-protected)

| Column | Type | Constraints |
|---|---|---|
| `id` | String(36) | PK — explicitly generated client-side before construction |
| `source_id` | String(36) | FK → `ingestion_sources.id`, `ON DELETE RESTRICT`, NOT NULL |
| `artifact_id` | String(36) | nullable, FK → `ingestion_artifacts.id`, `ON DELETE RESTRICT` — NULL iff `status='rejected'` |
| `status` | String(16) | NOT NULL, CHECK IN `('rejected','unresolved','staged')` |
| `disposition` | String(24) | nullable, CHECK IN `('accepted_new','duplicate_existing')` |
| `rejection_code` | String(32) | nullable, CHECK IN the closed 7-value taxonomy (§8) |
| `rejection_detail` | String(500) | nullable, CHECK forbidden unless `status='rejected'` |
| `target_drug_ingredient_id` | String(36) | nullable, FK → `drug_ingredients.id`, `ON DELETE RESTRICT` |
| `target_drug_product_id` | String(36) | nullable, FK → `drug_products.id`, `ON DELETE RESTRICT` |
| `executing_actor` | String(255) | NOT NULL, CHECK/ORM-validated to be `system:medication-ingestion` only |
| `triggered_by_user_id` | String(36) | nullable, FK → `users.id`, `ON DELETE RESTRICT` — never CLI-suppliable (§4.6, §6, §18), always `NULL` in Slice 2's actual shipped surface |
| `created_at` | DateTime(timezone=True) | NOT NULL |
| `completed_at` | DateTime(timezone=True) | NOT NULL, CHECK `>= created_at` |

**CHECK constraints — unchanged set from Fix Round 2/3** (`rejection_code`⟺`rejected`, `rejection_detail` forbidden unless `rejected`, artifact linkage, both-targets-forbidden, staged-exactly-one-target NULL-safe XOR, unresolved/rejected-zero-targets, `completed_at >= created_at`). None of these were ever implicated in the transition-history defect and none change here.

**Fix Round 4, NEW — immutability triggers.** `ingestion_attempts` is now protected by the same `BEFORE UPDATE`/`BEFORE DELETE` (both dialects) and `BEFORE TRUNCATE` (PostgreSQL) trigger treatment as `ingestion_artifacts` (§3.6). This was previously deliberately omitted — Fix Round 2/3 reasoned that leaving it open might matter for "a future, explicitly-scoped slice that might need to [update it]." That reasoning is withdrawn: now that `ingestion_attempts` is the *sole* audit record for an attempt (§3.4), it deserves the same immutability guarantee `ingestion_artifacts` already has, for the same reason. A future slice that genuinely needs to revisit a terminal attempt (e.g. re-resolving an `unresolved` one) should create a **new** attempt row referencing the old one, not mutate history — consistent with every other "insert-once, never updated" design decision already made in this plan.

**Fix Round 4 — the "wrong `attempt_id`" residual risk (Fix Round 3's Fix 8) is removed, not merely re-evaluated.** It existed only because a *separate* transitions table had its own `attempt_id` FK that could, in principle, be pointed at the wrong parent. With no separate table, there is nothing for a row to be "wrongly attributed" to — each `ingestion_attempts` row is self-contained and cannot reference a different attempt, because there is no second row per attempt to misattribute. This residual risk is now **structurally eliminated**, not accepted.

### 3.4 FK posture and the lesson from Fix Round 3 (Fix Round 4 — repurposed from the removed transitions-table section)

This section replaces the old `ingestion_attempt_transitions` schema and exists specifically so a future slice does not repeat Fix Round 3's mistake.

**Explicit, locked FK posture for Slice 2 (and a caution for any future slice building on it):**

- **SQLite `PRAGMA foreign_keys` is currently not globally enabled anywhere in this codebase.** Verified directly, independently, in every review round of this plan (`backend/app/core/database.py`, `backend/alembic/env.py`, and a repo-wide grep for `PRAGMA foreign_keys` — zero matches, every time this was checked).
- **`PRAGMA defer_foreign_keys=ON` is not a substitute for FK enforcement, and Fix Round 3 was wrong to treat it as one.** Deferring only changes *when* an already-enabled FK constraint is checked (from immediately to end-of-transaction); it has no effect at all when the FK system itself is off. Fix Round 3's design relied on this exact confusion — it declared `attempt_id`'s FK "deferred" and reasoned that this gave SQLite the same guarantee PostgreSQL's genuinely-enforced, genuinely-deferrable FK gives it. It does not, because SQLite was never enforcing that FK to begin with.
- **No Slice 2 invariant may rely on unenforced SQLite FK metadata being checked at any point, deferred or otherwise.** This was already true for the target-orphan-prevention design (§3.6, which correctly uses an explicit trigger instead of bare FK reliance) and is now stated as a general rule for the whole slice, not just that one case.
- **Required SQLite referential guarantees use either explicit triggers (as §3.6's orphan-prevention triggers already do) or, preferably, a schema design that structurally does not require child-before-parent insert ordering or any other FK-dependent choreography at all** — which is exactly what Fix Round 4's 3-table simplification achieves: `ingestion_attempts` has no children whose existence needs verifying, so there is nothing left that would have needed the broken mechanism in the first place.
- **Global SQLite FK enablement remains a separate governance item** (§19.5, unchanged) — Slice 2 does not enable it, does not need it after this simplification, and any future slice that wants to rely on genuine SQLite FK enforcement must explicitly bring that global change into its own scope, with its own whole-repository blast-radius evaluation and regression coverage, not inherit it implicitly from a narrower slice's design choice.

**Regression test requirement, proving the rejected Round 3 mechanism is gone (§15):** rather than a runnable test *of* the old mechanism (there is nothing left to run it against — the table it depended on no longer exists), this is a **documentation/structural-impossibility test**: a test (or, minimally, a code comment plus a schema-inspection assertion) confirming `ingestion_attempt_transitions` does not exist in the schema, so the exact failure mode Fix Round 4 was written to close (orphan child rows referencing a never-created parent, permitted because `PRAGMA foreign_keys` is off) is not merely mitigated but **structurally impossible** — there is no child table left for such a row to exist in.

### 3.5 Dialect-specific expressions

Unchanged from Fix Round 2/3 (`content_hash`, `byte_size`, `allowed_content_types`).

### 3.6 Trigger and function naming (Fix Round 4 — recounted, now smaller)

**Total: 8 distinct guard purposes (down from 10 in Fix Round 3 — the chain-validation and history-completeness purposes are gone along with the table they guarded). PostgreSQL: 8 triggers, backed by 3 shared functions. SQLite: 6 triggers** (2 TRUNCATE-purpose triggers have no SQLite equivalent).

| # | Purpose | Guarded table | Migration | SQLite trigger | PostgreSQL function (shared where noted) | PostgreSQL trigger(s) | Operation | Timing | Level |
|---|---|---|---|---|---|---|---|---|---|
| 1 | No UPDATE | `ingestion_artifacts` | 1 | `trg_k2s2_ingestion_artifacts_no_update` (38 chars) | `fn_k2s2_ingestion_artifacts_immutable` (37, shared 1–3) | `trg_k2s2_ingestion_artifacts_no_update` | UPDATE | BEFORE | ROW |
| 2 | No DELETE | `ingestion_artifacts` | 1 | `trg_k2s2_ingestion_artifacts_no_delete` (38) | same (shared) | `trg_k2s2_ingestion_artifacts_no_delete` | DELETE | BEFORE | ROW |
| 3 | No TRUNCATE | `ingestion_artifacts` | 1 | N/A | same (shared) | `trg_k2s2_ingestion_artifacts_no_truncate` (**40 — longest name in this plan**) | TRUNCATE | BEFORE | **STATEMENT** |
| 4 | **No UPDATE (Fix Round 4, NEW)** | `ingestion_attempts` | 2 | `trg_k2s2_ingestion_attempts_no_update` (37) | `fn_k2s2_ingestion_attempts_immutable` (36, shared 4–6) | `trg_k2s2_ingestion_attempts_no_update` | UPDATE | BEFORE | ROW |
| 5 | **No DELETE (Fix Round 4, NEW)** | `ingestion_attempts` | 2 | `trg_k2s2_ingestion_attempts_no_delete` (37) | same (shared) | `trg_k2s2_ingestion_attempts_no_delete` | DELETE | BEFORE | ROW |
| 6 | **No TRUNCATE (Fix Round 4, NEW)** | `ingestion_attempts` | 2 | N/A | same (shared) | `trg_k2s2_ingestion_attempts_no_truncate` (39) | TRUNCATE | BEFORE | **STATEMENT** |
| 7 | No orphan (target) | `drug_ingredients` | 2 | `trg_k2s2_drug_ingredients_no_orphan` (35) | `fn_k2s2_no_orphan_target` (24, shared 7–8, dispatches on `TG_TABLE_NAME`) | `trg_k2s2_drug_ingredients_no_orphan` | DELETE | BEFORE | ROW |
| 8 | No orphan (target) | `drug_products` | 2 | `trg_k2s2_drug_products_no_orphan` (32) | same (shared) | `trg_k2s2_drug_products_no_orphan` | DELETE | BEFORE | ROW |

**Removed from Fix Round 3's inventory (no longer exist, no longer applicable):** `trg_k2s2_ingestion_attempt_transitions_*` (all 4: no_update, no_delete, no_truncate, chain), `fn_k2s2_ingestion_attempt_transitions_*` (both: immutable, chain), `trg_k2s2_ingestion_attempts_history_complete`, `fn_k2s2_ingestion_attempts_history_complete`.

**Execution details (unchanged conventions from Fix Round 3, Fix 6, now applying to a smaller set):**
- `TG_OP` branching for the two shared immutability functions (purposes 1–3, 4–6), exactly as `fn_knowledge_content_no_hard_delete` does.
- TRUNCATE triggers `FOR EACH STATEMENT`; UPDATE/DELETE triggers `FOR EACH ROW`.
- `fn_k2s2_no_orphan_target` dispatches on `TG_TABLE_NAME` (purposes 7–8), unchanged.
- Downgrade dependency order: all triggers dropped before any of the 3 functions.
- Migration test requirement (schema-inspection assertion of the exact locked names above) — unchanged requirement, smaller table to check.

**FK enforcement layers:** unchanged reasoning — PostgreSQL genuine FK `RESTRICT` + explicit trigger for target-orphan-prevention; SQLite trigger-only (bare FK metadata inert there). This is the *only* place in Slice 2 that ever relied on trigger-based referential guarantees instead of FK metadata, and it was already designed that way correctly from Fix Round 1 onward — Fix Round 3's mistake was introducing a *second*, *incorrect* reliance pattern (deferred FK) elsewhere; Fix Round 4 removes that second pattern rather than trying to fix it a third time.

---

## 4. State Machine and Invariant Matrix

### 4.1 Legal transitions (Fix Round 4: now describes attempt outcomes directly, not a recorded multi-row walk)

| From (conceptual) | To (persisted `status`) | Trigger |
|---|---|---|
| received | `rejected` | any technical validation gate fails (§8) |
| received → validated | `unresolved` | all gates pass, no target supplied |
| received → validated | `staged` | all gates pass, target supplied and confirmed to exist |

This table is now purely descriptive of the processing logic inside `submit_artifact` (§5) — "received" and "validated" are momentary, in-memory states within one function call, never persisted anywhere, never independently observable, and (Fix Round 4) no longer recorded as rows at all. Only the single terminal outcome (`rejected`/`unresolved`/`staged`) is ever written to the database.

### 4.2 Why target validity is checked before the terminal status is decided

Unchanged reasoning from Fix Round 2 (target existence is one of the `received`-phase technical validation gates; only target *presence*, already validated, decides `unresolved` vs `staged`). Orphan prevention is trigger-enforced on both dialects (§3.6).

### 4.3 Duplicate is a disposition, not a status

Unchanged from Fix Round 2.

### 4.4 Case-by-case dedup behavior

Unchanged from Fix Round 2.

### 4.5 Terminal-only, insert-once, now also immutable — Fix Round 4

`ingestion_attempts.status` remains CHECK-constrained to 3 terminal values. There is, and never was, an `UPDATE` statement against this table anywhere in Slice 2 — **Fix Round 4 additionally makes this a DB-enforced guarantee** (§3.3's new immutability triggers), not merely an application-layer convention, closing the one remaining gap between "the app never updates it" and "the database would reject an update if something tried." Insert order is now simple and unremarkable — exactly one row, inserted once, no children, no ordering concern (contrast with Fix Round 3's now-removed reversed-order design). A crash or exception anywhere before commit leaves zero new rows, as always; retry always creates a new attempt.

### 4.6 Pre-attempt gates

Unchanged from Fix Round 3 — source resolution only (`source_not_found`, `source_disabled`); no initiator gate (§7 has no CLI flag to resolve).

---

## 5. Deduplication Transaction Design

**Fix Round 4 — restored to a simple, normal-order sequence; no reversed order, no deferred FK, no transition-row construction:**

```python
# Illustrative — exact code is a Phase C artifact, not Phase B
import uuid

def submit_artifact(session, source, *, content_type, raw_bytes, declared_charset,
                     source_item_identifier, target_ingredient_id, target_product_id,
                     triggered_by_user_id=None):
    # `source` is already resolved+enabled by the pre-attempt gate (§4.6).
    # triggered_by_user_id defaults to None and is never populated by Slice 2's
    # own CLI (§7) — retained only for a future, already-authenticated caller.

    attempt_id = str(uuid.uuid4())
    now = _current_time()

    with session.begin():  # the single outer atomic transaction — normal order,
                            # no deferred FK setting needed anywhere in Fix Round 4
        gate = _run_validation_gates(source, content_type, raw_bytes, declared_charset,
                                      target_ingredient_id, target_product_id)  # pure, no DB writes

        if gate.rejected:
            attempt = _build_terminal_attempt(
                id=attempt_id, status="rejected", rejection_code=gate.code,
                rejection_detail=gate.detail, source=source,
                triggered_by_user_id=triggered_by_user_id,
                created_at=now, completed_at=now)
        else:
            artifact, disposition = _persist_or_find_artifact(
                session, source.id, gate.content_hash, raw_bytes, content_type, ...)
            terminal_status = "staged" if gate.target_supplied else "unresolved"
            attempt = _build_terminal_attempt(
                id=attempt_id, status=terminal_status, artifact_id=artifact.id,
                disposition=disposition,
                target_drug_ingredient_id=gate.target_ingredient_id,
                target_drug_product_id=gate.target_product_id,
                source=source, triggered_by_user_id=triggered_by_user_id,
                created_at=now, completed_at=now)

        session.add(attempt)  # the ONLY row this transaction writes to
                               # ingestion_attempts — no dependent rows,
                               # no ordering concern
    # session.begin()'s context manager commits here, exactly once. Any
    # exception anywhere above rolls back everything, including a
    # released-but-not-yet-committed artifact savepoint.
    return attempt


def _persist_or_find_artifact(session, source_id, content_hash, **fields):
    try:
        with session.begin_nested():  # SAVEPOINT, nested inside the outer transaction
            artifact = IngestionArtifact(source_id=source_id, content_hash=content_hash, **fields)
            session.add(artifact)
            session.flush()
        return artifact, "accepted_new"
    except IntegrityError:
        existing = (
            session.query(IngestionArtifact)
            .filter_by(source_id=source_id, content_hash=content_hash)
            .one()
        )
        return existing, "duplicate_existing"
```

**Fix Round 4 note:** the artifact-dedup savepoint pattern (`_persist_or_find_artifact`) is completely unaffected by the removal of the transitions table — it was never part of the broken mechanism. The pysqlite savepoint caveat from Fix Round 3 (Fix 7) still stands, unchanged: this remains a required, not optional, empirical Phase C test (§15), not something this document claims is confirmed.

**PostgreSQL concurrency proof, SQLite equivalent behavior:** unchanged from Fix Round 2/3.

---

## 6. Actor and Authorization Boundary

Unchanged from Fix Round 3 (`executing_actor` always fixed and non-overridable; `triggered_by_user_id` never CLI-suppliable, attribution-only, `NULL`-means-no-claim, `ON DELETE RESTRICT`). **Fix Round 4 addition:** "Immutability of provenance/history fields" now includes `ingestion_attempts` being trigger-protected as well as artifacts (§3.3) — every identity field on every Slice 2 table is now genuinely DB-enforced immutable after its single insert, not just artifacts.

---

## 7. CLI Contract

Unchanged from Fix Round 3 — no `--triggered-by-user-id` flag, source-only pre-attempt gate, unchanged exit-code table, unchanged local-file security.

---

## 8. Payload Validation Contract

Unchanged from Fix Round 2/3.

---

## 9. Provenance Model

Unchanged from Fix Round 3, minus the reference to a separate transition audit trail — the attempt row itself is now stated as the complete provenance record for its own lifecycle facts (as distinct from `ingestion_artifacts`' own provenance fields, which are unaffected).

---

## 10. Migration Sequence and Downgrade Safety

**Revision IDs unchanged from Fix Round 3 (preserved, not touched by Fix Round 4):**

| # | Revision | Down-revision | Length | Head relationship |
|---|---|---|---|---|
| 1 | `k2s2_ingestion_core` | `k2_s0_round3_hardening` | 19 chars | chains directly off the current, verified single head |
| 2 | `k2s2_ingestion_guards` | `k2s2_ingestion_core` | 21 chars | chains off migration 1 |

Both verified ≤32 chars against Alembic's real `version_num` column width; both collision-free. Migration-plan requirement (every future revision ≤32 chars, PostgreSQL-verified not SQLite-assumed, CI-length-lint) — unchanged from Fix Round 3.

**Migration content — updated, simpler, for Fix Round 4:**

| # | Revision id | Creates |
|---|---|---|
| 1 | `k2s2_ingestion_core` | `ingestion_sources`, `ingestion_artifacts`, their named immutability triggers (§3.6, purposes 1–3) |
| 2 | `k2s2_ingestion_guards` | `ingestion_attempts` (**with its own new immutability triggers, purposes 4–6, Fix Round 4**), the two orphan-prevention triggers on `drug_ingredients`/`drug_products` (purposes 7–8). **No `ingestion_attempt_transitions` table, no chain-validation trigger, no completeness trigger, no deferred FK declaration anywhere — all removed.** |

**Downgrade preflight, statement ordering:** unchanged 6-point requirement (populated-data preflight is the literal first side-effecting statement, before any DROP, on both migrations) — now checking `ingestion_sources`/`ingestion_artifacts` (migration 1) and `ingestion_attempts` (migration 2, simpler — one table, not two).

**Everything else in §10** (single verified Alembic head, `batch_alter_table` non-applicability) unchanged.

---

## 11. SQLite / PostgreSQL Parity

**Fix Round 4 — the two Fix Round 3 rows for transition-history chain/pair enforcement and completeness are removed entirely (nothing left to compare, since the mechanism they described no longer exists).** Everything else unchanged from Fix Round 2/3, plus:

| Concern | PostgreSQL | SQLite |
|---|---|---|
| (all Fix Round 1/2/3 rows for artifacts/sources/target-orphan, unchanged) | — | — |
| **`ingestion_attempts` immutability (Fix Round 4, NEW)** | named trigger | named trigger — fully symmetric, ordinary immediate `BEFORE` triggers, no deferred anything |

---

## 12. Feature-Flag Dormancy

Unchanged from Fix Round 1/2/3.

---

## 13. CI Changes

Unchanged from Fix Round 1/2/3 (Option A, PR evidence requirement, revision-id-length lint).

---

## 14. File-by-File Implementation Plan (Phase C — not created by this document)

| File | Action | Contents |
|---|---|---|
| `backend/app/models/medication_ingestion.py` | new | `IngestionSource`, `IngestionArtifact`, `IngestionAttempt` (**no `IngestionAttemptTransition` class at all — removed, Fix Round 4**) + `@validates` hooks |
| `backend/app/services/medication_ingestion_repository.py` | new | `submit_artifact(...)` (**simple, normal-order, no reversed insert, no deferred-FK helper — Fix Round 4**), `_persist_or_find_artifact(...)`, `_build_terminal_attempt(...)`, `_resolve_source(...)` |
| `backend/app/jobs/medication_ingestion_submit.py` | new | CLI entrypoint — no `--triggered-by-user-id` flag |
| `backend/alembic/versions/k2s2_ingestion_core.py` | new | migration 1 |
| `backend/alembic/versions/k2s2_ingestion_guards.py` | new | migration 2 — **`ingestion_attempts` + its own immutability triggers + orphan triggers only; no transitions table (Fix Round 4)** |
| `backend/tests/unit/test_medication_ingestion_repository.py` | new | unit tests — **wrong-`attempt_id`/chain-continuity tests removed as no longer applicable (Fix Round 4)** |
| `backend/tests/integration/test_medication_k2_s2_ingestion_migration.py` | new | SQLite migration tests — **structural-impossibility assertion that `ingestion_attempt_transitions` does not exist (§3.4), migration-name-length check** |
| `backend/tests/integration/test_medication_k2_s2_ingestion_postgres.py` | new | PostgreSQL-only — concurrency, immutability (**now including `ingestion_attempts`, Fix Round 4**), orphan, embedded-NUL, savepoint empirical verification, `alembic_version` real-value assertion |
| `backend/tests/integration/test_medication_k2_s2_flag_off.py` | new | unchanged |
| `backend/tests/integration/test_medication_k2_s2_source_gate.py` | new | unchanged from Fix Round 3 |
| `backend/tests/integration/test_medication_k2_s2_slice1_regression.py` | new | unchanged |
| `.github/workflows/ci.yml` | edit | add new Postgres test file(s) + revision-id-length lint |

**No change needed:** unchanged list from Fix Round 1/2/3.

---

## 15. Detailed Test Matrix

**Fix Round 4 — the entire Fix Round 3 "Transition history" test section (22 rows) is removed**, replaced by:

| Test | Type |
|---|---|
| **Structural-impossibility assertion: `ingestion_attempt_transitions` does not exist in the schema — the exact failure mode Fix Round 4 was written to close (orphan child rows on SQLite, permitted because `PRAGMA foreign_keys` is off) has no table to occur in** (Fix Round 4, replaces the old runnable "child-first bypass" test since there is nothing left to run it against) | integration, schema-inspection, both dialects |
| `ingestion_attempts` immutability — UPDATE/DELETE/TRUNCATE via each new named trigger (§3.6, purposes 4–6) | integration, both dialects |
| A terminal attempt row alone (no other table) fully round-trips every field correctly for all 3 statuses | unit |

**Retained, unchanged from Fix Round 3 (per explicit instruction):**
- Revision ID length tests (both ≤32 chars).
- Real PostgreSQL `alembic upgrade head` / `alembic_version` value assertion.
- Source/flag zero-row pre-attempt gate tests.
- Hash embedded-NUL tests (unchanged, unaffected by this round).
- Dedup concurrency/savepoint tests, including the pysqlite empirical-verification requirement.
- Downgrade-first-preflight tests (6-point requirement, §10).
- Trigger/function inventory tests (now checking the smaller, 8-purpose table in §3.6).
- CLI actor/initiator tests (no `--triggered-by-user-id` flag exists; `triggered_by_user_id` always `NULL`; forged-namespace rejection tested directly against the service function).

All payload-validation, hash/immutability-for-artifacts, dedup/concurrency, orphan-guard, Slice 1 regression, and no-AI-construction tests from Fix Round 1/2/3 are retained unchanged.

---

## 16. Failure and Rollback Semantics

Unchanged core reasoning from Fix Round 2/3, simplified: with no separate transitions table, there is no longer a "partway through the reversed sequence" case to reason about at all — a failure at any point before the single `ingestion_attempts` `INSERT` (or before the artifact savepoint resolves, if applicable) rolls back everything, and there is nothing else in the transaction that could be partially complete.

---

## 17. Observability and Redaction

Unchanged from Fix Round 3.

---

## 18. Security Threat Model

Unchanged from Fix Round 3 (`triggered_by_user_id` never CLI-suppliable, attribution-not-authentication). **Fix Round 4 addition:**

| Threat | Mitigation |
|---|---|
| (all Fix Round 1/2/3 rows, unchanged) | — |
| **Orphan/unattributed audit rows via unenforced SQLite FK checking (Fix Round 4 — the defect this round exists to close)** | Structurally impossible — there is no child table (`ingestion_attempt_transitions` removed) whose rows could reference a nonexistent or wrong parent. `ingestion_attempts` is self-contained; every row is its own complete, immutable record. |

---

## 19. Tracked Future Gates

Unchanged from Fix Round 1/2/3 (§19.1–19.6), **plus explicit note added to §19.5 (global SQLite FK enablement):** any future slice that wants genuine SQLite FK enforcement, or that wants to reintroduce a multi-row history table depending on FK ordering tricks, must explicitly bring the global `PRAGMA foreign_keys=ON` change into its own scope first, with its own whole-repository blast-radius evaluation and regression coverage — it must not be assumed available or silently relied upon the way Fix Round 3 incorrectly did.

---

## 20. Open Questions

**None remain that block Phase C review.** All items from Fix Rounds 1 through 4 are resolved.

---

## 21. Phase C Implementation Gates

0. **A focused independent verification of this plan (now in its Fix Round 4 form) must complete and pass**, specifically confirming: (a) the 3-table simplification genuinely has no analogous cross-row/cross-table integrity gap of its own — there being no second table to guard is itself the thing to verify, not assume; (b) all Fix Round 3 corrections that were meant to be preserved actually were (revision IDs, no CLI initiator flag, trigger documentation conventions, savepoint-empirical-test requirement); (c) the FK-posture statement in §3.4 is accurate against the live repository at verification time, not just at the time this document was written.
1. **PTH sign-off**, specifically on the decision to remove `ingestion_attempt_transitions` entirely rather than pursue a parent-first-finalization alternative.
2. **Feature flag stays `False`** throughout Phase C.
3. **No HTTP route, no scheduler, no AI call.**
4. **Full test matrix (§15) green.**
5. **Slice 1 regression test green.**
6. **CI `ci.yml` update lands with linked execution evidence**, plus the revision-id-length lint passing.
7. **Migration downgrade-preflight tests pass**, including the simpler (one-table, not two) migration 2.
8. **The pysqlite savepoint empirical test passes on the real project stack** before the dedup transaction design is considered confirmed.

---

## Return Summary

- **1. Architectural option selected:** the preferred option — **remove `ingestion_attempt_transitions` entirely**, collapsing Slice 2 from 4 tables to 3. Not the parent-first-finalization alternative (which would have required an `UPDATE`, contradicting insert-once, and still could not fully close the raw-SQL loophole without disproportionate machinery for information the parent row already redundantly carried).
- **2. Why the Round 3 SQLite mechanism was invalid:** it relied on `PRAGMA defer_foreign_keys=ON` to permit a reversed (child-before-parent) insert order, reasoning this gave SQLite the same guarantee PostgreSQL's genuinely-enforced `DEFERRABLE` FK gives it. It does not — deferring only changes *when* an FK is checked, and this codebase never enables FK checking (`PRAGMA foreign_keys`) for SQLite at all, verified repeatedly. A raw-SQL insert of a transition row referencing a never-created attempt id would commit successfully on SQLite, with the completeness trigger (which lived only on the attempts table) never firing.
- **3. Exact schema changes:** `ingestion_attempt_transitions` table removed entirely (columns, CHECKs, triggers, all gone); `ingestion_attempts` gains 3 new immutability triggers (no-update/no-delete/no-truncate), matching `ingestion_artifacts`.
- **4. Whether the transition table remains:** **No — removed entirely**, not redefined as a single-row event table.
- **5. Final lifecycle representation:** entirely on the immutable `ingestion_attempts` row itself — `status`, `disposition`, `rejection_code`/`rejection_detail`, `artifact_id`, target FK, `created_at`, `completed_at`. "Received"/"validated" are in-memory processing states inside one function call, never persisted.
- **6. Final transaction order:** simple, normal FK order — artifact savepoint (if applicable) first, then the single `ingestion_attempts` INSERT last, one commit. No reversed order, no deferred FK, anywhere.
- **7. SQLite integrity mechanism:** none needed for the (now-removed) transition history; unchanged explicit-trigger mechanism for target-orphan-prevention (§3.6, purposes 7–8), which was never part of the defect.
- **8. PostgreSQL integrity mechanism:** same as SQLite now — no special deferred-FK machinery needed anywhere; ordinary immediate triggers throughout.
- **9. Updated trigger/function inventory:** 8 guard purposes (down from 10), 8 PostgreSQL triggers backed by 3 shared functions, 6 SQLite triggers. Full table in §3.6.
- **10. Updated migration design:** revision IDs unchanged (`k2s2_ingestion_core`, `k2s2_ingestion_guards`); migration 2's content simplified — one table plus its own immutability triggers plus the two orphan triggers, no chain/completeness triggers, no deferred FK declaration.
- **11. Updated tests and CI plan:** the 22-row Fix Round 3 transition-history test section replaced by a 3-row structural-impossibility/immutability section; every other Fix Round 3 test category (revision length, real Postgres migration, source/flag gates, hash/embedded-NUL, dedup/savepoint, downgrade preflight, trigger inventory, CLI actor/initiator) retained unchanged, per explicit instruction.
- **12. Remaining residual risks:** none new. The "wrong `attempt_id`" residual risk from Fix Round 3 is now structurally eliminated, not merely re-accepted. The pysqlite savepoint empirical-verification requirement remains open pending Phase C, as it already was.
- **13. Confirmation:** no code, migration, PR, or deployment work occurred in this task. Only the plan document was modified. No reviewer (Codex or otherwise) was run. No new review document was created.
- **14. Updated verdict: NOT READY FOR PHASE C — FOCUSED INDEPENDENT VERIFICATION REQUIRED.**

---

```
K2 SLICE 2 — PHASE B HYBRID REVIEW COMPLETE
K2 SLICE 2 — PHASE B ROUND 2 CLAUDE ADVERSARIAL SELF-REVIEW COMPLETE (NOT INDEPENDENT)
K2 SLICE 2 — PHASE B TRUE INDEPENDENT REVIEW COMPLETE (P0 0 / P1 3 / P2 5, NOT READY)
K2 SLICE 2 — PHASE B PLAN FIX ROUND 3 APPLIED
K2 SLICE 2 — PHASE B PLAN FIX ROUND 4 APPLIED (Round 3's SQLite deferred-FK mechanism was invalid — removed, replaced with structural simplification)
FOCUSED INDEPENDENT VERIFICATION REQUIRED — PHASE C NOT AUTHORIZED
```

No code. No commit. No PR. No deployment. Phase C remains unauthorized.
