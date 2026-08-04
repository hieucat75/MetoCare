# 09 — Performance & Capacity (WS9)

**Date:** 2026-08-04 · **Branch:** `feat/patient-platform-journey2` @ `6ab3b04` · **Target:** controlled pilot, **≤50 users**, staging backend, single ACA replica.

> **Read this first — measurement status.** Nothing in this document is a production measurement. Exactly **one** number below is measured (local Tesseract CPU per page, §6, on a dev laptop with a synthetic page). Everything else is a **derivation from source** (query counts, concurrency ceilings, timeout arithmetic) or an **explicit estimate** (request volumes, latencies, token counts). Each table cell is tagged `[MEASURED]`, `[DERIVED]` (arithmetic over cited source/config, no runtime observation) or `[ESTIMATE]` (assumption). §8 gives the exact steps to convert the estimates into measurements. Do not quote any `[ESTIMATE]` as a benchmark.

**Deployed shape being sized** (from the workflow, not from a live probe):
`--min-replicas 1 --max-replicas 1 --cpu 0.5 --memory 1.0Gi` (`.github/workflows/azure-staging.yml:227`) running Gunicorn `--workers 1 --timeout 120 --graceful-timeout 30` with a single `UvicornWorker` (`backend/Dockerfile:46`). Note this is **half** the "1 vCPU / 2 GiB" that `10-COST-MODEL.md` assumed; that document's compute line should be re-based.

---

## 1. Workload model — ≤50-user controlled pilot

Per-user-per-day request counts, built bottom-up from the mobile screens that actually call the API. The app fetches on mount and has **no polling** (`grep -rn "setInterval\|refetchInterval" mobile/src mobile/app` → no matches; `mobile/app/(app)/dashboard.tsx:40` is a one-shot `useEffect`), so volume scales with screen opens, not with session length.

| Journey | Endpoint(s) | Requests / user / day | Tag |
|---|---|---|---|
| J1 auth / app open | `POST /auth/refresh`, `GET /auth/me` | 3 (≈3 app opens) | `[ESTIMATE]` |
| J3 dashboard | `GET /patients/{id}/dashboard` | 3 (one per open) | `[ESTIMATE]` |
| J3 reminders | `GET /reminders/due`, `POST` dose action | 3 + 2.5 | `[ESTIMATE]` |
| metrics / labs browsing | `GET /patients/{id}/metrics`, `/metrics/trend`, lab reads | 4 | `[ESTIMATE]` |
| timeline | `GET /patients/{id}/health-timeline` | 0.5 | `[ESTIMATE]` |
| J2 documents | upload-session → blob `PUT` → finalize → list candidates → 3× confirm ≈ **7 requests per document**, at 4 documents/user/month (`10-COST-MODEL.md`) | ≈ 0.9 | `[ESTIMATE]` |
| J4 Meto | `POST /meto/chat[/stream]`, conversation list, at 20 messages/user/month | ≈ 1.4 | `[ESTIMATE]` |
| J5 marketplace | browse / booking / consultation reads | 0.2 | `[ESTIMATE]` |
| **Bottom-up total** | | **≈ 19 req/user/day** | `[ESTIMATE]` |
| **Planning figure used below** | reconciles with `10-COST-MODEL.md` (~1,500 req/user/month ≈ 50/day) | **50 req/user/day** | `[ESTIMATE]` |

**Aggregate at 50 users** (planning figure, ~2.6× the bottom-up model for headroom):

| Quantity | Value | Tag |
|---|---|---|
| Requests / day | 2,500 | `[DERIVED]` from 50 × 50 |
| Mean sustained rate | **0.03 rps** | `[DERIVED]` |
| Rate in a 4-hour evening peak carrying 60% of traffic | **0.10 rps** | `[ESTIMATE]` (traffic shape) |
| Peak-minute burst (reminder window, all cohorts open the app) | **~1 rps** | `[ESTIMATE]` |
| Document uploads / day (whole cohort) | ≈ 7 | `[DERIVED]` from 4 docs/user/month |
| Meto messages / day (whole cohort) | ≈ 33 | `[DERIVED]` from 20 msg/user/month |

**Conclusion:** raw request rate is **not** the constraint at this scale — a single 0.5-vCPU replica is two to three orders of magnitude away from RPS saturation. The constraints are (a) long-held resources during OCR and AI calls, and (b) query shapes that grow with per-patient history. Those are sized in §4–§5.

---

## 2. Per-endpoint cost — derived from source

Query counts are read off the code and are `[DERIVED]`; wall-clock and CPU columns are `[ESTIMATE]` until §8 is run.

| Endpoint | DB statements per call | Long pole | Wall clock (unmeasured) |
|---|---|---|---|
| `GET /patients/{id}/dashboard` | **7 + N** where N = active schedules: `sweep_missed` (1) + one `materialize_due` per active schedule (`app/services/patient_dashboard.py:44-51`) + 4 reads (`:54-111`) + commit. **It is a write-on-read endpoint.** | DB round-trips + commit | 30–120 ms `[ESTIMATE]` |
| `GET /patients/{id}/health-timeline` | **8 unbounded SELECTs** (`app/api/v1/routes/health_timeline.py:110,125,136,148,156,166,170,175`) + in-process engine build (`:197-210`) | full per-patient row materialisation; `limit` applied only in memory | 50 ms empty → seconds at multi-year history `[ESTIMATE]` |
| `GET /patients/{id}/metrics` | 1 SELECT capped at `limit=100` (`app/services/health_metrics.py:87-104`) **+ 1 audit INSERT + commit** (`:106-114`) | write amplification on a read path | 20–60 ms `[ESTIMATE]` |
| `POST /documents/{upload_id}/finalize` | ~6 statements (`app/services/mdi/service.py:141-275`) + 1 INSERT per candidate | **OCR call — dominates by 2–3 orders of magnitude** (§6) | seconds to minutes `[ESTIMATE]`; hard ceiling analysis in §6 |
| `PUT /documents/blob/{token}` | 0 | blocking disk write of up to 10 MB **on the event loop** (`app/api/v1/routes/documents.py:257,273`; PROD-F15) | 10–200 ms `[ESTIMATE]` |
| `POST /meto/chat` | **≥12**: consent load + ~10 context-builder statements (`app/ai/context/builder.py`, 10 query sites) + history (`app/services/meto_chat.py:141`) + conversation/message/audit writes | **LLM call** (§7) | 2–40 s `[ESTIMATE]` |

Two structural notes that matter more than the numbers:

1. **`/meto/chat` runs synchronous SQLAlchemy inside an `async def`.** The route is `async` (`app/api/v1/routes/meto.py:59`), and `MetoChatService.chat` builds context with a blocking session on the same coroutine (`app/services/meto_chat.py:112-119`). Those ~12 statements therefore block the **single** event loop of the **single** worker — delaying every other request, including in-flight SSE streams from `/meto/chat/stream`.
2. **`/dashboard` mutates on GET.** It sweeps and materialises doses before reading (`patient_dashboard.py:44-51`) — correct for freshness (a prior review P1), but it makes a read endpoint a write endpoint, so it takes a DB connection for its full duration and contends on commit.

---

## 3. Resource ceilings on one replica

| Resource | Configured value | Source | Implication |
|---|---|---|---|
| CPU | 0.5 vCPU | `azure-staging.yml:227` | any CPU-bound work (local OCR, PDF rasterization) runs at half a core |
| Memory | 1.0 GiB | `azure-staging.yml:227` | a 10 MB upload is fully buffered in memory (`documents.py:263`), then re-buffered on accept (`mdi/service.py:263`) |
| Worker processes | 1 | `backend/Dockerfile:46` | one event loop; one process kill takes down all in-flight requests |
| Sync-route threadpool | **40** | `[MEASURED]` — `anyio.to_thread.current_default_thread_limiter().total_tokens` → `40` | max 40 concurrent sync (`def`) routes |
| DB connections | **15** (`pool_size=5` + `max_overflow=10`, SQLAlchemy defaults) | `app/core/database.py:32` passes no pool args | **the real concurrency ceiling** |
| Request timeout | 120 s (gunicorn), then SIGKILL | `backend/Dockerfile:46` | see §6/§7 — two code paths can exceed it |
| Upload size | 10 MB | `app/core/config.py:135`, enforced `documents.py:264-266` | |
| Document pages | 20 | `app/core/config.py:96`, enforced `mdi/service.py:185-190` | 20 pages × per-page OCR cost is the worst-case finalize |

**Derived concurrency ceiling:** because `get_session` holds its connection for the whole request (`app/core/database.py:69-75`) and finalize queries the DB before OCR (`mdi/service.py:156`), **15 simultaneous document finalizes exhaust the connection pool**; the 16th and beyond wait 30 s on checkout and then 500. A practical safe ceiling is **~10 concurrent OCR requests** on this replica. At the pilot's ≈7 uploads/day (§1) this is never approached — but it is the number that must be respected if uploads are ever batch-triggered (e.g. a "import all my documents" flow or a migration script).

---

## 4. Headroom verdict for the pilot

| Dimension | Pilot demand | Ceiling | Headroom | Tag |
|---|---|---|---|---|
| Request rate | ~1 rps peak-minute | ≫ 50 rps for JSON endpoints | ≫ 50× | `[ESTIMATE]` |
| Concurrent OCR | ~1 (7 uploads/day) | ~10 safe / 15 hard | ≫ 10× | `[DERIVED]` |
| Concurrent AI | ~1 (33 msgs/day) | event-loop-bound; see §7 | adequate | `[DERIVED]` |
| DB connections | ~2 steady | 15 | ~7× | `[DERIVED]` |
| Blob storage | 50 users × 10 MB = **500 MB** | container filesystem, **no volume** | irrelevant — **data is lost on redeploy** (PROD-F1) | `[DERIVED]` |
| Memory | 1–2 buffered uploads ≈ 20–40 MB peak | 1.0 GiB | ample | `[ESTIMATE]` |

**Verdict: capacity is not a pilot blocker.** The 50-user pilot fits within one replica with large margin on every dimension. The risks in this workstream are **failure modes**, not saturation: two request paths can outlive the worker timeout (§6, §7), and one endpoint's cost grows without bound with patient history (§5).

---

## 5. What degrades first — ranked, with source evidence

**1. `POST /documents/{upload_id}/finalize` — synchronous OCR inside the HTTP request.**
`documents.py:229` → `mdi.finalize_upload` → `_run_extraction` → `run_pipeline` (`mdi/service.py:260-261, 343-347`) → `run_ocr`. The entire OCR is in-request; there is no queue on this path (the asyncio OCR worker `MCP_OCR_WORKER_ENABLED` is explicitly **false** in both deploy envs, `azure-staging.yml:208`, and belongs to the separate lab pipeline anyway). One user uploading a 20-page document occupies a thread **and** a DB connection for the whole OCR duration. Ceiling arithmetic in §6.

**2. `POST /meto/chat` — blocking DB on the event loop + an unbounded retry budget.**
See §2 note 1 and §7. The retry budget (up to 180 s) exceeds the 120 s worker timeout; when the worker is killed, **all** concurrent requests on the replica die, not just the chat.

**3. `GET /patients/{id}/health-timeline` — 8 unbounded queries, `limit` applied in memory.**
`health_timeline.py:110-182` materialises every lab result, medication, **dose occurrence**, document and confirmed candidate for the patient, then hands `limit` to the in-process engine (`:209`). Date filters are pushed to SQL for only 3 of the 8 sources. The dose table is the growth driver: a patient on 3 medications at 2 doses/day generates **6 `DoseOccurrence` rows/day ≈ 2,190/year** (`app/services/medication_schedule.py` materialisation, model at `app/models/medication_schedule.py:90-120`), all of which are fetched on every timeline call forever. At pilot durations (weeks) this is a few hundred rows and invisible; at a year of real use it is thousands of rows and megabytes of Python objects per request on a 0.5-vCPU box. **This is the endpoint that will degrade first in calendar time, not in load.** (PROD-F16.)

**4. `GET /patients/{id}/dashboard` — write-on-read with a per-schedule loop.**
`patient_dashboard.py:44-51` issues one `materialize_due` per active schedule inside a Python loop — a genuine N+1 in statement count (bounded by a patient's schedule count, realistically <10) — and commits on every dashboard open (3×/user/day). Fine at pilot scale; it is the reason dashboard is a write path in the DB-connection accounting of §3.

**5. Connection-pool exhaustion (PROD-F12).** 40 threads against 15 connections. Any event that makes requests slow (a cloud-OCR stall, a Postgres failover, a `pool_pre_ping`-less stale connection) converts latency into a pool queue, and the queue converts into 500s after 30 s. This is the most likely mechanism by which a single slow dependency becomes a full outage on this deployment.

**6. `GET /patients/{id}/metrics` — audit INSERT + commit per read** (`health_metrics.py:106-114`). Correct for compliance; it doubles the DB cost of the most-called read and makes reads contend on write locks. Not a pilot problem; note it before any read-heavy scaling.

---

## 6. OCR cost and its effect on the request path

### 6.1 What actually runs — correct this first

The plan of record (`00-CURRENT-STATE.md` §3, `10-COST-MODEL.md`) is *local Tesseract, cloud fallback OFF, $0 marginal*. **The deployed configuration does not match.** `run_ocr` prefers Azure Document Intelligence over Tesseract whenever the credentials are present, and **never checks `FeatureFlag.OCR_CLOUD_FALLBACK`** (`app/services/ocr_engine.py:479-500`; `configured()` is env-presence only, `:254-256`). Both workflows inject those credentials (`azure-staging.yml:213-214`, `azure-production.yml:226-227`). **Therefore, on staging today, OCR is a cloud call and Tesseract never executes.** This is filed as **PROD-F7 (P0)** in `01-PRODUCTION-READINESS-MATRIX.md` §4. The two sub-sections below size both engines, because the correct end-state (Tesseract primary) and the current state (Azure DI) have very different cost profiles.

### 6.2 Local Tesseract — `[MEASURED]`, with caveats

Measured this session, dev laptop (Apple silicon, macOS), `tesseract 5.5.2`, `lang=vie+eng`, `--psm 6`, on a **synthetic clean-text** VN prescription page rendered at two resolutions:

| Page | Wall clock | Child CPU | Text extracted |
|---|---|---|---|
| 1240 × 1754 (≈150 dpi A4) | 2.46–2.54 s | **1.63–1.72 s** | 1,907 chars |
| 2480 × 3508 (≈300 dpi A4) | 2.81–4.99 s | **1.96–2.07 s** | 1,909 chars |

Caveats that make this a **lower bound**, not a production number:
- Synthetic, perfectly clean, machine-rendered text. Real inputs are phone photos with skew, glare and noise — Tesseract is materially slower and less accurate on those.
- Apple-silicon dev hardware vs a **0.5 vCPU** x86 ACA container. A conservative derivation is **3–6× more CPU seconds** and, because the CPU quota is half a core, **wall time ≈ 2× CPU time**: **≈ 5–12 s CPU and ≈ 10–25 s wall per page** in-container `[DERIVED]`.
- The repo contains no real document fixtures to measure against (`backend/app/fixtures/qa_prescription.png` is a 1×1 px, 70-byte placeholder; the `.pilot-secrets` fixture is a 600×400 image yielding 0 characters). §8 step 3 fixes this.

**Request-path implication at the derived rate:** a 1-page document ≈ 10–25 s of a 120 s budget — acceptable. A **20-page** document (the configured maximum, `config.py:96`) would be 200–500 s and **cannot complete** within the worker timeout. Two mitigations already exist but are not wired on this path: `ocr_pdf_max_pages = 3` (`config.py:141`) is used by the lab pipeline (`app/services/lab_upload.py:169-171`), **not** by MDI, and MDI passes the whole file as a single "page" (`mdi/service.py:343-347`) which Tesseract cannot decode at all if it is a PDF (`ocr_engine.py:73-77` — PROD-F17).

### 6.3 Azure Document Intelligence — `[DERIVED]` timeout arithmetic

`AzureDocIntelEngine` submits synchronously and polls a long-running operation (`ocr_engine.py:269-326`) with `_SUBMIT_TIMEOUT_S = 30`, `_POLL_TIMEOUT_S = 30`, `_POLL_MAX_ATTEMPTS = 30`, `_POLL_INTERVAL_S = 1.0`, `_POLL_BACKOFF_CAP_S = 5.0` (`:247-251`). Realistic worst case with the service returning `retry-after: 5`: 30 s submit + 30 × 5 s sleep = **≈ 180 s**, before counting the poll requests themselves; the pathological bound (every poll itself timing out) is far higher. **All of it is inside the HTTP request**, and all of it exceeds gunicorn's `--timeout 120`.

> ### PROD-F19 — **P1** · Synchronous document finalize can outlive the worker timeout and kill the replica
> `POST /documents/{upload_id}/finalize` performs OCR in-request (`documents.py:229` → `mdi/service.py:260-261`). Either engine can exceed 120 s: cloud DI by its own poll budget (≈180 s, `ocr_engine.py:247-251`), local Tesseract by page count (20 pages × 10–25 s derived). Gunicorn then SIGKILLs the single worker (`backend/Dockerfile:46`), taking **every** concurrent request with it, and the client sees a connection reset with the document left mid-pipeline (recoverable — the quarantine object survives by design, `mdi/service.py:246-252`, and finalize is retryable).
> **Fix:** (a) bound the OCR call — cap the DI poll budget at ~60 s (`_POLL_MAX_ATTEMPTS` × cap, or an explicit deadline) and cap MDI pages via `settings.ocr_pdf_max_pages` after rasterization; (b) preferably move extraction off the request path: return `202` from finalize with `status=processing` and run `_run_extraction` in a background task/queue, letting the existing `GET /documents/{id}/extraction` polling surface the result. (b) also removes the DB-connection-hold in §3.

### 6.4 Cost

With cloud DI actually in use (§6.1), `10-COST-MODEL.md`'s "$0 marginal OCR" line is wrong for the current deployment. At the modelled 6 pages/user/month and Azure DI read pricing ≈ $1.50/1,000 pages: 50 users ≈ **$0.45/month** `[DERIVED]` — financially trivial, which is precisely why cost must not be the reason this is treated as low-priority. The issue is the **authorization/consent posture**, not the money.

---

## 7. Meto AI — latency and token budget

| Item | Value | Source | Tag |
|---|---|---|---|
| Per-attempt provider timeout | 30 s | `app/ai/providers/openai_provider.py:33` | `[DERIVED]` |
| Retries per provider | 3 attempts (`_MAX_RETRIES = 2`) | `:31` | `[DERIVED]` |
| Providers tried | whole chain, sequentially | `app/ai/registry.py:207-244` | `[DERIVED]` |
| **Worst-case wall clock** | 2 providers × 3 × 30 s = **180 s** > `--timeout 120` | above + `backend/Dockerfile:46` | `[DERIVED]` — **PROD-F10** |
| Declared timeout setting | `meto_timeout_seconds = 30` — **never referenced in code** | `app/core/config.py:75`; `grep -rn "meto_timeout_seconds" app/` returns only the definition | `[DERIVED]` |
| Max output tokens | 2,048 | `app/core/config.py:74`, passed at `app/services/meto_chat.py:161-167` | `[DERIVED]` |
| History window | last 20 messages, **by count, not tokens** | `app/ai/prompt/assembler.py:218` | `[DERIVED]` |
| Per-message input cap | 4,000 chars | `app/schemas/meto.py:17` | `[DERIVED]` |
| Context block truncation | **none** — no token budget is applied to the assembled context | `app/ai/prompt/assembler.py:196-222` (no truncation logic) | `[DERIVED]` |

**Token budget.**

| Scenario | Input tokens | Output tokens | Cost/message | Tag |
|---|---|---|---|---|
| Cost-model assumption | 1,500 | 500 | $0.012 | from `10-COST-MODEL.md` |
| Typical (short question, small record) | 1,500–3,000 | 300–800 | $0.01–0.03 | `[ESTIMATE]` |
| **Worst case** — 20 history messages × 4,000 chars ≈ 80k chars ≈ **27k tokens** (VN ≈ 3 chars/token) + context block | **~30,000** | 2,048 | **~$0.12** | `[ESTIMATE]` |

The worst case is **~10× the modelled cost per message**, is reachable by an ordinary long conversation (no exploit needed), and is not bounded by anything — there is no per-user cap on `/meto/chat` at all (**PROD-F11**). At 50 users this is at most a few dollars; the control matters before the cohort grows, and `10-COST-MODEL.md` already names AI as the dominant and most abuse-sensitive lever.

**Latency.** First-token and completion latency are **UNMEASURED** — no timing instrumentation exists on this path beyond the generic middleware histogram (`app/core/middleware.py:87-89`), and that is process-local and never scraped (WS5-F1). Streaming exists (`app/api/v1/routes/meto.py:91-121`, SSE with `X-Accel-Buffering: no`), so perceived latency should be first-token-bound; §8 step 5 measures it.

---

## 8. Load-test plan — converting estimates into measurements

Run against **staging with synthetic accounts only**. Do not point a load generator at any environment holding real data. Record every result in `docs/launch-readiness/evidence/` and update this file's tags from `[ESTIMATE]` to `[MEASURED]`.

**Step 0 — establish the baseline environment.**
```bash
az containerapp show -g rg-metocare-staging -n ca-metocare-backend \
  --query "{cpu:properties.template.containers[0].resources.cpu, mem:properties.template.containers[0].resources.memory, min:properties.template.scale.minReplicas, max:properties.template.scale.maxReplicas, mode:properties.configuration.activeRevisionsMode}"
curl -s https://<backend-fqdn>/api/v1/info | jq '{env, ocr_mode, storage_mode, migration_version, feature_flags}'
```
Record the CPU/memory actually deployed (§ assumes 0.5/1.0 from the workflow) and note that `ocr_mode` in `/info` is **not** the engine actually used (§6.1).

**Step 1 — per-endpoint latency under no load (establishes the floor).** Seed one synthetic patient with a realistic record (≥90 days of metrics, ≥3 medications with schedules, ≥5 documents), then:
```bash
for p in dashboard health-timeline metrics; do
  hey -n 200 -c 1 -H "Authorization: Bearer $TOKEN" \
      "https://<fqdn>/api/v1/patients/$PID/$p" | tee evidence/perf-$p-c1.txt
done
```
Capture p50/p95/p99. Repeat at `-c 5` and `-c 20` to find the knee.

**Step 2 — timeline growth curve (validates §5 item 3).** Seed three synthetic patients with 1 month / 6 months / 24 months of dose occurrences and lab results; run step 1 against each and plot p95 vs row count. Expected: linear in `DoseOccurrence` rows. This is the single most informative test in this plan.

**Step 3 — real OCR cost (replaces §6.2's synthetic measurement).** Collect 10 representative **synthetic-but-realistic** VN documents (phone photos of printed prescriptions/lab reports containing no real patient data), then time both engines in-container:
```bash
az containerapp exec -g rg-metocare-staging -n ca-metocare-backend --command /bin/bash
# inside the container:
time tesseract page.png - -l vie+eng --psm 6 >/dev/null
```
Record CPU and wall time per page at the real 0.5-vCPU quota. Then time `POST /documents/{id}/finalize` end-to-end for 1-, 3- and 20-page documents and confirm against the 120 s budget (PROD-F19).

**Step 4 — concurrency ceiling (validates §3's 15-connection claim).** Fire 20 concurrent finalizes of a 1-page document and watch for `QueuePool limit ... reached` in the container logs:
```bash
az containerapp logs show -g rg-metocare-staging -n ca-metocare-backend --follow \
  | grep -iE "QueuePool|TimeoutError|WORKER TIMEOUT"
```
Expect failures beyond ~15 in flight. If none appear, the derived pool size is wrong — re-derive from `app/core/database.py`.

**Step 5 — Meto latency and token accounting.** With `FEATURE_AI_ASSISTANT=true` on staging and a synthetic account, send 20 messages of increasing history depth (1 → 20 turns) and record time-to-first-token (streaming) and total wall clock; simultaneously log the provider's reported `usage` (input/output tokens) to validate §7's worst case. Then deliberately point the primary provider at an unreachable base URL to time the **failure** path and confirm whether it exceeds 120 s (PROD-F10).

**Step 6 — soak.** 2 hours at the modelled peak (1 rps mixed read traffic) with `pool_pre_ping` absent, to see whether stale-connection 500s appear after idle periods (PROD-F12 / WS5-F5).

**Exit criteria for this workstream to move from ⏳ to ✅:** steps 1–5 completed with results recorded; p95 for dashboard/timeline/metrics < 500 ms at 24 months of synthetic history; no path capable of exceeding the worker timeout (PROD-F10, PROD-F19 closed); pool-exhaustion threshold measured and documented in `12-PILOT-OPERATIONS-RUNBOOK.md`.

---

## 9. Explicitly UNMEASURED

Everything below is asserted nowhere in this document as fact:

- Real p50/p95/p99 for every endpoint — no APM, and the in-process histogram (`app/core/middleware.py:87-89`) is never scraped (WS5-F1).
- Actual container CPU/memory utilisation under load — no metrics pipeline.
- Real Tesseract or Azure DI timing **in-container** at 0.5 vCPU (§6.2 is a laptop measurement on synthetic input; §6.3 is timeout arithmetic).
- Meto first-token and completion latency, and real token usage per message.
- Postgres SKU, `max_connections`, IOPS and current row counts — run `az postgres flexible-server show -g rg-metocare-staging -n psql-metocare-staging` and `SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC LIMIT 20;`.
- Cold-start time from ACA scale-to-zero — not applicable while `--min-replicas 1`, but relevant if that ever changes.
- Mobile-side performance (render, bundle, battery) — out of scope here; see `11-MOBILE-DISTRIBUTION.md`.
