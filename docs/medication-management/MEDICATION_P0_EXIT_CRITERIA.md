# MetoCare Medication — P0 Architecture Exit Criteria

**Version:** 1.0  
**Date:** 2026-07-11  
**Architecture Baseline:** `medication-architecture-v1.0`  
**Purpose:** Define the conditions under which P0 is declared architecturally complete — not just code-complete.  
**Signed by PTH:** 2026-07-11

> Passing all test gates (T-01 to T-07) confirms code correctness.
> Passing this exit criteria confirms **architectural completeness**.
> Both are required before declaring: **Medication Architecture v1.0 — Successfully Implemented.**

---

## Exit Criteria

| # | Criterion | Condition | Verified By | Status |
|---|-----------|-----------|-------------|--------|
| **EC-01** | **Schema** | No legacy path forces direct writes to `medications` without going through `medication_statements` first. `is_supplement` column removed. All new columns present with correct constraints. | Tech Lead | |
| **EC-02** | **API additive rollout** | All existing endpoints return new fields without breaking existing clients. Alias window for `status` → `lifecycle_status` is active if mobile requires it. No endpoint contract was broken. | Tech Lead + Mobile QA | |
| **EC-03** | **Data migration** | 100% of pre-P0 `medications` rows migrated with correct defaults: `lifecycle_status='active'`, `verification_status='patient_reported'`, `source_type='patient_manual'`. Exception rows (if any) explicitly documented and approved by PTH. | Tech Lead | |
| **EC-04** | **Mobile stability** | App on staging operates normally against P0 schema. No crash on new fields. QA sign-off received from mobile team. | Mobile QA | |
| **EC-05** | **ADR compliance** | Architecture Compliance Review completed for all P0 PRs. No ❌ findings unresolved. No implementation violates ADR-01, 03, 04, 09, or 11. | Codex / Tech Lead | |
| **EC-06** | **Rollback rehearsal** | Full rollback script (M-04 → M-03 → M-02 → M-01b → M-01) executed and verified on a staging DB copy. Result: zero data loss, schema returns to pre-P0 state. | Tech Lead | |
| **EC-07** | **Audit trail** | `medication_audit_log` captures correct before/after snapshots for lifecycle and verification changes. Observational events (non_adherence) log correctly with NULL snapshots. Verified by test gate T-04. | Tech Lead | |
| **EC-08** | **Documentation integrity** | `ARCHITECTURE_DECISION_INDEX.md` reflects actual implementation. No ADR has been edited directly during P0. If any deviation was found, a superseding ADR (ADR-13+) was created and approved by PTH before implementation. | PTH | |

---

## Sign-off Sequence

All 8 criteria must be ✅ before PTH declares architectural completion.

```
EC-01  Schema           → Tech Lead confirms
EC-02  API rollout      → Tech Lead + Mobile QA confirms
EC-03  Data migration   → Tech Lead confirms
EC-04  Mobile stability → Mobile QA confirms
EC-05  ADR compliance   → Codex / Tech Lead confirms
EC-06  Rollback         → Tech Lead confirms
EC-07  Audit trail      → Tech Lead confirms (via test gate T-04)
EC-08  Documentation    → PTH confirms
         ↓
PTH signs: "Medication Architecture v1.0 — Successfully Implemented"
```

---

## Declaration (to be completed at P0 completion)

> **Medication Architecture v1.0 — Successfully Implemented**
>
> All 8 exit criteria passed.  
> P0 implementation complete.  
> Architecture baseline `medication-architecture-v1.0` is confirmed as implemented.
>
> **Signed:** _______________  
> **Date:** _______________  
> **Git commit:** _______________  

---

## What Happens After Declaration

- P1 planning may begin (Knowledge Structure + CDS foundation, pending ADR-01 and ADR-09 implementation details).
- Gate 2 ADR review session may be scheduled (ADR-02, 08, 10, 12).
- Any architectural change discovered during P1 → new ADR (ADR-13+), not edit to baseline.
- Documentation freeze on `docs/medication-management/` — no new files unless tied to a new ADR or implementation finding.
