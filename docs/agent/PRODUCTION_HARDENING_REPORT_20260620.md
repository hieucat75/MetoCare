# MetoCare — DigitalOcean Production Hardening Report
**Date:** 2026-06-20  
**Agent:** OpenClaw Master Coordinator  
**Status:** ✅ ALL TASKS COMPLETE

---

## Infrastructure

| Item | Value |
|------|-------|
| Provider | DigitalOcean |
| Droplet | `metocare-vps` (ID: 578953030) |
| Public IP | **`146.190.83.230`** |
| Region | Singapore (`sgp1`) |
| Size | `s-2vcpu-4gb` — 2 vCPU / 4 GB RAM / 80 GB SSD |
| OS | Ubuntu 24.04 LTS |
| Monthly cost | ~$24 USD |
| Deploy dir | `/opt/metocare/` |

---

## Task Results

### ✅ Task 1 — Final Deployment Report
This file. Stored at `docs/agent/PRODUCTION_HARDENING_REPORT_20260620.md`.

### ✅ Task 2 — Firewall (UFW)
```
Status: active
22/tcp    ALLOW  (SSH)
80/tcp    ALLOW  (HTTP)
443/tcp   ALLOW  (HTTPS)
All other inbound: DENY
```
PostgreSQL (5432) and Redis (6379) are **not exposed** — internal Docker network only.

### ✅ Task 3 — Automatic PostgreSQL Backup
- Script: `/opt/metocare/pg-backup.sh`
- Schedule: **daily at 02:00 UTC** (cron)
- Retention: 7 days (auto-prune)
- Output dir: `/opt/metocare/backups/`
- Log: `/var/log/metocare-backup.log`
- Test run: ✅ `metocare_pg_20260620_002934.sql.gz` (8K)

### ✅ Task 4 — Restore Test Procedure
Script: `/opt/metocare/pg-restore.sh`

```bash
# Restore from latest backup
/opt/metocare/pg-restore.sh backups/metocare_pg_20260620_002835.sql.gz
```

Procedure:
1. Script stops backend container
2. Drops + recreates `metocare` DB
3. Restores from gzip SQL dump
4. Restarts backend
5. Verifies `/health` returns `ok`

Requires: `Type 'yes'` confirmation (guards against accidental runs).

### ✅ Task 5 — GitHub Actions Deploy-to-DO Workflow
File: `.github/workflows/deploy-do.yml`

**Flow:**
```
push to main
  → build (Docker image → GHCR)
  → migrate (alembic upgrade head via CI runner)
  → deploy (SSH → docker pull → docker compose up → health poll)
```

**GitHub Secrets configured:**
| Secret | Purpose |
|--------|---------|
| `DO_SSH_PRIVATE_KEY` | SSH access to VPS |
| `DO_VPS_IP` | `146.190.83.230` |
| `GHCR_PAT` | Pull image on VPS |
| `MCP_DATABASE_URL` | Alembic migrations |
| `MCP_SECRET_KEY` | Production secret |
| `MCP_ENCRYPTION_KEYS` | PHI field encryption |

### ✅ Task 6 — Monitoring + Restart Alert
Script: `/opt/metocare/health-monitor.sh`
- Schedule: **every 5 minutes** (cron)
- Checks `GET /health` → expects `{"status":"ok"}`
- On failure: auto-restarts unhealthy/exited containers
- Log: `/var/log/metocare-monitor.log`
- Test: ✅ exits 0 silently when healthy

### ✅ Task 7 — HTTPS Activation (Pending DNS)
Script: `deploy/do/enable-https.sh`

**When DNS A record is set → run:**
```bash
ssh root@146.190.83.230
/opt/metocare/enable-https.sh yourdomain.com admin@yourdomain.com
```

Script does:
1. Installs certbot if missing
2. Verifies DNS resolution
3. Issues Let's Encrypt cert (webroot mode)
4. Writes HTTPS nginx config (HTTP→HTTPS redirect + HSTS)
5. Reloads nginx in container
6. Updates `MCP_CORS_ALLOWED_ORIGINS` in `.env`
7. Sets certbot auto-renew cron (03:00 UTC daily)

---

## Live Verification (at time of report)

```
GET http://146.190.83.230/health
→ HTTP 200: {"status":"ok"}

GET http://146.190.83.230/api/v1/info
→ HTTP 200: {
    "app": "Metabolic Care Platform",
    "env": "prod",
    "migration_version": "t27_uq_patient_profile_user_id"
  }

Restart survival: ✅ HTTP 200 within 20s
Alembic HEAD: t27_uq_patient_profile_user_id (22 migrations)
create_all() at runtime: NONE
```

---

## Stack Summary

| Container | Image | Status |
|-----------|-------|--------|
| `metocare-backend-1` | `ghcr.io/hieucat75/metocare-backend:4356fc0` | ✅ healthy |
| `metocare-postgres-1` | `postgres:16-alpine` | ✅ healthy |
| `metocare-redis-1` | `redis:7-alpine` | ✅ healthy |
| `metocare-nginx-1` | `nginx:1.27-alpine` | ✅ running |

---

## DNS Records Required

```
Type    Name        Value              TTL
A       @           146.190.83.230     300
A       api         146.190.83.230     300
A       metocare    146.190.83.230     300
```

---

## SSH Access

```bash
ssh -i ~/.ssh/id_ed25519_metocare_do root@146.190.83.230
```

**SSH Public Key (`metocare-do-deploy`):**
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGzh2qU7u5ylauHaVwP+/WXUDlW+MeKIA9JBOzfFHonx metocare-do-deploy
```

---

## Remaining Actions (PTH)

| Action | When |
|--------|------|
| Set DNS A record → `146.190.83.230` | Now |
| Run `enable-https.sh` | After DNS propagates (~5 min) |
| Store `.env` secrets in password manager | Now |
| Set up DO Spaces for off-site backup | Optional |

---

## Azure Status
Azure deployment **suspended**. No further troubleshooting. All production traffic routed through DigitalOcean VPS.
