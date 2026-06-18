# MetoCare Pilot Deploy Report — 2026-06-18

**Deploy SHA:** `ae4061b`  
**Authorized by:** PTH (message #1094, 2026-06-18 22:30 GMT+7)  
**Environment:** Local pilot (TimescaleDB + Redis via Docker/Colima)  
**Deployer:** OpenClaw autonomous coordinator

---

## Conditions Met

| Condition | Status |
|-----------|--------|
| Deploy main HEAD `ae4061b` only | ✅ Confirmed |
| Pre-deploy backup/migration check | ✅ Fresh DB — no pg_dump needed; migrations ran clean |
| Health check after deploy | ✅ `{"status":"ok","db":"ok"}` |
| T26 smoke checklist run | ✅ All critical paths verified (see below) |
| No new backend feature work | ✅ No code changes during deploy |
| Rollback plan documented | ✅ (runbook §4) |

---

## Infrastructure

| Service | Image | Status |
|---------|-------|--------|
| TimescaleDB | `timescale/timescaledb-ha:pg16` | ✅ Healthy |
| Redis | `redis:7-alpine` | ✅ Healthy |
| MinIO | Not started (local storage mode) | Deferred |

Runtime: Colima (macOS Virtualization.Framework, aarch64, 2 CPU, 4 GB RAM)

---

## Migration

```
alembic upgrade head  →  t23_add_notifications (head)
```

Full chain applied:
- Initial schema (14 entities)
- TimescaleDB hypertable (no-op on fresh DB for TimescaleDB, but extension available)
- PHI field encryption
- Refresh tokens + MFA
- ...all T4 chain migrations...
- T18: nutrition_logs
- T19: triage_logs
- T21: doctor_availability + booking_appointments
- T23: notifications

**Result: `t23_add_notifications (head)` ✅**

---

## Smoke Test Results

| Step | Endpoint | Result | Notes |
|------|----------|--------|-------|
| 1 | `GET /api/v1/health` | ✅ `{"status":"ok","db":"ok"}` | DB connectivity confirmed |
| 2 | `GET /api/v1/info` | ✅ `env=pilot`, `ai_mode=mock`, all AI flags false | Feature flags confirmed |
| 3 | `POST /api/v1/auth/register` | ✅ 201, patient-only enforced | `super_admin` role rejected — correct |
| 4 | `POST /api/v1/auth/login` | ✅ Valid JWT returned | `role`, `user_id` in response |
| 5 | Admin seed (direct DB) | ✅ SUPER_ADMIN created | `pilot-admin@metocare.vn` |
| 6 | `GET /api/v1/admin/users` | ✅ MFA enrollment required | Correct security gate for admin |
| 7 | Patient RBAC | ✅ 403 on admin-only routes | RBAC enforced |
| 8 | Migration version in /info | ✅ `t23_add_notifications` | T20 requirement confirmed |

---

## /info Confirmed State

```json
{
  "app": "Metabolic Care Platform",
  "env": "pilot",
  "ai_mode": "mock",
  "ocr_mode": "mock",
  "storage_mode": "local",
  "migration_version": "t23_add_notifications",
  "feature_flags": {
    "ai_triage": false,
    "ai_lab_interpret": false,
    "ai_care_plan_draft": false,
    "ai_safety_layer": false,
    "doctor_review_gate": true,
    "consent_gate": true,
    "ai_session_enabled": false,
    "ai_clinical_recs_enabled": false,
    "ai_escalation_enabled": false
  }
}
```

---

## Security Gates Confirmed

- ✅ Patient self-registration forced to `PATIENT` role (cannot self-promote to admin)
- ✅ Admin requires MFA enrollment before any admin API access
- ✅ RBAC enforced at route level (patient → 403 on admin routes)
- ✅ All AI feature flags `false` (medical board approval required before enabling)
- ✅ `DOCTOR_REVIEW_GATE=true`, `CONSENT_GATE=true`

---

## Known Notes for Production Deployment

1. **PatientProfile seeding**: `PatientProfile` entity is separate from `User`. Pilot admin must seed profiles for enrolled patients via admin API or direct DB import. Cannot self-create via `/register`.
2. **Admin accounts**: Must be seeded directly (registration enforces PATIENT-only). Recommend a `scripts/seed_admin.py` script for production.
3. **MFA for admin**: All admin roles require MFA enrollment before API access — correct. Production admins must enroll MFA immediately after account creation.
4. **TimescaleDB hypertable**: Migration `85416e7ef0e9` creates hypertable on `health_metrics`. Confirm TimescaleDB extension is active: `CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;`
5. **psycopg2-binary**: Added to venv for Postgres connectivity. Add to `requirements.txt` for production Docker builds.

---

## Next Steps (Post-Deploy)

Per PTH directive: **Switch focus to Patient App MVP. Doctor Portal deferred.**

Recommended immediate actions:
1. Add `psycopg2-binary` to `requirements.txt`
2. Create `scripts/seed_admin.py` for pilot admin account seeding
3. Define Patient App MVP scope and roadmap

---

**Deploy Status: ✅ PILOT LIVE — All conditions met**
