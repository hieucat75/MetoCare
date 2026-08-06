# Operational record — emergency staging PostgreSQL credential rotation

**Date/time of rotation:** 2026-07-27, 01:11–01:14 UTC
**Status:** completed
**Trigger:** staging PostgreSQL credential exposed in prior tool output (infra-security response, not application defect)
**Operator:** phamtrung.hieu@outlook.com (Azure AD user), executed via Claude Code CLI at PTH's explicit request

## Resources affected (all staging, `rg-metocare-staging`)

- PostgreSQL Flexible Server: `psql-metocare-staging` (admin login `metoadmin`) — password rotated
- Key Vault: `kv-metocare-stgd9e7`, secret `mcp-database-url` — new version created
- Container App: `ca-metocare-backend`, secret alias `db-url` — updated, new revision deployed
- Container Apps Job: `caj-metocare-migrate`, secret alias `db-url` — updated
- Container Apps Job: `caj-metocare-seed-demo`, secret alias `db-url` — updated (discovered during consumer audit, not in original resource list)
- Container Apps Job: `caj-seed-doctor`, secret alias `db-url` — updated (discovered during consumer audit, not in original resource list)

`ca-metocare-frontend` was checked and holds no database secret — no action needed.
CI/CD workflows (`azure-staging.yml`, `ci.yml`) read `mcp-database-url` live from Key Vault at deploy time; they hold no separate copy and needed no change.

## Sequence performed

1. Identified live admin login (`metoadmin`) and all consumers of the `db-url`/`mcp-database-url` secret via read-only Azure CLI queries, expanding the original scope to include two additional jobs found to hold the same secret alias.
2. Generated a new 32-character password (mixed-case + digits + URL-safe symbols) in-process only — never written to disk.
3. Rotated the server's admin password via a direct ARM REST `PATCH`, with the request body piped over stdin (no CLI argument, no temp file).
4. Confirmed the old credential was immediately invalid by triggering a `caj-metocare-migrate` execution while it still held the old secret — that execution **failed**, as expected.
5. Published a new version of Key Vault secret `mcp-database-url` via direct REST `PUT` (stdin body).
6. Updated `ca-metocare-backend`'s `db-url` secret and deployed a new revision (`ca-metocare-backend--rot20260727081236`) so the running app picked up the new credential.
7. Updated the `db-url` secret on all three affected jobs (`caj-metocare-migrate`, `caj-metocare-seed-demo`, `caj-seed-doctor`).
8. Confirmed the new credential works by re-triggering `caj-metocare-migrate` — that execution **succeeded**.
9. Confirmed the new backend revision is active and healthy, and that its DB-aware health endpoint (`/api/v1/health`) returns `200`.

Transition window between invalidating the old password and updating all consumers: **≈2 minutes** (01:12:18–01:13:57 UTC). No consumer was left holding the old credential at the end of the run.

## Confirmations

- Old credential invalidated: confirmed (pre-update job execution failed immediately after rotation).
- Backend and migration job use the new credential: confirmed (new revision healthy; post-update job execution succeeded).
- `caj-metocare-seed-demo` and `caj-seed-doctor` also updated to the new credential (same secret alias, discovered during the consumer audit).
- No production resource was touched: all operations were scoped to `rg-metocare-staging`; `rg-metocare-prod` / `psql-metocare-prod` were only read (state check), never written.
- `MEDICATION_KNOWLEDGE_RETRIEVAL` flag: unchanged (not present as a container-level override; this task did not touch application configuration).
- No secret value was printed, logged, or persisted to a file at any point in this operation. All secret material lived only in the memory of a single, short-lived shell process and was explicitly unset at the end of that process. No credential fragments were found in shell history after the run.
- Existing staging data and schema: unchanged — `alembic upgrade head` ran twice as a connectivity probe (idempotent no-op both times since the schema was already at head); no migration was applied.

No PHI, connection strings, or credential fragments are recorded in this document.
