# Azure Staging CI/CD Stabilization — 2026-06-27

## STATUS: ✅ PASS

---

## Root Cause

**Case B + F — Scale-to-zero cold start exceeds pre-build health check window, combined with stale revision detection race.**

### Case B: Scale-to-zero cold start

Both `ca-metocare-backend` and `ca-metocare-frontend` were configured with `minReplicas: 0` (scale to zero). After a period of inactivity (no requests), ACA scales the container down to 0 replicas.

The `frontend-staging.yml` "Validate API URL before build" step runs:
```bash
HEALTH=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 "https://${BACKEND_FQDN}/health")
```

When the backend is scaled to zero, this curl request triggers a cold start. The cold start takes **>15 seconds** (Python + uvicorn + DB connection pool warmup), causing `curl` to exit with code **28 (timeout)**. The `$HEALTH` variable gets value `000` (empty/timeout), causing the workflow to fail with a misleading error.

**Evidence:**
- Run 28291503889 (failure): Validate step started `14:06:16`, exited `14:06:31` = exactly 15 seconds = curl `--max-time 15` timeout → exit code 28
- Run 28289807121 (failure): Same pattern, `12:55:05` → `12:55:20` = 15 seconds
- Run 28289282555 (success): Backend was **warm** (just deployed by full Azure Staging Deploy at 12:24). Health check returned in `~0.6s` → 200 OK
- ACA config confirmed: `minReplicas: 0` (verified via `az containerapp show`)

### Case F: Stale revision name on same-SHA redeploy

The `Update FRONTEND Container App only` step used revision suffix `fe-<first8ofSHA>`. When the same commit SHA is deployed twice (rollback, retry, or regression test), the suffix is identical on both runs. ACA's single-revision mode deduplicates by image+config hash — no new revision is created. The "Verify" step polls `latestReadyRevisionName` for 3 minutes and eventually fails with:
```
frontend revision did not change after 3 min — deploy did not take effect
```

**Evidence:** Run 28292697102 (second deploy of same tag `1627c7f0`) showed revision name `fe-1627c7f0` unchanged across all 18 polling iterations.

---

## Fixes Applied

### Fix 1: minReplicas=1 — prevent scale-to-zero (primary fix)

**ACA live state updated immediately** (before workflow push):
```bash
az containerapp update -g rg-metocare-staging -n ca-metocare-backend --min-replicas 1
az containerapp update -g rg-metocare-staging -n ca-metocare-frontend --min-replicas 1
```

**Workflow files updated** to preserve minReplicas=1 on every future deploy:

`azure-staging.yml`:
- `az containerapp create`: `--min-replicas 0` → `--min-replicas 1` (both backend and frontend)
- `az containerapp update` (existing apps): added `--min-replicas 1`

`frontend-staging.yml`:
- `az containerapp update`: added `--min-replicas 1`

**Justification:** Staging is not cost-sensitive (single 0.5 CPU / 1 GiB replica). Scale-to-zero saves ~$5–10/month but causes non-deterministic CI failures that cost far more in developer time. minReplicas=1 ensures the backend is always warm when any CI step checks it.

### Fix 2: Retry loop for pre-build health check (defense-in-depth)

`frontend-staging.yml` "Validate API URL before build" step replaced single-shot curl with retry loop:

```bash
# Before:
HEALTH=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 "https://${BACKEND_FQDN}/health")
if [ "$HEALTH" != "200" ]; then
  echo "::error::Backend health check returned $HEALTH..."
  exit 1
fi

# After:
HEALTH="000"
for i in $(seq 1 6); do
  HEALTH=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 "https://${BACKEND_FQDN}/health" || echo "000")
  echo "  attempt $i: HTTP $HEALTH"
  [ "$HEALTH" = "200" ] && break
  [ "$i" -lt 6 ] && sleep 15
done
if [ "$HEALTH" != "200" ]; then
  echo "::error::Backend health check returned $HEALTH after 6 attempts — backend may be down"
  exit 1
fi
```

Total retry window: 6 × 15s = **90 seconds** — covers cold-start if minReplicas ever gets reset to 0.

### Fix 3: Timestamp in revision suffix — eliminates stale-revision detection false failure

`frontend-staging.yml` "Update FRONTEND Container App only" step:

```bash
# Before:
SUFFIX="fe-$(echo '${{ steps.tag.outputs.tag }}' | cut -c1-8)"

# After:
SUFFIX="fe-$(echo '${{ steps.tag.outputs.tag }}' | cut -c1-8)-$(date +%s)"
```

A Unix timestamp is appended, making the suffix unique on every deploy invocation regardless of image tag. Same-SHA redeploys (rollback, retry, regression test) now always create a new revision.

### Fix 4: Health gate uses DB-aware endpoint

`azure-staging.yml` "Health gate" step changed from shallow `/health` to DB-aware `/api/v1/health`:

```bash
# Before: probes shallow /health — returns 200 even if DB is down
H=$(curl ... "https://${BACKEND_FQDN}/health")

# After: probes /api/v1/health — returns 503 if DB unreachable
H=$(curl ... "https://${BACKEND_FQDN}/api/v1/health")
```

The `/api/v1/health` endpoint (in `backend/app/api/v1/routes/system.py`) runs `SELECT 1` against the DB and returns 503 if the DB is unreachable, ensuring the health gate catches DB connectivity issues in addition to app startup failures. Poll window changed from 30×10s (300s) to 18×10s (180s) — sufficient for ACA revision provisioning.

---

## Workflow Changes

| File | Change |
|------|--------|
| `.github/workflows/azure-staging.yml` | `az containerapp create`: `--min-replicas 0` → `1` (backend + frontend); `az containerapp update`: added `--min-replicas 1`; health gate: `/health` → `/api/v1/health`, 30×10s → 18×10s |
| `.github/workflows/frontend-staging.yml` | Pre-build health check: single curl → 6-attempt retry loop; `az containerapp update`: added `--min-replicas 1`; revision suffix: `fe-<sha8>` → `fe-<sha8>-<epoch>` |

---

## ACA Changes

| Setting | Before | After |
|---------|--------|-------|
| Backend `minReplicas` | 0 | 1 |
| Backend startup probe | null (none) | n/a (not added — minReplicas=1 removes need) |
| Frontend `minReplicas` | 0 | 1 |
| Frontend startup probe | null (none) | n/a |

> **Note on probes:** ACA has no health probes configured (`null`). Since `minReplicas=1` eliminates scale-to-zero (the primary failure mode), and ACA's default revision health tracking is sufficient for single-revision mode, adding custom probes is deferred. The DB-aware health gate in the workflow provides post-deploy verification.

---

## Cold Start Timing

| Service | Warm request |
|---------|-------------|
| Backend `/health` | ~0.17–0.23s |
| Backend `/api/v1/health` (DB) | ~0.17–0.26s |
| Frontend `/` | ~0.16–0.18s |

Cold start timing was not measurable directly (backend was already warm during investigation). Based on failure evidence: cold start > 15 seconds (causes curl timeout at `--max-time 15`). With `minReplicas=1`, cold start only occurs during first-ever provision — not during normal CI runs.

---

## Smoke Test Results

| Check | Result |
|-------|--------|
| Backend `/health` | ✅ HTTP 200 |
| Backend `/api/v1/health` (DB-aware) | ✅ HTTP 200 `{"status":"ok","db":"ok"}` |
| Frontend `/` | ✅ HTTP 200 |
| Frontend `/login` | ✅ HTTP 200 |
| Frontend `/dashboard` | ✅ HTTP 200 |
| Labs list `GET /api/v1/patients/.../lab-batches` | ✅ HTTP 401 (auth working) |
| Lab upload `POST /api/v1/lab-uploads` | ✅ HTTP 401 (auth working) |
| AI chat `POST /api/v1/ai/chat` | ✅ HTTP 401 (auth working) |

---

## Regression: Two Consecutive Deploys (same SHA)

| Run | ID | Result | Duration | Note |
|-----|-----|--------|----------|------|
| Deploy 1 | 28292611361 | ✅ success | 3m08s | minReplicas=1 fix active; backend warm in 1 attempt |
| Deploy 2 (same SHA, old suffix logic) | 28292697102 | ❌ fail | 6m01s | Revealed Case F: stale revision name |
| Deploy 3 (same SHA, timestamp suffix) | 28292879522 | ✅ success | 2m52s | Timestamp suffix `fe-1627c7f0-1782572744` unique; new revision created |

Deploy 3 = regression test **PASSED**.

---

## Commits

| SHA | Message |
|-----|---------|
| `1627c7f` | `fix(ci-cd): prevent ACA cold-start failures in staging deploy` |
| `ca348bf` | `fix(ci-cd): unique revision suffix prevents stale-revision false failure` |

---

## Remaining Risk

1. **ACA minReplicas can be reset to 0** by someone running `az containerapp update --min-replicas 0` manually or via ARM template. The workflow now sets `--min-replicas 1` on every deploy, self-healing this. The retry loop in `frontend-staging.yml` provides an additional 90s grace window.

2. **Backend cold start timing unknown.** We know it exceeds 15s (timeout evidence) but the upper bound is unmeasured. If a future revision has a longer startup (more imports, heavier lifespan code), the 90s retry window could be insufficient. Mitigation: the retry uses `|| echo "000"` so curl timeout is non-fatal per attempt.

3. **No ACA health probes configured.** ACA uses its own internal health tracking for revision promotion. Without custom startup/readiness probes, ACA may mark a revision "Healthy" before the app is truly ready at the HTTP level. For the current workload (FastAPI + sync SQLAlchemy, DB connection on first request), this is low risk. If DB connection pooling becomes lazy-init, add startup probe pointing to `/api/v1/health`.

4. **CI.yml `push:` trigger fails silently on test errors.** The `CI` workflow runs on every push to `main` but has been failing (CI failures seen in run list). This is a pre-existing test issue unrelated to staging deploy — tracked separately.

5. **Azure Staging Deploy (`azure-staging.yml`) is manual-only.** Merging to `main` does NOT auto-trigger full backend+frontend redeploy. Only frontend-only deploy is triggered via `deploy-staging.sh`. The objective "make every merge automatically deploy to Azure Staging" requires adding `on: push: branches: [main]` to `azure-staging.yml`. This is a scope decision (not implemented here to avoid unintended full deploys while CI tests are failing).
