# Medication Soft-Delete Audit

**Date:** 2026-07-11  
**Author:** OpenClaw subagent — P0 blocker close task  
**Branch:** chore/next15-react19  
**DB:** Local dev PostgreSQL (Docker timescale/timescaledb-ha:pg16, host=localhost:5432, user=mcp, db=mcp)  
**Connection method:** `PGPASSWORD='mcp_dev_only' psql -U mcp -h localhost -d mcp`

---

## Query 1 — Count Summary

```sql
SELECT 
  COUNT(*) FILTER (WHERE deleted_at IS NULL)     AS live_count,
  COUNT(*) FILTER (WHERE deleted_at IS NOT NULL) AS soft_deleted_count,
  COUNT(*)                                        AS total
FROM medications;
```

### Result

| live_count | soft_deleted_count | total |
|------------|-------------------|-------|
| 0          | 0                 | 0     |

---

## Query 2 — Detail of Soft-Deleted Rows (max 50)

```sql
SELECT id, patient_id, name, dose, note, created_at, deleted_at, deleted_by
FROM medications
WHERE deleted_at IS NOT NULL
ORDER BY deleted_at DESC
LIMIT 50;
```

### Result

*(0 rows)*  
No soft-deleted medication rows exist in this environment.

---

## Schema Verification

```sql
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'medications' 
ORDER BY ordinal_position;
```

### Result (current columns on medications table)

| column_name | data_type                   |
|-------------|----------------------------|
| patient_id  | character varying           |
| name        | character varying           |
| dose        | character varying           |
| note        | text                        |
| id          | character varying           |
| created_at  | timestamp with time zone    |
| updated_at  | timestamp with time zone    |
| deleted_at  | timestamp with time zone    |
| deleted_by  | character varying           |

> Note: `frequency` column added by `pr_d_add_medication_frequency` migration is also present on the ORM
> model but may not yet be in this local DB if that migration has not been run. Irrelevant for P0 M-01.

---

## Key Findings

### 1. `is_supplement` column — CONFIRMED ABSENT
The `is_supplement` boolean column does **NOT** exist in the `medications` table.  
Confirmed via `information_schema.columns` query above.  
**Action:** The `is_supplement` migration block must be removed from M-01 (as required by task spec and PTH decision in MEDICATION_P0_PRE_VALIDATION.md).

### 2. Soft-deleted row count — 0 in local dev DB
This is the local development database (Docker Compose). Row count = 0 because this is a development environment with no seeded data.

**Staging/Production note:** The staging DB (Azure PostgreSQL Flexible Server, psql-metocare-staging) could NOT be queried from this context. PTH must verify the soft-delete count against staging/prod before running M-01 there. The migration is written to be safe regardless of count.

### 3. Soft-delete mapping decision (PTH, 2026-07-11)
Per MEDICATION_P0_PRE_VALIDATION.md — PTH decision:

```
deleted_at IS NULL     → lifecycle_status = 'active'   (via NOT NULL DEFAULT)
deleted_at IS NOT NULL → lifecycle_status = 'entered_in_error'   (explicit UPDATE in M-01)
```

Rationale: Soft-deleted rows are semantically invalid/erroneous records that should never reappear in any query. `entered_in_error` is the correct FHIR-aligned status for records that should be treated as if they never existed.

The migration M-01 implements this with:
```sql
UPDATE medications SET lifecycle_status = 'entered_in_error' WHERE deleted_at IS NOT NULL;
```
This UPDATE runs **after** `ADD COLUMN ... NOT NULL DEFAULT 'active'` so:
1. All rows get `'active'` via the default (Postgres catalog default — zero row scan)
2. Only soft-deleted rows are then corrected to `'entered_in_error'` (targeted UPDATE)
3. Final state: live rows = `'active'`, soft-deleted rows = `'entered_in_error'`

---

## Staging DB Query (Required Before Running M-01 on Staging)

PTH must run the following against the staging PostgreSQL before executing the migration:

```sql
-- Connect to psql-metocare-staging (Azure Flexible Server)
SELECT 
  COUNT(*) FILTER (WHERE deleted_at IS NULL)     AS live_count,
  COUNT(*) FILTER (WHERE deleted_at IS NOT NULL) AS soft_deleted_count,
  COUNT(*)                                        AS total
FROM medications;

-- If soft_deleted_count > 0, inspect the rows:
SELECT id, patient_id, name, created_at, deleted_at, deleted_by
FROM medications
WHERE deleted_at IS NOT NULL
ORDER BY deleted_at DESC
LIMIT 50;
```

If soft_deleted_count > 0 on staging, the `UPDATE medications SET lifecycle_status = 'entered_in_error' WHERE deleted_at IS NOT NULL` in M-01 will correct those rows. No further action needed — the migration handles it.

---

## Conclusion

| Check | Result |
|-------|--------|
| `is_supplement` column exists | ❌ NO — migration block must be removed |
| P0 new columns already exist | ❌ NO — all 5 columns (`lifecycle_status`, `verification_status`, `source_type`, `medication_category`, `status_reason`) are absent — safe to add |
| Soft-deleted rows in local dev DB | 0 rows |
| Soft-deleted rows in staging DB | UNKNOWN — PTH must query before running migration |
| Migration safe to write | ✅ YES |
| `is_supplement` block needed | ❌ NO — removed from migration |
| Soft-delete mapping implementation | ✅ `entered_in_error` via targeted UPDATE after ADD COLUMN |
