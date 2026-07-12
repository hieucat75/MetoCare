# MetoCare Medication — Architecture Compliance Review Checklist

**Version:** 1.0  
**Date:** 2026-07-11  
**Architecture Baseline:** `medication-architecture-v1.0`  
**Purpose:** Pre-merge gate. Reviewer (Codex or Tech Lead) verifies that code changes comply with signed ADRs.  
**Scope:** Every PR that touches `medications`, `medication_statements`, `medication_audit_log`, `medication_category_codes`, or related service/API layer.

> This is an **architecture review**, not a code review.
> Code quality (style, naming, tests) is reviewed separately.
> This checklist answers one question: **Does this PR comply with the ADRs?**

---

## How to Use

1. Reviewer completes this checklist for each PR.
2. Any `❌` is a **blocking** finding — must be resolved before merge.
3. Any `⚠️` is a **risk flag** — must be discussed with PTH before merge.
4. Completed checklist is attached to PR as a comment or file.
5. PTH approval required before merge if any `❌` or `⚠️` remains.

---

## Section A — Knowledge Structure (ADR-01)

| # | Check | Status | Note |
|---|-------|--------|------|
| A1 | New drug entities stored in normalized catalog structure, not as ad-hoc JSON blobs | | |
| A2 | `generic_name` uses INN standard (not brand name as primary key) | | |
| A3 | No new flat JSON catalog patterns introduced | | |
| A4 | `drug_product_id` FK is nullable (catalog not yet built at P0/P1) | | |

---

## Section B — Medication Lifecycle (ADR-11)

| # | Check | Status | Note |
|---|-------|--------|------|
| B1 | `lifecycle_status` uses only the 7 approved values: `active \| paused \| on_hold \| completed \| discontinued \| expired \| entered_in_error` | | |
| B2 | No new lifecycle state introduced without a superseding ADR | | |
| B3 | `verification_status` uses only the 4 approved values: `patient_reported \| clinician_confirmed \| ocr_extracted \| system_inferred` | | |
| B4 | `on_hold` can only be set by DOCTOR role (enforced at service layer, not frontend) | | |
| B5 | Patient cannot clear `on_hold` — only DOCTOR can | | |
| B6 | Patient reporting non-adherence creates event, does NOT change `lifecycle_status` | | |
| B7 | `expired` is set only by the system background job, never by API caller | | |
| B8 | `source_type` and `verification_status` are written independently — not derived from each other | | |

---

## Section C — History & Audit (ADR-03)

| # | Check | Status | Note |
|---|-------|--------|------|
| C1 | Every `lifecycle_status` change writes to `medication_audit_log` atomically (same transaction) | | |
| C2 | Every `verification_status` change writes to `medication_audit_log` atomically | | |
| C3 | `before_snapshot` and `after_snapshot` are populated for all state-changing events | | |
| C4 | Observational events (non_adherence, reminder_taken) have NULL snapshots — event_data carries payload | | |
| C5 | No separate history table introduced alongside `medication_audit_log` (single source of truth) | | |

---

## Section D — Reconciliation & Provenance (ADR-04)

| # | Check | Status | Note |
|---|-------|--------|------|
| D1 | Every new canonical `medications` record was promoted from a `medication_statements` row | | |
| D2 | No code writes directly to `medications` without first creating a `medication_statements` entry | | |
| D3 | Auto-merge is NOT implemented — all reconciliation requires human action | | |
| D4 | When an expired medication is re-reported by patient, a new `medication_statements` row is created (assertion_type='continued_use') — direct lifecycle_status change to 'active' is blocked | | |
| D5 | Doctor-prescribed expired records (source_type='doctor_prescribed') are set to `statement_status='awaiting_clinician'` — patient cannot self-reactivate | | |
| D6 | AI context reads from canonical `medications` only — never from `medication_statements` directly | | |

---

## Section E — CDS Placement (ADR-09)

| # | Check | Status | Note |
|---|-------|--------|------|
| E1 | Safety checks (interaction, allergy) run in the domain service layer, not in frontend | | |
| E2 | No clinical decision logic placed in database triggers | | |
| E3 | No clinical decision logic placed in frontend validation only | | |
| E4 | CDS is called synchronously for medication writes (not fire-and-forget) | | |

---

## Section F — Category & Taxonomy (ADR-06 — P0 scope only)

| # | Check | Status | Note |
|---|-------|--------|------|
| F1 | `medication_category` is validated via FK to `medication_category_codes` — not via a hardcoded enum or CHECK constraint | | |
| F2 | New medication categories added only as INSERT into `medication_category_codes` — not by schema change | | |
| F3 | Full ADR-06 taxonomy (9 values) NOT implemented until Gate 3 approval | | |

---

## Section G — General Architecture Rules

| # | Check | Status | Note |
|---|-------|--------|------|
| G1 | No ADR has been edited directly — superseding done via new ADR (ADR-13+) | | |
| G2 | No new architectural pattern introduced without PTH approval | | |
| G3 | PHI fields follow encryption/access rules (ADR-12 — when applicable) | | |
| G4 | AI/LLM is not placed in any deterministic safety-critical path (interaction check, allergy check) | | |
| G5 | No feature from Gate 2 or Gate 3 is implemented in a Gate 1 PR | | |

---

## Findings Summary

| Category | ❌ Blocking | ⚠️ Risk | ✅ Pass |
|----------|------------|---------|--------|
| A — Knowledge Structure | | | |
| B — Lifecycle | | | |
| C — Audit | | | |
| D — Reconciliation | | | |
| E — CDS | | | |
| F — Category | | | |
| G — General | | | |

---

## Verdict

- [ ] **PASS** — All checks ✅. PR complies with `medication-architecture-v1.0`. Ready for merge pending PTH approval.
- [ ] **CONDITIONAL PASS** — Risk flags present. Discussed with PTH. Merge approved with noted exceptions.
- [ ] **BLOCK** — Blocking findings present. PR must be revised before merge.

**Reviewed by:** _______________  
**Date:** _______________  
**PR:** _______________  
**PTH sign-off:** _______________
