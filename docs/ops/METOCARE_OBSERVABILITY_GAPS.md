# MetoCare — Observability Gaps

> **T18D · Observability Review**
> Branch: `feature/t18d-pilot-deploy-runbook`
> Last updated: 2026-06-18
> Owner: Backend Lead / DevOps

---

## Overview

This document catalogues the current gaps in logging, monitoring, health checks,
and alerting for the MetoCare backend as of the T18D pilot deployment milestone.

**What exists today:**
- Structured JSON logging via `app/core/logging.py` (timestamp, level, logger, message, request_id, user_id + safe extra fields)
- In-process Prometheus-format metrics endpoint at `GET /metrics` (counters + histograms, gated by `MCP_METRICS_ENABLED`)
- X-Request-ID header propagation through middleware (correlation between client and server logs)
- Append-only audit log table in the database
- Rate limiting with configurable backend (memory or Redis)

**What is missing** is documented below with severity, recommendation, and effort estimate.

---

## Severity Legend

| Level | Meaning |
|---|---|
| **P1** | Blocks pilot go-live or creates compliance/safety risk; must fix before pilot |
| **P2** | Significant operational risk; fix within first week of pilot |
| **P3** | Quality-of-life / future scale; address in next sprint |

---

## Gap Inventory

### GAP-01 — No Database Connectivity Check in `/health`

**Severity:** P1

**Current state:**
`GET /health` returns `{"status": "ok"}` by executing a trivial Python dict return.
It performs no database query. A load balancer relying on `/health` will route
traffic to an application instance that cannot reach the database.

**Impact:**
- Deployment failures are invisible to the health check
- Load balancers (ELB, nginx upstream, k8s readiness probe) incorrectly mark the instance healthy
- First real API request fails with a 500 that appears to come from "nowhere"

**Recommendation:**
Add a DB connectivity check to `/health`:
```python
# system.py
from sqlalchemy import text
from app.core.database import get_session  # or however the session is obtained

@router.get("/health")
async def health(db: AsyncSession = Depends(get_session)) -> dict:
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    status = "ok" if db_ok else "degraded"
    return {"status": status, "db": "ok" if db_ok else "error"}
```
Return HTTP 503 when `db_ok=False` so load balancers stop routing to the instance.

**Effort:** ~1 hour

---

### GAP-02 — No Migration Version in `/health` or `/info`

**Severity:** P1

**Current state:**
`GET /info` returns `app`, `env`, `ai_mode`, `ocr_mode`, `storage_mode`.
The current Alembic revision is not exposed anywhere in the API.

**Impact:**
- Cannot verify from the API that migrations ran correctly after deploy
- In a multi-instance deployment, different instances may run different code
  against a partially-migrated schema with no visibility
- Ops must SSH into the host and run `alembic current` to confirm

**Recommendation:**
Add migration version to `/info`:
```python
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine

@router.get("/info")
async def info(db: AsyncSession = Depends(get_session)) -> dict:
    s = get_settings()
    # Get current alembic revision
    try:
        conn = await db.connection()
        ctx = MigrationContext.configure(conn)
        revision = ctx.get_current_revision()
    except Exception:
        revision = "unknown"
    return {
        "app": s.app_name,
        "env": s.env,
        "ai_mode": s.ai_mode,
        "ocr_mode": s.ocr_mode,
        "storage_mode": s.storage_mode,
        "migration_version": revision,
    }
```

**Effort:** ~2 hours (includes async SQLAlchemy wiring)

---

### GAP-03 — No Structured Log Fields for HTTP Method, Path, Status Code

**Severity:** P2

**Current state:**
`logging.py` defines `_SAFE_EXTRA_FIELDS` which includes `method`, `path`,
`status_code`, `duration_ms`. However, these are optional `extra` fields that
must be explicitly passed by the caller. There is no evidence that the request
middleware auto-populates all of these on every log line.

`middleware.py` propagates `request_id` and `user_id` via context vars, but
request method, path, status code, and duration need to be verified as being
consistently logged per request.

**Impact:**
- Log queries like "show all 500s on `/api/v1/patients`" may not work reliably
- Latency percentiles per endpoint cannot be computed from logs alone
- Audit trail for "which endpoints were called before an error" is incomplete

**Recommendation:**
Confirm middleware emits one structured log line per request with all safe extra
fields populated:
```python
logger.info(
    "request",
    extra={
        "method": request.method,
        "path": request.url.path,
        "status_code": response.status_code,
        "duration_ms": round((time.monotonic() - start) * 1000, 2),
    }
)
```
Log at `INFO` for 2xx/3xx, `WARNING` for 4xx, `ERROR` for 5xx.

**Effort:** ~2 hours

---

### GAP-04 — No Slow Query Logging

**Severity:** P2

**Current state:**
No slow query detection at the application or database level. There is no
SQLAlchemy event hook for query duration, and PostgreSQL `log_min_duration_statement`
is not configured as part of the deployment runbook.

**Impact:**
- Performance regressions in DB queries are invisible until they cause latency
  spikes or timeouts
- No data to optimize queries proactively
- In TimescaleDB hypertable queries (health_metrics), slow continuous aggregate
  refreshes are completely silent

**Recommendation:**
Two-layer approach:
1. **Application layer:** SQLAlchemy `before_cursor_execute` / `after_cursor_execute`
   events to log queries exceeding a threshold (e.g. 200ms):
   ```python
   # In database.py setup
   @event.listens_for(engine.sync_engine, "before_cursor_execute")
   def before_exec(conn, cursor, statement, parameters, context, executemany):
       conn.info.setdefault("query_start", time.monotonic())

   @event.listens_for(engine.sync_engine, "after_cursor_execute")
   def after_exec(conn, cursor, statement, parameters, context, executemany):
       total = time.monotonic() - conn.info.pop("query_start", time.monotonic())
       if total > 0.2:  # 200ms threshold
           logger.warning("slow_query", extra={"duration_ms": round(total*1000, 1)})
   ```
2. **PostgreSQL layer:** Set `log_min_duration_statement = 500` in `postgresql.conf`.

**Effort:** ~3 hours (application layer); PostgreSQL config is ops work

---

### GAP-05 — No Audit Event Streaming / Real-Time Alert on Anomalies

**Severity:** P2

**Current state:**
Audit logs are written to the `audit_logs` database table. There is no
streaming, alerting, or anomaly detection on audit events. The
`Security_Compliance_Framework.md` requires "cảnh báo bất thường" (anomaly
alerts) but no implementation exists.

**Impact:**
- Insider threat events (mass data export, unusual access patterns) are only
  discoverable by querying the audit table after the fact
- No real-time alert if an admin account is used unexpectedly
- Compliance requirement (VN PDPA) for breach detection SLA is not met

**Recommendation:**
Phase 1 (pilot): Ship audit events to a log aggregator (e.g. Loki, CloudWatch, ELK)
via the existing JSON log output — add an `audit_event=true` field so they can be
filtered separately. Set up a simple alert rule: N audit events with
`action=export` in 10 minutes.

Phase 2 (prod): Dedicated audit event stream (Kafka topic or database LISTEN/NOTIFY)
with an alert engine.

**Effort:** P1 stream setup ~4 hours; full anomaly detection ~2 weeks

---

### GAP-06 — No Alert on AI Triage EMERGENCY Escalation

**Severity:** P1

**Current state:**
The triage system (T19) can produce `risk_level=EMERGENCY` outputs. The
`AI_ESCALATION_ENABLED` feature flag controls the escalation workflow, but there
is no alerting (PagerDuty, Slack, SMS, email) when a triage result reaches
EMERGENCY level — even in mock mode.

**Impact:**
- A patient flagged as EMERGENCY may not receive timely medical attention if the
  escalation workflow is not monitored
- Medical/legal liability risk: AI identified an emergency but no human was
  notified
- Even if AI flags are disabled for pilot, the alert infrastructure should be
  ready before they are enabled

**Recommendation:**
When `risk_level=EMERGENCY` is produced by the triage engine:
1. Write a structured log line with `event=triage_emergency`, `patient_id` (opaque),
   `triage_session_id`
2. Emit a metric increment: `triage_emergency_total{source="ai"}`
3. Fire a webhook / notification to on-call channel (Slack, PagerDuty)
4. Ensure the `AI_ESCALATION_ENABLED` feature flag gate also triggers
   synchronous escalation, not fire-and-forget

**Effort:** ~1 day (log + metric: 2h; webhook integration: 4h; testing: 2h)

---

### GAP-07 — No Redis / Rate-Limiter Health Check

**Severity:** P2

**Current state:**
When `MCP_RATELIMIT_BACKEND=redis`, the rate limiter depends on a Redis instance.
If Redis goes down, the behavior depends on implementation (fail-open or fail-closed
is not documented in the code comments). There is no Redis health check in `/health`.

**Impact:**
- In fail-open mode: rate limiting stops working silently, exposing auth brute-force
- In fail-closed mode: all authenticated requests start failing with 429
- Either outcome is a silent production incident

**Recommendation:**
Add optional Redis ping to `/health` when `ratelimit_backend=redis`:
```python
if settings.ratelimit_backend == "redis":
    redis_ok = await redis_client.ping()
    health["redis"] = "ok" if redis_ok else "error"
```
Log a warning if Redis is unreachable but don't fail the overall health check
(degraded, not down) — unless rate limiting is considered critical path.

**Effort:** ~2 hours

---

### GAP-08 — No OpenTelemetry / Distributed Tracing

**Severity:** P3

**Current state:**
`X-Request-ID` is propagated via middleware and included in JSON logs. This
provides basic per-request correlation within a single service. There is no
distributed trace context propagation (W3C `traceparent`, OpenTelemetry spans)
and no trace export to Jaeger, Tempo, or a cloud tracing backend.

**Impact:**
- Cannot trace a request across the API → background worker → LLM gateway chain
- Latency attribution between service layers is manual
- When OCR worker or AI job is slow, cannot determine which layer is the bottleneck

**Recommendation:**
Instrument with `opentelemetry-sdk` + `opentelemetry-instrumentation-fastapi`:
```bash
pip install opentelemetry-sdk opentelemetry-instrumentation-fastapi \
            opentelemetry-exporter-otlp-proto-grpc
```
Export to an OTLP-compatible backend (Grafana Tempo, Jaeger, Honeycomb, Datadog).
Propagate `traceparent` header through LLM gateway calls and background workers.

**Effort:** ~1 day for basic instrumentation; ~3 days for full cross-service tracing

---

### GAP-09 — No Prometheus Scrape Configuration / Grafana Dashboard

**Severity:** P3

**Current state:**
`GET /metrics` exists and emits Prometheus text format via `app/core/metrics.py`
(in-process counters + histograms). However:
- There is no `prometheus.yml` scrape config checked into the repo
- There is no pre-built Grafana dashboard for MetoCare
- The metrics emitted are application-layer only; no process metrics
  (memory, CPU, file descriptors) from a standard exporter

**Impact:**
- Ops team must manually configure Prometheus to discover the endpoint
- No baseline dashboard means incidents require ad-hoc metric queries
- No alerting rules for error rate, latency P99, or saturation

**Recommendation:**
1. Add `prometheus.yml` scrape config to `infra/` or `docs/ops/`
2. Create a Grafana dashboard JSON with panels for:
   - Request rate (req/s by route)
   - Error rate (5xx %)
   - Latency P50/P95/P99
   - Auth events (login, lockout, MFA)
   - AI triage call rate + emergency count
3. Add alert rules: error rate > 5% for 5 minutes → page on-call

**Effort:** ~1 day (scrape config + dashboard template)

---

### GAP-10 — No Build Version / Git SHA in `/info`

**Severity:** P3

**Current state:**
`GET /info` returns runtime mode config but no build metadata (git SHA, version
tag, build timestamp). In a rolling deployment or rollback scenario, it is
impossible to confirm from the API which code version is running.

**Impact:**
- During a rollback, cannot confirm from the load balancer which instances
  are still running the old version
- Incident investigation requires SSH to determine deployed SHA
- Canary deployments are blind

**Recommendation:**
Inject build metadata at build time:
```bash
# In Dockerfile or CI
ENV BUILD_SHA=$(git rev-parse --short HEAD)
ENV BUILD_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ)
```
Expose in `/info`:
```python
"build_sha": os.getenv("BUILD_SHA", "unknown"),
"build_time": os.getenv("BUILD_TIME", "unknown"),
```

**Effort:** ~30 minutes

---

### GAP-11 — Audit Log Does Not Capture Triage/Nutrition Log Writes

**Severity:** P2

**Current state:**
The audit log framework captures auth events, data access, admin actions, and
consent changes (per `Security_Compliance_Framework.md`). The new T18
(`nutrition_logs`) and T19 (`triage_logs`) tables may not be wired to generate
audit events for writes to these tables.

**Impact:**
- Clinical actions (triage sessions, nutrition logging) may not be traceable
  in the audit trail
- VN PDPA / compliance requirement: all access to health data must be audited
- Triage EMERGENCY events especially must be audit-logged for medical liability

**Recommendation:**
Confirm (and add if missing) that:
1. `POST /nutrition` → creates `audit_log` entry with `action=nutrition_log_create`
2. `POST /ai/triage` → creates `audit_log` entry with `action=triage_create`, `resource_type=triage_log`
3. `risk_level=EMERGENCY` → additional `audit_log` entry with `action=triage_emergency`

**Effort:** ~2 hours per endpoint to verify + add if missing

---

### GAP-12 — No Log Rotation / Size Limit on Log Output

**Severity:** P3

**Current state:**
Logs are emitted to stdout (`StreamHandler`) in JSON format. This is correct for
container environments (Docker logs, k8s logging) but on VM/bare-metal deployments
without a log shipper, stdout logs may fill disk if not rotated.

**Impact:**
- On bare-metal or systemd deployments without journald size limits: disk full →
  app crash
- On Docker without a log driver configured: `/var/lib/docker/containers/<id>/*.log`
  grows unbounded

**Recommendation:**
For container deployments: configure Docker `--log-opt max-size=100m --log-opt
max-file=5` or equivalent in `docker-compose.yml`.

For systemd: set `SystemMaxUse=1G` in `/etc/systemd/journald.conf`.

Document this in the deployment runbook infra section.

**Effort:** ~30 minutes (config change + docs)

---

## Summary Table

| Gap | Title | Severity | Effort |
|---|---|---|---|
| GAP-01 | No DB connectivity check in `/health` | **P1** | ~1 hour |
| GAP-02 | No migration version in `/health` or `/info` | **P1** | ~2 hours |
| GAP-06 | No alert on AI triage EMERGENCY escalation | **P1** | ~1 day |
| GAP-03 | Structured log fields not guaranteed per-request | **P2** | ~2 hours |
| GAP-04 | No slow query logging | **P2** | ~3 hours |
| GAP-05 | No audit event streaming / real-time anomaly alert | **P2** | ~4 hours (P1) / ~2 weeks (full) |
| GAP-07 | No Redis / rate-limiter health check | **P2** | ~2 hours |
| GAP-11 | Triage/nutrition writes not in audit log | **P2** | ~2 hours per endpoint |
| GAP-08 | No OpenTelemetry / distributed tracing | **P3** | ~1–3 days |
| GAP-09 | No Prometheus scrape config / Grafana dashboard | **P3** | ~1 day |
| GAP-10 | No build version / git SHA in `/info` | **P3** | ~30 minutes |
| GAP-12 | No log rotation configuration | **P3** | ~30 minutes |

---

## Recommended Pilot Go-Live Minimum

Before the pilot launches with real patients, the following P1 gaps must be addressed:

1. **GAP-01** — Add DB health check to `/health` so the load balancer knows when the app is degraded
2. **GAP-02** — Add migration version to `/info` so deploys can be verified without SSH
3. **GAP-06** — Implement at minimum a structured log + metric for triage EMERGENCY (even if the webhook is TODO) so no EMERGENCY event goes unlogged

All P2 gaps should be addressed within the first week of pilot operation.

---

*See also: `METOCARE_PILOT_DEPLOYMENT_RUNBOOK.md` for deploy procedures and smoke tests.*
