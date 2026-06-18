# T20 — Production Hardening: Health Check + Observability P1 Fixes

**Branch:** `feature/t20-production-hardening`
**Base:** `main` (`f1c0e4c`)
**Owner:** Claude Code
**Status:** ✅ READY FOR CODEX REVIEW
**Date:** 2026-06-18

---

## Objective

Fix all P1 observability gaps identified by T18D before pilot go-live.
See: `docs/ops/METOCARE_OBSERVABILITY_GAPS.md`

---

## Scope

### P1 Fixes (All Implemented)

| ID | Gap | Fix | File |
|----|-----|-----|------|
| P1-FIX-01 | No DB check in `/health` | DB connectivity probe + HTTP 503 on failure | `system.py` |
| P1-FIX-02 | No migration version / feature flags in `/info` | `migration_version` + `feature_flags` dict | `system.py` |
| P1-FIX-03 | No startup env var validation | `validate_required_env_vars()` at lifespan startup | `config.py`, `main.py` |

### P2/P3 Gaps (Documented, Not Fixed in T20)

See `docs/ops/METOCARE_OBSERVABILITY_GAPS.md` for full inventory.
- **P2**: Distributed tracing (OpenTelemetry), structured log shipping, alerting rules
- **P3**: `/metrics` auth gating, SLO/SLA dashboards

---

## Files Changed

| File | Change |
|------|--------|
| `backend/app/api/v1/routes/system.py` | P1-FIX-01 + P1-FIX-02: DB health check + migration version + feature flags |
| `backend/app/core/config.py` | P1-FIX-03: `validate_required_env_vars()` method |
| `backend/app/main.py` | P1-FIX-03: call validation in lifespan startup hook |
| `backend/tests/api/test_system_api.py` | NEW: 7 tests for health + info endpoints |
| `docs/agent/T20_TASK_CARD.md` | This file |
| `docs/agent/T20_IMPLEMENTATION_REPORT.md` | Implementation details |

---

## Test Results

```
462 passed, 1 skipped
Baseline: 455 passed, 1 skipped
Net new: +7 tests
Ruff: PASS (0 errors)
```

---

## Validation Commands

```bash
cd /Users/pth/Developer/Metocare/backend
source ../.venv/bin/activate
ruff check app/api/v1/routes/system.py app/core/config.py app/main.py tests/api/test_system_api.py
python -m pytest tests/ -q
```
