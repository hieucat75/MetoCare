# MetoCare — Legacy DigitalOcean Infrastructure

**Status:** DEPRECATED — 2026-06-28  
**Decision by:** PTH  
**Reason:** Azure Container Apps confirmed as sole active deployment target.

## Why It Was Retired

DigitalOcean VPS was set up as the initial production environment (see `docs/MIGRATION_REPORT_DO_20260620.md`).
Azure Container Apps (ACA) was initially designated "staging only" but became the primary active environment as:
- Frontend was only deployed on Azure (never on DO VPS)
- DO VPS nginx has `server_name _` (no domain configured), SSL commented out as `DOMAIN_PLACEHOLDER`
- No DNS records point to `146.190.83.230`
- DO VPS has no Let's Encrypt certificate
- DO VPS migration is 8 versions behind ACA staging head

## What Remains on the Server

| Component | State |
|-----------|-------|
| IP | `146.190.83.230` |
| Backend | Running (`ghcr.io/hieucat75/metocare-backend:f2dc996`) |
| Postgres 16 | Running (migration: `t27_uq_patient_profile_user_id`) |
| Redis 7 | Running |
| Nginx | Running (HTTP only, port 80, no domain) |
| Frontend | NOT deployed |
| SSL/HTTPS | NOT configured |
| Domain | NOT configured |
| Last deploy | `f2dc996` (approx. 2026-06-22) |

## Archive Instructions

If PTH decides to decommission the VPS:
1. Take final DB dump: `docker exec metocare-postgres-1 pg_dump -U mcpadmin metocare > final_backup.sql`
2. Copy backup off-server
3. `docker compose down`
4. Destroy DigitalOcean Droplet via console

## Rollback Instructions (if Azure fails and DO needed temporarily)

DO NOT downgrade DB schema — `t8_m1_unitlen` downgrade risks silent data loss (see migration file).
App rollback only: update `IMAGE_TAG` in `/opt/metocare/.env` and `docker compose up -d --no-deps backend`.
DB is 8 migrations behind — DO VPS cannot run code from `bb4c309` without running migrations first.

## Related Files (retained, not deleted)

- `.github/workflows/deploy-do.yml` — legacy workflow
- `deploy/do/` — VPS setup scripts
- `docs/MIGRATION_REPORT_DO_20260620.md` — original migration report
- `docs/agent/PRODUCTION_HARDENING_REPORT_20260620.md` — VPS hardening report
