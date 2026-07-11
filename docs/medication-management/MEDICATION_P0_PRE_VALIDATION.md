# MetoCare Medication P0 — Pre-Implementation Validation Checklist

**Version:** 1.0  
**Date:** 2026-07-11  
**For:** Tech Lead — must complete BEFORE writing first migration  
**Ref:** P0 Implementation Plan v1.1, ADR-01/03/04/09/11  
**Architecture tag:** `medication-architecture-v1.0`

> PTH instruction: Do not hand over "Implement P0" directly.
> First validate P0 Implementation Plan against the existing MetoCare codebase.
> These two things are different.

---

## Instructions

Complete each section. Write answers inline. Return this document to PTH before starting any migration.

Estimated time: 2–4 hours of codebase inspection.

---

## Section 1 — Schema Compatibility

Inspect the current `medications` table definition. For each migration:

### M-01 — Add 5 columns to `medications`

| Question | Answer |
|----------|--------|
| Does `is_supplement` column exist in current schema? | |
| Does `lifecycle_status` column already exist? | |
| Does `verification_status` column already exist? | |
| Does `source_type` column already exist? | |
| Does `medication_category` column already exist? | |
| Estimated row count in `medications` table (prod/staging)? | |
| Will `ADD COLUMN NOT NULL DEFAULT` lock the table? (MySQL vs Postgres behavior differs) | |
| Is there a risk of long-running backfill during business hours? | |
| Any FK cycles introduced by M-01? | |
| Any existing CHECK constraints that conflict? | |

### M-01b — `medication_category_codes` lookup table

| Question | Answer |
|----------|--------|
| Does any existing table use this name? | |
| Will FK enforcement cause issues on rows inserted before FK is active? | |

### M-02 — `medication_audit_log`

| Question | Answer |
|----------|--------|
| Does any existing table use this name? | |
| `before_snapshot` / `after_snapshot` are JSONB — is this DB engine supported? | |
| If MySQL: TEXT or JSON column type instead? | |

### M-03 — `medication_statements`

| Question | Answer |
|----------|--------|
| Does any existing table use this name? | |
| `patient_profiles` is referenced by FK — confirm table name is correct for this codebase | |

### M-04 — Add `drug_product_id`, `generic_name` to `medications`

| Question | Answer |
|----------|--------|
| `drug_products` table does not exist yet (P1) — FK must remain nullable with no REFERENCES clause until P1 | |
| Confirm nullable columns are safe to add with zero backfill | |

### Concurrent index strategy

| Question | Answer |
|----------|--------|
| Does DB support `CREATE INDEX CONCURRENTLY`? (Postgres yes, MySQL no) | |
| If not, index creation plan during low-traffic window? | |

---

## Section 2 — Existing API Impact

List every endpoint that currently reads from or writes to `medications`.

| Endpoint | Method | Reads `medications`? | Writes `medications`? | Will P0 break it? |
|----------|--------|---------------------|----------------------|------------------|
| | | | | |

**Specific checks:**

| Question | Answer |
|----------|--------|
| Does the adherence endpoint (`/adherence`, `/adherence/weekly`) read from `medications`? | |
| Does the reminder system read `lifecycle_status` or `status` from `medications`? | |
| Does any AI context builder read from `medications`? What fields? | |
| Does Doctor Portal (if any) read `medications`? | |
| Any serializer/DTO that explicitly lists `medications` columns (would break if column added)? | |
| Any raw SQL `SELECT *` from `medications` that might be affected by new columns? | |

---

## Section 3 — Mobile Compatibility

| Question | Answer |
|----------|--------|
| Does the mobile app currently handle unknown JSON fields gracefully? (test on staging) | |
| Is there a field called `status` on the current `medications` API response? | |
| If yes: does any mobile code use `medication.status`? Must keep alias `"status": lifecycle_status` during transition. | |
| Will `lifecycle_status: null` or `verification_status: null` crash any mobile component? | |
| Does mobile have a staging build that can be tested against P0 API before production? | |

---

## Section 4 — Existing Data Migration Mapping

Confirm the correct default values for ALL existing `medications` rows:

| Field | Default for existing rows | Correct? | Exceptions? |
|-------|--------------------------|---------|-------------|
| `lifecycle_status` | `'active'` | | Any rows that should be `discontinued` or `expired`? |
| `verification_status` | `'patient_reported'` | | Any rows added by staff that should be `clinician_confirmed`? |
| `source_type` | `'patient_manual'` | | Any rows imported from other systems? |
| `medication_category` | `'conventional_drug'` | | If `is_supplement=TRUE` rows exist, they become `'supplement'` |

**If any exception rows exist:** write a targeted UPDATE before the default migration, or document why the default is acceptable.

---

## Section 5 — Rollback Safety

| Question | Answer |
|----------|--------|
| M-01 rollback (DROP COLUMN): safe only before API deployment — confirm rollback window | |
| M-02 rollback (DROP TABLE medication_audit_log): any FK deps from other tables? | |
| M-03 rollback (DROP TABLE medication_statements): same | |
| M-04 rollback (DROP COLUMN): same window constraint as M-01 | |
| Is a full DB snapshot taken automatically before every migration on staging? | |
| Is a full DB snapshot required before production migration? Who triggers it? | |
| Has the rollback script been written and dry-run on a local DB copy? | |

---

## Section 6 — Service Layer

| Question | Answer |
|----------|--------|
| Where is the `MedicationService` (or equivalent) in the codebase? | |
| Is there currently any RBAC check on `medications` writes? Where? | |
| Is there a transaction wrapper already available for multi-table atomic writes? | |
| Is there an existing background job runner for the `expired` detection job? | |
| Where should the expired detection cron be registered? | |
| Is `POST /medications/{id}/report-non-adherence` a new endpoint or does a similar one exist? | |

---

## Section 7 — Test Infrastructure

| Question | Answer |
|----------|--------|
| Is there an existing test DB / test migration runner? | |
| Can test gates T-01 to T-07 (from P0 Plan) be run in CI? | |
| Is there a staging environment where migrations can be validated before production? | |
| Who on the team owns mobile QA sign-off (Gate T-06)? | |

---

## Sign-off

Tech Lead confirms:
- [ ] All Section 1–7 questions answered
- [ ] No blocking issues found (or issues documented with mitigation)
- [ ] Rollback script written and tested on local DB
- [ ] Mobile team notified of upcoming API changes
- [ ] PTH notified of any deviations from P0 Implementation Plan

**Completed by:** _______________  
**Date:** _______________  
**Reviewed by PTH:** _______________

---

## Architecture Rules (PTH instruction, 2026-07-11)

1. Architecture is frozen at tag `medication-architecture-v1.0`.
2. ADRs (ADR-01 to ADR-12) are immutable from this point.
3. If implementation reveals an ADR is wrong or incomplete: create a new ADR (ADR-13+) that supersedes the relevant section. Do not edit the original.
4. Code must follow ADR. ADR is not edited to match code.
5. Every superseding ADR requires PTH approval before implementation.
