# P2-HARDENING-1 — Execution Plan (Runtime Verification + Operational Safety)

> Tác giả: Claude Code · Ngày: 2026-06-14 · Branch: `hardening/p2-hardening-1` (từ `main` sau merge PR #1)
> Baseline: 130 passed / 1 skipped (Task 1). **Không re-discovery.**

---

## 0. Objective

Tăng độ an toàn vận hành mà KHÔNG rewrite foundation, KHÔNG thêm heavy deps, KHÔNG đụng medical logic.
Honest về cái gì verify được (Docker DOWN → không claim Postgres/Timescale verified).

## 1. Recon findings (đo hôm nay)

| Item | Trạng thái hiện tại |
|------|---------------------|
| Docker daemon | **DOWN** → không verify Postgres/TimescaleDB được |
| CI trên main | **RED** (pre-existing): `backend/data/rag_seed/` bị `.gitignore` `data/` loại → CI không có seed → 3 RAG test fail |
| Rate-limit Redis backend | Placeholder `NotImplementedError` (chỉ in-memory) |
| Refresh-token cleanup | **CHƯA có** |
| Audit retention purge | **ĐÃ có** `audit_retention.purge_expired` (P1 #4), nhưng chưa có job entrypoint |
| Email blind-index | **CHƯA** (chỉ comment trong `crypto.py`); email plaintext cho login lookup |
| Secrets / .env / PHI | Sạch: `.env` ignored + untracked; không hardcoded secret; không PHI fixtures |

## 2. Scope phiên này (small, scoped)

| # | Hạng mục | Loại | Files (dự kiến) |
|---|----------|------|-----------------|
| A | **Fix CI: commit RAG seed corpus** (un-ignore `backend/data/rag_seed`) | Operational/CI | `.gitignore`, `backend/data/rag_seed/*.md` (commit), maybe `knowledge_base` fallback |
| B | **Refresh-token cleanup job** (xóa revoked+expired quá hạn) | Feature nhỏ | `app/services/auth.py` + test |
| C | **Maintenance job skeleton** (cron-friendly: audit purge + refresh cleanup) | Feature nhỏ | `app/jobs/maintenance.py` (new) + test |
| D | **Redis rate-limit backend** (lazy-import, optional dep, factory wiring) | Feature nhỏ | `app/core/ratelimit.py` + test (fake client) |
| E | **Email blind-index helper + review** | Helper + docs | `app/core/crypto.py` (`blind_index`) + test + report (wiring deferred) |
| F | **Security audit** (no secrets / .env ignored / no PHI) | Verify | report only |
| G | **Postgres/TimescaleDB verify** | Blocked | report blocker + exact commands (Docker DOWN) |

## 3. Blocker handling — Docker DOWN

Không claim verified. Cung cấp lệnh để PTH chạy thật:
```bash
open -a Docker            # macOS Docker Desktop
# hoặc: colima start
docker compose up -d postgres
cd backend && export MCP_TEST_POSTGRES_URL=postgresql+psycopg://mcp:mcp_dev_only@localhost:5432/mcp
alembic upgrade head        # chạy initial + Timescale hypertable + CAGG migrations
pytest tests/test_migrations.py::test_postgres_hypertable_ingest_and_trend
```
Migration #2 (Timescale) có guard `dialect == postgresql` — no-op trên SQLite, chỉ chạy thật trên Postgres.

## 4. Test plan

- pytest (kỳ vọng tăng từ 130 → 130 + N test mới, vẫn 1 skipped Postgres).
- ruff check + compileall + docker compose config.
- Redis backend: unit test dùng **fake in-memory redis-like client** (không cần Redis thật, không thêm dep test).
- Refresh cleanup + maintenance + blind-index: unit/integration test trên SQLite.
- CI: sau khi commit seed, RAG test sẽ pass trên fresh checkout (verify bằng cách xoá-local-simulate hoặc tin vào commit seed).

## 5. Non-scope (CẤM)

Next.js, Flutter, AI provider mới, real OCR, prod deploy, medical logic rewrite, UI, microservices, heavy deps.
Redis lib KHÔNG thêm vào hard requirements (lazy/optional). Email blind-index: chỉ helper + review, **không** wire vào model (cần migration — defer).

## 6. Rollback

Mỗi item = 1 commit logic trên branch `hardening/p2-hardening-1`. Rollback = revert commit. SQLite dev mode không đổi.

## 7. Acceptance criteria

- [ ] CI xanh trên fresh checkout (RAG seed committed).
- [ ] Refresh cleanup + maintenance job có test, idempotent.
- [ ] Redis backend selectable + test (fake client); in-memory vẫn default.
- [ ] blind-index helper có test; review documented.
- [ ] Security audit: no secrets/.env/PHI — documented.
- [ ] Postgres/Timescale: HONEST "not verified, Docker DOWN" + commands.
- [ ] pytest/ruff/compileall/compose pass; SQLite dev không vỡ; guardrails nguyên vẹn.
- [ ] MERGE_ALLOWED: NO (chờ PTH).
