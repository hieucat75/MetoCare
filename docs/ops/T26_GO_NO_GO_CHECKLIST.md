# T26 — Pilot Go/No-Go Checklist

**Sprint:** T26 — Final Pilot Hardening  
**Date:** 2026-06-18  
**Prepared by:** Claude Code (T26 subagent)  
**Approved by:** Pending PTH sign-off  

---

## Verdict: **GO** ✅

All P0 and P1 items are complete. Four items are deferred to post-pilot and documented with
remediation plans. The system is ready for a controlled pilot deployment with the
constraints noted in the "Deferred" section.

---

## Technical Readiness

| Item | Status | Detail |
|------|--------|--------|
| ✅ All API tests pass | **PASS** | 515/516 — 1 skipped (TimescaleDB, architectural) |
| ✅ Ruff clean | **PASS** | `All checks passed` |
| ✅ All P0/P1 Codex findings resolved | **PASS** | T6–T25 Codex reviews: 0 open P0/P1 blockers |
| ✅ DB health check returns 503 on failure | **PASS** | `GET /health` → 503 + `{"status":"unhealthy"}` when DB unreachable (T25) |
| ✅ Startup validation of required env vars | **PASS** | `Settings` raises `ValidationError` on missing `JWT_SECRET` / `DATABASE_URL` (T25) |
| ✅ Migration version in /info | **PASS** | `GET /info` returns `db_version` from Alembic head revision (T25) |
| ✅ PDF export works with reportlab installed | **PASS** | `GET /patients/{id}/summary/pdf` → 200 + `application/pdf` (T24) |
| ✅ ImportError guard in pdf_report.py | **PASS** | Module-level RuntimeError on missing reportlab (T26) |
| ✅ Rate limiting in-memory | **PASS** | Token bucket + lockout manager; 429 on auth spam, 423 on lockout (T10) |

---

## Clinical Safety

| Item | Status | Detail |
|------|--------|--------|
| ✅ Clinical red-team tests pass | **PASS** | 30/30 red-team scenarios pass (`T18C_CLINICAL_SAFETY_REDTEAM.md`) |
| ✅ PATIENT cannot access another patient's data | **PASS** | Cross-patient ownership checks on all endpoints; 403 on violation |
| ✅ AI_SERVICE cannot create clinical records with accepted status | **PASS** | C1 safety invariant — `@validates` hook on model rejects forbidden status (T8) |
| ✅ AI_SERVICE cannot approve care plans | **PASS** | Explicit 403 for AI_SERVICE on care plan approval endpoint (T20) |
| ✅ DOCTOR requires consent before accessing patient data | **PASS** | ConsentGuard enforced on profile, lab, summary, PDF endpoints |
| ✅ AI triage safety escalation | **PASS** | Critical risk level → escalation flag set; safety guardrails enforced (T18C) |
| ✅ MFA required for admin actions | **PASS** | `require_mfa=True` enforced on unlock, audit log, and admin endpoints (T9) |
| ✅ Audit trail for all state-changing actions | **PASS** | `AuditLog` entries created for all create/update/delete/close operations |
| ✅ Soft-delete (no hard-delete of clinical data) | **PASS** | All deletions are soft (`deleted_at`) — data retained, not destroyed |

---

## Operational Readiness

| Item | Status | Detail |
|------|--------|--------|
| ✅ Pilot deployment runbook exists | **PASS** | `docs/ops/METOCARE_PILOT_DEPLOYMENT_RUNBOOK.md` (T18D) |
| ✅ Observability gaps documented | **PASS** | `docs/ops/METOCARE_OBSERVABILITY_GAPS.md` (T18D) |
| ✅ UI/API contract documented | **PASS** | `docs/product/METOCARE_PILOT_UI_CONTRACT.md` (T18B) |
| ✅ API versioned (`/api/v1/`) | **PASS** | All routes under `/api/v1/` prefix |
| ✅ Structured error responses | **PASS** | All errors return `{"detail": "..."}` JSON |
| ✅ CORS configured | **PASS** | Configured in `app/main.py` via settings |
| ✅ No hardcoded secrets in codebase | **PASS** | All secrets via env vars / `Settings` (Pydantic BaseSettings) |

---

## Deferred Items (Post-Pilot)

These items do **not block** pilot launch. They are documented, tracked, and scheduled
for the first post-pilot sprint.

| # | Item | Reason Deferred | Tracking |
|---|------|-----------------|---------|
| D1 | Real push/email notification transport | In-app notifications only; `send_push/send_email` are stubs that always succeed (T23) | First post-pilot sprint |
| D2 | AI_SERVICE session close ownership check | `service_account_id` field missing on AISession model — requires migration (T26, T18A P2-W2) | `docs/CODEX_REVIEW_T26.md` P2-D1 |
| D3 | `valid_until` filter on consent list | `active_only` filter incomplete — does not check `valid_until` expiry (T18A P2-W1) | `docs/CODEX_REVIEW_T26.md` P2-D2 |
| D4 | Real Redis rate limiting | In-memory rate limiting (resets on restart); no Redis dependency in pilot (T10, test_migrations skip) | Post-pilot infra sprint |
| D5 | Medical board sign-off on vital thresholds | Normal ranges are clinical defaults pending medical review (T18C P2) | Pre-GA requirement |
| D6 | TimescaleDB hypertable integration test | Requires real PostgreSQL + TimescaleDB; 1 test skipped (T4) | `docs/CODEX_REVIEW_T26.md` P2-D3 |

---

## Pre-Deploy Checklist (Production Environment)

These items must be verified by the deployment team before go-live:

- [ ] `JWT_SECRET` set to a cryptographically random 64-char string (not default)
- [ ] `DATABASE_URL` points to production PostgreSQL
- [ ] `ENVIRONMENT=production` set in environment
- [ ] `ALLOWED_ORIGINS` set to pilot frontend domain
- [ ] Alembic migrations applied: `alembic upgrade head`
- [ ] `GET /api/v1/health` returns 200
- [ ] `GET /api/v1/info` returns correct `db_version`
- [ ] `reportlab` installed in production environment (`pip install reportlab>=4.0`)
- [ ] Pilot user accounts created (seed data)
- [ ] Observability/logging configured per `METOCARE_OBSERVABILITY_GAPS.md`

---

## Final Sign-Off

| Role | Name | Date | Status |
|------|------|------|--------|
| Engineering Lead | PTH | — | ⏳ Pending |
| Claude Code Agent | Claude Code T26 | 2026-06-18 | ✅ Signed |
| Codex Review | Codex | — | ⏳ Pending |
