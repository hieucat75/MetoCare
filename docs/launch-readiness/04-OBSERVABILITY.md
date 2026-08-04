# 04 — Observability Assessment (WS4/WS5)

**Date:** 2026-08-04 · **Branch:** `feat/patient-platform-journey2` @ `6ab3b04` · **Assessor:** independent Observability & Analytics assessor (fresh context, direct source inspection — no prior summary trusted).
**Method:** every claim below is anchored to `file:line` or a command. Anything not provable from the repo is marked **UNVERIFIED** with the exact command to run.

---

## 1. Verdict

> **A ≤50-user pilot can detect that the *backend* is failing. It cannot detect that the *product* is failing, and it cannot detect that the *app* crashed.**

Concretely: an HTTP 500 storm, a latency regression, or a hard outage will show up in the container's stdout stream. But an uncaught JS error on a tester's phone produces **no retrievable record anywhere** (§WS4-F1), a tester's bug report **cannot be joined to a backend log line** (§WS4-F2), a credential-stuffing burst leaves **no attributable trace** (§WS4-F3), and every product-funnel question ("did anyone finish a document import?") is answerable only by hand-querying Postgres.

The foundation is genuinely good — structured JSON logs with an allow-listed `extra`, request-id correlation, a PHI-free append-only audit log with 100+ distinct actions, and a Meto audit table that already records provider/latency/token/safety metadata. The gap is not design; it is **the last mile**: nothing is aggregated, nothing is alerted on, and the mobile tier is instrumented but sinkless.

**Recommendation:** 🟡 **READY-WITH-ACCEPTED-LIMITATION for a controlled synthetic-data pilot**, conditional on closing WS4-F1, WS4-F2, WS4-F3 and standing up the zero-vendor Log Analytics baseline in §6. **NOT READY** for a real-PHI pilot or public beta.

---

## 2. Inventory — what exists TODAY

| Component | Where | State |
|---|---|---|
| Structured JSON log formatter | `backend/app/core/logging.py:32-47` | ✅ real, PHI-conscious |
| Log allow-list for `extra` | `backend/app/core/logging.py:18-20` | ✅ real (7 fields) |
| Correlation context vars | `backend/app/core/context.py:8-10` | ✅ real |
| Request-id middleware + access log | `backend/app/core/middleware.py:64-111` | ✅ real |
| In-process metrics registry | `backend/app/core/metrics.py:23-76` | 🟡 real but process-local |
| `/metrics` Prometheus endpoint | `backend/app/main.py:181-185` | 🟡 real, **unauthenticated** |
| `/health` (liveness + DB probe) | `backend/app/api/v1/routes/system.py:17-35`, `backend/app/main.py:177-179` | ✅ real |
| `/info` (version/flags) | `backend/app/api/v1/routes/system.py:38-66` | 🟡 real, **unauthenticated** |
| Append-only audit log | `backend/app/services/audit.py:14-44`, model `backend/app/models/governance.py:57-80` | ✅ real, 127 call sites |
| Audit retention purge | `backend/app/services/audit_retention.py:43-71` | 🟡 code real, **never scheduled** |
| Maintenance job entrypoint | `backend/app/jobs/maintenance.py:23-47` | 🟡 code real, **never invoked** |
| Meto AI telemetry table | `backend/app/models/meto.py:91-117`, written at `backend/app/services/meto_chat.py:641-659` | ✅ real, rich, PHI-free |
| Mobile Monitor abstraction | `mobile/src/lib/monitor.ts:25-117` | 🟡 real API, **no-op sink in release** |
| Mobile root ErrorBoundary | `mobile/src/components/ErrorBoundary.tsx:23-62`, wired `mobile/app/_layout.tsx:11,16` | ✅ real UI recovery |
| Exception aggregation (Sentry/OTel/APM) | — | ⛔ **does not exist** (see §2.1) |
| Log aggregation / dashboard / alerting | — | ⛔ **does not exist** |
| Distributed tracing | — | ⛔ **does not exist** |
| Analytics instrumentation | — | ⛔ **does not exist** (see `05-ANALYTICS-EVENT-CATALOG.md`) |

### 2.1 Negative results (verified absences — these matter as much as the positives)

```
$ grep -rn "APPLICATIONINSIGHTS\|applicationinsights\|opentelemetry\|azure.monitor\|opencensus\|sentry" \
    backend/ mobile/src mobile/package.json frontend/package.json \
    --include="*.py" --include="*.txt" --include="*.json" --include="*.ts" --include="*.tsx"
# → zero matches
```

- No APM/error-reporting SDK is a dependency of any tier (`backend/requirements.txt` — full file inspected; `mobile/package.json`; `frontend/package.json`).
- **But** `APPLICATIONINSIGHTS_CONNECTION_STRING=secretref:appi` **is** injected into the container on both staging (`.github/workflows/azure-staging.yml:203`) and production (`.github/workflows/azure-production.yml:218`). It is dead config — see **WS4-F4**.
- No Prometheus/Grafana/scrape config anywhere in `.github/workflows/`, `backend/Dockerfile`, `backend/startup.sh`.
- No cron, timer, scheduled ACA Job, or workflow schedule invokes `app.jobs.maintenance` (grep across `*.py`, `*.yml`, `*.sh`, `Dockerfile*`: only the module itself and `backend/tests/test_hardening.py:17,102`).

---

## 3. The four-signal view

### 3.1 Logs — **available today: YES (structured), NO (aggregated)**

**Evidence.** `setup_logging()` (`backend/app/core/logging.py:50-60`) strips every root handler and installs one `StreamHandler` with `JsonFormatter` + `ContextFilter`. Every line is a single JSON object with `ts`, `level`, `logger`, `message`, `request_id`, `user_id`, plus any of 7 allow-listed extras (`logging.py:18-20`). `ObservabilityMiddleware` emits one `http_request` line per request with method / route-template / status / duration (`middleware.py:96-105`).

Correlation: the middleware accepts an inbound `X-Request-ID`, else mints a uuid4 hex (`middleware.py:66`), binds it to a `ContextVar` (`context.py:8`), echoes it on the response (`middleware.py:107`), and `app/api/deps.py:107` stamps `request.state.user_id` so the access line is user-attributed (`middleware.py:81-82`).

Transport: gunicorn + `UvicornWorker`, one worker, `--access-logfile '-' --error-logfile '-'` (`backend/startup.sh:12-20`); the container CMD is equivalent (`backend/Dockerfile` final line). So everything lands on stdout/stderr → the ACA console log stream.

**Gap.** Nothing reads that stream. There is no saved query, no workbook, no alert rule, and no evidence the ACA environment `cae-metocare-staging` is even attached to a Log Analytics workspace — the environment is pre-existing and is never created by the workflows (`.github/workflows/azure-staging.yml:27` only *references* `ENV_NAME`).
**UNVERIFIED — run:** `az containerapp env show -g <rg> -n cae-metocare-staging --query "properties.appLogsConfiguration"` and `az monitor log-analytics workspace list -g <rg> -o table`.

Second gap: **stack traces are discarded.** `JsonFormatter` records `exc_type` only and never formats `exc_info` into the payload (`logging.py:45-47`). See **WS4-F7**.

### 3.2 Metrics — **available today: PARTIALLY (emitted), NO (collected)**

**Evidence.** Eight metric series exist, total:

| Metric | Emitted at | Labels |
|---|---|---|
| `http_requests_total` | `middleware.py:85` | method, path, status |
| `http_request_duration_seconds` (histogram, 11 buckets) | `middleware.py:86-90`, buckets `metrics.py:13` | method, path |
| `http_server_errors_total` | `middleware.py:92-94` | method, path |
| `llm_rag_augmented_total` | `app/llm/gateway.py:46` | — |
| `llm_cache_hits_total` | `app/llm/gateway.py:90` | — |
| `llm_requests_total` | `app/llm/gateway.py:91,113,122` | result |
| `llm_blocked_total` | `app/llm/gateway.py:112` | — |

That is the complete set (`grep -rn "inc_counter\|registry.observe" backend/app`).

**Gap 1 — the LLM metrics do not cover the pilot's AI.** `app/llm/gateway.py` is imported only by `app/services/ai_assistant.py:20` (the legacy `/ai` surface). The Meto chat path used by the mobile app (`app/services/meto_chat.py`, routes `app/api/v1/routes/meto.py:58,90`) emits **zero** metrics. Its telemetry is the DB table `meto_audit_logs` instead — good data, but it is not a metric and nothing reads it.

**Gap 2 — process-local, unscraped, reset on deploy.** `registry` is a module-level plain object (`metrics.py:76`) holding `defaultdict`s. Values live only in the worker process; a revision update, a scale event, or a crash zeroes them. **WS5-F1 is CONFIRMED.** ACA runs `--min-replicas 1 --max-replicas 1` (`azure-staging.yml:222`), so there is at least no split-brain — but there is also no history.

**Gap 3 — the endpoint is public.** See **WS4-F5**. **Gap 4 — cardinality is externally controllable.** See **WS4-F6**.

### 3.3 Traces — **available today: NO**

No OpenTelemetry, no span propagation, no cross-service context beyond `X-Request-ID`. For a single-process modular monolith with one replica and ≤50 users this is **an acceptable, deliberate omission** — the request-id + access-log join gives you the same forensic power at 1% of the cost. Revisit when a second service or a background worker fleet appears.

The one place a trace would already earn its keep: the Meto provider fallback chain (`app/ai/registry.py:236-240`) and the MDI OCR pipeline (`app/services/mdi/pipeline.py:77-94`), where latency is multi-stage. Both are currently observable only as a single wall-clock number.

### 3.4 Errors / crashes — **available today: NO (both tiers)**

**Backend.** No aggregation. An unhandled exception becomes a 500 counted by `http_server_errors_total` and logged with `exc_type` but **no stack** (§3.1). There are five domain exception handlers that convert known failures into clean envelopes (`backend/app/main.py:110-175`) — good hygiene, but they also mean those failures never reach any error channel at all. `UndecryptablePHIError` is the only one that logs (`main.py:165`), and it deliberately logs no detail.

**Mobile.** Commit `9692bb3` added the right *shape*: a root `ErrorBoundary` (`mobile/src/components/ErrorBoundary.tsx:23`) wired at `mobile/app/_layout.tsx:16`, a global JS handler installed at module load (`mobile/app/_layout.tsx:11` → `mobile/src/lib/monitor.ts:101-111`), redaction (`monitor.ts:33-40`), and a pluggable `MonitorAdapter` (`monitor.ts:25-27, 64-66`). **But the only adapter that ships is `ConsoleMonitorAdapter`, whose `capture()` body is wrapped in `if (__DEV__)` (`monitor.ts:53-58`) — in the release APK the pilot installs, it does nothing.** `setMonitorAdapter` is never called outside `mobile/__tests__/monitor.test.ts`. See **WS4-F1**.

Additionally, `captureException` is called from exactly two places — the boundary and the global handler (`grep -rn "captureException" mobile/src mobile/app`). **API failures are not captured at all**: `mobile/src/api/client.ts:204-207` throws `ApiError` and every screen renders it locally. A 500 storm on document finalize is invisible from the app side.

---

## 4. PHI-safety review of every telemetry channel

This is the section that matters most. Each channel is rated on whether PHI, credentials, or free text can escape through it.

### 4.1 Channel matrix

| # | Channel | Sink | Carries PHI? | Verdict |
|---|---|---|---|---|
| 1 | `http_request` access log | container stdout | No (route template + status + ms) | ✅ SAFE — with the 404 caveat (WS4-F6) |
| 2 | Log `extra` fields | container stdout | No — hard allow-list of 7 keys, everything else dropped (`logging.py:18-20, 42-44`) | ✅ SAFE by construction |
| 3 | **Log `message` (interpolated args)** | container stdout | **Possible** — `record.getMessage()` (`logging.py:38`) runs `%`-interpolation *before* any filter; ~16 sites interpolate an exception | ⚠️ **RISK — WS4-F8** |
| 4 | `exc_info` | container stdout | No — only `exc_type` name is kept (`logging.py:45-47`) | ✅ SAFE (over-safe — WS4-F7) |
| 5 | uvicorn/gunicorn own loggers | container stdout | Unknown — `setup_logging` reconfigures only the **root** logger (`logging.py:51-60`); `uvicorn.error` may not propagate | ⚠️ **UNVERIFIED — WS4-F7** |
| 6 | `/metrics` render | HTTP, public | No PHI. Discloses route inventory + traffic + error counts | ⚠️ **RISK — WS4-F5** |
| 7 | `/info` | HTTP, public | No PHI. Discloses env, modes, migration rev, every flag | ⚠️ MINOR — WS4-F12 |
| 8 | `/health` | HTTP, public | No — `{"status","db"}` only (`system.py:31`) | ✅ SAFE |
| 9 | `AuditLog` rows | Postgres | No — schema is ids/enums; docstring is explicit (`governance.py:58`); all 20 inspected `details=` payloads are id/enum/status pairs | ✅ SAFE |
| 10 | `MetoAuditLog` rows | Postgres | No — no message content, no health values (`models/meto.py:94-95`); fields are provider/flags/latency/tokens | ✅ SAFE |
| 11 | In-app `Notification` rows | Postgres | **Yes, by design** — `title`/`body` include the medication name (`app/services/medication_schedule.py:291-294`) | ✅ ACCEPTABLE — patient's own access-controlled record; the PHI-free `metadata` is what any future push transport carries (`app/services/notification_transport.py:44-47, 60-70`) |
| 12 | Deterministic notification sink | in-memory + log | No — logs `event` + `user_id` via allow-listed extras (`app/services/notifications.py:34`) | ✅ SAFE |
| 13 | Mobile monitor payload | `console.error` in dev only | No — message/stack redacted (`monitor.ts:33-40, 78-79`), context is app/device metadata only (`monitor.ts:42-49`), component props/state never captured (`ErrorBoundary.tsx:30-33`) | ✅ SAFE — but also inert (WS4-F1) |
| 14 | Mobile fallback UI | screen | No — generic Vietnamese copy, raw error never rendered (`ErrorBoundary.tsx:46-49`) | ✅ SAFE |
| 15 | OCR dataset export | container disk | **Yes** — writes extracted rows with `contains_phi=True` until manually reviewed (`app/domain/ocr_dataset_export.py:1-11`) | ✅ CONTROLLED — fail-closed double gate: env ∈ {staging,dev} **AND** `MCP_OCR_DATASET_EXPORT_ENABLED` (default `False`, `config.py:139`), OR explicit per-user consent (`ocr_dataset_export.py:49-56`) |
| 16 | DEBUG-level extractor logs | container stdout | **Yes if enabled** — logs verbatim OCR'd test names (`app/domain/lab_table_extractor.py:980`) | ⚠️ **RISK — WS4-F9** |

### 4.2 The three real leak paths, in priority order

**(a) Exception text in the log `message` — WS4-F8, CONFIRMS and sharpens WS5-F7.**
The allow-list at `logging.py:18-20` is a genuinely good design, but it guards only the `extra` dict. `JsonFormatter.format` calls `record.getMessage()` (`logging.py:38`), which interpolates positional args into the message string *before* the formatter can inspect anything. Sixteen sites pass an exception object:

`app/ai/context/builder.py:329, 388, 457, 499, 571, 637, 693` · `app/services/meto_chat.py:117, 175, 279, 361, 660` · `app/services/lab_pipeline.py:120, 225` · `app/services/ocr_case.py:144` · `app/knowledge/registry.py:58`

Most of these sit inside broad `except Exception as exc:` blocks wrapping **SQL reads of PHI tables** (`builder.py:571` wraps the recent-labs query; `builder.py:499` the medication query). SQLAlchemy's `StatementError.__str__` appends `[SQL: ...] [parameters: ...]` unless the engine is built with `hide_parameters=True` — and it is not: `create_engine(url, connect_args=connect_args, future=True)` (`backend/app/core/database.py:32`). A malformed row, a type coercion failure, or a driver hiccup on a write path therefore puts **bound parameter values into the log stream**.

*Fix (one word + hygiene):* add `hide_parameters=True` at `database.py:32`; convert the sixteen sites to `logger.warning("...", extra={"event": "..."})` and let `exc_type` carry the diagnosis. Add a test asserting `json.loads(line)["message"]` contains no `[parameters:`.

**(b) DEBUG-level document content — WS4-F9.**
`app/domain/lab_table_extractor.py:980` logs `row.original_test_name` with `%r` — that is verbatim text lifted off a patient's lab report. Default `log_level` is `INFO` (`config.py:187`) so it is dormant, but `MCP_LOG_LEVEL=DEBUG` is precisely the change an operator makes at 2am to debug a pilot OCR complaint, and it would start streaming document content into whatever aggregates stdout. *Fix:* drop the value or log a length/hash.

**(c) The uvicorn/gunicorn logger blind spot — WS4-F7.**
`setup_logging` removes handlers from the **root** logger only (`logging.py:51-56`). Under `gunicorn -k uvicorn.workers.UvicornWorker`, whether `uvicorn.error` and `gunicorn.error` propagate to root (→ JSON, traceback dropped) or keep their own handlers (→ plain-text traceback on stderr) determines whether a 500's full stack — which can embed repr'd row data — reaches the log sink unredacted. Uvicorn is not installed in this workspace, so this could not be settled statically.
**UNVERIFIED — run:** deploy, force a 500, then `az containerapp logs show -g <rg> -n ca-metocare-backend --tail 200` and check whether any non-JSON traceback lines appear. If they do, treat it as a PHI channel and fix with an explicit `dictConfig` covering `uvicorn.*` and `gunicorn.*`.

### 4.3 What the PHI review got right (worth preserving)

- The `extra` allow-list is a **default-deny** design — the correct posture, and rare.
- `exc_info` handling deliberately drops tracebacks (`logging.py:45-47`). This trades debuggability for safety; the trade is defensible for a health product, but it must be a *conscious* trade — see the WS4-F7 fix, which recovers debuggability without recovering the leak.
- `user_id` in logs is an opaque UUID, documented as such (`context.py:9-10`), never an email or phone.
- Metric labels use the **route template**, not the raw path (`middleware.py:78-79`) — so `/documents/{document_id}` never becomes a document-id enumeration in `/metrics`. (Except on 404 — WS4-F6.)
- The notification transport docstring encodes the right rule: PHI stays in the in-app DB record; anything that could leave the device carries ids only (`app/services/notification_transport.py:5-12, 44-47`).
- Meto never records message content, and the provider name is deliberately masked as `"meto"` before it reaches the audit row (`app/services/meto_chat.py:232`).

---

## 5. Corrections to the prior register

| Prior finding | Status after direct inspection |
|---|---|
| **WS5-F1** — metrics process-local, never scraped | ✅ **CONFIRMED.** `metrics.py:76` module-global; zero scrape config in any workflow. Additionally: the Meto AI path emits no metrics at all (§3.2 Gap 1). |
| **WS5-F3** — no exception aggregation either tier | ✅ **CONFIRMED**, and worse than stated for mobile: the adapter is a release-build no-op (WS4-F1), not merely "not yet remote". |
| **WS5-F6 / SEC-F4** — `/info` unauth disclosure | ✅ **CONFIRMED** (`system.py:38-66`). Restated as WS4-F12. **New, larger sibling: `/metrics` is also unauthenticated (WS4-F5).** |
| **WS5-F7** — exception text in log `message` | ✅ **CONFIRMED** and upgraded from P2 to **P1**, with a specific mechanism (SQLAlchemy bound-parameter stringification) and a one-word fix (WS4-F8). |
| **PROD-F5** — `audit_retention_*` declared, no enforcement job | ✅ **CONFIRMED and refined**: the job *does* exist and *is* tested (`app/jobs/maintenance.py:23-30`; `backend/tests/test_audit_retention.py:20`) — what is missing is purely the schedule (WS4-F10). |
| **R-02** — mobile crash/log capture not wired | 🟡 **PARTIALLY RESOLVED** by `9692bb3` (abstraction + boundary + redaction landed) but **not functionally closed** — WS4-F1. |
| `12-PILOT-OPERATIONS-RUNBOOK.md:35` — bug reports correlate "via request/correlation IDs — WS5" | ❌ **NOT ACHIEVABLE TODAY.** The mobile client neither sends nor surfaces a request id (WS4-F2). The runbook line should be corrected or the fix shipped. |

---

## 6. Minimal pilot-grade plan — zero new paid vendors

Design constraint: ≤50 users, one ACA replica, no budget line for Datadog/Sentry/Grafana Cloud, no new PHI processor agreement. Everything below runs on infrastructure already paid for.

### 6.1 Architecture (three moves)

```
  mobile ──X-Request-ID──▶ FastAPI ──JSON stdout──▶ ACA console stream
     │                        │                          │
     │                        ├─ AuditLog (Postgres)      ▼
     └─ local ring buffer     └─ MetoAuditLog          Log Analytics
        + "Send diagnostics"                          (KQL + manual review)
```

1. **Make stdout the single log bus.** Already true. Confirm the ACA environment has `appLogsConfiguration.destination = "log-analytics"` (command in §3.1). If it does not, that is a one-time owner action on Azure infra — **owner-gated per the project guardrail; do not modify the workflow as part of this program.**
2. **Make the client a first-class log participant.** Generate a uuid per request in `mobile/src/api/client.ts:176`, send it as `X-Request-ID` (the backend already honours inbound ids, `middleware.py:66`), keep the last 50 `(ts, request_id, method, path, status)` tuples in a monitor ring buffer, and expose them on a hidden diagnostics screen the tester can copy into a bug report. Cost: ~40 lines, zero dependencies.
3. **Make Postgres the product-metrics warehouse.** `audit_logs` and `meto_audit_logs` already contain the funnel (§7). A single read-only SQL script run daily produces the pilot report — no analytics vendor required for the pilot. (Instrumentation design: `05-ANALYTICS-EVENT-CATALOG.md`.)

### 6.2 The queries to run

**Log Analytics (KQL).** Table name for ACA console output is `ContainerAppConsoleLogs_CL` with the raw line in `Log_s`. **UNVERIFIED — confirm with:** `az monitor log-analytics query -w <workspace-id> --analytics-query "search * | distinct \$table" -o table`.

```kusto
// 0. Base view — parse the JSON access log once, reuse everywhere.
let reqs =
  ContainerAppConsoleLogs_CL
  | where ContainerAppName_s == "ca-metocare-backend"
  | extend j = parse_json(Log_s)
  | where tostring(j.event) == "http_request"
  | project ts=todatetime(j.ts), lvl=tostring(j.level), rid=tostring(j.request_id),
            uid=tostring(j.user_id), method=tostring(j.method), path=tostring(j.path),
            status=toint(j.status_code), ms=todouble(j.duration_ms);
```

```kusto
// 1. 5xx rate, 5-minute buckets  → alert if > 1% over 15 min
reqs | summarize errors=countif(status >= 500), total=count() by bin(ts, 5m)
     | extend error_rate = todouble(errors) / total | order by ts desc
```

```kusto
// 2. Per-endpoint failure hotspots (last 24h) → the pilot triage list
reqs | where ts > ago(24h)
     | summarize total=count(), e5=countif(status>=500), e4=countif(status between (400 .. 499)),
                 p95=percentile(ms, 95) by method, path
     | where e5 > 0 or e4 > 5 | order by e5 desc, e4 desc
```

```kusto
// 3. Auth failure burst → alert if > 20 in 5 min (see WS4-F3 for why this is the ONLY signal)
reqs | where path endswith "/auth/login" and status in (401, 423)
     | summarize failures=count() by bin(ts, 5m) | where failures > 20
```

```kusto
// 4. Full request trace for a tester's bug report
reqs | where rid == "<request-id-from-diagnostics-screen>"
```

```kusto
// 5. AI output-safety replacements (the ONLY place this is visible today — WS4-F11)
ContainerAppConsoleLogs_CL
| extend j = parse_json(Log_s)
| where tostring(j.message) startswith "Meto output failed safety check"
| summarize replacements=count() by bin(todatetime(j.ts), 1h)
```

```kusto
// 6. Provider fallback / total AI failure (app/ai/registry.py:240, app/services/meto_chat.py:175)
ContainerAppConsoleLogs_CL
| extend j = parse_json(Log_s)
| where tostring(j.message) has_any ("Provider ", "All providers failed", "Circuit OPENED")
| project ts=todatetime(j.ts), level=tostring(j.level), msg=tostring(j.message)
| order by ts desc
```

```kusto
// 7. Cold-start / restart detector — also tells you your metrics just reset (WS5-F1)
ContainerAppConsoleLogs_CL
| where Log_s has "Startup: schema managed by Alembic"     // backend/app/main.py:49
| project TimeGenerated, ContainerAppName_s | order by TimeGenerated desc
```

**Postgres (product signals).** Run read-only, from the maintenance path, never against a replica holding real PHI without authorization:

```sql
-- 8. Document funnel, last 7 days (source: app/services/mdi/service.py:134,255,485,519,533)
SELECT action, COUNT(*) FROM audit_logs
WHERE timestamp > now() - interval '7 days' AND action LIKE 'document.%'
GROUP BY action ORDER BY 2 DESC;

-- 9. Adherence actions (source: app/services/medication_schedule.py:335)
SELECT action, COUNT(*) FROM audit_logs
WHERE timestamp > now() - interval '7 days' AND action LIKE 'medication_dose.%'
GROUP BY action;

-- 10. Meto health: fallback rate, escalation rate, p95 latency (source: app/models/meto.py:91-117)
SELECT date_trunc('day', created_at) AS d,
       COUNT(*)                                         AS turns,
       AVG(fallback_used::int)                          AS fallback_rate,
       AVG(safety_flags_detected::int)                  AS safety_flag_rate,
       AVG(escalation_triggered::int)                   AS escalation_rate,
       PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY response_time_ms) AS p95_ms
FROM meto_audit_logs WHERE action = 'chat_request'
GROUP BY 1 ORDER BY 1 DESC;
```

### 6.3 What to alert on — manually, once a day, plus two synthetic checks

There is no alerting engine and there does not need to be one for 50 users. The operating model is:

| Cadence | Check | Mechanism |
|---|---|---|
| Every 5 min | `/health` returns 200 | ACA built-in health probe **UNVERIFIED — confirm:** `az containerapp show -g <rg> -n ca-metocare-backend --query "properties.template.containers[0].probes"`. If absent, a free external uptime pinger against `/health` is sufficient. |
| Every 5 min | `/info.migration_version` == expected head | one-line cron or uptime-checker keyword match; catches a half-applied migration |
| Daily (start of pilot hours) | Queries 1, 2, 3, 5, 6 above | operator runs the saved KQL set; **10 min** |
| Daily | Queries 8, 9, 10 | operator runs the SQL set; feeds the pilot KPI table in `12-PILOT-OPERATIONS-RUNBOOK.md:42-53` |
| Per bug report | Query 4 | request id from the tester's diagnostics screen (requires WS4-F2) |
| Weekly | `SELECT COUNT(*) FROM audit_logs` growth vs retention TTLs | until WS4-F10 is scheduled, this is how you notice unbounded growth |

**Escalation thresholds for the pilot** (deliberately loose — 50 users is a small denominator; a single tester can move a percentage):

| Signal | Page the operator |
|---|---|
| 5xx rate > 1% over 15 min, **or** any single 5xx on `/auth/*` or `/documents/*/finalize` | immediately |
| `/health` non-200 twice consecutively | immediately |
| Auth 401/423 > 20 in 5 min from the pilot cohort | immediately (security) |
| Meto safety-replacement count > 0 in an hour | same day, clinical review |
| `All providers failed` present at all | same day |
| Any log line matching `[parameters:` or `Traceback` | **immediately — treat as a potential PHI-in-logs incident** (this is the WS4-F8 canary) |

### 6.4 Explicitly deferred (and why that is correct)

| Deferred | Why it is right to defer |
|---|---|
| Sentry / Bugsnag | External PHI processor; needs a DPA and an owner decision. The `MonitorAdapter` seam (`monitor.ts:25-27`) makes it a 20-line swap later. |
| OpenTelemetry + tracing | One process, one replica. `X-Request-ID` gives the same forensics at a fraction of the complexity. |
| Prometheus / Grafana | Requires a scrape target and a persistent store. The stdout access log answers every question `/metrics` would, with history. |
| Application Insights SDK | Would be the *natural* choice given the connection string is already provisioned — but wiring it means a new dependency and PHI flowing into a new store. Owner decision. Until then, **delete the dead env var** (WS4-F4). |

---

## 7. The ten signals that tell you a ≤50-user pilot is failing

Ordered by how fast they turn into a bad user outcome. "Source today" is what you can compute **now**; "Gap" is what is missing.

| # | Signal | Definition | Source today (`file:line`) | Gap |
|---|---|---|---|---|
| 1 | **HTTP 5xx rate** | `5xx / total`, 5-min bins | access log `middleware.py:96-105`; counter `middleware.py:92` | none — KQL §6.2 q1 |
| 2 | **Upload→finalize failure rate** | non-2xx on `POST /documents/{upload_id}/finalize` ÷ `POST /documents/upload-session` | route templates `app/api/v1/routes/documents.py:159, 220`; success audit `app/services/mdi/service.py:134` | **failures are not audited** — only the access log has them. Acceptable; join on `path` |
| 3 | **OCR candidate rejection rate** | `document.candidate_reject ÷ (confirm + merge + reject)` — the honest proxy for extraction quality | `app/services/mdi/service.py:485, 519, 533` | none — SQL §6.2 q8. **This is the single best product-health number the pilot has.** |
| 4 | **Document acceptance conversion** | `document.accepted ÷ document.upload_session` | `mdi/service.py:255` vs `:134` | none |
| 5 | **Quarantine hold rate** | `document.quarantine_hold ÷ upload_session` — malware/oversize/malformed rejections | `mdi/service.py:218, 230` | none |
| 6 | **Reminder→action rate** | `medication_dose.taken + .skipped ÷ doses that reached state `notified`` | audit `app/services/medication_schedule.py:335`; state transition `medication_schedule.py:281-284` | **"delivered" is never recorded as an event** — WS4-F13. Must be read off `dose_occurrences.state`, and it only advances when the client polls `GET /patients/{id}/reminders/due` (`routes/medication_schedule.py:243`) |
| 7 | **AI safety-replacement rate** | fraction of Meto turns whose output was replaced by the guardrail | enforcement `app/services/meto_chat.py:203-212`; log line `:204`; boolean `models/meto.py:111` | **cannot be isolated in SQL** — the boolean merges input red-flags and output replacements (`meto_chat.py:213`) — WS4-F11. Log-only today (KQL §6.2 q5) |
| 8 | **AI availability / fallback rate** | `fallback_used` share; `All providers failed` count | `models/meto.py:110`; `app/services/meto_chat.py:175`; circuit `app/ai/registry.py:167-171` | none — SQL §6.2 q10 + KQL q6 |
| 9 | **Auth failure spike** | 401 + 423 on `/auth/login` per 5 min | access log only | **no audit record for failed login, no log/metric for lockout or rate-limit** — WS4-F3. Anonymous counts only |
| 10 | **Mobile crash-free session rate** | sessions without a fatal `captureException` | `mobile/src/lib/monitor.ts:74-86`; boundary `ErrorBoundary.tsx:33` | ⛔ **not computable** — the sink is a no-op in release (WS4-F1). The runbook's "Crash-free ≥ 99%" KPI (`12-PILOT-OPERATIONS-RUNBOOK.md:51`) is currently **unmeasurable**. |
| 11 | *(bonus)* **p95 latency by route** | histogram | `middleware.py:86-90` | metrics reset on deploy (WS5-F1); use `duration_ms` from the access log instead — KQL §6.2 q2 |
| 12 | *(bonus)* **Container restart count** | Alembic startup line frequency | `backend/app/main.py:49` | none — KQL §6.2 q7. Doubles as the "your document blobs just vanished" alarm while `MCP_STORAGE_MODE=local` (PROD-F1) |

**Read this table as the honest scoreboard: 8 of 12 signals are computable today; 4 are not (6, 7, 9, 10), and 10 is the one that would have caught the worst pilot outcome — a tester whose app white-screens and who silently stops using it.**

---

## 8. NEW findings — WS4-F1 …

Severity: **P0** = blocks the controlled pilot · **P1** = must fix before the pilot cohort widens or before real PHI · **P2** = close before public beta.

| ID | Sev | Finding | Evidence | Exact fix |
|---|---|---|---|---|
| **WS4-F1** | **P1** | **Mobile crash telemetry is a no-op in the build the pilot installs.** The `Monitor` abstraction, root boundary, global handler and redaction all landed in `9692bb3`, but the only shipped adapter guards its body with `if (__DEV__)`. In the release APK `__DEV__` is `false`, so every captured error is discarded. `setMonitorAdapter` is never called outside tests. The runbook KPI "Crash-free sessions ≥ 99%" is therefore unmeasurable. | `mobile/src/lib/monitor.ts:52-59`, `:61`, `:64-66`; wired `mobile/app/_layout.tsx:11,16`; `mobile/src/components/ErrorBoundary.tsx:33`; APK is a release build per `00-CURRENT-STATE.md:72` | Two changes in `mobile/src/lib/monitor.ts`: (a) drop the `__DEV__` guard at `:54` so `console.error` always fires — retrievable in a release build via `adb logcat`; (b) add a `RingBufferMonitorAdapter` keeping the last 50 reports in memory + `expo-file-system`, and a hidden diagnostics screen with copy-to-clipboard. Add a jest case asserting capture occurs with `__DEV__ = false`. |
| **WS4-F2** | **P1** | **No client↔server correlation.** The mobile API client never sends `X-Request-ID` and never reads the one the backend echoes, so a tester's bug report cannot be joined to any backend log line — contradicting the runbook, which instructs testers to supply a timestamp "for log correlation via request/correlation IDs". | `mobile/src/api/client.ts:176-211` (no such header); backend accepts inbound at `backend/app/core/middleware.py:66` and echoes at `:107`; runbook claim `12-PILOT-OPERATIONS-RUNBOOK.md:35` | In `apiFetch` (`client.ts:176`): mint `const rid = uuid()`, add `headers['X-Request-ID'] = rid`, and on both success and `ApiError` push `{ts, rid, method: path, status}` into the monitor ring buffer from WS4-F1. Surface on the diagnostics screen. Then the runbook line becomes true. |
| **WS4-F3** | **P1** | **Failed authentication is invisible.** `authenticate()` raises before reaching its `audit.record` call, so only *successful* logins are audited. Account lockout (423) and the rate limiter emit no log, metric, or audit entry whatsoever. Brute-force and credential-stuffing are detectable only as anonymous status-code counts. | `backend/app/services/auth.py:240-241` (raise) vs `:244-251` (audit, success path only); lockout raises bare `HTTPException` at `backend/app/api/v1/routes/auth.py:104-112`, `:123`, `:130-134`; `backend/app/core/ratelimit.py` contains no logger (`grep -n "logger\|audit\|inc_counter"` → empty) | In `backend/app/api/v1/routes/auth.py`, inside the `except auth.AuthError` block (`:121-123`), add `audit.record(db, actor_type="user", actor_id=None, action="login", resource_type="user", outcome="deny", severity="warning", details={"key_hash": sha256(lkey)[:16], "reason": "bad_credentials"})` plus the same on the lockout branch with `reason="locked"`; commit. `key_hash` keeps it PHI-free while still allowing per-account correlation. Add `registry.inc_counter("auth_failures_total", {"reason": ...})`. |
| **WS4-F4** | **P1** | **Dead APM config creates a false belief that monitoring exists.** `APPLICATIONINSIGHTS_CONNECTION_STRING` is provisioned as an ACA secret on staging **and** production, but no code reads it and no App Insights / OpenTelemetry package is a dependency. An operator reading the deploy workflow will reasonably conclude the backend reports to App Insights. It does not. It also means a live secret is distributed for no reason. | `.github/workflows/azure-staging.yml:203`, `.github/workflows/azure-production.yml:218`; `backend/requirements.txt` (no APM package); `grep -rn "APPLICATIONINSIGHTS\|opentelemetry\|azure.monitor" backend/app` → zero | **Owner decision, infra-gated (do not edit the Azure workflow in this program).** Either (a) add `azure-monitor-opentelemetry` to `backend/requirements.txt` and call `configure_azure_monitor()` in `create_app()` (`backend/app/main.py:37`) — which routes PHI-adjacent logs to a new store and needs a privacy sign-off; or (b) remove the env var + `appi` secret from both workflows and record "stdout → Log Analytics" as the sanctioned path. **Recommend (b) for the pilot.** Until then, document it here so nobody is misled. |
| **WS4-F5** | **P1** | **`/metrics` is unauthenticated on a public ingress.** Mounted with no auth dependency, enabled via `MCP_METRICS_ENABLED=true` on staging and production, on a Container App with `--ingress external`. Anyone on the internet can enumerate every route template, request volumes, per-endpoint error counts, and latency distribution — a free reconnaissance map and availability oracle. No PHI, but it should not be public. | `backend/app/main.py:181-185` (no `Depends`); `.github/workflows/azure-staging.yml:210`, `azure-production.yml:223`; ingress `azure-staging.yml:224` | Cheapest: set `MCP_METRICS_ENABLED=false` (the access log supersedes it — §6.2) — an env change, owner-gated. Code fix: guard the handler with a shared-secret header check, e.g. compare `request.headers.get("X-Metrics-Token")` against a new `settings.metrics_token` using `hmac.compare_digest`, 404 on mismatch. Also fixes half of WS4-F6's exposure. |
| **WS4-F6** | **P1** | **Externally-controlled metric cardinality + raw paths in logs.** When no route matches (404s, and anything rejected pre-routing), the middleware falls back to `request.url.path`. That raw, attacker-controlled string becomes (a) a permanent label in the in-process metric registry — an unbounded-memory vector, since nothing ever evicts — and (b) the `path` field of the JSON access log. A scanner hitting 100k random URLs grows the registry monotonically and pollutes the log. | `backend/app/core/middleware.py:78-79`; registry has no eviction (`backend/app/core/metrics.py:24-30`); rendered wholesale at `metrics.py:56-73` | `backend/app/core/middleware.py:79` → `path = getattr(route, "path", None) or "<unmatched>"`. One line. Add a test asserting a request to `/nope-<random>` yields `path == "<unmatched>"` in both the metric label and the log record. |
| **WS4-F7** | **P1** | **Stack traces are unavailable in structured logs, and the uvicorn/gunicorn loggers are unaudited.** `JsonFormatter` keeps only `exc_type` and never renders `exc_info`, so no 500 in the pilot can be diagnosed from the log alone. Separately, `setup_logging` reconfigures only the root logger, leaving it unproven whether `uvicorn.error`/`gunicorn.error` propagate (→ JSON, no trace) or keep their own plain-text handlers (→ raw traceback on stderr, a possible PHI channel). | `backend/app/core/logging.py:45-47`, `:50-60`; process model `backend/startup.sh:12-20`, `backend/Dockerfile` CMD | (a) In `JsonFormatter.format`, add `payload["stack"] = redact(traceback.format_exception(*record.exc_info))[-4000:]` behind a new `settings.log_stack_traces` (default **on** for staging, **off** for prod until the redactor is reviewed). (b) Replace the ad-hoc root config in `setup_logging` with `logging.config.dictConfig` that explicitly attaches `JsonFormatter` to `uvicorn`, `uvicorn.error`, `uvicorn.access`, `gunicorn.error` with `propagate: false`. **UNVERIFIED until run:** force a 500 on staging and `az containerapp logs show -g <rg> -n ca-metocare-backend --tail 200`; any non-JSON line proves (b) is required. |
| **WS4-F8** | **P1** | **Exception text bypasses the log allow-list — and SQLAlchemy will put bound parameters in it.** `record.getMessage()` interpolates `%s` args into `message` before any filter runs, so the 7-field `extra` allow-list does not protect this channel. Sixteen sites interpolate an exception; several wrap direct SQL reads of PHI tables. The engine is built without `hide_parameters=True`, so a `StatementError` stringifies as `... [SQL: ...] [parameters: (...)]` — real PHI values in the log stream. **Confirms WS5-F7; upgraded P2 → P1 because a concrete mechanism now exists.** | `backend/app/core/logging.py:38` vs `:18-20, 42-44`; engine `backend/app/core/database.py:32`; sites `backend/app/ai/context/builder.py:329,388,457,499,571,637,693`, `backend/app/services/meto_chat.py:117,175,279,361,660`, `backend/app/services/lab_pipeline.py:120,225`, `backend/app/services/ocr_case.py:144`, `backend/app/knowledge/registry.py:58` | (1) `backend/app/core/database.py:32` → `create_engine(url, connect_args=connect_args, future=True, hide_parameters=True)` — one word, kills the mechanism. (2) Convert the sixteen sites to argument-free messages plus `extra={"event": "..."}`; `exc_type` already carries the class. (3) Regression test: force a `StatementError`, assert the emitted JSON `message` contains neither `[SQL:` nor `[parameters:`. |
| **WS4-F9** | **P1** | **Document content is logged at DEBUG.** The lab table extractor logs the verbatim OCR'd test name with `%r`. Dormant at the default `INFO`, but a single `MCP_LOG_LEVEL=DEBUG` — the obvious move when debugging a pilot OCR complaint — starts streaming patient document text to whatever aggregates stdout. | `backend/app/domain/lab_table_extractor.py:980`; default level `backend/app/core/config.py:187` | `backend/app/domain/lab_table_extractor.py:980` → log `len(row.original_test_name)` or `sha256(...)[:8]` instead of the value. Then grep the codebase for other `%r`/`%s` of extracted content and apply the same rule. Add a CI grep gate: no logging call may interpolate a field named `*_name`, `*_text`, `raw_*`, or `original_*`. |
| **WS4-F10** | **P1** | **No scheduled retention enforcement.** The purge job is implemented, category-correct, and unit-tested — and is invoked by nothing outside tests. `audit_logs` grows without bound and the declared TTLs (365/730/1095 days) are aspirational, which is a compliance exposure once real PHI-adjacent access records accumulate. **Confirms and refines PROD-F5.** | job `backend/app/jobs/maintenance.py:23-30, 33-47`; policy `backend/app/services/audit_retention.py:33-71`; TTLs `backend/app/core/config.py:194-197`; only callers `backend/tests/test_hardening.py:17,102` and `backend/tests/test_audit_retention.py:9` | **Owner/infra-gated.** Add an ACA scheduled Job on the same image running `python -m app.jobs.maintenance` (the migration Job at `.github/workflows/azure-staging.yml:155` is the pattern to copy) with a daily cron. Until scheduled, add the weekly `SELECT COUNT(*) FROM audit_logs` check to §6.3 — done. |
| **WS4-F11** | **P2** | **AI output-safety replacement rate is not derivable from the audit table.** `safety_flags_detected` is a single boolean set from the union of input red-flags and output-replacement flags, so SQL cannot separate "patient said something alarming" (expected, frequent) from "the model produced a forbidden clinical instruction and we replaced it" (the actual safety signal). It exists only as a free-text log line. | union `backend/app/services/meto_chat.py:213`; write `:650`; column `backend/app/models/meto.py:111`; the only distinguishing record is the log at `backend/app/services/meto_chat.py:204-208` | At the `_save_and_return`/`_write_audit` call chain (`backend/app/services/meto_chat.py:222-240` → `:641-659`), pass `details={"output_replaced": not output_safety.safe, "input_flagged": bool(input_safety.flags)}`. `details` is already a JSON column (`models/meto.py:117`) and already documented PHI-free. Zero migration. |
| **WS4-F12** | **P2** | **`/info` unauthenticated disclosure.** Returns `env`, `ai_mode`, `ocr_mode`, `storage_mode`, the exact Alembic revision, and the state of every feature flag, to anyone. Operationally useful; also a precise fingerprint for choosing an exploit. **Confirms WS5-F6 / SEC-F4.** | `backend/app/api/v1/routes/system.py:38-66`, flags enumerated at `:56` | Split: keep `{app, env, migration_version}` public (deploy verification needs it — `12-PILOT-OPERATIONS-RUNBOOK.md`, `15-FINAL-LAUNCH-REVIEW.md:79`); move `feature_flags`, `ai_mode`, `ocr_mode`, `storage_mode` behind `Depends(current_admin)`. Acceptable to defer to beta for a closed synthetic pilot — but record the acceptance. |
| **WS4-F13** | **P2** | **Reminder "delivery" is pull-only and unrecorded.** `deliver_due_reminders` runs only inside a client request (`GET .../reminders/due` or the dashboard). It writes no audit row and no metric; the sole trace is `DoseOccurrence.state` flipping `pending → notified`. A user who never opens the app is therefore indistinguishable from a delivery failure, and the runbook KPI "Reminder engagement (delivered → acted)" has no denominator. | `backend/app/services/medication_schedule.py:255-300` (no `audit.record`), transition `:281-284`; route `backend/app/api/v1/routes/medication_schedule.py:243`; KPI `12-PILOT-OPERATIONS-RUNBOOK.md:49` | Add `audit.record(..., action="medication_dose.notified", resource_type="dose_occurrence", resource_id=dose.id)` after the successful claim at `medication_schedule.py:284`, and `registry.inc_counter("reminders_delivered_total")`. Also correct the runbook to define pilot "delivered" as "surfaced in-app on next open" — there is no push (WS12-F1). |
| **WS4-F14** | **P2** | **`/info.ocr_mode` does not describe the document pipeline.** `ocr_mode` is read in exactly one place — the legacy lab path. The MDI document pipeline that Journey A actually uses calls `run_ocr` directly and is gated by `FEATURE_OCR`, not by `ocr_mode`. Staging sets `MCP_OCR_MODE=mock`, so an operator checking `/info` will conclude document OCR is mocked when it is running real Tesseract. | `ocr_mode` consumed only at `backend/app/services/lab.py:346, 369`; MDI path `backend/app/services/mdi/pipeline.py:20, 54-56, 77`; staging env `.github/workflows/azure-staging.yml:205` | Rename the `/info` key to `legacy_lab_ocr_mode` and add `document_ocr_engine` derived from the MDI engine selection (`backend/app/services/ocr_engine.py`). Documentation-level severity, but it will cause a wrong call during an incident. |
| **WS4-F15** | **P2** | **Metrics reset silently on every deploy and nothing records that they did.** With a process-local registry and no scrape, each revision update zeroes all counters with no marker in the metric stream. Anyone reading `/metrics` after a deploy sees a healthy-looking zero error count. **Elaborates WS5-F1.** | `backend/app/core/metrics.py:76`; deploy `--revision-suffix` at `.github/workflows/azure-staging.yml:219` | For the pilot: do not use `/metrics` as a source of truth — use the access log (§6.2), which has history. Structural fix (post-pilot): expose a `process_start_time_seconds` gauge and treat the startup log line (`backend/app/main.py:49`) as the reset marker — KQL §6.2 q7. |

**Summary: 0 new P0 · 10 new P1 · 5 new P2.** No finding blocks a synthetic-data controlled pilot on its own; **WS4-F1 + WS4-F2 + WS4-F3 together do**, because without them the pilot cannot observe its own most likely failure modes.

---

## 9. Conditions to call observability pilot-ready

1. **WS4-F1** — mobile capture works in a release build (ring buffer + always-on console). *Code, ~1h.*
2. **WS4-F2** — `X-Request-ID` sent by the client and surfaced on a diagnostics screen. *Code, ~1h.* Makes `12-PILOT-OPERATIONS-RUNBOOK.md:35` true.
3. **WS4-F3** — failed logins and lockouts audited. *Code, ~30m.*
4. **WS4-F8** — `hide_parameters=True` + the `[parameters:` canary alert in §6.3. *Code, 1 line + 1 test.*
5. **WS4-F6** — `<unmatched>` path fallback. *Code, 1 line.*
6. **Owner/infra (not edited by this program):** confirm the ACA env writes to Log Analytics (§3.1); decide WS4-F4 (wire or delete App Insights); decide WS4-F5 (disable public `/metrics`); schedule WS4-F10.
7. **Operator:** save the six KQL queries and three SQL queries from §6.2, and adopt the daily cadence in §6.3.

Items 1–5 are isolated, testable, and touch no clinical or auth logic. Item 6 is owner-gated by the standing Azure-infra guardrail.

## 10. Cross-references

`00-CURRENT-STATE.md §5` (this document is the promised WS5 depth assessment) · `12-PILOT-OPERATIONS-RUNBOOK.md §Pilot KPIs, §Operator dashboard` (KPI 10 is unmeasurable until WS4-F1) · `15-FINAL-LAUNCH-REVIEW.md §3` (WS5-F1/F3/F6/F7 and PROD-F5 dispositions updated in §5 above) · `05-ANALYTICS-EVENT-CATALOG.md` (product-event layer built on the audit backbone described here).
