# MetoCare Medication — K1-S2 Catalog Migration Report

**Date:** 2026-07-15
**Migration:** `k1_s2_m01_catalog_migration` (Revises `k1_m01_knowledge_schema`)
**Source:** `drug_catalog` table, 41 rows (seeded by `t9_m2_drug_seed`)
**Purpose:** Per-entry classification — migrated cleanly / migrated with nullable gaps / blocked by ambiguous identity. No entry was normalized by guessing.

---

## Result: 41/41 migrated. 0 blocked.

Analysis of all 41 source rows (via direct inspection of `app/services/drug_catalog.py::_SEED`, cross-checked against the live `drug_catalog` table) found:

- Every entry has **exactly one** `active_ingredients` value — no combination products in this catalog.
- **Zero** duplicate active-ingredient values across different `generic_name` entries (clean 1:1 product↔ingredient mapping).
- **Zero** brand/alias/Vietnamese-name collisions across different `generic_name` entries (no name is claimed by two different drugs).
- `generic_name` is unique across all 41 rows.

Given this, **no entry required a judgment call about identity** — there was nothing ambiguous to resolve or block on. This is reported as a genuine finding, not assumed in advance.

## Category 1 — Migrated cleanly (41/41)

All 41 entries: `drug_products` row (from `generic_name` + regulatory/status fields), `drug_ingredients` row (from `active_ingredients[0]`), `drug_product_ingredients` link (`role="active_ingredient"`, `is_primary=true`), and `drug_product_names` rows for every entry in `brand_names` + `vietnamese_common_names` + `aliases` (255 rows total across all 41 products).

Full list (generic_name → active_ingredient → drug_class): metformin→metformin hydrochloride→biguanide, gliclazide→gliclazide→sulfonylurea, glimepiride→glimepiride→sulfonylurea, sitagliptin→sitagliptin phosphate monohydrate→dpp4_inhibitor, vildagliptin→vildagliptin→dpp4_inhibitor, empagliflozin→empagliflozin→sglt2_inhibitor, dapagliflozin→dapagliflozin propanediol→sglt2_inhibitor, insulin glargine→insulin glargine→long_acting_insulin, insulin aspart→insulin aspart→rapid_acting_insulin, pioglitazone→pioglitazone→thiazolidinedione, rosuvastatin→rosuvastatin→statin, atorvastatin→atorvastatin→statin, simvastatin→simvastatin→statin, fenofibrate→fenofibrate→fibrate, ezetimibe→ezetimibe→cholesterol_absorption_inhibitor, amlodipine→amlodipine→calcium_channel_blocker, perindopril→perindopril→ace_inhibitor, losartan→losartan→arb, valsartan→valsartan→arb, telmisartan→telmisartan→arb, candesartan→candesartan→arb, bisoprolol→bisoprolol→beta_blocker, nebivolol→nebivolol→beta_blocker, metoprolol→metoprolol→beta_blocker, hydrochlorothiazide→hydrochlorothiazide→thiazide_diuretic, indapamide→indapamide→thiazide_like_diuretic, spironolactone→spironolactone→aldosterone_antagonist, levothyroxine→levothyroxine→thyroid_hormone, allopurinol→allopurinol→xanthine_oxidase_inhibitor, febuxostat→febuxostat→xanthine_oxidase_inhibitor, colchicine→colchicine→anti_inflammatory_gout, aspirin→aspirin→antiplatelet, clopidogrel→clopidogrel→antiplatelet, rivaroxaban→rivaroxaban→noac, apixaban→apixaban→noac, warfarin→warfarin→vitamin_k_antagonist, omeprazole→omeprazole→proton_pump_inhibitor, esomeprazole→esomeprazole→proton_pump_inhibitor, pantoprazole→pantoprazole→proton_pump_inhibitor, silymarin→silymarin→hepatoprotective_supplement, essential phospholipids→polyenylphosphatidylcholine→hepatoprotective_supplement.

25 distinct `drug_classes` rows created (one per distinct source `drug_class` string; several drugs share a class, e.g. 4 ARBs, 3 PPIs, 3 statins, 3 beta blockers).

## Category 2 — Migrated with nullable gaps (universal, not per-entry)

These gaps apply to **all 41 entries uniformly** — not a data-quality problem with specific rows, but fields the source catalog never captured:

| Field | Value | Why left NULL, not guessed |
|-------|-------|------------------------------|
| `drug_classes.atc_code` / `atc_level` | NULL for all 25 classes | No WHO ATC code exists anywhere in `drug_catalog`. Per ADR-01 Open Question 1, sourcing ATC codes requires a licensed data source (WHO/MoH) — assigning one from memory would be exactly the kind of clinical guess this migration must not make. |
| `drug_ingredients.name_vietnamese` | NULL for all 41 ingredients | `vietnamese_common_names` in the source is a **product/brand** name list (e.g. "Glucophage" for metformin), not a translation of the ingredient's own name. Mapping it into the ingredient's Vietnamese-name field would assert something the source doesn't actually say. |
| `drug_ingredients.cas_number` | NULL for all 41 ingredients | Not present anywhere in `drug_catalog`. |
| `drug_ingredients.name_inn` | Source value verbatim (e.g. `"metformin hydrochloride"`, not the bare INN `"metformin"`) | The source's `active_ingredients` field mixes true INN names (e.g. `"empagliflozin"`) with named salt forms (e.g. `"dapagliflozin propanediol"`). Splitting salt from base INN requires pharmacological judgment this migration isn't positioned to make — the source string is taken as-is. |
| `drug_product_names.language` | `"vi"` for every row, including brand names that are internationally-used strings (e.g. "Glucophage") | Reflects the fact that all 41 source entries are `country_context="VN"` (market context), not a linguistic claim that "Glucophage" is a Vietnamese word. |

## Category 3 — Blocked by ambiguous identity (0/41)

**None.** No entry had a combination-product ingredient list, a name collision with another entry, or any other identity ambiguity that would require a human decision before migrating. If this changes in a future catalog update (e.g. a combination product is added), this migration's one-ingredient-per-row assumption (`row.active_ingredients[0]`) would need revisiting — it is not silently generalized to handle multi-ingredient rows.

---

## Verification

- Row count reconciliation: `SELECT COUNT(*) FROM drug_catalog` = 41 = `EXPECTED_SOURCE_ROW_COUNT` (migration raises `RuntimeError` and refuses to run if this count ever changes unexpectedly).
- Live counts after migration: `drug_classes`=25, `drug_ingredients`=41, `drug_products`=41, `drug_product_ingredients`=41, `drug_product_names`=255.
- Idempotency proven at the data level: `migrate_catalog_rows()` invoked a second time against the already-migrated database inserted **0** new rows in any table (verified directly, not inferred).
- `drug_catalog` unchanged: still 41 rows, untouched by this migration (read-only access only).
