#!/usr/bin/env bash
# MetoCare — Internal DEV Deployment Script
# Target: /opt/metocare on 172.20.0.100
# Usage: Run this script ON THE DEV SERVER inside /opt/metocare
# Do NOT run as root. Use setup user with docker group membership.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$REPO_DIR/docker-compose.internal.yml"
ENV_FILE="$REPO_DIR/.env.internal"

log() { echo "[$(date '+%H:%M:%S')] $*"; }
die() { echo "[ERROR] $*" >&2; exit 1; }

# ── Preflight ─────────────────────────────────────────────────────────────────
log "=== MetoCare Internal Deploy ==="
log "Repo: $REPO_DIR"
log "Compose: $COMPOSE_FILE"

[[ -f "$ENV_FILE" ]] || die ".env.internal not found. Copy .env.internal.example and fill values."
[[ -f "$COMPOSE_FILE" ]] || die "docker-compose.internal.yml not found."

command -v docker >/dev/null 2>&1 || die "Docker not found. Install Docker first."
docker compose version >/dev/null 2>&1 || die "Docker Compose not found."

# Verify required env vars are set
source "$ENV_FILE"
[[ -z "${POSTGRES_PASSWORD:-}" ]] && die "POSTGRES_PASSWORD is empty in .env.internal"
[[ -z "${MCP_SECRET_KEY:-}" ]] && die "MCP_SECRET_KEY is empty in .env.internal"
[[ "${MCP_SECRET_KEY}" == "GENERATE_WITH_COMMAND_ABOVE_MIN_32_CHARS" ]] && die "MCP_SECRET_KEY is still the example placeholder"
[[ -z "${MCP_ENCRYPTION_KEYS:-}" ]] && die "MCP_ENCRYPTION_KEYS is empty in .env.internal"
[[ "${MCP_ENCRYPTION_KEYS}" == "GENERATE_WITH_COMMAND_ABOVE_FERNET_KEY" ]] && die "MCP_ENCRYPTION_KEYS is still the example placeholder"

log "Preflight: OK"

# ── Port conflict check ───────────────────────────────────────────────────────
log "Checking ports 18000, 13000 (15432 is localhost-only)..."
for port in 18000 13000; do
    if ss -tln 2>/dev/null | grep -q ":${port} " || netstat -tln 2>/dev/null | grep -q ":${port} "; then
        die "Port $port is already in use. Resolve conflict before deploying."
    fi
done
log "Ports: OK"

# ── Git pull ──────────────────────────────────────────────────────────────────
log "Pulling latest main..."
cd "$REPO_DIR"
git fetch origin main
git checkout main
git pull origin main
log "Git HEAD: $(git rev-parse --short HEAD)"

# ── Build images ──────────────────────────────────────────────────────────────
log "Building images (this takes a few minutes)..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" build --no-cache
log "Build: OK"

# ── Start stack ───────────────────────────────────────────────────────────────
log "Starting stack..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d
log "Stack started"

# ── Wait for DB ───────────────────────────────────────────────────────────────
log "Waiting for database to be healthy..."
TRIES=0
until docker inspect --format='{{.State.Health.Status}}' metocare_db 2>/dev/null | grep -q "healthy"; do
    TRIES=$((TRIES + 1))
    [[ $TRIES -gt 30 ]] && die "Database did not become healthy within 5 minutes"
    sleep 10
    echo -n "."
done
echo ""
log "Database: healthy"

# ── Run migrations ────────────────────────────────────────────────────────────
log "Running Alembic migrations..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" \
    exec -T backend \
    sh -c "cd /app && alembic upgrade head"
log "Migrations: done"

# Verify migration HEAD
ALEMBIC_HEAD=$(docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" \
    exec -T backend \
    sh -c "cd /app && alembic current 2>&1" | tail -1)
log "Alembic current: $ALEMBIC_HEAD"
echo "$ALEMBIC_HEAD" | grep -q "t27_uq_patient_profile_user_id" || \
    log "WARNING: Expected t27_uq_patient_profile_user_id head — got: $ALEMBIC_HEAD"

# ── Seed demo data ────────────────────────────────────────────────────────────
log "Seeding demo users (idempotent)..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" \
    exec -T backend \
    sh -c "cd /app && python scripts/seed_demo.py"
log "Seed: done"

# ── Wait for backend health ───────────────────────────────────────────────────
log "Waiting for backend health endpoint..."
TRIES=0
until curl -sf "http://localhost:18000/health" >/dev/null 2>&1; do
    TRIES=$((TRIES + 1))
    [[ $TRIES -gt 20 ]] && die "Backend health check failed after 3 minutes"
    sleep 10
    echo -n "."
done
echo ""
log "Backend: healthy at http://172.20.0.100:18000"

# ── Wait for frontend ─────────────────────────────────────────────────────────
log "Waiting for frontend..."
TRIES=0
until curl -sf "http://localhost:13000" >/dev/null 2>&1; do
    TRIES=$((TRIES + 1))
    [[ $TRIES -gt 20 ]] && die "Frontend did not respond after 3 minutes"
    sleep 10
    echo -n "."
done
echo ""
log "Frontend: live at http://172.20.0.100:13000"

log ""
log "=== DEPLOY COMPLETE ==="
log "Backend API:  http://172.20.0.100:18000"
log "API Docs:     http://172.20.0.100:18000/docs"
log "Frontend:     http://172.20.0.100:13000"
log ""
log "Demo credentials:"
log "  Patient:  demo.patient@example.com / DemoPatient123!"
log "  Doctor:   demo.doctor@example.com  / DemoDoctor123!"
log "  Admin:    demo.admin@example.com   / DemoAdmin123!"
log ""
log "Next: run scripts/verify_internal.sh to validate all smoke checks"
