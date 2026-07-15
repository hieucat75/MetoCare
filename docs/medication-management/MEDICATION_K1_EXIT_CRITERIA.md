# MetoCare Medication — K1 Exit Criteria

**Version:** 1.0
**Date:** 2026-07-15
**Scope:** K1 — Medication Knowledge Repository (schema, catalog migration, lifecycle/versioning, draft workflow)
**Related:** `MEDICATION_K1_PRE_VALIDATION.md`, `adrs/ADR-13-KNOWLEDGE-CONTENT-LIFECYCLE.md`, `adrs/ADR-01-MEDICATION-KNOWLEDGE-STRUCTURE.md`
**Purpose:** Define the conditions under which K1 is declared complete — code-complete AND safe to leave dormant in production until K2 wires consumers to it.

> This is the **Definition of Done** for K1. Passing all 10 criteria closes the Medication Knowledge architecture phase.
> After sign-off, no further architecture docs are opened for K1 — only Implementation, Codex Review, Test, Merge, Deploy.

---

## Exit Criteria

| # | Criterion | Condition | Verified By | Status |
|---|-----------|-----------|-------------|--------|
| **EC-01** | **Schema — ADR-13 compliance** | Knowledge tables (`drug_usage`, `drug_patient_education`, `drug_side_effects`, `drug_monitoring`, `drug_contraindications`, `drug_interactions`) match ADR-13's structure, per-table business keys, and lifecycle/versioning columns exactly. No test-fixture-shaped constraints in the applied schema. | Tech Lead | |
| **EC-02** | **Schema — ADR-01 compliance** | Overall knowledge structure (entity boundaries, relationships to `drug_products`) matches ADR-01. No deviation implemented without a superseding ADR. | Tech Lead | |
| **EC-03** | **Catalog migration correctness** | All 41 catalog entries migrated with correct content mapping and zero malformed rows. Spot-checked against source content by Tech Lead. | Tech Lead | |
| **EC-04** | **No data loss** | Row-count and checksum comparison pre/post migration matches expected counts. Any discrepancy explicitly documented and approved by PTH. | Tech Lead | |
| **EC-05** | **Rollback rehearsal** | Full rollback executed and verified on a staging DB copy. Result: zero data loss, schema returns to pre-K1 state. | Tech Lead | |
| **EC-06** | **Draft workflow functional** | Draft → review → approve/reject state transitions work end-to-end per ADR-13's lifecycle model, covered by migration/workflow tests. | Tech Lead | |
| **EC-07** | **No approved knowledge in production** | Zero rows with `status='approved'` in any knowledge table on production at K1 completion. K1 ships schema + drafts only, not clinically live content. | Tech Lead | |
| **EC-08** | **Knowledge API not exposed** | No public/internal API route reads from or writes to the new knowledge tables. Repository layer exists in code only, unwired to any router. | Tech Lead | |
| **EC-09** | **Frontend unchanged** | No frontend behavior, route, or contract changes as a result of K1. `frontend/` diff for this work is empty or docs-only. | Tech Lead | |
| **EC-10** | **AI does not read new repository** | Meto / clinical-copilot context builders and prompts have zero references to the new knowledge tables or repository. AI behavior is unchanged by K1. | Tech Lead | |

---

## Sign-off Sequence

All 10 criteria must be ✅ before PTH declares K1 complete.

```
EC-01  Schema (ADR-13)      → Tech Lead confirms
EC-02  Schema (ADR-01)      → Tech Lead confirms
EC-03  Catalog migration    → Tech Lead confirms
EC-04  No data loss         → Tech Lead confirms
EC-05  Rollback rehearsal   → Tech Lead confirms
EC-06  Draft workflow       → Tech Lead confirms
EC-07  No approved rows     → Tech Lead confirms
EC-08  API not exposed      → Tech Lead confirms
EC-09  Frontend unchanged   → Tech Lead confirms
EC-10  AI unwired           → Tech Lead confirms
         ↓
PTH signs: "K1 Knowledge Repository — Complete"
```

Note: EC-01 through EC-10 gate **K1 completion** (dormant, production-safe repository). They are separate from — and do not by themselves authorize — the **K1 Production** migration GO, which additionally requires the production `drug_product_id` audit and full 9-point pre-validation per `MEDICATION_K1_PRE_VALIDATION.md`.

---

## Declaration (to be completed at K1 completion)

> **K1 Knowledge Repository — Complete**
>
> All 10 exit criteria passed.
> Repository exists in production schema, dormant (no consumers wired).
>
> **Signed:** _______________
> **Date:** _______________
> **Git commit:** _______________

---

## What Happens After Declaration

- No new architecture docs are opened for K1. Remaining work is Implementation → Codex Review → Test → Merge → Deploy, same pattern as Medication P0.
- K2 (wiring consumers: Knowledge API exposure, AI context integration) requires its own separate GO and is out of scope here.
- ADR-14 (Patient Context Resolution) stays deferred to K4 per PTH's standing decision — unaffected by K1 completion.
