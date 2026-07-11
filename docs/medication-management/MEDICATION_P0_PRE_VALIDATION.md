# MetoCare Medication P0 — Pre-Implementation Validation Checklist

**Version:** 1.0  
**Date:** 2026-07-11  
**Completed:** 2026-07-11 (codebase inspection by OpenClaw subagent)  
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

### Current `medications` columns (confirmed via model + migration chain)

From initial migration (`2c30ffd33627`) + subsequent additive migrations:
- `id` (String/36, PK), `patient_id` (FK → patient_profiles), `name`, `dose`, `note`
- `created_at`, `updated_at` (TimestampMixin)
- `deleted_at`, `deleted_by` — added by `t4_m9_add_sdel`
- `frequency` — added by `pr_d_add_medication_frequency`

**None of the P0 target columns exist today.**

### M-01 — Add 5 columns to `medications`

| Question | Answer |
|----------|--------|
| Does `is_supplement` column exist in current schema? | **PASS — does NOT exist.** Not in initial migration, ORM model (`app/models/clinical.py:144`), or any subsequent migration. No `is_supplement` migration to execute; the `UPDATE ... WHERE is_supplement=TRUE` block in M-01b can be skipped. |
| Does `lifecycle_status` column already exist? | **PASS — does NOT exist.** Confirmed: no entry in any Alembic version file; not in ORM `Medication` model. Clean to add. |
| Does `verification_status` column already exist? | **PASS — does NOT exist.** The only `verification_status` in codebase is on the `consultations` table (`t10_m1_consultation_marketplace.py:227`), not on `medications`. |
| Does `source_type` column already exist? | **PASS — does NOT exist on `medications`.** `source_type` exists on `lab_results` only (`t6_m1_lieng`, line 19). Not on `medications`. |
| Does `medication_category` column already exist? | **PASS — does NOT exist.** |
| Estimated row count in `medications` table (prod/staging)? | **UNKNOWN — cannot determine from codebase.** App is live on Azure staging (ACA + PostgreSQL). No analytics/metrics tool accessible. PTH must query production/staging DB: `SELECT COUNT(*) FROM medications;`. Expected: low (early-stage product, small user base). |
| Will `ADD COLUMN NOT NULL DEFAULT` lock the table? (MySQL vs Postgres behavior differs) | **PASS (low risk).** Production DB is **PostgreSQL** (TimescaleDB image `timescale/timescaledb-ha:pg16`, `docker-compose.yml:8`; staging uses Azure Postgres Flexible Server, `ci.yml:267`). In Postgres ≥ 11, `ADD COLUMN NOT NULL DEFAULT <constant>` is metadata-only — no table rewrite, no row-level lock beyond brief `ACCESS EXCLUSIVE`. All 4 defaults (`'active'`, `'patient_reported'`, `'patient_manual'`, `'conventional_drug'`) are string literals — qualifies for instant ADD. |
| Is there a risk of long-running backfill during business hours? | **PASS — no backfill required.** Postgres ≥ 11 adds the default to the catalog; existing rows only get the default value when fetched. No explicit UPDATE needed for the 4 new NOT NULL columns. Only the optional `UPDATE ... WHERE is_supplement=TRUE` matters — but `is_supplement` doesn't exist, so that block is skipped entirely. |
| Any FK cycles introduced by M-01? | **PASS.** The CHECK constraints and the `medication_category` FK to `medication_category_codes` (added in M-01b) are acyclic. No cycle. |
| Any existing CHECK constraints that conflict? | **PASS.** No existing CHECK constraints on the `medications` table in any migration file. New CHECKs (`chk_lifecycle_status`, `chk_verification_status`, `chk_source_type`) are net-new. |

### M-01b — `medication_category_codes` lookup table

| Question | Answer |
|----------|--------|
| Does any existing table use this name? | **PASS — does NOT exist.** Searched all 56 Alembic version files; no table named `medication_category_codes`. |
| Will FK enforcement cause issues on rows inserted before FK is active? | **PASS — no risk.** Migration sequence is M-01b BEFORE M-01's FK constraint (`ADD CONSTRAINT fk_medication_category`). M-01b seeds `conventional_drug` and `supplement` before M-01 establishes the FK. All existing rows get `medication_category='conventional_drug'` via the NOT NULL DEFAULT, which is a valid key in the lookup table. |

### M-02 — `medication_audit_log`

| Question | Answer |
|----------|--------|
| Does any existing table use this name? | **PASS — does NOT exist.** Tables named `audit_logs` and `meto_audit_logs` exist, but `medication_audit_log` does not. Confirmed across all 56 migration files. |
| `before_snapshot` / `after_snapshot` are JSONB — is this DB engine supported? | **PASS.** Production is PostgreSQL (TimescaleDB pg16). JSONB is natively supported. **RISK: CI tests run on SQLite** (`conftest.py:6` — `MCP_DATABASE_URL=sqlite:///...`). SQLite does not have JSONB; Alembic/SQLAlchemy will fall back to TEXT. JSONB-specific operators (e.g., `@>`, `->>`) will fail in SQLite tests. Migration tests for M-02 MUST run against Postgres, not SQLite. |
| If MySQL: TEXT or JSON column type instead? | **N/A — not MySQL.** DB is PostgreSQL. |

### M-03 — `medication_statements`

| Question | Answer |
|----------|--------|
| Does any existing table use this name? | **PASS — does NOT exist.** Confirmed across all 56 migration files. |
| `patient_profiles` is referenced by FK — confirm table name is correct for this codebase | **PASS.** Table name is `patient_profiles` (`app/models/patient.py:19`, `__tablename__ = "patient_profiles"`; original migration `2c30ffd33627` creates it). FK `patient_id REFERENCES patient_profiles(id)` is correct. |

### M-04 — Add `drug_product_id`, `generic_name` to `medications`

| Question | Answer |
|----------|--------|
| `drug_products` table does not exist yet (P1) — FK must remain nullable with no REFERENCES clause until P1 | **PASS — confirmed.** The P0 plan adds `drug_product_id VARCHAR(36) NULL` with no REFERENCES clause until `drug_products` exists at P1. Note: `drug_catalog` table (different from `drug_products`) was added in `t9_m1_drug_cat`. The new table planned for P1 is `drug_products` (knowledge structure), which is distinct. No FK conflict. |
| Confirm nullable columns are safe to add with zero backfill | **PASS.** Both `drug_product_id` and `generic_name` are nullable — Postgres adds them as NULL for all existing rows. Zero backfill, no lock. |

### Concurrent index strategy

| Question | Answer |
|----------|--------|
| Does DB support `CREATE INDEX CONCURRENTLY`? (Postgres yes, MySQL no) | **PASS.** PostgreSQL supports `CREATE INDEX CONCURRENTLY`. However, the P0 plan's SQL uses plain `CREATE INDEX` (no CONCURRENTLY keyword). For production, indexes in M-02 and M-03 should use `CREATE INDEX CONCURRENTLY` to avoid ACCESS SHARE lock during creation. **RISK:** If table already has data (staging), plain `CREATE INDEX` will lock. Recommend adding CONCURRENTLY to all index creation in M-02 and M-03 migration scripts. |
| If not, index creation plan during low-traffic window? | **N/A — Postgres supports CONCURRENTLY.** If CONCURRENTLY is used, no maintenance window needed. If plain CREATE INDEX, schedule during low-traffic window (e.g., 03:00–05:00 SGT). |

---

## Section 2 — Existing API Impact

List every endpoint that currently reads from or writes to `medications`.

| Endpoint | Method | Reads `medications`? | Writes `medications`? | Will P0 break it? |
|----------|--------|---------------------|----------------------|------------------|
| `POST /patients/{id}/medications` | POST | No | Yes — `INSERT INTO medications` | Low risk. Response returns `MedicationOut` (explicit field list, not SELECT *). New columns have defaults; service layer `add_medication` only sets `name, dose, frequency, note`. New columns silently get DB defaults. **No break if MedicationOut not updated yet.** |
| `GET /patients/{id}/medications` | GET | Yes — ORM select via `list_medications()` | No | Low risk. `MedicationOut` schema (`app/schemas/medication.py:36`) explicitly lists fields: `id, patient_id, name, dose, frequency, note, created_at`. New columns NOT in schema — won't be serialized until schema is updated. **No break.** |
| `PATCH /patients/{id}/medications/{med_id}` | PATCH | Yes (read then update) | Yes | Low risk. `MedicationUpdate` only accepts `name, dose, frequency, note`. New columns can't be written via PATCH yet. **No break.** |
| `DELETE /patients/{id}/medications/{med_id}` | DELETE | Yes (ownership check) | Yes (soft-delete) | **No break.** Only sets `deleted_at`. |
| `GET /patients/{id}/medications/adherence-summary` | GET | Yes — reads all active medications for patient (`list_medications()`) | No | Low risk. Uses `name, dose, frequency` from `Medication` ORM. New columns present in ORM but not accessed. **No break.** |
| `POST /patients/{id}/medications/{med_id}/adherence` | POST | Yes (ownership check on `medications`) | Yes (writes `medication_adherence`) | **No break.** Only validates `medication_id` FK. |
| `GET /patients/{id}/medications/{med_id}/adherence` | GET | Yes (ownership check) | No | **No break.** |
| `GET /medications/suggest` | GET | No (reads `drug_catalog`, not `medications`) | No | **No break.** |
| Doctor Portal health timeline | GET | Yes — `db.query(Medication).filter(...)` (`routes/doctor_portal.py:176`) | No | Low risk. Uses ORM objects. New columns present in ORM object but not referenced in timeline engine. **No break.** |
| AI context builder (`_build_medications`) | GET | Yes — raw SQL: `SELECT name, dose, frequency, note, created_at FROM medications` (`context/builder.py`) | No | **PASS — no break.** Query explicitly names 5 columns; new columns are not selected. Adding columns to the table does NOT affect this query. |
| `patient_summary._fetch_medications` | Internal | Yes — ORM select, returns `id, name, dose, note, created_at` | No | **No break.** Explicit field access only. |

**Specific checks:**

| Question | Answer |
|----------|--------|
| Does the adherence endpoint (`/adherence`, `/adherence/weekly`) read from `medications`? | **YES.** `adherence_summary()` calls `list_medications()` which does ORM select on `medications`. Reads `name, dose, frequency` from each `Medication` ORM object. New columns will be present in ORM object after M-01 but never accessed — **no break.** |
| Does the reminder system read `lifecycle_status` or `status` from `medications`? | **NO.** The only reminder-adjacent code is `app/domain/policies.py` (`daily_reminders`) and `app/models/notification.py` (`appointment_reminder`). Neither reads from `medications`. No reminder system currently filters by `lifecycle_status` or any medication status. The `expired` detection job planned for P0 does not exist yet — **clean surface for new code.** |
| Does any AI context builder read from `medications`? What fields? | **YES** — `context/builder.py:_build_medications()` (line ~340). Raw SQL: `SELECT name, dose, frequency, note, created_at`. Does NOT read `id`, `lifecycle_status`, or any new column. **After P0:** the query should be updated to also filter `WHERE lifecycle_status IN ('active','paused','on_hold')` — otherwise it may return `expired` or `discontinued` medications to the AI context. **This is a RISK/follow-up item.** |
| Does Doctor Portal (if any) read `medications`? | **YES** — `routes/doctor_portal.py:176`: ORM `db.query(Medication).filter(deleted_at IS NULL)`. Used in health timeline engine. After M-01, `lifecycle_status` will be present on the ORM object but the timeline engine does not access it. **No break, but after P0 the timeline filter should also exclude `expired`/`discontinued` records.** |
| Any serializer/DTO that explicitly lists `medications` columns (would break if column added)? | **PASS — no break risk.** `MedicationOut` schema (`app/schemas/medication.py:36`) is an explicit Pydantic model with fixed fields. Adding columns to the DB does NOT add them to the response until `MedicationOut` is updated. Frontend API interface `patient.ts:Medication` also lists explicit fields only. **Safe — additive.** |
| Any raw SQL `SELECT *` from `medications` that might be affected by new columns? | **PASS — none found.** `_build_medications()` in `context/builder.py` uses explicit column list. `list_medications()` uses ORM `select(Medication)` which expands to explicit columns via SQLAlchemy. No `SELECT *` from `medications` found anywhere. |

---

## Section 3 — Mobile Compatibility

| Question | Answer |
|----------|--------|
| Does the mobile app currently handle unknown JSON fields gracefully? (test on staging) | **UNKNOWN — mobile app source not in repo.** `/Users/pth/Developer/Metocare/mobile/` contains only `.claude/`, `.vscode/`, and `design-reference/` (a static HTML mock). No actual React Native / Flutter source code present. Mobile JSON parsing behavior cannot be verified from codebase. **PTH must confirm with mobile team before API deployment.** |
| Is there a field called `status` on the current `medications` API response? | **NO — not in the backend `MedicationOut` schema** (`app/schemas/medication.py:36`). The backend currently does NOT return a `status` field for medications. However: the design-system `MedicationCard.tsx` component (`frontend/src/design-system/components/healthcare/MedicationCard.tsx:29`) has a local `status: 'active' | 'paused' | 'completed' | 'discontinued'` type in its props interface — this is a **frontend-only design prop, not wired to API data**. The `frontend/src/lib/api/patient.ts:Medication` interface has NO `status` field (confirmed: `patient.ts:767–774`). |
| If yes: does any mobile code use `medication.status`? Must keep alias `"status": lifecycle_status` during transition. | **N/A — backend currently has no `status` field on medications response.** When P0 adds `lifecycle_status` to the API response, it is a **new field** (not a rename). No alias is needed for the current state. However, if the mobile app frontend **pre-emptively** reads `status` from the medication response (e.g., expecting it from a mock), that would be an issue. Cannot confirm without mobile source. |
| Will `lifecycle_status: null` or `verification_status: null` crash any mobile component? | **LOW RISK — likely not, but unverifiable.** New columns have `NOT NULL DEFAULT` — values will never be null for existing or new rows after migration. The only null-risk is if a row is returned that somehow bypasses the default (not possible with `NOT NULL DEFAULT`). **Still requires mobile QA sign-off.** |
| Does mobile have a staging build that can be tested against P0 API before production? | **UNKNOWN.** CI/CD deploys backend + frontend to Azure staging (`ci.yml`). No mobile staging build pipeline found in `.github/workflows/`. PTH must confirm. |

---

## Section 4 — Existing Data Migration Mapping

Confirm the correct default values for ALL existing `medications` rows:

| Field | Default for existing rows | Correct? | Exceptions? |
|-------|--------------------------|---------|-------------|
| `lifecycle_status` | `'active'` | **YES** — `list_medications()` currently filters `deleted_at IS NULL` only (no status concept). All live medications are considered active. | **RISK:** Any rows with `deleted_at IS NOT NULL` (soft-deleted) will also get `lifecycle_status='active'` after M-01. This is technically fine (the app always filters by `deleted_at IS NULL`), but audit-conscious: soft-deleted rows showing `lifecycle_status='active'` is semantically odd. Mitigation: `UPDATE medications SET lifecycle_status='discontinued' WHERE deleted_at IS NOT NULL` before adding default, if desired. PTH decision needed. |
| `verification_status` | `'patient_reported'` | **YES** — all pre-P0 entries are patient-entered via `POST /patients/{id}/medications`. No doctor-portal writes exist yet. No OCR medication import pipeline exists. | **PASS — no exceptions found in codebase.** |
| `source_type` | `'patient_manual'` | **YES** — only write path is patient-facing `POST /medications` or PATCH. No `pharmacy_import`, `fhir_import`, or `ocr_confirmed` pipelines exist. | **PASS — no exceptions.** |
| `medication_category` | `'conventional_drug'` | **YES — with caveat.** Since `is_supplement` does NOT exist in the current schema, all rows default to `'conventional_drug'`. There are no supplement rows to reclassify. | **PASS — the `is_supplement → supplement` migration block in M-01b is a no-op and must be skipped.** |

**If any exception rows exist:** The `deleted_at IS NOT NULL` soft-deleted rows receiving `lifecycle_status='active'` is the only edge case. PTH should decide: accept it (app always excludes `deleted_at IS NOT NULL` anyway) or add a targeted `UPDATE medications SET lifecycle_status='discontinued' WHERE deleted_at IS NOT NULL` before M-01.

---

## Section 5 — Rollback Safety

| Question | Answer |
|----------|--------|
| M-01 rollback (DROP COLUMN): safe only before API deployment — confirm rollback window | **RISK.** `DROP COLUMN` in Postgres is safe any time at schema level. However, if API code using `lifecycle_status` has been deployed, rollback must DROP the column AND revert the API deployment atomically. Rolling back M-01 after API deployment that writes `lifecycle_status` will cause 500 errors. Rollback window: M-01 DROP COLUMN is safe ONLY before the new API code is deployed to any environment. |
| M-02 rollback (DROP TABLE medication_audit_log): any FK deps from other tables? | **PASS — safe.** `medication_audit_log` is append-only. It has a FK TO `medications` (ON DELETE CASCADE), not FROM other tables. `DROP TABLE medication_audit_log` is always safe. No other table references it. |
| M-03 rollback (DROP TABLE medication_statements): same | **PASS — safe.** `medication_statements` has FKs to `patient_profiles` and `medications` (both outgoing). No table references `medication_statements`. `DROP TABLE medication_statements` is always safe. |
| M-04 rollback (DROP COLUMN): same window constraint as M-01 | **PASS with same caveat as M-01.** Nullable columns — safe to drop any time before API code uses them. After API deployment references `drug_product_id` or `generic_name`, rollback requires coordinated API revert. |
| Is a full DB snapshot taken automatically before every migration on staging? | **NO — not automated.** The CI/CD pipeline (`ci.yml`) runs `alembic upgrade head` via a Container Apps Job before deploying the backend image. There is NO explicit `pg_dump` or snapshot step before migration in the workflow. Azure Postgres Flexible Server has automated backups (configurable retention), but there is no explicit pre-migration snapshot step in the current pipeline. **RISK: PTH must either add a manual snapshot step or verify Azure PITR (Point-in-Time Restore) is enabled with adequate RPO.** |
| Is a full DB snapshot required before production migration? Who triggers it? | **REQUIRED — not yet automated.** P0 Implementation Plan §10 requires "DB backup confirmed within 1 hour of migration window." Current pipeline does not automate this. PTH or DevOps must manually trigger Azure Postgres backup/snapshot before production migration. |
| Has the rollback script been written and dry-run on a local DB copy? | **NO — not written yet.** This is a pre-implementation task. The `scripts/rollback_internal.sh` is for Docker container rollback (infrastructure), not DB schema rollback. A dedicated `rollback_medication_p0.sql` must be written and tested. |

---

## Section 6 — Service Layer

| Question | Answer |
|----------|--------|
| Where is the `MedicationService` (or equivalent) in the codebase? | **`app/services/medication.py`** — confirmed. Contains `add_medication()`, `update_medication()`, `list_medications()`, `delete_medication()`, `log_adherence()`, `get_adherence()`, `adherence_summary()`. Pure service functions; no HTTP concerns. |
| Is there currently any RBAC check on `medications` writes? Where? | **YES — at route layer, not service layer.** `routes/patients.py:_check_write_access()` (line ~80) blocks `AI_SERVICE` and `CLINIC_ADMIN`. DOCTOR is allowed for writes but blocked from DELETE (`routes/patients.py:591`). PATIENT is ownership-gated. **RISK: The service layer itself has NO RBAC checks** — it trusts callers. For P0 `lifecycle_status` RBAC (patient vs doctor vs system), the enforcement must be added in the service layer or as a new pre-call validation in the route. The existing pattern puts RBAC in routes. |
| Is there a transaction wrapper already available for multi-table atomic writes? | **PARTIAL.** SQLAlchemy session (`db`) is used directly with `db.add()` / `db.commit()`. The P0 plan requires BEGIN/COMMIT transactions spanning `medications` + `medication_audit_log`. The current `add_medication()` is a single-table commit (`db.commit()` after `db.add(record)`). **No existing multi-table transaction helper exists.** P0 must implement explicit transaction blocks: `db.begin()` (implicit in SQLAlchemy 2.x with `autocommit=False`) + multi-step operations + single `db.commit()`. The session is configured with `autocommit=False` (`database.py:SessionLocal`) which enables this pattern natively. |
| Is there an existing background job runner for the `expired` detection job? | **YES — minimal infrastructure.** `app/jobs/maintenance.py` is the existing cron-friendly job (audit retention + token cleanup). It uses `python -m app.jobs.maintenance` pattern (direct Python module invocation). No Celery/APScheduler/RQ/Beat found anywhere in the codebase. **RISK: No scheduler framework.** The `expired` detection job must be invoked externally (cron, Azure Container Apps scheduled job, or Azure Function). The maintenance job pattern is the only precedent. |
| Where should the expired detection cron be registered? | **Azure Container Apps scheduled job** — consistent with the existing `caj-metocare-migrate` job pattern in `ci.yml:313`. Add a new `caj-metocare-expired-job` as a scheduled Container Apps Job (daily UTC 00:00). Alternatively, add to `app/jobs/maintenance.py` and extend the existing maintenance cron. **PTH decision needed on scheduling mechanism.** |
| Is `POST /medications/{id}/report-non-adherence` a new endpoint or does a similar one exist? | **NEW ENDPOINT — does not exist.** Current adherence system uses `POST /patients/{id}/medications/{med_id}/adherence` (log taken/skipped dose). There is no `report-non-adherence` endpoint. The new endpoint in P0 plan writes to `medication_audit_log` only (no `medication_adherence` table write). These are distinct operations and must be added as a new route. |

---

## Section 7 — Test Infrastructure

| Question | Answer |
|----------|--------|
| Is there an existing test DB / test migration runner? | **YES — SQLite in-memory.** `tests/conftest.py:6-7` sets `MCP_DATABASE_URL=sqlite:///...` and calls `create_all()` (not Alembic). Tests run against SQLite, not Postgres. **RISK: JSONB columns in M-02 (`before_snapshot`, `after_snapshot`, `event_data`) and M-03 (`payload_snapshot`) are PostgreSQL-specific.** SQLAlchemy renders JSONB as TEXT on SQLite — functional for storage/retrieval but JSONB operators won't work in unit tests. **P0 tests that verify JSONB snapshot content will pass on SQLite (stored as TEXT), but tests that use Postgres JSONB operators (e.g., `@>`, `->>`) must run against a real Postgres instance.** CI uses SQLite (confirmed `ci.yml:78`). |
| Can test gates T-01 to T-07 (from P0 Plan) be run in CI? | **PARTIAL.** T-01 (migration correctness), T-02 (new write), T-03 (lifecycle state machine), T-04 (audit capture), T-05 (non-adherence + expired re-review), T-06 (API backward compatibility) can all run in SQLite-backed CI. **RISK for T-07 (expired detection job):** Job trigger mechanism is external; CI does not run scheduled jobs. T-07 can be tested as a unit test calling the job function directly (same pattern as `run_maintenance()` in `maintenance.py`). |
| Is there a staging environment where migrations can be validated before production? | **YES.** Azure Container Apps staging (`cae-metocare-staging`) with Azure Postgres Flexible Server (`psql-metocare-staging`). CI pipeline deploys to staging on every merge to `main` via `alembic upgrade head`. Migrations can be manually validated on staging before promoting to production. |
| Who on the team owns mobile QA sign-off (Gate T-06)? | **UNKNOWN — not determinable from codebase.** No mobile team member identified in docs, AGENTS.md, or code. PTH must identify the mobile QA owner. |

---

## Sign-off

Tech Lead confirms:
- [x] All Section 1–7 questions answered
- [ ] No blocking issues found (or issues documented with mitigation) — **SEE SUMMARY: 3 items require PTH decision**
- [ ] Rollback script written and tested on local DB — **NOT YET WRITTEN**
- [ ] Mobile team notified of upcoming API changes — **PENDING**
- [ ] PTH notified of any deviations from P0 Implementation Plan — **SEE SUMMARY**

**Completed by:** OpenClaw Subagent (codebase inspection)  
**Date:** 2026-07-11  
**Reviewed by PTH:** _______________

---

## Architecture Rules (PTH instruction, 2026-07-11)

1. Architecture is frozen at tag `medication-architecture-v1.0`.
2. ADRs (ADR-01 to ADR-12) are immutable from this point.
3. If implementation reveals an ADR is wrong or incomplete: create a new ADR (ADR-13+) that supersedes the relevant section. Do not edit the original.
4. Code must follow ADR. ADR is not edited to match code.
5. Every superseding ADR requires PTH approval before implementation.

---

## Summary (Appended by Inspector)

### Overall: CONDITIONAL PASS

All schema migrations are safe to proceed. No hard blockers from the codebase itself. Three items require PTH decision before the first migration is run.

---

### Blocking Issues

None. No schema conflicts, no name collisions, no FK cycles.

---

### Risk Flags Requiring PTH Decision

**RISK-1 — JSONB in CI tests uses SQLite (no real JSONB)**
- **File:** `tests/conftest.py:6` + `ci.yml:78`
- **Impact:** `medication_audit_log.before_snapshot`, `after_snapshot`, `event_data` and `medication_statements.payload_snapshot` are JSONB in Postgres but TEXT in SQLite tests. Tests T-01 through T-06 can pass on SQLite for basic CRUD. Any test using Postgres JSONB operators will only work against real Postgres.
- **Decision needed:** Should P0 test gates run against a real Postgres instance in CI (add `services: postgres:` to `ci.yml`), or are SQLite tests sufficient for T-01–T-07? Recommended: add Postgres service to CI for migration tests, keep SQLite for unit tests.

**RISK-2 — AI context builder `_build_medications()` does not filter by `lifecycle_status`**
- **File:** `app/ai/context/builder.py:_build_medications()` (raw SQL with no status filter)
- **Impact:** After P0, `expired`, `discontinued`, and `entered_in_error` medications will continue to appear in the AI context (the query only filters `deleted_at IS NULL`). This is a functional regression in AI quality.
- **Decision needed:** P0 API scope says "expose new fields in response." Should updating the AI context query filter (to exclude non-active lifecycle_status) be part of P0 or deferred to P1? Recommended: include in P0 service layer changes as a low-risk query fix.

**RISK-3 — Soft-deleted rows will get `lifecycle_status='active'` after M-01**
- **Files:** `t4_m9_add_sdel` (adds `deleted_at`) + M-01 NOT NULL DEFAULT
- **Impact:** Rows with `deleted_at IS NOT NULL` (soft-deleted medications) will receive `lifecycle_status='active'` via the NOT NULL DEFAULT. These rows are already excluded from all list queries (`deleted_at IS NULL` filter), so there is no user-visible impact. However, it is semantically incorrect.
- **Decision needed:** Add `UPDATE medications SET lifecycle_status='discontinued' WHERE deleted_at IS NOT NULL` as a targeted pre-step in M-01, or accept the inconsistency (app behavior is unaffected). Low urgency but noted for audit correctness.

**RISK-4 — Pre-migration DB snapshot not automated**
- **File:** `.github/workflows/ci.yml` — no snapshot step before `alembic upgrade head`
- **Impact:** If staging migration fails midway, recovery relies on Azure PITR (not a guaranteed instant snapshot). Production migration has no automated snapshot gate.
- **Decision needed:** Add explicit `az postgres flexible-server backup create` step to `ci.yml` before the Alembic migration job, and confirm PITR retention policy on production DB. PTH or DevOps must own this.

**RISK-5 — Mobile app source not in repo — JSON graceful degradation unverifiable**
- **Impact:** Cannot confirm mobile app handles unknown JSON fields. `MedicationCard` in design-system has a `status` field in its component interface (design mock, not API-wired), but the actual mobile app (React Native or Flutter) is not in the repository.
- **Decision needed:** PTH must direct mobile team to confirm: (a) JSON parser ignores unknown fields; (b) no hardcoded expectation of a `status` field on medication API response; (c) staging build available for Gate T-06 sign-off.

**RISK-6 — No background job scheduler framework**
- **Impact:** `expired` detection job has no infrastructure to run on. No Celery/APScheduler/RQ. Only pattern is manual `python -m app.jobs.<module>` (see `maintenance.py`).
- **Decision needed:** How should the daily expired-detection cron be scheduled? Options: (A) Azure Container Apps Scheduled Job (consistent with migrate job), (B) extend `maintenance.py` and re-use existing cron, (C) Azure Function Timer. Must be decided before P0 service layer implementation begins.

---

### Minor Notes (No PTH Decision Required)

- **M-01 index CONCURRENTLY:** The P0 migration SQL uses plain `CREATE INDEX`. For production Postgres with live data, recommend changing to `CREATE INDEX CONCURRENTLY` in M-02 and M-03 to avoid brief lock during index builds. This is a migration script detail, not an architecture decision.
- **Doctor portal + AI context lifecycle filter:** After M-01, both should be updated to add `lifecycle_status NOT IN ('expired', 'discontinued', 'entered_in_error')` to their medication queries. Low-risk change, should be in P0 scope.
- **`is_supplement` migration block:** The M-01b block `UPDATE medications SET medication_category='supplement' WHERE is_supplement=TRUE; ALTER TABLE medications DROP COLUMN is_supplement` is **a no-op** — `is_supplement` does not exist. This block must be removed or wrapped in a conditional check to avoid migration failure.

---

### Recommended Next Step

1. **PTH reviews this document** and decides RISK-1 through RISK-6 above.
2. **Write rollback script** (`rollback_medication_p0.sql`) and dry-run on local Postgres (not SQLite).
3. **Remove the `is_supplement` block** from M-01b — column does not exist, migration will error if left as-is.
4. **Contact mobile team** for Gate T-06 pre-alignment before any API changes are deployed.
5. **Decide on scheduler mechanism** (RISK-6) before writing service layer code.
6. **Add Postgres CI service** (or confirm SQLite is sufficient for T-01–T-07).
7. Once PTH approves, proceed to write and test M-01 → M-01b → M-02 → M-03 → M-04 on local Postgres, then staging.

---

## PTH Decisions on Risk Flags (2026-07-11)

**Verdict:** CONDITIONAL PASS — implementation coding may begin. Migration staging blocked until three technical blockers are resolved.

### RISK-1 — JSONB / SQLite CI → **BLOCKS migration staging**

**Decision:** SQLite is not sufficient evidence for migration compatibility. Required:
- Add PostgreSQL integration test for P0 migrations (upgrade from current schema to head)
- Run downgrade within rollback scope
- Test insert/read/update on all JSONB columns (`before_snapshot`, `after_snapshot`, `event_data`, `payload_snapshot`)
- CI SQLite tests may remain for unit tests (speed), but CANNOT be the pass criteria for migration gates

### RISK-2 — AI context builder does not filter lifecycle_status → **Fix required in P0 (does not block migration)**

**Decision:** Must fix `_build_medications()` in P0 scope alongside migrations.

Allowlist for AI current-medication context:
- `active` — always include (currently taking)
- `on_hold` — include; output MUST label clearly as clinician-suspended (model must not interpret as currently active)
- `paused` — include for P0 allowlist; output MUST carry `lifecycle_status` field so model does not interpret as currently taking; default to include for history/adherence/reconciliation queries only if context-aware routing is added at P1
- `completed`, `discontinued`, `expired`, `entered_in_error` — always exclude from current context

Implementation: `WHERE lifecycle_status IN ('active', 'on_hold', 'paused')`. Use allowlist, not blocklist.

**Output rule:** `_build_medications()` MUST include `lifecycle_status` in the returned payload (not just `name, dose, frequency`). The consuming model must receive the status to correctly interpret `on_hold` and `paused` records — never silently present them as active medications.

### RISK-3 — Soft-deleted rows → **Fix mapping before migration**

**Decision:** Do NOT backfill all soft-deleted rows as `active`. Correct mapping:

```
deleted_at IS NULL     → lifecycle_status = 'active'
deleted_at IS NOT NULL → lifecycle_status = 'entered_in_error'
```

**Prerequisite before running M-01:** Tech Lead must audit soft-deleted medication data:
- Total medication count
- Count of soft-deleted rows
- Who created/deleted them and when
- Whether any audit/reason data exists
- Whether soft-delete was used to represent clinical discontinuation (not just data entry error)

If insufficient data to classify: retain deleted state, do not force-classify. Do not include soft-deleted rows in Current Medication List regardless.

The M-01 migration must include:
```sql
UPDATE medications SET lifecycle_status = 'entered_in_error' WHERE deleted_at IS NOT NULL;
-- (run before the NOT NULL DEFAULT takes effect, or as separate targeted UPDATE)
```

### RISK-4 — No automated DB snapshot → **BLOCKS migration staging and production**

**Decision:** Pre-migration snapshot workflow is mandatory. Minimum requirements:
- Backup runs before migration
- Backup name contains: environment + timestamp + pre-migration commit SHA
- If backup command fails, migration does not run
- Log/artifact reference saved
- Restore rehearsal on staging or temporary DB

**Azure PostgreSQL Flexible Server — async backup (PTH, 2026-07-11):**
`az postgres flexible-server backup create` is asynchronous. Exit code 0 = request accepted, NOT backup completed. Pipeline must:
1. Trigger backup
2. Poll operation status until state = `Succeeded` (timeout → fail closed)
3. Only then run `alembic upgrade head`
4. Save backup name/restore-point as CI artifact

Do NOT treat exit code 0 as evidence of a valid restore point.

Rollback migration ≠ backup. Both are required independently.

### RISK-5 — Mobile app source not in repo → **Blocks production, does not block backend staging**

**Decision:** Backend staging may proceed with additive contract only. Production blocked until mobile sign-off.

While mobile repo is unlocated, Tech Lead must:
- Identify correct mobile repo/branch/released version
- Check medication response decoder
- Confirm unknown fields do not cause crash
- Run smoke test against P0 staging backend

Backend contract rules (mandatory, not assumed):
- No existing fields deleted or renamed
- New fields: nullable or safe default
- No existing enum values changed in a breaking way
- API contract test added using current mobile payload shape

Mobile compatibility cannot be declared on the assumption that "JSON typically ignores unknown fields." Evidence from the actual client is required.

### RISK-6 — No scheduler framework → **Does not block M-01 to M-05 if cron not required for P0**

**Decision:** Do not build a scheduler just to complete foundation.

Separation of concerns:
- Lifecycle transitions triggered by API/domain service: implement in P0
- Automatic expiry / background reconciliation: defer
- If a background job is truly required, use existing workflow/job runner with idempotency and lock
- Choose scheduler framework via new ADR when actually needed

Do not embed temporary cron into `app.main`.

---

## M-01b Fix — Mandatory Before Any Migration Runs

The `is_supplement` column does NOT exist in the current schema. The following block in M-01b will **fail** if left as-is:

```sql
-- THIS BLOCK MUST BE REMOVED:
UPDATE medications SET medication_category = 'supplement' WHERE is_supplement = TRUE;
ALTER TABLE medications DROP COLUMN is_supplement;
```

**Rule:** Migrations must be based on the actual confirmed schema, not assumptions from prior documentation. Remove this block entirely. Do not replace with conditional SQL unless multiple production baselines are confirmed.

---

## Staging Migration Gate — Conditions to Proceed

Migration staging may only run when ALL of the following are complete:

- [ ] **M-01b `is_supplement` block removed** from migration script
- [ ] **PostgreSQL integration test** for P0 migrations passes (upgrade + rollback on real Postgres)
- [ ] **Soft-deleted row audit** complete; `entered_in_error` mapping confirmed or exception documented with PTH approval
- [ ] **Pre-migration snapshot workflow** implemented and verified in staging pipeline
- [ ] **Migration dry-run** on staging schema/data copy passes
- [ ] **API contract remains additive** — no existing field removed or renamed
- [ ] **AI context lifecycle filter** (`_build_medications()`) included in same P0 PR stack

---

## Production Gate (Additional, After Staging)

- [ ] Mobile team confirms compatibility (repo identified, decoder verified, smoke test passed)
- [ ] All 7 Test Gates (T-01 to T-07) pass on PostgreSQL
- [ ] Architecture Compliance Review completed for all P0 PRs
- [ ] EC-01 to EC-08 (Exit Criteria) all pass
- [ ] PTH signs declaration: "Medication Architecture v1.0 — Successfully Implemented"

---

**PTH sign-off:** PTH  
**Date:** 2026-07-11  
**Status:** CONDITIONAL PASS — coding permitted, staging blocked pending three technical blockers
