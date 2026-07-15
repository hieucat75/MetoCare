# MetoCare Medication — K1 PR-1 Architecture Compliance Review

**Version:** 1.1 (revised after Codex review round 1 — see Section F)
**Date:** 2026-07-15
**PR scope:** K1-M01 — Medication Knowledge Repository schema (EC-01 + EC-02 only, excluding `drug_interactions` — see Section F)
**Branch:** `feat/k1-knowledge-schema` (PR #123), rebased on `docs/k1-adr13-adr14-index` (PR #124)
**Reviewer:** Tech Lead (self-review) + independent Codex CLI review (round 1: 3×P1 + 3×P2, all resolved below)
**Purpose:** Pre-merge gate answering: does this PR comply with ADR-01 and ADR-13?

> This is an **architecture review**, not a code review. Code quality is reviewed separately by Codex.

---

## Section A — ADR-01 Reconciliation Gap (resolved, contingent on PR #124)

**Round-1 finding (self-review):** ADR-01's "Consequences" section proposes a
single generic `drug_ingredient_knowledge(knowledge_type, value_json)` table.
ADR-13 instead builds on typed tables, referencing a "K0 Medication Knowledge
Architecture doc" and "ADR-01 §2.2" not present in the repo at the time.

**Codex round-1 finding (P1, upgraded severity):** independent review found
this gap was worse than "flagged, non-blocking" — `git log --all` showed
**ADR-13 did not exist in git history on any branch at all**, and the
committed `ARCHITECTURE_DECISION_INDEX.md` on `origin/main` still read v1.0
with no ADR-13/14 entries. The original Section A's claim of an "ADR-13 v1.1"
was based on an uncommitted local file, not a real artifact this PR could
honestly cite.

**Resolution:** PTH decided to land the docs first, separately (PR #124,
`docs/k1-adr13-adr14-index`) — ADR-13, ADR-14, the updated
`ARCHITECTURE_DECISION_INDEX.md` (v1.1), `MEDICATION_K1_PRE_VALIDATION.md`,
and `MEDICATION_K1_EXIT_CRITERIA.md`, all previously reviewed and signed off
by PTH in-session but never committed. This PR (#123) is rebased on top of
that branch. **This PR must not merge before PR #124 merges to `main`** —
tracked as an explicit PR dependency, not a soft note.

Once #124 lands, the remaining reconciliation (ADR-01's generic-table
proposal vs. ADR-13's typed tables) is a real but non-blocking gap: this PR
implements ADR-01's relational core (unambiguous, still current) and ADR-13's
typed tables on top of it, not the abandoned generic-table shape. Recommend a
follow-up one-line metadata note on ADR-01 reconciling this — does not block
K1 schema work.

---

## Section B — ADR-01 Compliance (Relational Core)

| # | Check | Status | Note |
|---|-------|--------|------|
| B1 | Ingredient is a first-class entity with an ID (`drug_ingredients.id`) | ✅ | |
| B2 | Ingredient ↔ product is a joinable many-to-many, not JSON (`drug_product_ingredients`) | ✅ | |
| B3 | Drug class is a first-class entity with ATC code fields (`drug_classes`) | ✅ | Self-referential hierarchy via `parent_class_id`, per ADR-01. |
| B4 | Canonical ingredient name = INN (ADR-01 OQ-2) | ✅ | `name_inn` unique, `name_vietnamese` kept as a separate display field. |
| B5 | `drug_catalog` (flat table) left untouched | ✅ | Verified by test `test_drug_catalog_untouched` — 41 rows unchanged. |
| B6 | No new flat JSON catalog pattern introduced | ✅ | Only `drug_classes.required_specialties` uses JSON, and that's an ADR-13 addition (specialty codes list), not a catalog field. |

---

## Section C — ADR-13 Compliance (Knowledge Lifecycle)

| # | Check | Status | Note |
|---|-------|--------|------|
| C1 | `status` column: 5 values, CHECK-enforced (`draft/clinical_review/approved/deprecated/retired`) | ✅ | Verified live on Postgres (`\d drug_usage`) + test `TestStatusCheckConstraint`. |
| C2 | Approved-row invariants (reviewed_by/evidence_level/source/version/last_reviewed_at) enforced at schema level | ✅ | Conditional CHECK per table; verified by `TestApprovedInvariantsCheck` (both reject and accept paths). |
| C3 | Self-approval block (authored_by ≠ status_changed_by) is service-layer, NOT a DB CHECK | ✅ (by design) | ADR-13 explicitly requires a logged override path a hard CHECK would foreclose — deferred to the service layer PR. |
| C4 | Per-table business key uniqueness, scoped to `status='approved'` only | ✅ | Partial unique index per table, exact keys per ADR-13's table (verified: `drug_usage`, and by symmetry the same `Index(..., postgresql_where=..., sqlite_where=...)` pattern for the other 5 — reused from `clinic.py`'s existing `uq_clinic_services_clinic_code` precedent). |
| C5 | `drug_side_effects.concept_code` / `drug_contraindications.condition_key` added as new normalized identifiers distinct from free text | ✅ | Per ADR-13 round-2 revision. |
| C6 | `drug_interactions` | ⏸️ Deferred | Removed from this PR — see Section F. Not one of the five tables this PR creates. |
| C7 | `clinical_specialties` + `knowledge_review_specialties` implement the controlled-vocabulary + many-to-many review model (round-1 addendum) | ✅ | Polymorphic association on `knowledge_row_id`, matching ADR-13's own stated rationale. `knowledge_table` CHECK now present on both the ORM model and the migration (Codex P2, fixed). |
| C8 | No CHECK constraint encodes "test data"/environment markers | ✅ | Confirmed: no constraint anywhere references `source` patterns or env names, per ADR-13's "Production Schema Must Not Encode Test Data". |
| C9 | Knowledge-row completeness against `drug_class_required_specialties` (every required specialty has a review row) | ⚠️ Not DB-enforced | Cross-table invariant; ADR-13 says transition rules are service-layer, and this specific check needs a trigger or service logic beyond schema scope. Documented limitation, not a blocker for EC-01/EC-02 (schema-only PR). |

---

## Section D — K1 Exit Criteria Scope Boundary

| # | Check | Status | Note |
|---|-------|--------|------|
| D1 | No clinical content authored (EC-07/EC-09) | ✅ | Migration creates empty tables only; no seed/insert statements. |
| D2 | No API route added or modified (EC-08) | ✅ | No changes under `app/api/` or `app/routers/` in this PR. |
| D3 | No frontend change (EC-09) | ✅ | `frontend/` untouched. |
| D4 | AI/Meto context builders unchanged (EC-10) | ✅ | No changes under `app/services/meto*` or context builder modules. |
| D5 | `drug_catalog` migration (EC-03/EC-04) deferred to a separate PR | ✅ | Explicitly out of scope here — this PR is schema only. |

---

## Section E — Migration Safety

| # | Check | Status | Note |
|---|-------|--------|------|
| E1 | Upgrade runs cleanly from current head (`merge_c1m08_p0med`) on real PostgreSQL | ✅ | Verified manually + via `alembic upgrade head`. |
| E2 | Downgrade removes all 13 new tables, no orphan constraints/indexes | ✅ | Verified manually (`\dt` count = 0 after downgrade) + `TestRollback.test_downgrade_removes_all_new_tables`. |
| E3 | Upgrade → downgrade → upgrade rehearsal is idempotent | ✅ | `TestRollback.test_upgrade_downgrade_upgrade_idempotent` passes. |
| E4 | All constraints portable to SQLite (dev/unit test default) | ✅ | CHECK constraints and `sqlite_where` partial indexes used throughout (SQLite ≥ 3.8 supports both) — `import app.models` + `Base.metadata` registration verified without dialect-specific branching needed. |
| E5 | Revision ID fits `alembic_version` VARCHAR(32) | ✅ | `k1_m01_knowledge_schema` = 23 chars. |
| E6 | New integration test module wired into CI | ✅ | Codex P2 finding — `.github/workflows/ci.yml`'s PostgreSQL integration job now runs `test_medication_k1_knowledge_migration.py` alongside the P0 module. |

Table count: **12** (was 13 — `drug_interactions` removed, see Section F).

---

## Section F — Codex Round-1 Review: Findings and Resolutions

Independent Codex CLI review (`gpt-5.6-terra`, reasoning effort high, 82K tokens) of the original 13-table PR found **3 P1 + 3 P2**. None were dismissed; all resulted in a real change:

| # | Finding | Severity | Resolution |
|---|---------|----------|------------|
| 1 | ADR-13 not in git history anywhere; index still v1.0 | P1 | PR #124 lands ADR-13/14 + updated index first; this PR now depends on it (Section A). |
| 2 | `drug_interactions` schema can't represent ADR-02's directional/conditional interaction rules (a single `canonical_pair_key` uniqueness forbids multiple valid approved rules per subject pair) | P1 | Removed from this PR entirely — migration, ORM model, and tests. Deferred to a follow-up PR scoped to full ADR-02 compliance. |
| 3 | An interaction row could reach `approved` with NULL severity/clinical_effect/management | P1 | Moot — table removed with finding #2. Will be addressed in the follow-up PR's redesign. |
| 4 | `knowledge_review_specialties.knowledge_table` CHECK existed in the migration but not the ORM model (SQLite dev schema looser than Postgres prod schema) | P2 | Added matching `CheckConstraint` to the ORM model's `__table_args__`, deriving from the same `KNOWLEDGE_TABLES` constant. |
| 5 | New integration tests not wired into CI | P2 | Added to `ci.yml`'s PostgreSQL integration test step. |
| 6 | `drug_ingredients.name_inn` unique index name drifted between ORM (`unique=True, index=True`) and migration (`UniqueConstraint`) | P2 | Replaced inline `unique=True`/`index=True` with an explicit named `UniqueConstraint` matching the migration exactly, on `drug_classes.name`, `drug_ingredients.name_inn`, and `clinical_specialties.code` (same class of drift, fixed consistently across all three). |

All fixes verified: full Postgres integration suite re-run (24/24 pass, down from 27 — the 3 `drug_interactions`-parametrized cases removed), upgrade/downgrade rehearsal re-run clean, full backend unit suite re-run clean (exit 0).

---

## Overall Verdict

**No unresolved CRITICAL/P1 findings** after round-1 fixes. One documented, non-blocking scope limitation remains (C9 — cross-table completeness check, deferred to service layer). This PR is contingent on PR #124 merging first (Section A). Recommend a Codex round-2 review to confirm the fixes before merge, per PTH's standing instruction not to merge before a clean Codex pass.
