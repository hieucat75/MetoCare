# 01 — Production Readiness Matrix (WS1)

**Date:** 2026-08-04 · **Branch:** `feat/patient-platform-journey2` @ `6ab3b04` · **Method:** direct source + workflow inspection this session. No prior summary was trusted; every material claim below carries a `file:line` or command-output citation, or is explicitly marked `UNVERIFIED`.

**Scope note.** Two gates are assessed separately throughout: **CP** = controlled pilot (≤50 users, staging backend, synthetic-or-consented data) and **PB** = public beta / production. `00-CURRENT-STATE.md` and `15-FINAL-LAUNCH-REVIEW.md` remain the baseline; this document adds the per-dimension verdicts and the findings register `PROD-F7`+ that the final review anticipated but did not enumerate.

**Guardrail compliance.** `PROD-F1` (`MCP_STORAGE_MODE=local` → blobs on ephemeral container disk) and `PROD-F2` (production deploy omits `MCP_MFA_ENFORCEMENT_ENABLED` → boot refused → crash-loop) are **infrastructure/deploy-config items owned by the project owner**. Per the standing project guardrail ("do not touch Azure infra workflow/config"), **no Azure workflow or infra file was edited by this assessment** — both are re-verified below and left for owner action. The same restriction applies to the new workflow-level findings `PROD-F7`, `PROD-F8`, `PROD-F13`, `PROD-F14`: they are **documented, not fixed**.

---

## 1. Verification baseline (commands run this session)

| Check | Result | Command |
|---|---|---|
| Alembic heads | **single head** `j4_m8_consent_versioning` | `cd backend && source .venv/bin/activate && alembic heads` → `j4_m8_consent_versioning (head)` (exit 0) |
| Runtime lib versions in dev venv | fastapi `0.138.0`, starlette `1.3.1`, SQLAlchemy `2.0.51`, anyio `4.14.1`, gunicorn `26.0.0`, uvicorn `0.49.0` | `pip list` |
| Default request threadpool | **40 threads** | `anyio.to_thread.current_default_thread_limiter().total_tokens` → `40` |
| Auth env vars in any workflow | **none set** (`MCP_ALLOW_RELAXED_AUTH`, `MCP_MFA_ENFORCEMENT_ENABLED`, `MCP_QA_FIXTURE_ENABLED` absent) | `grep -rn "ALLOW_RELAXED\|MFA_ENFORCEMENT\|QA_FIXTURE" .github/workflows/` → no output |
| Runtime health probes | **none configured** (no ACA probe, no Docker `HEALTHCHECK`) | `grep -rn "HEALTHCHECK\|probe\|liveness\|readiness"` over both workflows + `backend/Dockerfile` → only the post-deploy curl step |

---

## 2. Per-dimension readiness matrix

Legend: ✅ READY · 🟡 READY-WITH-LIMITATION · ⛔ BLOCKED

| # | Dimension | CP (controlled pilot) | PB (public beta / prod) | Evidence | Limitation / blocker |
|---|---|---|---|---|---|
| 1 | **Config & secrets — fail-loud guards** | ✅ | 🟡 | `backend/app/core/config.py:218-305` (required-var check, committed-default JWT/Fernet refusal `:244-262`, relaxed-auth refusal `:267-295`, QA-fixture prod refusal `:300-305`); invoked at startup `backend/app/main.py:43` | Guard logic is genuinely production-grade. The **deployed env that satisfies it is not in version control** (PROD-F4, re-confirmed §1 grep) → see PROD-F14. |
| 2 | **Config & secrets — injection path** | ✅ | ✅ | Key Vault → OIDC → ACA secrets, masked, never echoed: `.github/workflows/azure-staging.yml:116-143`, `:190`, `:220` | Secrets are `secretref:`-mounted, not baked into the image. Rotation runbook UNVERIFIED — no `az` access this session. |
| 3 | **Migrations — single head & ordering** | ✅ | 🟡 | single head verified §1; one-shot ACA job runs `alembic upgrade head` **before** the app image is deployed: `azure-staging.yml:145-185`, `azure-production.yml:184-208`; no runtime `create_all()` (`app/main.py:45-49`, guarded at `app/core/database.py:53-61`) | The **gate is not fail-closed on timeout** → **PROD-F8** (P1). No automated `downgrade` path in either workflow; rollback is manual. |
| 4 | **Deploy & rollback** | 🟡 | ⛔ | staging deploy + post-deploy health curl `azure-staging.yml:187-261`; production workflow exists `azure-production.yml:210-245` | Prod path cannot boot as written (**PROD-F2**, §3). The "ACA keeps previous healthy revision (auto-rollback)" comment at `azure-staging.yml:260` is **not backed by a configured probe** (§1) → **PROD-F13**. Revision mode (single vs multiple) UNVERIFIED — run `az containerapp show -g rg-metocare-staging -n ca-metocare-backend --query properties.configuration.activeRevisionsMode`. |
| 5 | **Storage durability** | 🟡 (synthetic data only) | ⛔ | `MCP_STORAGE_MODE=local` in **both** environments: `azure-staging.yml:209`, `azure-production.yml:222`; local adapter writes to `settings.storage_local_dir` default `./storage` (`app/core/config.py:87`, `app/services/storage/local.py:101-105`); container dir is a plain image path `backend/Dockerfile:30`; no volume mount in either workflow | **PROD-F1** (P0, owner-gated, not edited). Azure Blob adapter exists and is inert (`app/services/storage/factory.py:44-49`). Any redeploy/replica replacement loses every uploaded document. |
| 6 | **Database — engine & pooling** | 🟡 | ⛔ | `app/core/database.py:23-37` — `create_engine(url, connect_args=..., future=True)`: **no `pool_size`, `max_overflow`, `pool_pre_ping`, or `pool_recycle`** → SQLAlchemy defaults 5 + 10 overflow = **15 connections**, against a **40-thread** request pool (§1) | **PROD-F12** (P1): threadpool is 2.7× the connection pool. `pool_pre_ping` absence already logged as WS5-F5 (P2); it compounds here because ACA/Azure PG drop idle TCP. Postgres SKU/`max_connections` UNVERIFIED — run `az postgres flexible-server show -g rg-metocare-staging -n psql-metocare-staging`. |
| 7 | **Database — schema/index fitness** | ✅ | 🟡 | single-column indexes present on the hot patient columns: `app/models/medication_schedule.py:60-62,105-116` (`patient_id`, `scheduled_utc`, `state`), `app/models/medical_document.py:79-81,170-172,194-206` (`patient_id`, `status`, `candidate_type`) | No composite `(patient_id, state, scheduled_utc)`; Postgres bitmap-AND is adequate at pilot volume. Growth risk is query shape, not indexing — see `09-PERFORMANCE-CAPACITY.md` §5. |
| 8 | **Rate limiting & lockout** | 🟡 | ⛔ | in-memory token bucket + lockout `app/core/ratelimit.py:31-91`; Redis adapter implemented `:101+`; deployed as `MCP_RATELIMIT_BACKEND=memory` (`azure-staging.yml:209`, `azure-production.yml:222`) | **PROD-F3** (pre-existing): correct only at 1 replica — which is what is deployed (`--min-replicas 1 --max-replicas 1`, `azure-staging.yml:227`). **New:** the AI endpoints are **not rate-limited at all** → **PROD-F11** (P1). |
| 9 | **Health checks** | 🟡 | ⛔ | DB-aware readiness endpoint exists and is correct: `app/api/v1/routes/system.py:17-35` (200/503 on `SELECT 1`); shallow liveness `app/main.py:177-179` | **PROD-F13** (P1): nothing consumes them at runtime. The only use is a one-shot curl during deploy (`azure-staging.yml:248-261`). No Docker `HEALTHCHECK` (`backend/Dockerfile`, 46 lines, none present). |
| 10 | **Dependency pinning / reproducibility** | 🟡 | ⛔ | `backend/requirements.txt` — floor-only (`>=`) constraints throughout, with its own admission on line 2: *"Pinned loosely for foundation; lock with a resolver before production."* Image build resolves at build time: `backend/Dockerfile:22-23` | **PROD-F9** (P1). No lockfile, no hashes. Evidence of live drift: the floor is `fastapi>=0.115` while the dev venv already resolves `fastapi 0.138.0` / `starlette 1.3.1` (§1) — two images built a week apart are not the same software. |
| 11 | **Error handling** | ✅ | ✅ | typed domain handlers for validation/password/consent/permission/undecryptable-PHI `app/main.py:110-175`; PHI never echoed (`:157-175`); request-id + access log + 5xx capture `app/core/middleware.py:70-108` | Aggregation still missing (WS5-F1/F3, pre-existing). No global request-timeout middleware — bounded only by gunicorn `--timeout 120` (`backend/Dockerfile:46`), which **PROD-F10** (AI chain) and **PROD-F19** (sync OCR) can both exceed; on a 1-worker container that means replica-wide request loss, not a single failed call. |
| 12 | **Single-replica assumptions** | 🟡 | ⛔ | `--min-replicas 1 --max-replicas 1 --cpu 0.5 --memory 1.0Gi` (`azure-staging.yml:227`, `azure-production.yml:241`); `--workers 1` (`backend/Dockerfile:46`, `backend/startup.sh:13`) | Three state-in-process dependencies would break on scale-out: rate limiter/lockout (`app/core/ratelimit.py:31`), local-disk storage (dim. 5), LLM response cache (`app/core/config.py:111-114`). **Scaling past 1 replica is a config change that silently degrades security controls** — it must be gated on PROD-F1 + PROD-F3 first. Note the deployed size is **0.5 vCPU / 1 GiB**, half of the "1 vCPU / 2 GiB" assumed in `10-COST-MODEL.md` §"Cost model by scale". |
| 13 | **Feature-flag posture** | 🟡 | ⛔ | fail-closed resolver `app/core/feature_flags.py:97-122`; defaults `:65-94` | Deployed flags **contradict the documented posture**: both workflows set `MCP_FEATURE_OCR_CLOUD_FALLBACK=true` (`azure-staging.yml:211`, `azure-production.yml:224`) while `00-CURRENT-STATE.md` §3 and `TRACKING.md` R-05 record it OFF. Worse, the OCR engine ignores the flag entirely → **PROD-F7 (P0)**. |
| 14 | **Public surface / info disclosure** | 🟡 | 🟡 | `/metrics` unauthenticated on external ingress (`app/main.py:181-185` + `MCP_METRICS_ENABLED=true`, `azure-staging.yml:210`); `/info` unauthenticated (`app/api/v1/routes/system.py:38-66`) | `/info` already logged as WS5-F6/SEC-F4 (P2); `/metrics` addition → **PROD-F18** (P2). Interactive docs are correctly forced off in prod (`app/main.py:71`) **and** disabled by env (`MCP_ENABLE_DOCS=false`). |

### Gate roll-up

| Gate | Verdict | Rationale |
|---|---|---|
| **Controlled pilot (≤50 users, staging, synthetic data)** | 🟡 **GO once PROD-F7 is resolved** | Everything else is either sound or a documented, accepted limitation at 1 replica / synthetic data. PROD-F7 is new and contradicts a control the program has already asserted to the owner. |
| **Public beta / production** | ⛔ **NO-GO** | PROD-F1, PROD-F2, PROD-F3, PROD-F8, PROD-F9, PROD-F10, PROD-F12, PROD-F13 all open, plus the pre-existing credential/backup/monitoring blockers in `15-FINAL-LAUNCH-REVIEW.md` §6. |

---

## 3. Re-verification of the two owner-gated P0s (NOT edited)

**PROD-F1 — object storage on ephemeral container disk.** Confirmed unchanged. `MCP_STORAGE_MODE=local` is set in the staging deploy env (`azure-staging.yml:209`) and the production deploy env (`azure-production.yml:222`). The factory resolves that to `LocalDiskStorage` (`app/services/storage/factory.py:38-43`), rooted at `settings.storage_local_dir`, whose default is `./storage` (`app/core/config.py:87`) and which **neither workflow overrides** — i.e. `/app/storage` inside the container image (`backend/Dockerfile:30`). No volume, no mount, no backup. The Azure Blob adapter is implemented and reachable by a single env change (`factory.py:44-49`), so the fix is configuration + credential, not code.
*Owner action (unchanged):* set `MCP_STORAGE_MODE=azure` + `MCP_STORAGE_AZURE_CONNECTION_STRING`, enable Blob soft-delete/versioning, before any real PHI. **Not editable by this assessment.**

**PROD-F2 — production boot config.** Confirmed unchanged and now sharper. No workflow anywhere in `.github/workflows/` sets `MCP_MFA_ENFORCEMENT_ENABLED` or `MCP_ALLOW_RELAXED_AUTH` (§1 grep, empty). `config.py:268-289` refuses to start when `env ∈ {staging, prod, production}` and MFA enforcement is off, with production having **no override path at all** (`:279-284`). The production `COMMON_ENV` (`azure-production.yml:215-232`) therefore produces a container that raises `RuntimeError` during lifespan → crash-loop.
*Owner action (unchanged):* add `MCP_MFA_ENFORCEMENT_ENABLED=true` to the production env block and dry-run to healthy before any cutover. **Not editable by this assessment.**

---

## 4. NEW findings confirmed this session (`PROD-F7`+)

### PROD-F7 — **P0** · Cloud OCR is the *primary* engine on staging and production, bypassing its own feature flag

**What the code does.** `app/services/ocr_engine.py:479-505` selects an engine in this order: explicit-mock → **Azure Document Intelligence** → Tesseract. The Azure branch (`:491-492`) is guarded **only** by `AzureDocIntelEngine.configured()`, which is pure env presence (`:254-256`: `bool(os.getenv("AZURE_DOC_INTEL_KEY") and os.getenv("AZURE_DOC_INTEL_ENDPOINT"))`). **`FeatureFlag.OCR_CLOUD_FALLBACK` is never consulted on this path** — the flag is checked only inside `run_cloud_ocr_if_permitted()` (`:424`), a separate escalation helper used by the lab-draft builder.

**What is deployed.** Both workflows inject the credentials — `AZURE_DOC_INTEL_ENDPOINT` + `AZURE_DOC_INTEL_KEY=secretref:doc-intel-key` (`azure-staging.yml:213-214`, `azure-production.yml:226-227`) — **and** additionally set `MCP_FEATURE_OCR_CLOUD_FALLBACK=true` (`azure-staging.yml:211`, `azure-production.yml:224`).

**Consequence.** Every page ingested through the Medical Document Intelligence pipeline (`app/services/mdi/pipeline.py:52-54` → `run_ocr`) and the lab-upload pipeline (`app/services/lab_upload.py:30`) is uploaded to Azure Document Intelligence. Tesseract never executes. This contradicts, in the same words used to the owner, `00-CURRENT-STATE.md` §3 (`OCR_CLOUD_FALLBACK` = "**OFF** … no PHI leaves device/region until owner authorizes"), `TRACKING.md` R-05 ("flag OFF + fail-closed; owner authorization required to enable") and `10-COST-MODEL.md` ("Keep cloud OCR OFF; local/mock path is $0 marginal"). It also invalidates the cost model's cloud-OCR line and the "local Tesseract, $0 marginal" capacity assumption.

**Aggravating detail.** `GET /info` reports `"ocr_mode": s.ocr_mode` (`app/api/v1/routes/system.py:62`) and both workflows set `MCP_OCR_MODE=mock` — but `ocr_mode` is read **only** by the legacy `app/services/lab.py:346,369` path and has no effect on `run_ocr`. So the very probe used as staging evidence reports `ocr_mode=mock` while real PHI images are being sent to a cloud service. Any prior "verified OCR posture via `/info`" evidence is therefore not load-bearing.

**Exact remediation** (two parts; part (b) is owner-gated infra):
- **(a) code — restores fail-closed:** in `app/services/ocr_engine.py:491`, change the branch to
  `if is_enabled(FeatureFlag.OCR_CLOUD_FALLBACK) and AzureDocIntelEngine.configured():`
  so the credential alone can never route PHI to the cloud, and add a regression test asserting `run_ocr` picks `tesseract` when the key is present but the flag is off.
- **(b) deploy — owner action, NOT edited here:** remove `MCP_FEATURE_OCR_CLOUD_FALLBACK=true`, `MCP_OCR_CLOUD_PROVIDER=azure`, `AZURE_DOC_INTEL_ENDPOINT` and `AZURE_DOC_INTEL_KEY` from `azure-staging.yml:211-214` and `azure-production.yml:224-227` until PHI-to-cloud processing is explicitly authorized, and re-state the authorized posture in `TRACKING.md` §E.

> **Severity rationale.** Rated P0 rather than P1 because `TRACKING.md` R-05 already classifies this exact condition as "P0-if-flipped", and because it is *already flipped in the deployed environment* — with the code path making the documented control unenforceable even after the flag is turned off. Mitigating: the destination is an Azure resource inside the owner's own subscription (`docintel-metocare-staging`), not an unrelated third party, and the pilot data is synthetic.

### PROD-F8 — **P1** · Migration gate is not fail-closed on timeout

`azure-staging.yml:176-185` polls the migration job's execution status 40 × 15 s. The loop `break`s on `Succeeded` and `exit 1`s on `Failed` — but if the status is never terminal (job stuck, ACA control-plane hiccup, `az` query returning empty), **the loop simply ends and the step succeeds**, and the very next step deploys the new image against a possibly-unmigrated schema. Identical defect at `azure-production.yml:200-208` (40 × 10 s). Secondary: the query reads `[0].properties.status` (`:177-178`), and ACA does not guarantee the execution list is newest-first — a stale `Succeeded` can be read.

**Fix:** after the loop, re-read the status into `ST` and `[ "$ST" = "Succeeded" ] || { echo "::error::migration did not reach Succeeded"; exit 1; }`. Select the execution by name from the `az containerapp job start` output rather than by list index. *(Workflow file — owner-gated, not edited.)*

### PROD-F9 — **P1** · No dependency lockfile; images are not reproducible

`backend/requirements.txt` pins only floors (`fastapi>=0.115`, `SQLAlchemy>=2.0`, `openai>=1.0.0`, `anthropic>=0.112.0`, …) and states its own remediation on line 2. `backend/Dockerfile:22-23` runs `pip install --no-cache-dir -r requirements.txt` at build time, so the image contents depend on the day it was built. Measured drift: the dev venv resolves `fastapi 0.138.0` / `starlette 1.3.1` against a `>=0.115` floor. A rebuild for an unrelated hotfix can therefore ship a different framework major than the one the 3 761-test suite was green against.

**Fix:** generate `backend/requirements.lock` with `uv pip compile requirements.txt --generate-hashes -o requirements.lock` (or `pip-compile`), change `Dockerfile:23` to `pip install --no-cache-dir --require-hashes -r requirements.lock`, and add a CI job that fails when the lock is stale. Re-run the full suite against the locked set once.

### PROD-F10 — **P1** · AI provider retry budget can exceed the worker timeout and kill the whole container

`app/ai/providers/openai_provider.py:31-33` sets `_MAX_RETRIES = 2` and `_REQUEST_TIMEOUT = 30.0`; `app/ai/registry.py:207-244` walks the **entire** provider chain sequentially, and each provider consumes its own full retry budget. With the two providers the staging env configures (OpenRouter primary + fallback model, `azure-staging.yml:216-218`), worst case is 2 × 3 × 30 s = **180 s**. Gunicorn is started with `--timeout 120 --workers 1` (`backend/Dockerfile:46`; same in `backend/startup.sh:12-19`), so the worker is killed first — and because there is exactly one worker, **every other in-flight request on that container dies with it**. `settings.meto_timeout_seconds` (`app/core/config.py:75`) exists for precisely this purpose but is referenced nowhere (`grep -rn "meto_timeout_seconds" app/` returns only the definition).

**Fix:** wrap the chain call in `app/services/meto_chat.py:169` with `async with asyncio.timeout(settings.meto_timeout_seconds):` (and the same for `stream_chat`), pass `settings.meto_timeout_seconds` into the provider clients instead of the module constant, and keep the total budget comfortably under `--timeout 120` (e.g. 30 s per provider, chain capped at 60 s).

### PROD-F11 — **P1** · No rate limit or per-user cap on the AI endpoints

`POST /meto/chat` and `POST /meto/chat/stream` (`app/api/v1/routes/meto.py:58-121`) call **no** `enforce_rate_limit`, unlike every document endpoint (`app/api/v1/routes/documents.py:167, 208, 228, 413, 451, 489, 510`). There is a per-minute LLM guard in config (`app/core/config.py:108-110`) but it belongs to the separate legacy LLM-gateway service, not this path. With `10-COST-MODEL.md` costing a Meto message at ≈ $0.012 and `MetoChatRequest.message` capped at 4 000 chars (`app/schemas/meto.py:17`) with a 20-message history and no token-budget truncation (`app/ai/prompt/assembler.py:216-222`), a single authenticated account can drive spend without bound — the exact abuse lever `10-COST-MODEL.md` §"Cost ceiling" flagged as needing a control.

**Fix:** add `enforce_rate_limit(request, "meto_chat")` to both routes (requires adding the `request: Request` parameter), plus a per-user **daily** message counter persisted in the DB (the sliding in-memory bucket resets on redeploy). Do this before `AI_ASSISTANT` is enabled beyond the pilot cohort.

### PROD-F12 — **P1** · Request threadpool is 2.7× the database connection pool

`app/core/database.py:32` builds the engine with no pool arguments → SQLAlchemy `QueuePool` defaults, `pool_size=5` + `max_overflow=10` = **15** connections. Every sync (`def`) route runs in the anyio threadpool, measured at **40** tokens (§1). Under 40 concurrent sync requests, 25 of them block on connection checkout for the default 30 s and then raise `TimeoutError: QueuePool limit … reached`, surfacing as 500s. Same engine object also lacks `pool_pre_ping` (already WS5-F5, P2) and `pool_recycle`, so idle-connection drops by Azure PG/ACA turn into intermittent 500s on the first request after a quiet period.

**Fix:** `create_engine(url, connect_args=connect_args, future=True, pool_size=20, max_overflow=10, pool_pre_ping=True, pool_recycle=1800)` for non-SQLite URLs (leave SQLite on its current defaults), and validate against the Postgres `max_connections` for the deployed SKU before raising further.

### PROD-F13 — **P1** · No runtime liveness/readiness probe; deploy-time health gate only

The application provides exactly the right endpoint — `GET /api/v1/health` returns 503 when `SELECT 1` fails (`app/api/v1/routes/system.py:17-35`) — but nothing consumes it at runtime. Neither workflow configures ACA `probes` and `backend/Dockerfile` has no `HEALTHCHECK` (§1 grep). Consequences: (a) a replica whose DB connection is broken keeps receiving traffic indefinitely; (b) the "ACA keeps previous healthy revision (auto-rollback)" claim at `azure-staging.yml:260` is unfounded — ACA's revision-health judgement without a readiness probe is container-start only.

**Fix:** deploy the container app from a YAML template carrying `probes:` — `readiness` and `liveness` on `/api/v1/health` (readiness `periodSeconds: 10`, `failureThreshold: 3`; liveness `initialDelaySeconds: 30`) — and add `HEALTHCHECK CMD curl -fsS http://localhost:8000/api/v1/health || exit 1` to `backend/Dockerfile` (the image already installs `curl` for this purpose, `Dockerfile:7,13`). *(Workflow portion owner-gated, not edited.)*

### PROD-F14 — **P1** · Disaster-recovery recreate from the workflow produces a non-booting app in **staging** too

`az containerapp update --set-env-vars` merges into the existing env, so the out-of-band `MCP_ALLOW_RELAXED_AUTH` that lets staging boot today survives every deploy — which is why staging is healthy despite §1's empty grep. But the create branch (`azure-staging.yml:225-228`) passes **only** `$COMMON_ENV`. If the container app is ever deleted and recreated (DR, region move, environment rebuild), staging hits the same `RuntimeError` as production (`config.py:268-289`). This is the operational teeth behind the pre-existing PROD-F4 "config drift" note: the environment cannot currently be rebuilt from source.

**Fix:** codify the full auth env in the workflow (`MCP_ALLOW_RELAXED_AUTH=true` for staging only, `MCP_MFA_ENFORCEMENT_ENABLED=true` for production) so both create and update paths are self-sufficient, and add a CI assertion that the deployed env set matches the workflow's. *(Workflow file — owner-gated, not edited.)*

### PROD-F15 — **P2** · Blocking disk I/O on the event loop in the blob upload endpoint

`PUT /documents/blob/{token}` is declared `async def` (`app/api/v1/routes/documents.py:257`) but performs synchronous filesystem calls — `storage.exists(...)` (`:268`) and `storage.put_bytes(...)` (`:273`) → `open()/write()/os.replace()` (`app/services/storage/local.py:60-67`) — for a body of up to `ocr_max_upload_mb` = 10 MB (`app/core/config.py:135`, enforced at `documents.py:264-266`). This stalls the single event loop, delaying **all** concurrent requests including SSE Meto streams.
**Fix:** either drop `async` (FastAPI then runs it in the threadpool) or wrap both calls in `starlette.concurrency.run_in_threadpool`.

### PROD-F16 — **P2** · Health-timeline issues 8 unbounded per-patient queries and applies `limit` in memory

`app/api/v1/routes/health_timeline.py:110-182` fetches lab batches, **all** lab results (`:125-132`), BP/weight metrics, **all** medications (`:148-153`), symptom logs, **all** dose occurrences (`:166-167`), **all** documents (`:170-174`) and **all** confirmed candidates (`:175-182`). `from_date`/`to_date` are pushed to SQL for only three of the eight; the `limit` parameter (`:86`) is handed to the in-process engine (`:209`) after every row is already materialised. Detailed growth analysis in `09-PERFORMANCE-CAPACITY.md` §5.
**Fix:** push `from_date`/`to_date` into all eight queries and add a per-source `.limit()` sized from the requested `limit`.

### PROD-F17 — **P2** · PDF documents cannot be extracted without the cloud engine

`app/services/mdi/service.py:343-347` passes the entire file as a single element — `page_bytes=[data]` — and `TesseractEngine.run` immediately does `Image.open(io.BytesIO(image_bytes))`, raising `OcrEngineError("Không đọc được tệp ảnh.")` for anything PIL cannot decode (`app/services/ocr_engine.py:73-77`). PDFs therefore only work while Azure DI is the selected engine — i.e. the PDF path silently depends on PROD-F7's misconfiguration and breaks the moment cloud OCR is correctly disabled. `document_max_pages` = 20 (`config.py:96`) implies multi-page PDFs are an expected input.
**Fix:** rasterize PDFs before the pipeline using the same `pdf2image.convert_from_bytes` approach already proven in `app/services/lab_upload.py:169-171`, bounded by `settings.ocr_pdf_max_pages` (`config.py:141`), and pass one element per page.

### PROD-F19 — **P1** · Synchronous document finalize can outlive the worker timeout and kill the replica

`POST /documents/{upload_id}/finalize` runs the full OCR/extraction pipeline **inside the HTTP request** (`app/api/v1/routes/documents.py:229` → `app/services/mdi/service.py:260-261` → `app/services/mdi/pipeline.py:52-54`). There is no queue on this path: `MCP_OCR_WORKER_ENABLED=false` in both deploy envs (`azure-staging.yml:208`, `azure-production.yml:221`), and that worker belongs to the separate lab pipeline regardless. Either engine can exceed gunicorn's `--timeout 120` (`backend/Dockerfile:46`):

- **Cloud DI:** 30 s submit + up to 30 polls with a 5 s backoff cap = **≈180 s** (`app/services/ocr_engine.py:247-251, 302-326`).
- **Local Tesseract:** derived 10–25 s per page in-container × up to `document_max_pages` = 20 (`app/core/config.py:96`) — see `09-PERFORMANCE-CAPACITY.md` §6.2 for the measurement this is derived from.

On timeout the **single** worker is SIGKILLed, dropping every concurrent request on the replica. The document itself is recoverable — the quarantine object deliberately survives and finalize is retryable (`mdi/service.py:246-252`).

**Fix:** (a) bound the OCR call — give the DI poll loop an explicit ~60 s deadline and cap MDI pages via `settings.ocr_pdf_max_pages` (`config.py:141`) after rasterization (PROD-F17); (b) preferably move extraction off the request path — return `202` with `status=processing` from finalize and run `_run_extraction` in a background task, letting the existing `GET /documents/{id}/extraction` read surface the result. (b) also releases the DB connection that finalize otherwise holds for the entire OCR duration (see PROD-F12).

### PROD-F18 — **P2** · `/metrics` served unauthenticated on the external ingress

`app/main.py:181-185` exposes the Prometheus-text registry with no auth, and `MCP_METRICS_ENABLED=true` is set on external-ingress apps in both environments (`azure-staging.yml:210`, `azure-production.yml:223`). Contents are counters/histograms, not PHI, but they disclose route inventory and traffic volume. Companion to the existing `/info` disclosure item (WS5-F6 / SEC-F4).
**Fix:** require a bearer/shared-secret header on `/metrics`, or move it behind an internal-only ingress once a scraper exists (WS5-F1).

---

## 5. Findings summary

| ID | Sev | One-line | Owner |
|---|---|---|---|
| PROD-F1 | P0 | Blobs on ephemeral container disk (`MCP_STORAGE_MODE=local`) | Owner (infra) — **not edited** |
| PROD-F2 | P0 | Prod deploy omits `MCP_MFA_ENFORCEMENT_ENABLED` → crash-loop | Owner (infra) — **not edited** |
| **PROD-F7** | **P0** | Cloud OCR is primary engine, flag never checked; enabled in both envs | Eng (code) + Owner (workflow) |
| **PROD-F8** | **P1** | Migration poll loop is not fail-closed on timeout | Owner (workflow) |
| **PROD-F9** | **P1** | No dependency lockfile; images non-reproducible | Eng |
| **PROD-F10** | **P1** | AI retry budget (180 s) exceeds gunicorn `--timeout 120` on a 1-worker container | Eng |
| **PROD-F11** | **P1** | No rate limit / per-user cap on `/meto/chat[/stream]` | Eng |
| **PROD-F12** | **P1** | 40-thread request pool vs 15-connection DB pool; no pre-ping/recycle | Eng |
| **PROD-F13** | **P1** | No runtime liveness/readiness probe; "auto-rollback" unfounded | Owner (workflow) + Eng (Dockerfile) |
| **PROD-F14** | **P1** | Workflow alone cannot rebuild a bootable staging app (DR gap) | Owner (workflow) |
| **PROD-F19** | **P1** | Sync OCR in `finalize` can exceed the 120 s worker timeout → replica-wide request loss | Eng |
| **PROD-F15** | **P2** | Blocking disk I/O on the event loop in `blob_put` | Eng |
| **PROD-F16** | **P2** | Timeline: 8 unbounded queries, in-memory `limit` | Eng |
| **PROD-F17** | **P2** | PDFs unextractable without cloud OCR (no rasterization on MDI path) | Eng |
| **PROD-F18** | **P2** | `/metrics` unauthenticated on external ingress | Eng |

Pre-existing PROD-F3–F6 are unchanged and remain as recorded in `15-FINAL-LAUNCH-REVIEW.md` §3.

## 6. Explicitly UNVERIFIED (needs credentials or a running environment)

| Claim | How to verify |
|---|---|
| Live staging revision, env-var set, and whether `MCP_ALLOW_RELAXED_AUTH` is actually present | `az containerapp show -g rg-metocare-staging -n ca-metocare-backend --query "properties.template.containers[0].env"` |
| ACA active-revisions mode (does a failed revision really hold traffic?) | `az containerapp show … --query properties.configuration.activeRevisionsMode` |
| Postgres SKU, `max_connections`, backup retention / PITR window | `az postgres flexible-server show -g rg-metocare-staging -n psql-metocare-staging` |
| Whether Azure Document Intelligence has actually received requests (PROD-F7 blast radius) | Azure Monitor metrics on `docintel-metocare-staging`, request count since the v1.4.0 deploy |
| Full backend suite green at `6ab3b04` | `cd backend && source .venv/bin/activate && pytest -q` → record in `TEST-STATUS.md` |
