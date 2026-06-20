# MetoCare — DigitalOcean Production Migration Report
**Date:** 2026-06-20  
**Status:** ✅ COMPLETE

---

## Summary

Migrated MetoCare from Azure App Service (suspended due to ContainerCreateFailure
blocking issues) to a self-managed DigitalOcean Droplet with full Docker Compose stack.

---

## Infrastructure

| Component | Detail |
|-----------|--------|
| Provider | DigitalOcean |
| Droplet | `metocare-vps` (ID: 578953030) |
| Region | Singapore (sgp1) |
| Size | s-2vcpu-4gb — 2 vCPU / 4 GB RAM / 80 GB SSD |
| OS | Ubuntu 24.04 LTS |
| Public IP | `146.190.83.230` |
| Cost | ~$24/month |

---

## Stack

| Service | Image | Status |
|---------|-------|--------|
| backend | `ghcr.io/hieucat75/metocare-backend:4356fc0` | ✅ healthy |
| postgres | `postgres:16-alpine` | ✅ healthy |
| redis | `redis:7-alpine` | ✅ healthy |
| nginx | `nginx:1.27-alpine` | ✅ running |

Deploy dir: `/opt/metocare/`

---

## Security

| Component | Config |
|-----------|--------|
| UFW | allow 22/80/443 only |
| fail2ban | enabled |
| SSH | ed25519 key only (`metocare-do-deploy`) |
| Secrets | `/opt/metocare/.env` (chmod 600, not in git) |
| DB | internal Docker network only, not exposed |
| Redis | internal Docker network only, not exposed |

---

## Alembic Migrations Applied

22 migrations applied — HEAD: `t27_uq_patient_profile_user_id`

- `2c30ffd33627` initial schema 14 core entities  
- `85416e7ef0e9` timescaledb (skipped gracefully — plain PostgreSQL)  
- `fad70c6f2d60` encrypt PHI fields  
- `65849f86200f` refresh tokens and mfa  
- `8e3134ab9679` refresh token family and audit severity  
- `a1b2c3d4e5f6` lab document pipeline status  
- `t4_m0_role` add ai_service to users.role  
- `t4_m1_ren_conv` rename ai conversations to ai sessions  
- `t4_m2_ext_sess` extend ai session fields  
- `t4_m3_add_recs` add ai clinical recommendations  
- `t4_m4_add_encs` add encounter table  
- `t4_m4b_enc_fk` add encounter FKs  
- `t4_m5_add_cpln` add care plan table  
- `t4_m6_add_bksp` add booking health snapshot  
- `t4_m7_add_junc` add doctor clinic junction  
- `t4_m8_ext_drcl` extend doctor clinic fields  
- `t4_m9_add_sdel` add soft delete columns  
- `t18_add_ntrl` add nutrition_logs table  
- `t19_add_triage_log` add triage_logs table  
- `t21_add_booking` add doctor_availability and booking_appointments  
- `t23_add_notifications` add notifications table  
- `t27_uq_patient_profile_user_id` add unique constraint patient_profiles.user_id ← HEAD

---

## Verification Results

| Test | Result |
|------|--------|
| `GET /health` | ✅ HTTP 200 `{"status":"ok"}` |
| `GET /api/v1/info` | ✅ HTTP 200 — env=prod, migration_version=t27_uq_patient_profile_user_id |
| Restart survival | ✅ HTTP 200 within 20s of `docker compose restart backend` |
| 2-worker boot | ✅ No create_all() race — schema Alembic-only |

---

## Code Changes (Runtime Schema Removal)

| File | Change |
|------|--------|
| `backend/app/main.py` | Removed `from app.core.database import create_all` and entire create_all() block |
| `backend/startup.sh` | `-w 2` → `--workers 1` |
| `backend/Dockerfile` | Explicit gunicorn CMD, `--workers 1`, `/tmp/gunicorn` writable |
| `backend/alembic/versions/85416e7ef0e9_...py` | SAVEPOINT guard for TimescaleDB — skips gracefully on plain PostgreSQL |

---

## DNS Records Required

Point your domain to `146.190.83.230`:

```
A    @              146.190.83.230    TTL 300
A    api            146.190.83.230    TTL 300
A    metocare       146.190.83.230    TTL 300
```

After DNS propagates, run certbot for TLS:
```bash
ssh root@146.190.83.230
apt-get install -y certbot python3-certbot-nginx
certbot --nginx -d yourdomain.com --non-interactive --agree-tos -m admin@yourdomain.com
```

---

## Next Steps

1. Set DNS A record → `146.190.83.230`
2. Run certbot for HTTPS
3. Update `nginx.conf` — uncomment HTTPS block, add HTTP→HTTPS redirect
4. Set `MCP_CORS_ALLOWED_ORIGINS` to production domain
5. Store `/opt/metocare/.env` credentials in a secrets manager
6. Configure PostgreSQL daily backups (pg_dump → S3 or DO Spaces)

---

## SSH Access

```bash
ssh -i ~/.ssh/id_ed25519_metocare_do root@146.190.83.230
```

**SSH Public Key:**
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGzh2qU7u5ylauHaVwP+/WXUDlW+MeKIA9JBOzfFHonx metocare-do-deploy
```
