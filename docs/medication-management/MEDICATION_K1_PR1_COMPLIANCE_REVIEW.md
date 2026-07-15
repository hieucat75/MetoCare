# MetoCare Medication — K1 PR-1 Architecture Compliance Review

**Version:** 1.0
**Date:** 2026-07-15
**PR scope:** K1-M01 — Medication Knowledge Repository schema (EC-01 + EC-02 only)
**Branch:** `feat/k1-knowledge-schema`
**Reviewer:** Tech Lead (self-review, pending Codex pass before merge)
**Purpose:** Pre-merge gate answering: does this PR comply with ADR-01 and ADR-13?

> This is an **architecture review**, not a code review. Code quality is reviewed separately by Codex (task #7).

---

## Section A — ADR-01 Reconciliation Gap (must read first)

ADR-01's "Consequences" section (as currently written on disk) proposes a single
generic `drug_ingredient_knowledge(knowledge_type, value_json)` table. ADR-13
(v1.1, Accepted 2026-07-15) instead builds on **six typed tables**
(`drug_usage`, `drug_patient_education`, `drug_side_effects`, `drug_monitoring`,
`drug_contraindications`, `drug_interactions`), referencing a "K0 Medication
Knowledge Architecture doc" and "ADR-01 §2.2" that do not exist as files in the
repository (confirmed by repo-wide grep — no match outside ADR-13 itself).

**Finding:** ADR-01 as literally written and the six-typed-table design ADR-13
assumes are not the same schema. This PR does **not** implement ADR-01's
`drug_ingredient_knowledge` proposal.

**Resolution applied in this PR:** implement only the parts of ADR-01 that are
unambiguous and still current — the relational core (`drug_classes`,
`drug_ingredients`, `drug_products`, `drug_product_ingredients`,
`drug_product_names`) — and build the six ADR-13 typed tables on top of it via
`drug_ingredient_id`. This satisfies ADR-01's actual stated problem (ingredient
lacks an ID, can't be joined) without inventing schema ADR-01 doesn't specify.

**Status:** ⚠️ Flagged, not blocking. `drug_ingredient_knowledge` is treated as
superseded in practice by the K0/ADR-13 design (per
`ARCHITECTURE_DECISION_INDEX.md` v1.1 changelog entry), but no formal
`Superseded By` marker exists on ADR-01. Recommend PTH/Tech Lead add a
one-line metadata note reconciling this — does not block K1 schema work per
PTH's "no more architecture docs" directive, since this PR doesn't need a new
ADR to proceed, only an acknowledgment of the gap.

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
| C6 | `drug_interactions.canonical_pair_key` stored, not computed by schema | ✅ | Column exists; population is explicitly a service-layer responsibility (no service layer in this PR). |
| C7 | `clinical_specialties` + `knowledge_review_specialties` implement the controlled-vocabulary + many-to-many review model (round-1 addendum) | ✅ | Polymorphic association on `knowledge_row_id`, matching ADR-13's own stated rationale. |
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

---

## Overall Verdict

**No CRITICAL findings.** One flagged, non-blocking reconciliation gap (Section A) and one documented, non-blocking scope limitation (C9). Recommend proceeding to Codex review (task #7) before merge, per PTH's standing instruction not to merge before a clean Codex pass.
