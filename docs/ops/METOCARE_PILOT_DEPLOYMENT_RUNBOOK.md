# MetoCare — Pilot Deployment Runbook

> **T18D · Ops Runbook**
> Branch: `feature/t18d-pilot-deploy-runbook`
> Last updated: 2026-06-18
> Owner: DevOps / Backend Lead
> Environment scope: **Pilot (staging-like, real data, limited users)**

---

## Overview

This runbook covers the end-to-end procedure for deploying the MetoCare backend
for the first pilot launch. It is intentionally prescriptive — follow each step
in order, check boxes as you go. Deviations must be documented.

Audience: whoever presses the deploy button. Assumes `git`, `alembic`, and
`python` (or the container runtime) are available on the deploy host.

---

## 1. Pre-Deploy Checklist

### 1.1 Environment Variables

All variables use the `MCP_` prefix. Set via secret manager / environment
injection — **never** hardcode in code, Dockerfile, or CI logs.

| Variable | Required for Prod | Default (dev) | Notes |
|---|---|---|---|
| `MCP_ENV` | ✅ | `dev` | Set to `prod` or `pilot` |
| `MCP_DEBUG` | ✅ | `True` | Set to `False` in prod |
| `MCP_SECRET_KEY` | ✅ | `dev-insecure-secret-*` | **Must change.** ≥ 32 chars, high entropy. Failure mode: startup warns loudly; tokens signed with weak key. |
| `MCP_ENCRYPTION_KEYS` | ✅ | Fernet placeholder | Comma-separated Fernet keys. First = active encrypt key; all = decrypt (rotation support). Generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `MCP_DATABASE_URL` | ✅ | `sqlite:///./data/mcp_dev.sqlite3` | Use `postgresql+asyncpg://...` (TimescaleDB preferred) for prod. See §2 for SQLite vs PG differences. |
| `MCP_AI_MODE` | ✅ | `mock` | `mock` (no LLM calls) or `gateway` (real LLM via gateway). **Set to `mock` for pilot unless AI features are medically approved.** |
| `MCP_OCR_MODE` | ✅ | `mock` | `mock` or `provider`. Set to `mock` unless OCR pipeline is ready. |
| `MCP_STORAGE_MODE` | ✅ | `local` | `local`, `s3`, or `minio`. Use `s3`/`minio` in prod. |
| `MCP_LLM_GATEWAY_URL` | if `ai_mode=gateway` | `""` | URL of internal LLM gateway |
| `MCP_LLM_API_KEY` | if `ai_mode=gateway` | `""` | API key for LLM gateway |
| `MCP_LLM_PROVIDER` | if `ai_mode=gateway` | `mock` | `mock`, `openai`, `anthropic` |
| `MCP_OCR_PROVIDER_URL` | if `ocr_mode=provider` | `""` | OCR provider endpoint |
| `MCP_OCR_API_KEY` | if `ocr_mode=provider` | `""` | OCR provider API key |
| `MCP_STORAGE_LOCAL_DIR` | if `storage_mode=local` | `./storage` | Ensure writable |
| `MCP_LOG_LEVEL` | ✅ | `INFO` | `INFO` for prod, `DEBUG` only for troubleshooting |
| `MCP_METRICS_ENABLED` | ✅ | `True` | `False` if `/metrics` must not be publicly accessible |
| `MCP_ENABLE_DOCS` | ✅ | `True` | Forced `False` in prod by app logic regardless; can be omitted |
| `MCP_API_PREFIX` | Optional | `/api/v1` | Only change if behind a path-stripping proxy |
| `MCP_ACCESS_TOKEN_TTL_MINUTES` | Optional | `15` | Keep short (15m) in prod |
| `MCP_REFRESH_TOKEN_TTL_MINUTES` | Optional | `10080` (7d) | Adjust per policy |
| `MCP_RATELIMIT_ENABLED` | ✅ | `True` | Must be `True` in prod |
| `MCP_RATELIMIT_BACKEND` | Optional | `memory` | `redis` for multi-instance; requires `MCP_RATELIMIT_REDIS_URL` |
| `MCP_RATELIMIT_REDIS_URL` | if redis backend | `""` | e.g. `redis://redis:6379/0` |
| `MCP_LOCKOUT_MAX_FAILURES` | Optional | `5` | Auth lockout threshold |
| `MCP_LOCKOUT_COOLDOWN_MINUTES` | Optional | `15` | Auth lockout cooldown |
| `MCP_LLM_MAX_REQUESTS_PER_MINUTE` | Optional | `20` | Per-user LLM rate limit |
| `MCP_LLM_MAX_TOKENS_PER_MINUTE` | Optional | `20000` | Per-user LLM token budget |
| `MCP_LLM_CACHE_ENABLED` | Optional | `True` | LRU response cache; disable only for debugging |
| `MCP_RAG_ENABLED` | Optional | `True` | Enable RAG retrieval |
| `MCP_EMBEDDING_PROVIDER` | Optional | `mock` | `mock` or `openai` |
| `MCP_VECTOR_STORE` | Optional | `memory` | `memory`, `pgvector`, `qdrant` |
| `MCP_RAG_SEED_DIR` | Optional | `./data/rag_seed` | Path to RAG seed data |
| `MCP_OCR_WORKER_ENABLED` | Optional | `True` | Enable background OCR queue |
| `MCP_AUDIT_RETENTION_AUTH_DAYS` | Optional | `365` | Auth audit retention |
| `MCP_AUDIT_RETENTION_DATA_ACCESS_DAYS` | Optional | `730` | Data access audit retention |
| `MCP_AUDIT_RETENTION_ADMIN_DAYS` | Optional | `1095` | Admin audit retention |

> **⚠️ Prod startup warnings:** If `MCP_ENV=prod` and `SECRET_KEY` or
> `ENCRYPTION_KEYS` are the dev defaults, the app logs a warning at startup. Treat
> these as **deploy blockers**.

### 1.2 Security Pre-flight

- [ ] `MCP_SECRET_KEY` is NOT the default `dev-insecure-secret-change-me-in-production-0123456789`
- [ ] `MCP_SECRET_KEY` is ≥ 32 characters (required for HS256 JWT signing)
- [ ] `MCP_ENCRYPTION_KEYS` is NOT the default Fernet placeholder
- [ ] `MCP_ENCRYPTION_KEYS` was generated with `Fernet.generate_key()`, not manually typed
- [ ] `MCP_DATABASE_URL` does NOT use SQLite (pilot should use PostgreSQL)
- [ ] `MCP_DEBUG=False`
- [ ] `MCP_ENABLE_DOCS=False` (or rely on app's forced-off-in-prod logic)
- [ ] No secrets in `.env` committed to git (`.env` is in `.gitignore`)
- [ ] TLS/HTTPS is configured on the reverse proxy layer

### 1.3 Feature Flags Pre-flight

Feature flags are set via environment variables: `FEATURE_<FLAG_NAME>=true|false`.
Default is **fail-closed** (disabled) for all AI flags.

| Flag | Env Var | Default | Required State for Pilot |
|---|---|---|---|
| `AI_TRIAGE` | `FEATURE_AI_TRIAGE` | `false` | `false` — **disabled until Medical Board approval** |
| `AI_LAB_INTERPRET` | `FEATURE_AI_LAB_INTERPRET` | `false` | `false` — disabled |
| `AI_CARE_PLAN_DRAFT` | `FEATURE_AI_CARE_PLAN_DRAFT` | `false` | `false` — disabled |
| `AI_SAFETY_LAYER` | `FEATURE_AI_SAFETY_LAYER` | `false` | `false` — disabled |
| `DOCTOR_REVIEW_GATE` | `FEATURE_DOCTOR_REVIEW_GATE` | `true` | `true` — **mandatory, do not disable** |
| `CONSENT_GATE` | `FEATURE_CONSENT_GATE` | `true` | `true` — **mandatory, do not disable** |
| `AI_SESSION_ENABLED` | `FEATURE_AI_SESSION_ENABLED` | `false` | `false` — disabled |
| `AI_CLINICAL_RECS_ENABLED` | `FEATURE_AI_CLINICAL_RECS_ENABLED` | `false` | `false` — disabled |
| `AI_ESCALATION_ENABLED` | `FEATURE_AI_ESCALATION_ENABLED` | `false` | `false` — disabled |

> **Rule:** Never enable AI feature flags in a pilot unless the Medical Board has
> approved that specific feature. `DOCTOR_REVIEW_GATE` and `CONSENT_GATE` must
> **always** be `true`.

### 1.4 AI / OCR / Storage Mode Confirmation

- [ ] `MCP_AI_MODE=mock` (unless AI pipeline is ready and medically approved)
- [ ] `MCP_OCR_MODE=mock` (unless OCR pipeline is connected and tested)
- [ ] `MCP_STORAGE_MODE` set correctly (`local` for single-instance pilot, `s3`/`minio` for production)
- [ ] If `storage_mode=local`, confirm `MCP_STORAGE_LOCAL_DIR` is writable and on persistent storage

---

## 2. Migration Checklist

### 2.1 Complete Migration Chain (in order)

The full chain from initial schema to HEAD:

| # | Revision ID | Description | File |
|---|---|---|---|
| 1 | `2c30ffd33627` | Initial schema — 14 core entities | `2c30ffd33627_initial_schema_14_core_entities.py` |
| 2 | `85416e7ef0e9` | TimescaleDB hypertable + continuous aggregate | `85416e7ef0e9_timescaledb_hypertable_and_continuous_.py` |
| 3 | `fad70c6f2d60` | Encrypt PHI fields (field-level encryption) | `fad70c6f2d60_encrypt_phi_fields.py` |
| 4 | `65849f86200f` | Refresh tokens + MFA | `65849f86200f_refresh_tokens_and_mfa.py` |
| 5 | `8e3134ab9679` | Refresh token family + audit severity | `8e3134ab9679_refresh_token_family_and_audit_severity.py` |
| 6 | `a1b2c3d4e5f6` | Lab document pipeline status | `a1b2c3d4e5f6_lab_document_pipeline_status.py` |
| 7 | `t4_m0_role` | Add `ai_service` to UserRole constraint | `t4_m0_role_add_ai_service_to_userrole_constraint.py` |
| 8 | `t4_m1_ren_conv` | Rename ai_conversations → ai_sessions | `t4_m1_ren_conv_rename_ai_conversations_to_ai_sessions.py` |
| 9 | `t4_m2_ext_sess` | Extend ai_session fields | `t4_m2_ext_sess_extend_ai_session_fields.py` |
| 10 | `t4_m3_add_recs` | Add ai_clinical_recommendations | `t4_m3_add_recs_add_ai_clinical_recommendations.py` |
| 11 | `t4_m4_add_encs` | Add encounter table | `t4_m4_add_encs_add_encounter_table.py` |
| 12 | `t4_m4b_enc_fk` | Add encounter FK to ai_sessions | `t4_m4b_enc_fk_add_encounter_fk_to_ai_sessions.py` |
| 13 | `t4_m5_add_cpln` | Add care_plan table | `t4_m5_add_cpln_add_care_plan_table.py` |
| 14 | `t4_m6_add_bksp` | Add booking health snapshot | `t4_m6_add_bksp_add_booking_health_snapshot.py` |
| 15 | `t4_m7_add_junc` | Add doctor_clinic junction | `t4_m7_add_junc_add_doctor_clinic_junction.py` |
| 16 | `t4_m8_ext_drcl` | Extend doctor_clinic fields | `t4_m8_ext_drcl_extend_doctor_clinic_fields.py` |
| 17 | `t4_m9_add_sdel` | Add soft-delete columns | `t4_m9_add_sdel_add_soft_delete_columns.py` |
| 18 | `t18_add_ntrl` | Add nutrition_logs table (T18) | `t18_add_nutrition_log.py` |
| 19 | `t19_add_triage_log` | Add triage_logs table (T19) | `t19_add_triage_log.py` |
| 20 | `t21_add_booking` | Add doctor_availability + booking_appointments (T21) | `t21_add_booking.py` |
| 21 | `t23_add_notifications` | Add notifications table (T23) | `t23_add_notifications.py` |
| 22 | `t27_uq_patient_profile_user_id` | Unique constraint patient_profiles.user_id — **HEAD** | `t27_unique_patient_profile_user_id.py` |

### 2.2 Run Migrations

```bash
# From repo root or inside the container
cd backend

# Check current revision (should be None on fresh DB, or prior revision on upgrade)
alembic current

# Apply all pending migrations to HEAD
alembic upgrade head

# Verify
alembic current
# Expected output: t27_uq_patient_profile_user_id (head)
```

### 2.3 Rollback Procedures

```bash
# Roll back the last migration (one step)
alembic downgrade -1

# Roll back to a specific named revision (e.g. stop before T18)
alembic downgrade t4_m9_add_sdel

# Roll back everything (DANGEROUS — use only on fresh deploy gone wrong)
alembic downgrade base
```

> After any rollback, re-deploy the matching code version before restarting the app.

### 2.4 SQLite vs PostgreSQL Differences

| Concern | SQLite (dev) | PostgreSQL / TimescaleDB (prod) |
|---|---|---|
| Migration `85416e7ef0e9` (TimescaleDB) | **No-op** — migration skips hypertable creation | Creates hypertable + continuous aggregate |
| Migration `t4_m0_role` (UserRole constraint) | **No-op** — no DB-level CHECK constraint on SQLite | Drops and recreates `userrole` CHECK constraint |
| Migration `fad70c6f2d60` (PHI encryption) | Column widening only | Column widening + note about re-encryption job for existing data |
| Transactions | Single-writer; DDL inside transaction | Full ACID; DDL transactional (can roll back failed migrations) |
| Concurrency | Not suitable for >1 connection | Required for multi-instance / worker deployments |
| **Pre-existing data + PHI encryption** | N/A (dev fresh DBs) | Must run `app.services.phi_migration.encrypt_existing_phi` one-off job after migration if rows existed pre-encryption |

### 2.5 Fresh Deploy vs Upgrade

**Fresh deploy (empty DB):**
```bash
alembic upgrade head  # creates all tables from scratch
```

**Upgrade from prior version:**
```bash
# 1. Take a DB backup BEFORE migration (see §4.2)
# 2. Run migration
alembic upgrade head
# 3. Smoke test (see §3)
# 4. If something goes wrong, rollback + restore backup
```

---

## 3. Smoke Test Runbook

Run these in order after a fresh deploy. Use `curl` or any HTTP client.
`BASE_URL` = your deployment URL (e.g. `https://api.pilot.metocare.vn`).

Replace placeholder values (`<...>`) with real values from prior steps.

### Step 1 — Health Check

```bash
curl -s $BASE_URL/health | jq .
# Expected: {"status": "ok"}
```
✅ Pass: `{"status": "ok"}`
❌ Fail: any error or connection refused → app is not running

### Step 2 — Info Endpoint

```bash
curl -s $BASE_URL/info | jq .
# Expected:
# {
#   "app": "Metabolic Care Platform",
#   "env": "pilot",        ← or "prod"
#   "ai_mode": "mock",     ← confirm this matches what you set
#   "ocr_mode": "mock",
#   "storage_mode": "local"  ← or "s3"/"minio"
# }
```
✅ Pass: all fields present, `env` is NOT `dev` in pilot
❌ Fail: `ai_mode: gateway` when you didn't configure it → check env vars

### Step 3 — Register a Test Patient

```bash
curl -s -X POST $BASE_URL/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "smoke-test@metocare.local",
    "password": "SmokeTest!2026",
    "full_name": "Smoke Test",
    "role": "patient"
  }' | jq .
# Expected: HTTP 201, user object with id
```
✅ Pass: `201 Created` with `id` field
❌ Fail: `422 Unprocessable Entity` → check request schema; `500` → check DB connection

### Step 4 — Login and Get Token

```bash
TOKEN=$(curl -s -X POST $BASE_URL/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=smoke-test@metocare.local&password=SmokeTest!2026" \
  | jq -r '.access_token')
echo "Token: $TOKEN"
# Expected: non-empty JWT string
```
✅ Pass: valid JWT (three dot-separated base64 segments)
❌ Fail: `401 Unauthorized` → user registration failed or password mismatch; `500` → SECRET_KEY issue

### Step 5 — Patient Profile

```bash
# First get the patient id from registration response, or decode the JWT
PATIENT_ID="<uuid-from-step-3>"

curl -s $BASE_URL/api/v1/patients/$PATIENT_ID/profile \
  -H "Authorization: Bearer $TOKEN" | jq .
# Expected: HTTP 200, patient profile object
```
✅ Pass: `200 OK` with profile data
❌ Fail: `403 Forbidden` → RBAC or consent issue; `404` → patient not found

### Step 6 — AI Triage (mock mode)

```bash
curl -s -X POST $BASE_URL/api/v1/ai/triage \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "patient_id": "'$PATIENT_ID'",
    "symptoms": ["fatigue", "increased thirst"],
    "vitals": {"blood_glucose": 7.2}
  }' | jq .
# Expected: triage result with risk_level, recommendations (mock response)
# If AI_TRIAGE feature flag is disabled: 403 or feature-not-enabled response
```
✅ Pass: structured triage response or explicit feature-disabled response
❌ Fail: `500` → check AI service config; unexpected real LLM call → verify `MCP_AI_MODE=mock`

### Step 7 — Metrics Endpoint

```bash
curl -s $BASE_URL/metrics | head -20
# Expected: Prometheus text format output (counter/histogram lines)
# If MCP_METRICS_ENABLED=False: 404 or disabled response
```
✅ Pass: Prometheus-format text with metric names like `http_requests_total`
❌ Fail: `404` → `MCP_METRICS_ENABLED=False` (check if intentional)

### Step 8 — Admin Audit Logs (requires admin token)

```bash
# Register or use an existing admin user
ADMIN_TOKEN="<admin-jwt>"

curl -s "$BASE_URL/api/v1/admin/audit-logs" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq .
# Expected: HTTP 200, paginated list (may be empty on fresh deploy)
```
✅ Pass: `200 OK` with `items` array (empty is fine on fresh DB)
❌ Fail: `403 Forbidden` → token is not admin role; `500` → DB issue

---

## 4. Rollback Procedure

### 4.1 Application Rollback

```bash
# 1. Identify the last known-good git SHA or tag
git log --oneline -10

# 2. Roll back the migration (if the new code introduced migrations)
cd backend && alembic downgrade -1

# 3. Checkout the prior code version
git checkout <prior-sha-or-tag>

# 4. Restart the application
# (depends on deployment method — Docker, systemd, etc.)
docker restart metocare-api
# or
systemctl restart metocare-api
```

### 4.2 Database Backup Before Upgrade

Always take a backup before running `alembic upgrade head`:

**PostgreSQL:**
```bash
pg_dump -Fc -d $DATABASE_NAME -h $DB_HOST -U $DB_USER \
  -f metocare_backup_$(date +%Y%m%d_%H%M%S).dump
```

**Restore:**
```bash
pg_restore -Fc -d $DATABASE_NAME -h $DB_HOST -U $DB_USER \
  metocare_backup_YYYYMMDD_HHMMSS.dump
```

**SQLite (dev only):**
```bash
cp ./data/mcp_dev.sqlite3 ./data/mcp_dev_backup_$(date +%Y%m%d).sqlite3
```

### 4.3 Migration Rollback Specifics

```bash
# Roll back T19 (triage_logs) only
alembic downgrade t18_add_ntrl

# Roll back T18 + T19 (nutrition_logs + triage_logs)
alembic downgrade t4_m9_add_sdel

# Roll back entire T4 chain (to pre-T4, leaving base schema intact)
alembic downgrade a1b2c3d4e5f6
```

> ⚠️ Rolling back `fad70c6f2d60` (PHI encryption migration) on a database with
> real patient data requires running the reverse re-encryption job first. Do not
> blindly `alembic downgrade` past this point on a live database.

### 4.4 Git Revert + Redeploy

```bash
git revert <bad-commit-sha>
git push origin main
# Trigger CI/CD pipeline for redeploy, or manually rebuild and restart
```

---

## 5. Health Check Coverage

### 5.1 Current `GET /health`

```json
{"status": "ok"}
```

**What this checks:** The application process started and the route handler executed.

**What this does NOT check:**
- Database connectivity (no DB query)
- Database migration version (no `alembic current` check)
- Encryption key validity (no Fernet test)
- External service reachability (LLM gateway, OCR provider)
- Redis connectivity (if rate limiting uses Redis backend)
- Disk space for local storage

### 5.2 Current `GET /info`

```json
{
  "app": "Metabolic Care Platform",
  "env": "dev",
  "ai_mode": "mock",
  "ocr_mode": "mock",
  "storage_mode": "local"
}
```

**What this exposes:** Runtime mode configuration.

**What is missing:**
- Current Alembic revision / migration version
- Uptime
- Build SHA / version tag
- Feature flag states

### 5.3 Known Health Check Gaps

These are tracked in `METOCARE_OBSERVABILITY_GAPS.md`:

| Gap | Impact | Workaround |
|---|---|---|
| No DB connectivity check in `/health` | Load balancer may route to an app that can't reach DB | Monitor DB separately; check smoke test step 3 manually |
| No migration version in `/health` or `/info` | Can't confirm migration ran from health endpoint | Run `alembic current` manually post-deploy |
| No Redis ping in `/health` | Rate limiting silently degrades if Redis is down | Monitor Redis separately |
| No encryption key validity check | Bad `ENCRYPTION_KEYS` only surfaces on first write | Verify with `python -c "from cryptography.fernet import Fernet; Fernet(b'<key>')"` pre-deploy |

---

## 6. Backup / Restore Assumptions

### 6.1 Data at Risk

The following tables contain patient data and must be covered by backup:

| Table | Data Type | Sensitivity |
|---|---|---|
| `users` | Identity, role, credentials | High |
| `patient_profiles` | PHI (field-level encrypted) | **Critical** |
| `health_metrics` | TimescaleDB hypertable | High |
| `audit_logs` | Append-only compliance log | High (compliance) |
| `triage_logs` | AI triage records (T19) | High |
| `nutrition_logs` | Nutrition intake logs (T18) | Medium |
| `ai_sessions` | AI session metadata | Medium |
| `ai_clinical_recommendations` | Clinical AI output | High |
| `encounters` | Clinical encounters | High |
| `care_plans` | Patient care plans | High |
| `lab_documents` | Uploaded lab files | High |
| `consents` | Patient consent records | **Critical** (legal) |
| `refresh_tokens` | Auth tokens | Medium (rotate on restore) |

### 6.2 SQLite (Dev Only)

```bash
# Backup
cp ./data/mcp_dev.sqlite3 ./data/mcp_dev.sqlite3.bak

# Restore
cp ./data/mcp_dev.sqlite3.bak ./data/mcp_dev.sqlite3
```

### 6.3 PostgreSQL / TimescaleDB (Pilot / Prod)

```bash
# Full backup
pg_dump -Fc -d metocare_db -h $DB_HOST -U $DB_USER \
  -f /backups/metocare_$(date +%Y%m%d_%H%M%S).dump

# Restore to new DB
createdb metocare_restore -h $DB_HOST -U $DB_USER
pg_restore -Fc -d metocare_restore -h $DB_HOST -U $DB_USER \
  /backups/metocare_YYYYMMDD_HHMMSS.dump

# TimescaleDB: ensure timescaledb extension is enabled on restore target
# CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
```

### 6.4 Object Storage (Lab Documents / Profile Photos)

- **Local storage:** Backup the `MCP_STORAGE_LOCAL_DIR` directory.
- **S3/MinIO:** Enable versioning + cross-region replication at the bucket level.
- Lab document files must be restorable and linked to the correct `lab_documents` DB rows.

### 6.5 PITR (Point-in-Time Recovery)

For production, configure PostgreSQL WAL archiving + continuous backup (e.g.
pgBackRest, Barman, or managed cloud PITR). WAL-based PITR allows recovery to
any point without slot gaps.

---

## 7. Post-Deploy Verification Checklist

- [ ] `GET /health` returns `{"status": "ok"}`
- [ ] `GET /info` shows correct `env`, `ai_mode`, `ocr_mode`, `storage_mode`
- [ ] `alembic current` shows `t27_uq_patient_profile_user_id (head)`
- [ ] Startup logs show NO insecure-config warnings
- [ ] Test user registration succeeds (Step 3)
- [ ] Test user login succeeds and returns valid JWT (Step 4)
- [ ] Feature flags confirmed: AI flags are `false`, review/consent gates are `true`
- [ ] `GET /metrics` responds (if `MCP_METRICS_ENABLED=True`)
- [ ] Audit log entry created for test user login (Step 8)
- [ ] No `500` errors in application logs during smoke test

---

## 8. Configuration Quick Reference

```bash
# Minimal prod-ready env file (fill in real values)
MCP_ENV=pilot
MCP_DEBUG=False
MCP_SECRET_KEY=<generate: python -c "import secrets; print(secrets.token_hex(32))">
MCP_ENCRYPTION_KEYS=<generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
MCP_DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/metocare_db
MCP_AI_MODE=mock
MCP_OCR_MODE=mock
MCP_STORAGE_MODE=s3
MCP_LOG_LEVEL=INFO
MCP_METRICS_ENABLED=True
MCP_ENABLE_DOCS=False
MCP_RATELIMIT_ENABLED=True

# Feature flags (all AI disabled for pilot)
FEATURE_AI_TRIAGE=false
FEATURE_AI_LAB_INTERPRET=false
FEATURE_AI_CARE_PLAN_DRAFT=false
FEATURE_AI_SAFETY_LAYER=false
FEATURE_DOCTOR_REVIEW_GATE=true
FEATURE_CONSENT_GATE=true
FEATURE_AI_SESSION_ENABLED=false
FEATURE_AI_CLINICAL_RECS_ENABLED=false
FEATURE_AI_ESCALATION_ENABLED=false
```

---

*See also: `METOCARE_OBSERVABILITY_GAPS.md` for known monitoring gaps to address before full production launch.*
