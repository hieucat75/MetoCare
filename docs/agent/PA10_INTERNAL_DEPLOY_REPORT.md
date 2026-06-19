# PA-10A — Internal Deployment Preparation Report

**Date:** 2026-06-19  
**Main HEAD:** `dc999c4`  
**Target:** `172.20.0.100` (internal LAN only, no public exposure)  
**Deploy dir:** `/opt/metocare`  
**Mode:** Command-pack via PTH's Electerm session  

---

## Files Generated

| File | Purpose |
|------|---------|
| `backend/Dockerfile` | Python 3.11-slim, uvicorn, non-root user |
| `frontend/Dockerfile` | Node 20 multi-stage, standalone Next.js |
| `frontend/next.config.mjs` | Added `output: 'standalone'` |
| `docker-compose.internal.yml` | Isolated stack: ports 18000/13000/15432-local |
| `.env.internal.example` | Secret template (safe to commit) |
| `scripts/deploy_internal.sh` | Full automated deploy (git pull → build → up → migrate → seed → health wait) |
| `scripts/verify_internal.sh` | 18-item PA-08 smoke checklist (automated) |
| `scripts/rollback_internal.sh` | Teardown (safe by default, `--wipe` for data reset) |

## Ports Used

| Port | Service | Binding |
|------|---------|---------|
| `18000` | Backend API (FastAPI) | `0.0.0.0:18000` — LAN accessible |
| `13000` | Frontend (Next.js) | `0.0.0.0:13000` — LAN accessible |
| `15432` | PostgreSQL (TimescaleDB) | `127.0.0.1:15432` — localhost only |

**No SSL. No public DNS. Internal access only.**

## Environment

- `MCP_ENV=dev` | `MCP_DEBUG=false`
- `MCP_AI_MODE=mock` | `MCP_OCR_MODE=mock` | `MCP_STORAGE_MODE=local`
- `MCP_SKIP_MFA_IN_DEV=true` (smoke test convenience — never use in prod)
- All AI feature flags: `false` | Doctor review + consent gates: `true`

---

## Command Packs for PTH (Electerm)

**Send each batch, paste output back here. I interpret results and give next batch.**

---

### BATCH 1 — Server Inspection

```bash
echo "=== HOSTNAME ===" && hostname
echo "=== OS ===" && cat /etc/os-release | grep -E "^NAME|^VERSION"
echo "=== DISK ===" && df -h / | tail -1
echo "=== MEMORY ===" && free -h | grep Mem
echo "=== DOCKER ===" && docker version --format 'Client: {{.Client.Version}} / Server: {{.Server.Version}}' 2>/dev/null || echo "DOCKER_NOT_FOUND"
echo "=== COMPOSE ===" && docker compose version 2>/dev/null || docker-compose version 2>/dev/null || echo "COMPOSE_NOT_FOUND"
echo "=== RUNNING CONTAINERS ===" && docker ps --format "{{.Names}}\t{{.Ports}}" 2>/dev/null || echo "none"
echo "=== OPEN PORTS ===" && ss -tlnp | grep -E ":(80|443|3000|8000|13000|18000|5432|15432|6379) " || echo "none_of_interest"
echo "=== PORT 18000 ===" && ss -tln | grep ":18000 " && echo "IN_USE" || echo "FREE"
echo "=== PORT 13000 ===" && ss -tln | grep ":13000 " && echo "IN_USE" || echo "FREE"
```

---

### BATCH 2 — Environment Preparation

*(Run ONLY after I confirm Batch 1 output is clear)*

```bash
# Create deploy dir and clone repo
sudo mkdir -p /opt/metocare && sudo chown setup:setup /opt/metocare
cd /opt/metocare
git clone https://github.com/hieucat75/MetoCare.git . || git pull origin main

# Generate secrets
echo "=== GENERATING SECRETS ===" 
python3 -c "import secrets; print('MCP_SECRET_KEY=' + secrets.token_urlsafe(48))"
python3 -c "from cryptography.fernet import Fernet; print('MCP_ENCRYPTION_KEYS=' + Fernet.generate_key().decode())"

# Create .env.internal from template (secrets will be pasted manually)
cp .env.internal.example .env.internal
echo "=== .env.internal created — open and fill in generated values above ==="
cat .env.internal
```

*(After Batch 2: PTH opens .env.internal in nano/vi and pastes the three generated values: POSTGRES_PASSWORD, MCP_SECRET_KEY, MCP_ENCRYPTION_KEYS. Confirm when done.)*

---

### BATCH 3 — Deploy

*(Run ONLY after .env.internal is filled)*

```bash
cd /opt/metocare
# Verify .env.internal has no placeholder values
grep "CHANGE_ME\|GENERATE_WITH" .env.internal && echo "ERROR: fill .env.internal first" && exit 1 || echo "env OK"

# Check ports again (final guard)
ss -tln | grep -E ":18000 |:13000 " && echo "PORT_CONFLICT_ABORT" || echo "PORTS_FREE"

# Build and start stack (takes 5-10 minutes)
docker compose -f docker-compose.internal.yml --env-file .env.internal build --no-cache 2>&1 | tail -5
docker compose -f docker-compose.internal.yml --env-file .env.internal up -d
docker ps --filter "name=metocare_" --format "{{.Names}}\t{{.Status}}"
```

---

### BATCH 4 — Migration + Seed

*(Run after Batch 3 containers show "Up" status)*

```bash
cd /opt/metocare
# Wait for DB healthy
echo "Waiting for DB..." && \
  until docker inspect --format='{{.State.Health.Status}}' metocare_db 2>/dev/null | grep -q healthy; do sleep 5 && echo -n "."; done && echo " DB HEALTHY"

# Run migrations
docker compose -f docker-compose.internal.yml --env-file .env.internal \
  exec -T backend sh -c "cd /app && alembic upgrade head"

# Verify HEAD
docker compose -f docker-compose.internal.yml --env-file .env.internal \
  exec -T backend sh -c "cd /app && alembic current"

# Seed demo users (idempotent)
docker compose -f docker-compose.internal.yml --env-file .env.internal \
  exec -T backend sh -c "cd /app && python scripts/seed_demo.py"
```

---

### BATCH 5 — Verification

*(Run after Batch 4 completes cleanly)*

```bash
cd /opt/metocare
# Quick health checks
curl -sf http://localhost:18000/health && echo " BACKEND_OK" || echo " BACKEND_FAIL"
curl -sf http://localhost:18000/info | python3 -c "import sys,json; d=json.load(sys.stdin); print('env=%s ai=%s' % (d['env'],d['ai_mode']))"
curl -sf -o /dev/null -w "frontend HTTP=%{http_code}\n" http://localhost:13000/

# Run full 18-item smoke checklist
bash scripts/verify_internal.sh
```

---

### BATCH 6 — Rollback (only if needed)

```bash
cd /opt/metocare
# Stop containers, keep data volumes
bash scripts/rollback_internal.sh

# Verify only metocare_ containers removed
docker ps --filter "name=metocare_"

# To also wipe database and storage (full reset):
# bash scripts/rollback_internal.sh --wipe
```

---

## Status

- [x] All deployment files written and committed (`dc999c4`)
- [x] Command packs ready (Batches 1–6)
- [ ] **Awaiting Batch 1 output from PTH**
