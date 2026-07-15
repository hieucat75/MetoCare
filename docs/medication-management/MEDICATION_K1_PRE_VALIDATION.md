# Medication K1 — Pre-Validation Status

**Last updated:** 2026-07-15
**Purpose:** Canonical, git-tracked gate tracker for K1 (Knowledge Repository) pre-validation — mirrors the role `ARCHITECTURE_DECISION_INDEX.md` plays for ADR status. Updated only from real evidence; results are never inferred or copied between environments.
**Related:** `adrs/ADR-13-KNOWLEDGE-CONTENT-LIFECYCLE.md`, `adrs/ADR-01-MEDICATION-KNOWLEDGE-STRUCTURE.md`, `adrs/ARCHITECTURE_DECISION_INDEX.md`

---

## Gate Status

```
K1 Pre-Validation

✓ ADR-13 Accepted
✓ Staging drug_product_id audit (0 non-null rows)
⏳ Production drug_product_id audit
⏳ Business-key uniqueness review
⏳ Remove production DB constraint tied to test fixtures (nếu còn)
```

---

## Evidence Log

### Staging `drug_product_id` audit — ✅ PASS (2026-07-15)

- **Query:** `SELECT COUNT(*) FROM medications WHERE drug_product_id IS NOT NULL;`
- **Result:** `staging_non_null_count = 0`
- **Verified by:** PTH, via Azure Cloud Shell (2026-07-15) — an already-allowlisted channel; direct access from the local dev environment had been blocked earlier by the Postgres firewall (by design) and, separately, by the agent's own safety classifier when a broader `containerapp exec` channel was attempted instead of the specific query.
- **Conclusion:** adding `medications.drug_product_id → drug_products.id` as an FK constraint is additive and safe on staging. Every row is currently `NULL`, so no backfill is required and there is no orphan-reference risk for this environment.

### Production `drug_product_id` audit — ⏳ PENDING

- Not run. **Not inferred from the staging result** — a zero count on staging says nothing about production's actual data.
- **Per PTH: this audit will be run immediately before the production migration, and does not block K1 implementation on the development branch.** Production and staging are audited independently because they can diverge (production may carry real historical data staging never had).
- Owner: PTH / Tech Lead, via an already-allowlisted channel (Azure Cloud Shell), using the same query above against the production database.

### Business-key uniqueness — design complete, verification pending

- Per-table business keys are fully designed and documented: `ADR-13-KNOWLEDGE-CONTENT-LIFECYCLE.md` §"Per-Table Business Key & Uniqueness Policy" (added in the 2026-07-15 revision), replacing the earlier flawed generic "one approved row per ingredient" rule with a table-specific key for each of `drug_usage`, `drug_patient_education`, `drug_side_effects`, `drug_monitoring`, `drug_contraindications`, `drug_interactions`.
- Marked ⏳ here, not because the design is unfinished, but because this checklist item verifies the constraint **actually behaves as designed against a real migrated schema** — that verification requires migration code to exist and run, which K1 implementation has not yet started.

### Test-fixture DB constraint — removed from design, verification pending

- `ADR-13-KNOWLEDGE-CONTENT-LIFECYCLE.md` §"Production Schema Must Not Encode Test Data" (2026-07-15 revision) removed the earlier `source NOT LIKE 'test_fixture%'` CHECK constraint concept. Enforcement of "test data never reaches `approved`" was moved out of the schema entirely, to RBAC (no approval permission exists in test/CI environments) and a CI guard.
- Marked ⏳ here because this checklist item confirms **no such constraint exists in the actually-applied schema** — there is nothing to verify against yet since no migration has been written or run.

---

## ADR-13 Status

**Accepted** (PTH, 2026-07-15) — supersedes the interim "approved in substance, Accepted pending" status recorded after PTH's first K0 review round. See the ADR file's metadata table and status line for the full history of both review rounds.

## ADR-14 Status

Unchanged — remains **Proposed**, approved in principle, formal Acceptance deferred to K4 per PTH's standing decision. Not affected by this update.

---

## Remaining Blockers Before K1 Implementation Start

Per the original 5-condition gate (PTH review round 2):

1. ~~ADR-13 Accepted~~ — ✅ cleared, this update.
2. ~~Staging `drug_product_id` audit~~ — ✅ cleared, this update. Production audit remains open but is explicitly non-blocking for development-branch work (see above).
3. ~~Business-key/unique policy per table~~ — ✅ cleared (documented in ADR-13, 2026-07-15 revision).
4. ~~Remove production-schema "test fixture" constraint~~ — ✅ cleared (documented in ADR-13, 2026-07-15 revision).
5. Tech Lead 9-point Pre-Validation with PASS/FAIL + real codebase evidence — this is the gate to consider **K1 complete**, not a precondition to **starting** it (it validates migration code that doesn't exist yet). Not a start-blocker.

**No condition currently blocks starting K1 schema/catalog migration work on a development branch.** Production migration itself remains separately gated on the production `drug_product_id` audit (above) and, ultimately, on the full 9-point pre-validation passing with evidence.

## Non-Blockers (Explicitly Decoupled)

- **Production `drug_product_id` audit** — deferred to the window immediately before production migration, per PTH's explicit instruction. Does not gate development-branch implementation.

---

## Scope Reminder

This document tracks status only — it does not itself authorize starting implementation. Per this session's standing working pattern, writing the K1 migration requires a separate, explicit GO instruction from PTH even when every tracked condition shows clear.
