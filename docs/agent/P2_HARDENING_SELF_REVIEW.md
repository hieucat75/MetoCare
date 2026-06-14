# P2-HARDENING-1 — Self Review

> Tác giả: Claude Code · Ngày: 2026-06-14 · Branch: `hardening/p2-hardening-1`

---

## 1. Summary

Operational-safety hardening (no foundation rewrite, no heavy deps, no medical logic change):
fixed the pre-existing **red CI** (RAG seed was gitignored), added **refresh-token cleanup** +
**maintenance job**, implemented the **Redis rate-limit backend** (optional, lazy-imported), and an
**email blind-index helper**. Postgres/TimescaleDB **NOT verified** (Docker daemon DOWN — honest).

## 2. Files changed

| File | Change |
|------|--------|
| `.gitignore` | un-ignore `backend/data/rag_seed/` (seed corpus must be committed for CI) |
| `backend/data/rag_seed/{biomarkers,lifestyle,metabolic_disorders}.md` | committed (curated guideline, NOT PHI) |
| `backend/app/services/auth.py` | `cleanup_expired_refresh_tokens()` (idempotent); import `delete, or_` |
| `backend/app/jobs/__init__.py`, `backend/app/jobs/maintenance.py` | cron-friendly maintenance job (audit purge + refresh cleanup) + CLI |
| `backend/app/core/ratelimit.py` | `RedisRateLimiter` (lazy/optional redis) + factory wiring + `set_rate_limiter` |
| `backend/app/core/config.py` | `ratelimit_redis_url` |
| `backend/app/core/crypto.py` | `blind_index()` HMAC helper (review building block) |
| `.env.example` | `MCP_RATELIMIT_REDIS_URL` |
| `backend/tests/test_hardening.py` | tests for cleanup/maintenance/Redis/blind-index (6 tests) |
| `docs/agent/P2_HARDENING_EXECUTION_PLAN.md`, this file | evidence |

## 3. Tests run + actual results

```
pytest:                 136 passed, 1 skipped, 1 warning   (was 130; +6 hardening tests)
ruff check:             All checks passed!
compileall:             OK
docker-compose config:  VALID
```
1 skipped = `test_postgres_hypertable_ingest_and_trend` (needs Postgres).

**CI fix verification:** the 3 RAG tests fail on a *fresh checkout* because `backend/data/rag_seed/`
was gitignored. After committing the seed (this branch), a fresh checkout has the corpus → tests pass.
Cannot run GitHub CI from here; verified that the seed files are now git-tracked (`git add -n` lists them).

## 4. Review dimensions

- **Architecture:** modular monolith preserved; jobs are a thin orchestration layer over existing
  services; Redis backend slots behind the existing `RateLimiter` interface (no call-site change).
- **Security:** Redis backend lazy-imports (no new hard dep); blind-index keyed by SECRET_KEY (no plaintext);
  refresh cleanup reduces stale-token surface; `.env` ignored + untracked; no hardcoded secrets; no PHI fixtures.
- **Medical safety:** untouched. Guardrails / triage / policies / system-safety-prompt unchanged. AI still mock.
- **Privacy:** RAG seed is approved guideline content, explicitly "không chứa dữ liệu bệnh nhân thật".
  Refresh cleanup keeps a 7-day grace on revoked tokens for incident inspection.
- **Migration:** none added this phase (blind-index wiring deferred to avoid a User-model migration now).

## 5. Postgres / TimescaleDB verification — HONEST

**NOT verified. Docker daemon is DOWN in this environment.** No claim of Timescale hypertable/CAGG
working on real Postgres. Commands for PTH to verify on a Docker host:
```bash
open -a Docker            # or: colima start
docker compose up -d postgres
cd backend
export MCP_TEST_POSTGRES_URL=postgresql+psycopg://mcp:mcp_dev_only@localhost:5432/mcp
alembic upgrade head
pytest tests/test_migrations.py::test_postgres_hypertable_ingest_and_trend
```

## 6. Known limitations

- Postgres/TimescaleDB unverified (Docker DOWN).
- Redis backend uses **fixed-window** (approx token bucket); tested with a fake client, not a real server.
- `redis` is NOT in requirements (optional); selecting backend=redis without it raises a clear runtime error.
- Email blind-index: **helper only**; not wired into the `User` model (would need a migration + login-path
  change) — deferred to a dedicated task.
- Maintenance job is a CLI/function; not yet scheduled (cron/systemd timer is deploy-time).
- Rate-limit/lockout still in-memory by default; Redis is opt-in.

## 7. Risks introduced

Low. New code is additive + covered by tests. No change to auth happy-path, guardrails, or SQLite dev mode.
Refresh cleanup deletes only expired / long-revoked rows (grace window) — reversible by not scheduling it.

## 8. Next task

Next-phase preference (per PTH): **Next.js portal before Flutter**. Before that, recommend PTH run the
Postgres/TimescaleDB verification on a Docker host and confirm GitHub CI is green post-merge.

## 9. Verdict

- **MERGE_ALLOWED: NO** (await PTH external review).
- **REASON:** All local validation green (136/1 skipped, ruff/compileall/compose); CI red root-caused and
  fixed (seed committed); changes additive, no medical/guardrail/foundation changes; Postgres/Timescale
  honestly unverified (Docker DOWN). Needs PTH review + CI-green confirmation before merge.
