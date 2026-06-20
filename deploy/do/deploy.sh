#!/bin/bash
# MetoCare deploy script — run on VPS at /opt/metocare
# Usage: ./deploy.sh [image_tag]
# Pulls latest image, runs alembic upgrade head, restarts backend
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
IMAGE_TAG="${1:-latest}"
COMPOSE="docker compose"

cd "$DEPLOY_DIR"

echo "=== MetoCare Deploy: $IMAGE_TAG ==="
echo "Time: $(date -u)"

# Load .env
if [ ! -f .env ]; then
  echo "ERROR: .env not found at $DEPLOY_DIR/.env" >&2
  exit 1
fi
export $(grep -v '^#' .env | xargs)

# Pull new image
echo "--- Pulling ghcr.io/hieucat75/metocare-backend:${IMAGE_TAG} ---"
echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin
docker pull "ghcr.io/hieucat75/metocare-backend:${IMAGE_TAG}"
export IMAGE_TAG

# Run Alembic migrations before restart
echo "--- Running Alembic migrations ---"
docker run --rm \
  --network metocare_internal \
  --env-file .env \
  -e MCP_DATABASE_URL="postgresql+psycopg2://mcpadmin:${POSTGRES_PASSWORD}@postgres:5432/metocare" \
  -e MCP_ENV=prod \
  "ghcr.io/hieucat75/metocare-backend:${IMAGE_TAG}" \
  sh -c "cd /app && alembic upgrade head && alembic current"

echo "--- Restarting backend ---"
$COMPOSE up -d --no-deps --pull never backend

# Health check
echo "--- Health check ---"
for i in $(seq 1 30); do
  HTTP=$(docker exec metocare-backend-1 curl -sf http://localhost:8000/health 2>/dev/null && echo "200" || echo "fail")
  echo "  [$i] /health → $HTTP"
  if [ "$HTTP" = "200" ]; then
    echo "✅ Deploy successful — backend healthy"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "❌ Backend not healthy after 5 minutes" >&2
    docker logs metocare-backend-1 --tail 50 2>/dev/null || true
    exit 1
  fi
  sleep 10
done

echo "=== Deploy complete: $(date -u) ==="
