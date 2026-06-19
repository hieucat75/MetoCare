# PA-09 Pilot Deploy Preparation Report

**Date:** 2026-06-19  
**Executed by:** OpenClaw Coordinator (autonomous PA-09 execution)  
**Main SHA:** `02152e8` (verified clean)  
**Report scope:** Deploy preparation checklist + blocking gate assessment  

---

## Overall Status

| # | Task | Status |
|---|------|--------|
| 1 | Verify clean main | ✅ PASS |
| 2 | Final backend tests | ✅ PASS |
| 3 | Final frontend build | ✅ PASS |
| 4 | Verify env vars (backend + frontend) | ✅ DOCUMENTED |
| 5 | Verify seed_admin / seed_patient process | ✅ VERIFIED |
| 6 | Verify backup + migration runbook | ✅ VERIFIED (runbook gap found) |
| 7 | Deploy to staging/pilot | 🔴 **BLOCKED — infrastructure not provisioned** |
| 8 | Rerun PA-08 smoke against deployed URL | 🔴 **BLOCKED — no deployed URL** |
| 9 | Produce PA09_DEPLOY_REPORT.md | ✅ THIS DOCUMENT |

---

## 🔴 STOP — Infrastructure Blocker

**Actual pilot/staging deploy cannot proceed.** The following are missing:

| Missing | Detail |
|---------|--------|
| No hosting platform configured | No Fly.toml, no Railway config, no Render yaml, no Heroku Procfile |
| No Dockerfiles | Backend and frontend have no container definitions |
| Docker daemon not running | Colima stopped; `docker ps` fails with socket connection error |
| No GitHub Actions deploy workflow | `.github/workflows/ci.yml` runs tests only — no deploy step |
| No GitHub Actions secrets | `gh secret list` returns empty (no deploy tokens, no DB URLs) |
| No pilot server / domain | No staging URL, no TLS cert, no DNS |
| No staging database | No PostgreSQL/TimescaleDB instance provisioned |
| No staging secrets | `MCP_SECRET_KEY`, `MCP_ENCRYPTION_KEYS`, `MCP_DATABASE_URL` not set for any pilot environment |

**Action required from PTH before deploy can proceed:**
1. Choose a hosting platform (Fly.io, Railway, Render, DigitalOcean, AWS, VPS, etc.)
2. Provision a PostgreSQL instance (TimescaleDB recommended per runbook §2.4)
3. Generate and store production secrets (SECRET_KEY, ENCRYPTION_KEYS)
4. Write Dockerfiles for backend + frontend (or use platform buildpacks)
5. Configure a GitHub Actions deploy workflow with secrets
6. Register a domain and configure TLS

Steps 1–3 are PTH decisions. Once infrastructure decisions are made, implementation can be delegated to antigravity.

---

## Task 1 — Verify Clean Main ✅

```
Commit:  02152e8
Message: docs(pa08): smoke report — 16/18 PASS, 0 P0/P1 remaining, pilot-ready
Branch:  main
Remote:  https://github.com/hieucat75/MetoCare.git
Status:  clean (only tsconfig.tsbuildinfo and AGENTS.md unstaged — both non-blocking)
CI:      ✅ PASS on all 5 recent pushes (GitHub Actions CI)
```

Recent commit log:
```
02152e8 docs(pa08): smoke report — 16/18 PASS, 0 P0/P1 remaining, pilot-ready
6e65ba5 fix(pa08): smoke test P1 — lab contract fix + dev MFA bypass
ab1b538 docs(fe): FE_FINAL_VALIDATION_REPORT — pilot-ready verdict
c22e7a7 fix(fe-fix): PA-07 P1 contract fixes — 5 URL/field mismatches corrected
9c15d43 docs(pa07): backend contract verification
```

---

## Task 2 — Final Backend Tests ✅

```
Command: cd backend && ../.venv/bin/pytest tests/ --tb=no
Result:  535 passed, 1 skipped, 35 warnings in 11.67s
Failures: 0
```

All 535 tests pass. 1 skipped = TimescaleDB hypertable test (skipped when `MCP_TEST_POSTGRES_URL` is unset — expected in dev/local).

---

## Task 3 — Final Frontend Build ✅

```
Command: cd frontend && npm run build
Result:
  ✓ Compiled successfully
  ✓ Generating static pages (35/35)
  TypeScript: 0 errors
  Lint: 0 errors (5 pre-existing warnings in design-system only)
```

---

## Task 4 — Env Var Verification

### Backend — Required Variables

| Variable | Dev Default | Pilot/Prod Requirement | Status |
|----------|------------|----------------------|--------|
| `MCP_ENV` | `dev` | Must be `pilot` or `prod` | ⚠️ needs override |
| `MCP_DEBUG` | `True` | Must be `False` | ⚠️ needs override |
| `MCP_SECRET_KEY` | `dev-insecure-secret-*` | ≥32 chars, high entropy | 🔴 **MUST generate** |
| `MCP_ENCRYPTION_KEYS` | Fernet placeholder | Real Fernet key(s) | 🔴 **MUST generate** |
| `MCP_DATABASE_URL` | `sqlite:///./data/mcp_dev.sqlite3` | PostgreSQL+TimescaleDB | 🔴 **MUST provision** |
| `MCP_AI_MODE` | `mock` | `mock` for pilot | ✅ keep mock |
| `MCP_OCR_MODE` | `mock` | `mock` for pilot | ✅ keep mock |
| `MCP_STORAGE_MODE` | `local` | `local` or `s3` | ⚠️ depends on infra |
| `MCP_LOG_LEVEL` | `INFO` | `INFO` | ✅ |
| `MCP_RATELIMIT_ENABLED` | `True` | Must be `True` | ✅ |
| `MCP_SKIP_MFA_IN_DEV` | `False` | Must be `False` | ✅ default safe |
| `MCP_ENABLE_DOCS` | `True` | App forces `False` in prod | ✅ app-enforced |

**Generate secrets:**
```bash
# MCP_SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(48))"

# MCP_ENCRYPTION_KEYS
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Backend — Feature Flags (must all be set)

| Flag | Required Pilot Value | Safety Rule |
|------|---------------------|-------------|
| `FEATURE_AI_TRIAGE` | `false` | Disabled until Medical Board approval |
| `FEATURE_AI_LAB_INTERPRET` | `false` | Disabled |
| `FEATURE_AI_CARE_PLAN_DRAFT` | `false` | Disabled |
| `FEATURE_AI_SAFETY_LAYER` | `false` | Disabled |
| `FEATURE_DOCTOR_REVIEW_GATE` | **`true`** | **Mandatory — do not disable** |
| `FEATURE_CONSENT_GATE` | **`true`** | **Mandatory — do not disable** |
| `FEATURE_AI_SESSION_ENABLED` | `false` | Disabled |
| `FEATURE_AI_CLINICAL_RECS_ENABLED` | `false` | Disabled |
| `FEATURE_AI_ESCALATION_ENABLED` | `false` | Disabled |

### Frontend — Required Variables

| Variable | Dev Value | Pilot Value |
|----------|-----------|-------------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000/api/v1` | `https://api.pilot.metocare.vn/api/v1` (example) |

> Frontend has zero other env vars — intentionally simple. Only the API base URL changes.

### Minimal Pilot `.env` (template)

```bash
# ── App ───────────────────────────────────────────────────────────────────────
MCP_ENV=pilot
MCP_DEBUG=False
MCP_LOG_LEVEL=INFO

# ── Security (generate new values; never reuse dev defaults) ──────────────────
MCP_SECRET_KEY=<run: python -c "import secrets; print(secrets.token_urlsafe(48))">
MCP_ENCRYPTION_KEYS=<run: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">

# ── Database ──────────────────────────────────────────────────────────────────
MCP_DATABASE_URL=postgresql+psycopg2://mcp:STRONG_PASS@db-host:5432/metocare_pilot

# ── AI/OCR/Storage (all mock for pilot) ──────────────────────────────────────
MCP_AI_MODE=mock
MCP_OCR_MODE=mock
MCP_STORAGE_MODE=local
MCP_STORAGE_LOCAL_DIR=/app/storage

# ── Rate limiting ─────────────────────────────────────────────────────────────
MCP_RATELIMIT_ENABLED=True
MCP_RATELIMIT_BACKEND=memory

# ── Feature flags ─────────────────────────────────────────────────────────────
FEATURE_AI_TRIAGE=false
FEATURE_AI_LAB_INTERPRET=false
FEATURE_AI_CARE_PLAN_DRAFT=false
FEATURE_AI_SAFETY_LAYER=false
FEATURE_DOCTOR_REVIEW_GATE=true
FEATURE_CONSENT_GATE=true
FEATURE_AI_SESSION_ENABLED=false
FEATURE_AI_CLINICAL_RECS_ENABLED=false
FEATURE_AI_ESCALATION_ENABLED=false

# ── Dev-only flag (must be False in pilot/prod) ───────────────────────────────
MCP_SKIP_MFA_IN_DEV=False
```

---

## Task 5 — Seed Process Verification ✅

All three seed scripts verified working. Dry-run confirmed.

### Admin Seed (doctors/admins cannot self-register)

```bash
# From backend/ directory
# SQLite dev
python scripts/seed_admin.py \
  --email admin@metocare.vn \
  --password "PilotAdmin!2026" \
  --role super_admin \
  --full-name "MetoCare Pilot Admin"

# PostgreSQL pilot
MCP_DATABASE_URL=postgresql+psycopg2://... \
python scripts/seed_admin.py \
  --email admin@metocare.vn \
  --password "PilotAdmin!2026" \
  --role super_admin \
  --full-name "MetoCare Pilot Admin"

# Dry-run validation
python scripts/seed_admin.py --email ... --password ... --role super_admin --dry-run
```

Supported roles: `super_admin`, `internal_admin`, `doctor`, `clinic_admin`

### Patient Seed (full demographics for metabolic scoring)

```bash
python scripts/seed_patient.py \
  --email patient@metocare.vn \
  --password "PilotPatient!2026" \
  --full-name "Nguyen Van A" \
  --dob 1985-06-15 \
  --gender male \
  --height-cm 172 \
  --weight-kg 70
```

Both scripts are **idempotent** — safe to run repeatedly. Existing accounts print `SKIPPED`.

### Doctor Provisioning Note

Doctor accounts require:
1. Seed via `seed_admin.py --role doctor`
2. TOTP setup via app UI (or bypass with `MCP_SKIP_MFA_IN_DEV=true` in local dev only)
3. MFA is **mandatory** for `doctor`, `internal_admin`, `super_admin` roles in production

---

## Task 6 — Backup + Migration Runbook ✅ (with gap)

### Migration Chain Status

**Current HEAD:** `t27_uq_patient_profile_user_id`  
**Full chain (22 migrations):**

| # | Revision | Description |
|---|----------|-------------|
| 1 | `2c30ffd33627` | Initial schema — 14 core entities |
| 2 | `85416e7ef0e9` | TimescaleDB hypertable + continuous aggregate |
| 3 | `fad70c6f2d60` | Encrypt PHI fields |
| 4 | `65849f86200f` | Refresh tokens + MFA |
| 5 | `8e3134ab9679` | Refresh token family + audit severity |
| 6 | `a1b2c3d4e5f6` | Lab document pipeline status |
| 7–17 | `t4_m0` → `t4_m9` | AI sessions, recommendations, encounters, care plans, booking, clinic, soft-delete |
| 18 | `t18_add_ntrl` | Nutrition logs |
| 19 | `t19_add_triage_log` | Triage logs |
| 20 | `t21_add_booking` | Doctor availability + appointments |
| 21 | `t23_add_notifications` | Notifications table |
| 22 | `t27_uq_patient_profile_user_id` | Unique constraint patient_profiles.user_id ← **HEAD** |

⚠️ **Runbook gap:** `METOCARE_PILOT_DEPLOYMENT_RUNBOOK.md` §2.1 shows HEAD as `t19_add_triage_log` — **outdated**. Actual HEAD is `t27_uq_patient_profile_user_id` (3 additional migrations since runbook was written).

### Migration Commands (pilot fresh deploy)

```bash
cd backend

# 1. Backup FIRST (PostgreSQL)
pg_dump -Fc -d metocare_pilot -h $DB_HOST -U $DB_USER \
  -f /backups/metocare_pilot_$(date +%Y%m%d_%H%M%S).dump

# 2. Run migrations
MCP_DATABASE_URL=postgresql+psycopg2://... alembic upgrade head

# 3. Verify
MCP_DATABASE_URL=postgresql+psycopg2://... alembic current
# Expected: t27_uq_patient_profile_user_id (head)
```

### Rollback

```bash
# Roll back last migration (t27)
alembic downgrade t23_add_notifications

# Roll back to pre-PA series
alembic downgrade t4_m9_add_sdel
```

⚠️ **PHI encryption warning:** Do NOT roll back past `fad70c6f2d60` on a live database with patient data. Requires PHI re-encryption job first.

### Backup Reference

```bash
# PostgreSQL backup (before every migration)
pg_dump -Fc -d metocare_pilot -h $DB_HOST -U $DB_USER \
  -f metocare_pilot_backup_$(date +%Y%m%d_%H%M%S).dump

# Restore
pg_restore -Fc -d metocare_pilot_restore -h $DB_HOST -U $DB_USER \
  metocare_pilot_backup_YYYYMMDD_HHMMSS.dump

# SQLite (dev only)
cp data/mcp_dev.sqlite3 data/mcp_dev_backup_$(date +%Y%m%d).sqlite3
```

---

## Tasks 7 & 8 — Deploy + Smoke Against Deployed URL

### 🔴 BLOCKED — Cannot Execute

**Reason:** No staging/pilot infrastructure exists. See blocking list at top of this document.

**What is needed before PTH can resume PA-09:**

### PTH Decision Required

| Decision | Options |
|---------|---------|
| **Hosting platform** | Fly.io (recommended for small pilot), Railway, Render, DigitalOcean App Platform, bare VPS |
| **Database** | Supabase (free tier PostgreSQL), Neon.tech, Railway PostgreSQL, PlanetScale, self-hosted |
| **Frontend deploy** | Vercel (easiest for Next.js), Netlify, same platform as backend |
| **Domain** | metocare.vn or pilot.metocare.vn — needs DNS configuration |
| **Object storage** | Cloudflare R2 (free tier), AWS S3, MinIO on VPS |

### Recommended Minimal Pilot Stack (cost-optimized)

```
Backend:   Fly.io (free tier: 3 shared VMs)
Database:  Supabase (free tier: 500MB PostgreSQL — sufficient for pilot)
Frontend:  Vercel (free tier: Next.js native)
Storage:   Cloudflare R2 (free tier: 10GB)
Domain:    pilot.metocare.vn → Cloudflare DNS
TLS:       Auto via platform (Let's Encrypt)
```

**Cost: $0–5/month for a small pilot.**

Once PTH confirms the platform choice, antigravity can:
1. Write `backend/Dockerfile` + `frontend/Dockerfile`
2. Write `fly.toml` (or platform equivalent)
3. Add GitHub Actions deploy workflow (`.github/workflows/deploy.yml`)
4. Set all secrets in GitHub Actions
5. Run first deploy
6. Run `alembic upgrade head` on the pilot database
7. Run `seed_admin.py` for pilot admin/doctor accounts
8. Execute the PA-08 18-item smoke checklist against the deployed URL

---

## Runbook Gap — Update Required

`docs/ops/METOCARE_PILOT_DEPLOYMENT_RUNBOOK.md` §2.1 migration table is outdated. It shows HEAD as `t19_add_triage_log` but actual HEAD is `t27_uq_patient_profile_user_id` (3 migrations added: T21 booking, T23 notifications, T27 unique constraint).

The runbook needs update to add:

| # | Revision | Description |
|---|----------|-------------|
| 20 | `t21_add_booking` | Doctor availability + appointments (T21) |
| 21 | `t23_add_notifications` | Notifications table (T23) |
| 22 | `t27_uq_patient_profile_user_id` | Unique constraint patient_profiles.user_id ← **HEAD** |

---

## Summary

| Item | Result |
|------|--------|
| Main HEAD | `02152e8` — clean, all CI passing |
| Backend tests | **535 passed**, 1 skipped |
| Frontend build | **35/35 pages**, 0 errors |
| Env var template | Documented (see §4) |
| Seed scripts | Verified idempotent, dry-run clean |
| Migration chain | 22 migrations, HEAD `t27_uq_patient_profile_user_id` |
| Runbook | Valid (§2.1 migration table stale — needs 3 rows added) |
| **Actual deploy** | 🔴 **BLOCKED — infrastructure not provisioned** |
| **Smoke vs live URL** | 🔴 **BLOCKED — no deployed URL** |

**Next action: PTH to confirm hosting platform.** Once confirmed, antigravity implements Dockerfiles + deploy workflow in one task.
