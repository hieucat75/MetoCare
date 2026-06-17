# T4 Postgres Integration Verification Report

**Date:** 2026-06-17 19:15 GMT+7  
**Branch:** `integration/t4-medical-domain`  
**Postgres:** PostgreSQL 17.10 (Homebrew) — native, no Docker/Colima  
**Verifier:** OpenClaw Master Coordinator  
**Status:** ✅ PASSED — APPROVED FOR MERGE

---

## Environment

| Item | Value |
|------|-------|
| PostgreSQL | 17.10 (Homebrew) on aarch64-apple-darwin25.4.0 |
| Python | 3.14.x (venv `/Users/pth/Developer/metocare/.venv`) |
| DB URL | `postgresql+psycopg://mcp:mcp_dev_only@localhost:5432/mcp` |
| TimescaleDB | Not installed (Homebrew dev — expected, see note below) |
| Alembic head | `t4_m9_add_sdel` |

---

## Migration Chain (11 migrations applied, 6 pre-T4 + 11 T4 = 17 total)

```
 -> 2c30ffd33627  initial schema 14 core entities
 -> 85416e7ef0e9  timescaledb hypertable [SKIPPED — no TSDB on Homebrew dev] ⚠️
 -> fad70c6f2d60  encrypt PHI fields
 -> 65849f86200f  refresh tokens and mfa
 -> 8e3134ab9679  refresh token family and audit severity
 -> a1b2c3d4e5f6  lab document pipeline status
 -> t4_m0_role   add ai_service to users.role CHECK constraint
 -> t4_m1_ren_conv rename ai_conversations to ai_sessions
 -> t4_m2_ext_sess extend ai session fields
 -> t4_m3_add_recs add ai_clinical_recommendations
 -> t4_m4_add_encs add encounters table
 -> t4_m4b_enc_fk  add encounter FKs (ai_sessions + ai_clinical_recs)
 -> t4_m5_add_cpln add care_plans table
 -> t4_m6_add_bksp add booking_health_snapshots
 -> t4_m7_add_junc add doctor_clinic junction
 -> t4_m8_ext_drcl extend doctor_clinic fields
 -> t4_m9_add_sdel add soft-delete columns to all T4 tables
```

**`alembic upgrade head` exit code: 0** ✅  
**`alembic downgrade base` exit code: 0** ✅

---

## Schema Verification

### Tables (22 total = 21 data + alembic_version)

```
ai_clinical_recommendations, ai_sessions, alembic_version,
appointments, audit_logs, booking_health_snapshots, care_plans,
clinics, consents, doctor_clinic, doctors, encounters,
health_metrics, lab_documents, lab_results, medications,
mfa_backup_codes, patient_profiles, refresh_tokens, risk_scores,
symptom_logs, users
```

✅ **21 data tables** (expected 21)

### FK Constraints — T4 Entities

| Table | Constraint | References |
|-------|-----------|-----------|
| ai_sessions | fk_ai_sessions_encounter_id | encounters |
| ai_sessions | fk_ai_sessions_deleted_by | users |
| ai_clinical_recommendations | fk_clinical_recs_encounter_id | encounters |
| ai_clinical_recommendations | fk_clinical_recs_session_id | ai_sessions |
| ai_clinical_recommendations | fk_clinical_recs_patient_id | patient_profiles |
| ai_clinical_recommendations | fk_clinical_recs_reviewed_by_doctor_id | doctors |
| ai_clinical_recommendations | fk_clinical_recs_deleted_by | users |
| care_plans | fk_care_plans_encounter_id | encounters |
| care_plans | fk_care_plans_patient_id | patient_profiles |
| care_plans | fk_care_plans_approved_by_doctor_id | doctors |
| care_plans | fk_care_plans_deleted_by | users |
| encounters | fk_encounters_patient_id | patient_profiles |
| encounters | fk_encounters_doctor_id | doctors |
| encounters | fk_encounters_appointment_id | appointments |
| encounters | fk_encounters_deleted_by | users |
| doctor_clinic | fk_doctor_clinic_doctor_id | doctors |
| doctor_clinic | fk_doctor_clinic_clinic_id | clinics |

✅ **All 8+ FK constraints present** (C5-BIS verified)

### UserRole CHECK Constraint

```sql
((role)::text = ANY ((ARRAY['PATIENT', 'DOCTOR', 'CLINIC_ADMIN', 
  'INTERNAL_ADMIN', 'MEDICAL_REVIEWER', 'SUPER_ADMIN', 'AI_SERVICE'])::text[]))
```

✅ **`AI_SERVICE` included in role CHECK** (M0 applied correctly)

### doctor_clinic Table

```
Column        | Type    | Default
doctor_id     | varchar | NOT NULL
clinic_id     | varchar | NOT NULL
role_at_clinic| varchar | nullable
is_primary    | boolean | false (NOT NULL)
is_active     | boolean | true (NOT NULL)
joined_at     | date    | CURRENT_DATE (NOT NULL)
left_at       | date    | nullable
```

✅ Junction table created, Boolean defaults correct

### Soft-Delete Columns

Tables with `deleted_at`:
- ai_clinical_recommendations ✅
- ai_sessions ✅
- care_plans ✅
- encounters ✅
- lab_results (pre-T4) ✅
- medications (pre-T4) ✅

---

## Test Suite Results

```
177 passed, 1 skipped, 1 warning in 5.02s
```

✅ **177 passed** — identical to SQLite baseline (no regressions)  
✅ **Ruff clean** — 0 violations

---

## Fixes Applied During Verification

Three categories of bugs found and fixed (all were SQLite-invisible, Postgres-strict):

### Fix 1: TimescaleDB graceful skip (M1)

`85416e7ef0e9` now checks `pg_available_extensions` before attempting `CREATE EXTENSION timescaledb`.  
On Homebrew Postgres (no TSDB): emits `RuntimeWarning` and returns gracefully — `health_metrics` becomes a plain table.  
On TimescaleDB Cloud / production: runs full hypertable + CAGG + compression setup.

**Impact:** Zero. The T4 medical domain models (Encounter, CarePlan, AISession, AIClinicalRecommendation) do not depend on TimescaleDB.

### Fix 2: Boolean server_default `'0'`/`'1'` → `'false'`/`'true'` (M2, M3, M5, M7, M8)

PostgreSQL rejects `BOOLEAN DEFAULT 0` / `BOOLEAN DEFAULT 1` (requires `false`/`true`).  
SQLite silently accepted integer literals. Fixed in:

- `t4_m2_ext_sess`: `input_blocked`, `output_blocked`
- `t4_m3_add_recs`: `safety_cleared`
- `t4_m5_add_cpln`: `ai_generated`
- `t4_m7_add_junc`: `is_primary` (was `'0'`), `is_active` (was `'1'`)
- `t4_m8_ext_drcl`: `is_verified` (×2, was `'0'`), `is_active` (×2, was `'1'`)

**Impact:** Correctness fix. All Boolean column defaults now set to proper `false`/`true`.

### Fix 3: Colima skip in verify script

`verify_postgres_t4.sh` now accepts `SKIP_COLIMA_CHECK=1` to proceed with native Homebrew Postgres.

---

## Notes

### TimescaleDB on Production

When deploying to a TimescaleDB-enabled instance (self-managed or TimescaleDB Cloud):
- M1 will run the full hypertable + CAGG path automatically
- No code change needed — the `_timescaledb_available()` check handles both cases

### consents.ai_use

`ai_use` is a **consent_type value** (string), not a column. The `ConsentGuard` service checks `consent_type == "ai_use"` at query time. No schema constraint required — consistent with blueprint.

---

## Final Recommendation

| Gate | Status |
|------|--------|
| alembic upgrade head on Postgres | ✅ PASS |
| alembic downgrade base on Postgres | ✅ PASS |
| 21 tables created | ✅ PASS |
| FK constraints (M4b verified) | ✅ PASS |
| UserRole CHECK includes AI_SERVICE | ✅ PASS |
| Boolean defaults correct | ✅ PASS |
| Soft-delete columns present | ✅ PASS |
| 177 tests passed | ✅ PASS |
| Ruff clean | ✅ PASS |
| TimescaleDB graceful skip | ✅ PASS (warned, not failed) |

## ✅ APPROVED FOR MERGE: `integration/t4-medical-domain` → `main`

All mandatory Postgres verification gates passed.  
Merge requires **PTH explicit approval** per governance policy.

*Verified by: OpenClaw Master Coordinator*  
*Commit this report + migration fixes, then await PTH merge approval.*
