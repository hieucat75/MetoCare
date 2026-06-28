# Azure Container Apps — Staging Deployment Report

**Status:** 🟢 **LIVE**
**Date:** 2026-06-20
**Environment:** SECONDARY STAGING (Azure Container Apps)
**Region:** Southeast Asia (Singapore)
**Resource Group:** `rg-metocare-staging`

---

## 1. Architecture roles (LOCKED)

| Platform | Role | Status | Deploy |
|---|---|---|---|
| **DigitalOcean VPS** | ~~PRIMARY PRODUCTION~~ **[LEGACY]** | Deprecated 2026-06-28 | `deploy-do.yml` (archive only) |
| **Azure Container Apps** | **SECONDARY STAGING** | **Live** | `azure-staging.yml` (`workflow_dispatch`) |
| ~~Azure App Service~~ | Deprecated | Archived | `.github/workflows/_archived/main_metocare.yml.archived` |

**Hard rules:**
- ❌ **Do NOT merge the two approaches.** DigitalOcean (Docker Compose + self-managed PostgreSQL/TimescaleDB on a VPS) and Azure ACA (managed PG Flexible + serverless containers) are independent stacks with independent migration behavior. Keep them separate.
- ❌ **Do NOT continue / reactivate the App Service path.** Azure staging is Container Apps only.
- ✅ DigitalOcean VPS is **[LEGACY — DEPRECATED 2026-06-28]**. Azure ACA is now the sole active deployment target.

---

## 2. Live URLs

- **Backend:** `https://ca-metocare-backend.wittyflower-55a3afa4.southeastasia.azurecontainerapps.io`
- **Frontend:** `https://ca-metocare-frontend.wittyflower-55a3afa4.southeastasia.azurecontainerapps.io`

---

## 3. Security — OIDC only, no long-lived secrets

Auth from GitHub Actions to Azure uses **OIDC federated identity** exclusively. No client secrets, no service-principal passwords stored anywhere.

App Registration: `4989751d-0044-4c84-9b75-c1b705928507`

**Two federated credentials** (both issuer `https://token.actions.githubusercontent.com`, audience `api://AzureADTokenExchange`):

| Name | Subject | Purpose |
|---|---|---|
| `github-staging-main` | `repo:hieucat75/MetoCare:ref:refs/heads/main` | branch-scoped (provisioning) |
| `github-env-azure-staging` | `repo:hieucat75/MetoCare:environment:azure-staging` | **environment-scoped** — required because the deploy job runs in the `azure-staging` GitHub environment |

GitHub secrets used: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` (identifiers only, not credentials). App secrets (DB URL, secret key, encryption keys, App Insights connection string) live in **Key Vault `kv-metocare-stgd9e7`** and are read at deploy time via the OIDC SP (role: *Key Vault Secrets User*), then injected as ACA secrets.

---

## 4. Resources & cost

| Resource | Config | ~$/month |
|---|---|---|
| ACA backend `ca-metocare-backend` | 0.5 vCPU / 1 GiB, **min 0 / max 1** (scale-to-zero) | ~$0 (within free grant) |
| ACA frontend `ca-metocare-frontend` | 0.25 vCPU / 0.5 GiB, **min 0 / max 1** | ~$0 |
| PG Flexible `psql-metocare-staging` | B1ms Burstable, PG 16, 32 GB | ~$13–15 (dominant) |
| Key Vault / Log Analytics / App Insights | low usage, free tiers | ~$0–1 |
| **Total** | | **~$13–16/month** — under the **$20/month** cap ✅ |

ACA free grant: 180,000 vCPU-seconds + 360,000 GiB-seconds per month; staging traffic with scale-to-zero stays within it.

---

## 5. TimescaleDB on Azure — Apache license limitation

Azure Database for PostgreSQL Flexible Server ships the **Apache-2** build of TimescaleDB, which supports hypertables but **NOT** continuous aggregates (CAGG) or native compression (those are TSL/community features). Calling them raises `functionality not supported under the current "apache" license`.

**Fix — license-aware migration** (`backend/alembic/versions/85416e7ef0e9_*.py`, commit `891276b`):
- `_try_create_timescaledb_extension()` — `CREATE EXTENSION` inside a **SAVEPOINT**; on rejection it `ROLLBACK TO SAVEPOINT` and leaves `health_metrics` a plain table (defense-in-depth, no transaction abort).
- `_timescale_license()` — reads `current_setting('timescaledb.license')`. The hypertable (Apache-licensed) is always created; **CAGG + compression are skipped unless the build reports `timescale` (TSL)**.

Behavior matrix (same migration chain everywhere):

| Backend | Result |
|---|---|
| SQLite / non-Postgres | full no-op |
| **Apache TimescaleDB (Azure PG Flexible)** | **hypertable only — CAGG/compression skipped** |
| TSL TimescaleDB (e.g. DigitalOcean self-managed) | hypertable + CAGG + compression |

Verified: 535 backend tests pass + 1 skip; migration `Succeeded` on Azure Apache build with hypertable created and 0 CAGGs.

---

## 6. Deploy pipeline & infra fixes

Deploy is a single `workflow_dispatch` workflow (`azure-staging.yml`): build+push backend/frontend to GHCR → OIDC Azure login → resume PG if stopped → read Key Vault secrets → **Alembic `upgrade head` as a one-shot ACA Job** (no runtime `create_all`) → deploy backend ACA → deploy frontend ACA → health gate on `/health`.

Reaching LIVE took **3 attempts**, each surfacing one infrastructure gap (no code defects):

| # | RUN ID | Failed step | Root cause | Fix (OIDC-only, free) |
|---|---|---|---|---|
| 1 | 27857491922 | Azure login (OIDC) | Only a `ref:refs/heads/main` federated credential existed; the job runs in environment `azure-staging` → presented subject `…:environment:azure-staging` had no match (`AADSTS700213`) | Added federated credential `github-env-azure-staging` (environment subject) |
| 2 | 27857577796 | Alembic migration | PG firewall allowed only a single home IP; ACA outbound IPs were blocked → `psycopg.errors.ConnectionTimeout` | Added PG firewall rule `AllowAzureServices` (`0.0.0.0`) |
| 3 | **27857823291** | — | — | ✅ **SUCCESS (~6m28s, all 13 steps)** |

Both fixes persist on Azure and are reproduced in any fresh provisioning.

---

## 7. Migration & acceptance

- **Migration job:** ACA Job `caj-metocare-migrate`, execution `qn6x279` → **Succeeded**.
- **Alembic head:** `t27_uq_patient_profile_user_id` (full chain applied, including the TimescaleDB migration `85416e7ef0e9`).

| Check | Result |
|---|---|
| `GET /health` (liveness, no DB) | ✅ 200 `{"status":"ok"}` |
| `GET /api/v1/health` (readiness, `SELECT 1`) | ✅ 200 `{"status":"ok","db":"ok"}` |
| `GET /api/v1/info` | ✅ 200 — `env=staging`, `ai_mode=mock`, `ocr_mode=mock`, `storage_mode=local`, `migration_version=t27_uq_patient_profile_user_id` |
| Frontend `/login`, `/dashboard` | ✅ 200 (`/` → 307 Next.js app-router redirect, by design) |

> Note: the readiness path is **`/api/v1/health`**, not `/api/v1/system/health` — `system.router` is mounted without a prefix under `/api/v1`.

---

## 8. Operational notes

- **PostgreSQL stays running 24/7** (decision: staging must be test-ready; avoids cold-start/resume failures and workflow noise; cost remains under the $20 cap). Azure PG Flexible does not auto-stop. The deploy workflow resumes it automatically if it is ever stopped.
- **ACA apps scale to zero** (min 0) — no idle compute cost.
- **App secrets** are sourced from Key Vault at deploy time; runtime config disables docs (`MCP_ENABLE_DOCS=false`), uses mock AI/OCR, local storage, in-memory rate limiting.
- **Deploy command:** `gh workflow run "Azure Staging Deploy" --ref main`.

---

## 9. References

- Migration (license-aware + SAVEPOINT): commit `891276b`
- Merge commits to main: `427b0aa` (PR #4 migration), `635e685` (PR #6 archive App Service), `0ca04dc` (PR #5 ACA workflow)
- Workflow: `.github/workflows/azure-staging.yml`
- Plan: `docs/agent/AZURE_CONTAINER_APPS_STAGING_PLAN.md`
- Successful deploy run: `27857823291`

> All merges to `main` for this work used `[skip ci]` to avoid auto-triggering DigitalOcean production (`deploy-do.yml` push trigger). A follow-up PR gates `deploy-do.yml` behind an opt-in `[deploy-do]` tag so the workaround is no longer needed.

---

## 10. Post-verification (2026-06-20) — scale-from-zero, frontend build-arg, CORS

A follow-up test package (full pytest + backend smoke + browser-driven frontend flow) surfaced and fixed three issues. The original "LIVE" claim was true only **while warm**; the items below make staging durably reachable and the UI functional.

### 10.1 ImagePullBackOff on scale-from-zero (fixed)
The ACA apps were created with `--registry-password ${{ secrets.GITHUB_TOKEN }}` — an ephemeral token. After scale-to-zero + node recycle, the scale-from-zero re-pull used the expired credential → `Pending:ImagePullBackOff` → backend unreachable after idle.

**Fix:** made the `metocare-backend` + `metocare-frontend` GHCR packages **public** and removed all `--registry-*` flags from the workflow (job + both app creates). ACA now pulls anonymously; there is no credential to expire. Verified: registry config empty, fresh replica (revision restart) serves `/health`, `/api/v1/health`, `/api/v1/info`, `/login` → all 200.

### 10.2 Frontend baked the dev API URL (fixed)
The frontend bundle called `http://172.20.0.100:8000/api/v1` (dev IP) → `ERR_CONNECTION_REFUSED` + Mixed Content; UI login/register broken. Root cause: `NEXT_PUBLIC_*` is **inlined at build time**, `frontend/Dockerfile` carried a dev-IP default, and the workflow passed the value only as a (no-op) runtime env var.

**Fix:** removed the dev default from the Dockerfile (`ARG NEXT_PUBLIC_API_URL=`); the workflow now computes the deterministic backend FQDN (`<app>.<ACA-env-defaultDomain>`) **before** the frontend build and passes `--build-arg NEXT_PUBLIC_API_URL=https://<backend-fqdn>/api/v1`. The build step order was changed: Azure login → Compute FQDNs → builds.

### 10.3 CORS (fixed + persisted)
Backend allowed only `localhost` origins → the frontend origin got a 400 preflight. **Fix:** the workflow now sets `MCP_CORS_ALLOWED_ORIGINS=https://<frontend-fqdn>` on the backend deploy env (create + update paths). Preflight from the frontend origin now returns 200 with `access-control-allow-origin`.

### 10.4 Acceptance after fix (deploy run `27859677885`)
| Check | Result |
|---|---|
| Backend smoke (warm + post-restart cold) | `/health`, `/api/v1/health` (`db:ok`), `/api/v1/info` → 200 |
| Frontend register (UI) | ✅ → `/dashboard`, JWT in `localStorage` |
| Frontend login (UI, incl. fresh post-cold-start) | ✅ → `/dashboard` |
| 9 patient routes (`/dashboard … /settings`) | ✅ 9/9 → 200, no redirect to `/login` |
| Session persist (hard reload `/dashboard`) | ✅ stays authenticated |
| Backend pytest | 535 passed + 1 skipped, 0 fail |

**Minor (app-level, not deployment):** the dashboard widget data calls (`/metrics`, `/lab-documents`, `/care_plans`, `/notifications`, `/medications`, `/metabolic-score`) show `net::ERR_ABORTED` + a couple of 404s for a brand-new patient with no data (React double-fetch cancellation). Auth, routing, and session are unaffected.

**Cost:** unchanged — no new resources; PG B1ms + scale-to-zero ACA, ~$13–16/mo, under the $20 cap. PG kept running 24/7 per decision.

> Defects 10.1–10.3 were pre-existing in the deploy setup, independent of the application code. All fixes are OIDC-only, introduce no long-lived secrets, and do not touch DigitalOcean.
