#!/usr/bin/env bash
# MetoCare — Internal DEV Rollback Script
# Stops and removes MetoCare containers (and optionally data volumes).
# Safe: does NOT touch any container or volume not prefixed with "metocare_".
#
# Usage:
#   bash scripts/rollback_internal.sh          # stop + remove containers; KEEP data volumes
#   bash scripts/rollback_internal.sh --wipe   # stop + remove containers AND data volumes (DESTRUCTIVE)

set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$REPO_DIR/docker-compose.internal.yml"
ENV_FILE="$REPO_DIR/.env.internal"
WIPE=false
[[ "${1:-}" == "--wipe" ]] && WIPE=true

log()  { echo "[$(date '+%H:%M:%S')] $*"; }
warn() { echo "[WARN] $*"; }

log "=== MetoCare Internal Rollback ==="

[[ -f "$COMPOSE_FILE" ]] || { warn "docker-compose.internal.yml not found — nothing to roll back"; exit 0; }

ENV_ARG=""
[[ -f "$ENV_FILE" ]] && ENV_ARG="--env-file $ENV_FILE"

if $WIPE; then
    log "WIPE MODE: stopping containers AND removing data volumes"
    log "This will DELETE all database data and uploaded files."
    read -rp "  Type 'yes-wipe-data' to confirm: " confirm
    [[ "$confirm" == "yes-wipe-data" ]] || { log "Aborted."; exit 1; }
    docker compose -f "$COMPOSE_FILE" $ENV_ARG down --volumes --remove-orphans 2>/dev/null || true
    log "Containers and volumes removed."
else
    log "Stopping containers (data volumes preserved)..."
    docker compose -f "$COMPOSE_FILE" $ENV_ARG down --remove-orphans 2>/dev/null || true
    log "Containers stopped. Volumes metocare_pgdata + metocare_storage preserved."
fi

# Safety check: verify only metocare_ containers are affected
REMAINING=$(docker ps -a --filter "name=metocare_" --format "{{.Names}}" 2>/dev/null)
if [[ -z "$REMAINING" ]]; then
    log "All MetoCare containers removed."
else
    warn "Some MetoCare containers still running: $REMAINING"
    warn "Run: docker rm -f $REMAINING"
fi

log ""
log "=== Rollback complete ==="
log "To redeploy: bash scripts/deploy_internal.sh"
log "To wipe all data and redeploy: bash scripts/rollback_internal.sh --wipe && bash scripts/deploy_internal.sh"
