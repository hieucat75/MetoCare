# MetoCare Medication — K1-S2 Compliance Review

**Version:** 1.0
**Date:** 2026-07-15
**PR scope:** K1-S2-M01 — migrate the 41-entry `drug_catalog` into the ADR-01 relational core
**Branch:** `feat/k1-s2-catalog-migration`
**Reviewer:** Tech Lead (self-review) + independent Codex CLI review
**Purpose:** Pre-merge gate — does this PR comply with the K1-S2 scope lock PTH set?

---

## Scope lock verification

| Requirement | Status | Evidence |
|---|---|---|
| Migrate 41/41 entries | ✅ | `MEDICATION_K1_S2_CATALOG_MIGRATION_REPORT.md` — 41/41, 0 blocked. Migration itself raises `RuntimeError` if source count ≠ 41. |
| Don't delete/modify `drug_catalog` | ✅ | Migration only `SELECT`s from `DrugEntry` (read-only ORM query); no `UPDATE`/`DELETE` statement touches `drug_catalog` anywhere in upgrade() or downgrade(). Verified: `test_source_catalog_untouched` (41 rows before/after, spot-checked content). |
| No `Medication.drug_product_id` backfill | ✅ | No `medications` table reference anywhere in the migration. |
| No clinical content authored | ✅ | No `drug_usage`/`drug_side_effects`/`drug_monitoring`/`drug_contraindications`/`drug_patient_education` row touched — this PR only populates the ADR-01 relational core. |
| No API/frontend/AI opened | ✅ | No changes under `app/api/`, `frontend/`, or Meto/context-builder modules. |
| No `drug_interactions` touched | ✅ | Not referenced anywhere in this migration (table doesn't exist per K1-M01). |

## Requirement 1 — Mapping

Documented in full in `MEDICATION_K1_S2_CATALOG_MIGRATION_REPORT.md`. Summary: product/ingredient/class mapped from source fields verbatim; ATC code, ingredient CAS number, and ingredient-level Vietnamese name left NULL (no source data exists for any of them — not guessed). Per-entry classification: 41 clean, 0 blocked (see report for why zero ambiguity existed in this specific catalog).

## Requirement 2 — Idempotent

- Business keys: `drug_classes.name` (UNIQUE, pre-existing from K1-M01), `drug_ingredients.name_inn` (UNIQUE, pre-existing), `drug_products.display_name` (UNIQUE, **added by this migration**), `drug_product_names(drug_product_id, name, name_type)` (UNIQUE, **added by this migration**), `drug_product_ingredients(drug_product_id, drug_ingredient_id)` (composite PK, pre-existing).
- Evidence, not assumption: `TestBusinessKeyConstraints` proves both new constraints reject duplicates live on Postgres. `TestIdempotency.test_rerunning_migration_logic_inserts_nothing_new` calls the migration's core upsert function (`migrate_catalog_rows`) a **second time** directly against the already-migrated database (bypassing Alembic's own once-per-revision tracking) and asserts zero new rows in every table — this is the strongest form of the idempotency proof, verified manually before the automated test was written (second manual run: `{'classes': 0, 'ingredients': 0, 'products': 0, 'product_names': 0}`).

## Requirement 3 — Zero loss

- `len(catalog_rows) != 41` raises `RuntimeError` and aborts the migration rather than silently proceeding with a partial set.
- Live counts reconciled: 41 `drug_catalog` → 41 `drug_products`, 41 `drug_ingredients`, 25 `drug_classes` (shared across ingredients), 41 `drug_product_ingredients` links, 255 `drug_product_names`.
- No JSON field is silently dropped: `brand_names`, `vietnamese_common_names`, and `aliases` are each fully iterated into `drug_product_names` rows (`caution_flags`, `contraindication_keywords`, `common_indications`, `metric_groups`, `notes_for_matching_only` are intentionally NOT migrated — they belong to the future ADR-13 knowledge tables or CDS domain, not the ADR-01 relational core this PR populates; migrating them here would be scope creep beyond K1-S2's locked scope).

## Requirement 4 — Rollback-safe

- `downgrade()` deletes only the 5 tables this migration (and K1-M01, which shipped them empty) ever wrote to — `drug_catalog` is never referenced in `downgrade()`.
- Verified: `TestRollback.test_downgrade_removes_all_migrated_rows_but_keeps_catalog` — all 5 relational-core tables empty after downgrade, `drug_catalog` still 41 rows.
- `TestRollback.test_upgrade_downgrade_upgrade_idempotent` — full cycle restores exact same counts (25/41/41/255).
- The two new UNIQUE constraints are dropped in `downgrade()`, restoring K1-M01's exact original schema.

## Requirement 5 — PostgreSQL integration tests

`tests/integration/test_medication_k1_s2_catalog_migration.py`, 14 tests: zero-loss (3), product-ingredient linkage (3), name handling incl. duplicate-alias-across-types (3), business-key constraint enforcement (2), idempotent re-run (1), rollback + rehearsal (2). Wired into `.github/workflows/ci.yml`'s PostgreSQL integration job.

## Requirement 6 — Compliance

### 5-question governance answers

1. **Which ADR?** ADR-01 (relational core) — this PR populates it with real data for the first time; ADR-13 not touched (no clinical content).
2. **Which Exit Criterion?** Advances EC-02 (ADR-01 schema) from "structure exists" to "structure populated with real catalog data." Does not close EC-03/EC-04 formally (those were defined for the original 41-drug catalog migration in the P0-era docs) — this PR is the concrete implementation of that requirement for the K1 relational core specifically.
3. **Scope expansion?** No — confirmed against every item in PTH's scope lock above.
4. **Technical debt?** One item: `drug_ingredients.name_inn` stores the source's salt-form string verbatim (e.g. "metformin hydrochloride") rather than a normalized pure-INN + salt-form split — flagged in the migration report as a deliberate non-guess, not fixed here.
5. **Rollback loss?** Nothing — `drug_catalog` (the only pre-existing data) is untouched; the 5 relational-core tables this migration populates had zero prior data (shipped empty by K1-M01), so downgrade loses only what this PR itself created.

### Codex review (round 1) — 2 P1 + 3 P2, all resolved

| # | Finding | Severity | Resolution |
|---|---|---|---|
| 1 | `downgrade()` unconditionally cleared all 5 tables — safe only at initial deploy; if a later migration/service ever wrote to these tables under different keys, downgrading this revision would destroy that data too. | P1 | Rewrote `downgrade()` to delete only rows matching business keys re-derived from `drug_catalog` (product `display_name`, ingredient `name_inn`, class `name`), never a blanket `DELETE`. |
| 2 | `row.active_ingredients[0]` would silently truncate a future combination product to its first ingredient — contradicted the report's "not silently generalized" claim, which described intent, not enforced behavior. | P1 | Added an explicit `RuntimeError` if `len(active_ingredients) != 1`, before any write. Verified: the report's claim is now actually true, not aspirational. |
| 3 | The pre-loop 41-row count guard doesn't prove every source row produced a product+ingredient+link — only that the total count matched. | P2 | Added a post-loop reconciliation pass: for every source row, verify a matching `drug_products` row and at least one `drug_product_ingredients` link exist, raising `RuntimeError` otherwise. |
| 4 | Query-then-insert idempotency is proven for serial re-runs only, not concurrent migration execution. | P2 | Documented as an explicit, accepted limitation in the migration's module docstring — this project's deploy process never runs `alembic upgrade` concurrently against the same database; a race would fail loudly (UNIQUE violation) rather than duplicate data. |
| 5 | The migration report's per-entry mapping list had factual errors — several entries transcribed from memory instead of the actual migrated values (e.g. "pioglitazone→pioglitazone" vs. the true "pioglitazone hydrochloride"). | P2 | Regenerated the entire list by querying the live migrated database directly, not from memory. Report now states this explicitly, including the error it caught in itself. |

All fixes re-verified: 14/14 integration tests pass, upgrade/downgrade/upgrade rehearsal clean, full backend unit suite green.
