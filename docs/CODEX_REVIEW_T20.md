# Codex Review — T20 Production Hardening

**Branch:** `feature/t20-production-hardening`
**Reviewer:** Codex (read-only)
**Date:** 2026-06-18
**Commits reviewed:** `c22ca6d` (feat), `62509b3` (docs)

---

**Result:** ⚠️ REQUEST_CHANGES

**P1 Blockers:** 2 (see below)
**P2 Warnings:** 2
**Security:** PASS (conditional — see P2-W1)
**Test Results:** 7/7 PASS (reported; 462 passed, 0 failures)
**Acceptance Criteria:** 5/7 met

---

## Findings

### ✅ AC1 — P1-FIX-01: /health DB check (PASS)

`system.py` lines 17–30 correctly:
- Executes `SELECT 1` via SQLAlchemy `text()` (safe, correct)
- Returns `JSONResponse(status_code=503, content=body)` when `db_status != "ok"` — **503 is explicitly set**
- Returns `JSONResponse(status_code=200, content=body)` when healthy
- Response shape `{"status": "ok"|"degraded", "db": "ok"|"error"}` is consistent

**AC1 verdict: PASS**

---

### ✅ AC2 — P1-FIX-02: /info migration_version + feature_flags (PASS)

`system.py` lines 35–68:
- Queries `alembic_version` via SQLAlchemy `text("SELECT version_num FROM alembic_version LIMIT 1")`
- Falls back to `"unknown"` on any exception — correct defensive behavior
- Iterates all `FeatureFlag` enum members via `is_enabled()` — all flags exposed, all boolean

**AC2 verdict: PASS**

---

### ✅ AC3 — P1-FIX-03: Startup validation placement (PASS)

`main.py` diff shows `settings.validate_required_env_vars()` is the **very first line** inside the `@asynccontextmanager async def lifespan()` function, before `create_all()`, before OCR worker start, and before `yield`. It is **inside** the lifespan context manager, not at module import time.

`config.py` `validate_required_env_vars()`:
- Checks both `self.secret_key` and `self.database_url` for empty/whitespace-only values
- Raises `RuntimeError` with a descriptive message listing missing vars
- Logic is correct: `not value or not value.strip()` catches empty string and whitespace

**AC3 verdict: PASS**

---

### ❌ AC4 — Existing /health callers still get `status` key (PARTIAL FAIL → P1 BLOCKER)

There are **two `/health` handlers** in this application:

1. `backend/app/main.py` line 112: `@app.get("/health")` → returns `{"status": "ok"}` — root-level, no DB check, HTTP 200 always
2. `backend/app/api/v1/routes/system.py` line 17: `@router.get("/health")` → mounted at `/api/v1/health`, DB-checking, 503-capable

The tests exclusively call `/api/v1/health`. The root `/health` handler in `main.py` has **not been updated** to match the new shape: it still returns `{"status": "ok"}` with no `db` key, no DB check, and always returns 200.

**Impact:**
- Load balancers pointed at `/health` (root) will **never see a 503** — the entire P1-FIX-01 benefit is bypassed for root-level health checks
- Any infra tooling using `/health` gets a stale, degraded-blind response
- The `db` field is missing from the root `/health` response (AC4 partial fail)

The root `/health` should either:
a) Be removed and load balancers pointed to `/api/v1/health`, **or**
b) Be updated to also do the DB check and return 503 on failure

**P1 BLOCKER #1 — Root `/health` bypass: load balancers will never see 503**

---

### ✅ AC5 — Public endpoints (PASS)

Neither `/api/v1/health` nor `/api/v1/info` have `Depends(get_current_user)` or any auth guard. Both use only `Depends(get_session)` for DB access. Tests T20-S02 and T20-S05 confirm this. 

**AC5 verdict: PASS**

---

### ✅ AC6 — HTTP 503 on DB failure: code path confirmed (PASS — code only)

The production code path is correct: `JSONResponse(status_code=503, content=body)` is explicitly returned when `db_status != "ok"`. The status code is not just a dict field — it is the actual HTTP response status.

**HOWEVER:** No test covers the 503 degraded path (see P1 Blocker #2 below).

---

### ❌ AC7 — 7 tests, 0 regressions (PARTIAL — P1 BLOCKER)

All 7 tests exist and pass per the reported result (462 total, +7 from baseline 455). **However:**

**P1 BLOCKER #2 — No test for the 503 degraded path (AC6/AC7 gap)**

None of T20-S01 through T20-S07 test the DB-failure 503 path. The task card explicitly lists this as a **Priority Focus** item: "verify tests cover the degraded/503 path (even via monkeypatch)."

The missing test should:
```python
def test_health_returns_503_when_db_down(client, monkeypatch):
    """T20-S08: GET /health → 503 + {status: degraded, db: error} when DB unreachable."""
    from sqlalchemy.orm import Session
    monkeypatch.setattr(Session, "execute", lambda *a, **kw: (_ for _ in ()).throw(Exception("DB down")))
    r = client.get("/api/v1/health")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    assert body["db"] == "error"
```

The 503 code path is only exercised in production if the DB actually fails — there is **zero test coverage** for the most critical new behavior.

---

## P2 Warnings

### P2-W1 — `validate_required_env_vars()` passes in dev with default placeholder values

`config.py` has:
```python
secret_key: str = "dev-insecure-secret-change-me-in-production-0123456789"
database_url: str = "sqlite:///./data/mcp_dev.sqlite3"
```

Both have non-empty defaults, so `validate_required_env_vars()` **will never raise** in any environment that uses defaults, including production if someone forgets to set these. The validation only catches truly empty strings.

The AC says "raises RuntimeError if `MCP_SECRET_KEY` or `MCP_DATABASE_URL` **empty**" — technically met. But the intent (fail-fast in production with insecure defaults) is not fully achieved.

**Recommendation:** Add a `is_prod` guard: if `self.is_prod and self.secret_key.startswith("dev-insecure-secret")`, raise RuntimeError. (The existing `warn_if_insecure()` warns but does not block startup.)

### P2-W2 — `lru_cache` on `get_settings()` can cause `validate_required_env_vars()` to be called on a stale cached instance

`get_settings()` uses `@lru_cache`. In the test suite, `conftest.py` sets env vars before importing the app, which ensures the cached `Settings` instance has the right values. In production this is fine. However, if someone ever calls `get_settings.cache_clear()` between the cached-instance creation and the lifespan startup (e.g., in complex test setups), `validate_required_env_vars()` would run on a new Settings instance with potentially different env. Low risk, but worth noting. No action required.

---

## Summary

The core implementation of P1-FIX-01 (503 on DB failure), P1-FIX-02 (migration_version + feature_flags), and P1-FIX-03 (lifespan startup validation) is **correctly implemented** in the code. The 503 status code is explicitly set via `JSONResponse(status_code=503, ...)` — not just a dict field. The lifespan hook placement is correct.

**Two P1 blockers prevent approval:**
1. The root `/health` endpoint in `main.py` was not updated — load balancers using `/health` (not `/api/v1/health`) will never see a 503, defeating the purpose of P1-FIX-01.
2. There is no test for the DB-failure/503 degraded path — the single most important new behavior has zero test coverage.

Both are quick fixes (update root handler + add one monkeypatched test). Once resolved, the branch is ready to merge.
