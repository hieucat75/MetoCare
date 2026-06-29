#!/usr/bin/env bash
# Frontend/Backend health check — run before Design QA or after restart.
# Fails fast if any required service is broken.
# Usage:
#   ./scripts/dev-health-check.sh              # single pass
#   ./scripts/dev-health-check.sh --wait 60    # retry for 60 seconds (post-restart)

set -euo pipefail

FRONTEND_PORT="${FRONTEND_PORT:-3099}"
BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
WAIT=0
[ "${2:-}" = "--wait" ] && WAIT="${3:-30}"
[ "${1:-}" = "--wait" ] && WAIT="${2:-30}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BOLD='\033[1m'; NC='\033[0m'
pass() { echo -e "  ${GREEN}✓${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; FAILED=$((FAILED+1)); }
warn() { echo -e "  ${YELLOW}!${NC} $1"; }

FAILED=0
deadline=$(($(date +%s) + WAIT))

check_all() {
  FAILED=0

  # ── 1. Next.js process alive ─────────────────────────────────────────────────
  echo -e "\n${BOLD}Process${NC}"
  NEXT_PID=$(lsof -iTCP:${FRONTEND_PORT} -sTCP:LISTEN -n -P 2>/dev/null \
    | awk 'NR>1{print $2}' | head -1)
  if [ -n "$NEXT_PID" ]; then
    ELAPSED=$(ps -p "$NEXT_PID" -o etime= 2>/dev/null | tr -d ' ')
    pass "Next.js PID=$NEXT_PID listening on :${FRONTEND_PORT} (up ${ELAPSED})"
  else
    fail "No process on port ${FRONTEND_PORT} — start with: cd frontend && next dev --turbo --port ${FRONTEND_PORT}"
    echo -e "\n${RED}Cannot continue — Next.js not running.${NC}"
    return 1
  fi

  # ── 2. Client-side JS chunks (Turbopack: extract URLs from page HTML) ────────
  echo -e "\n${BOLD}Client-side JS chunks${NC}"
  PAGE_HTML=$(curl -s --max-time 8 "http://localhost:${FRONTEND_PORT}/login" 2>/dev/null)
  if [ -z "$PAGE_HTML" ]; then
    fail "/login returned empty body — dev server may be stalled"
  else
    # Extract first 4 chunk script paths from the HTML
    CHUNK_PATHS=$(echo "$PAGE_HTML" | grep -o 'src="/_next/static/chunks/[^"]*"' \
      | sed 's/src="//;s/"//' | head -4)
    CHUNK_COUNT=0
    JS_OK=0
    while IFS= read -r path; do
      [ -z "$path" ] && continue
      CHUNK_COUNT=$((CHUNK_COUNT+1))
      result=$(curl -s --max-time 5 \
        -o /tmp/_dev_health_chunk.bin \
        -w "%{http_code}|%{content_type}|%{time_total}" \
        "http://localhost:${FRONTEND_PORT}${path}" 2>/dev/null)
      http=$(echo "$result" | cut -d'|' -f1)
      ct=$(echo "$result" | cut -d'|' -f2)
      t=$(echo "$result" | cut -d'|' -f3)
      name=$(basename "$path")
      if [ "$http" = "200" ] && echo "$ct" | grep -q "javascript"; then
        pass "${name} → 200 JS (${t}s)"
        JS_OK=$((JS_OK+1))
      elif echo "$ct" | grep -q "html"; then
        fail "${name} → ${http} HTML (chunk compilation stalled)"
      else
        fail "${name} → ${http} ${ct}"
      fi
    done <<< "$CHUNK_PATHS"
    if [ "$CHUNK_COUNT" -eq 0 ]; then
      fail "No script chunks found in page HTML — server may not be compiling"
    fi
  fi

  # ── 3. Frontend page render ──────────────────────────────────────────────────
  echo -e "\n${BOLD}Frontend page render${NC}"
  FE_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    "http://localhost:${FRONTEND_PORT}/login" 2>/dev/null)
  [ "$FE_CODE" = "200" ] && pass "/login → 200" || fail "/login → ${FE_CODE}"

  # ── 4. Backend liveness ──────────────────────────────────────────────────────
  echo -e "\n${BOLD}Backend${NC}"
  INFO_RESP=$(curl -s "${BACKEND_URL}/api/v1/info" 2>/dev/null)
  INFO_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${BACKEND_URL}/api/v1/info" 2>/dev/null)
  if [ "$INFO_CODE" = "200" ]; then
    ENV=$(echo "$INFO_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('env','?'))" 2>/dev/null || echo "?")
    pass "/api/v1/info → 200 (env=${ENV})"
  else
    fail "/api/v1/info → ${INFO_CODE}"
  fi

  # ── 5. Auth endpoint ─────────────────────────────────────────────────────────
  AUTH_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    "${BACKEND_URL}/api/v1/auth/me" 2>/dev/null)
  # 401 = endpoint alive, correctly rejects unauthenticated request
  if [ "$AUTH_CODE" = "401" ] || [ "$AUTH_CODE" = "200" ]; then
    pass "/api/v1/auth/me → ${AUTH_CODE} (endpoint alive)"
  else
    fail "/api/v1/auth/me → ${AUTH_CODE}"
  fi

  # ── Summary ──────────────────────────────────────────────────────────────────
  echo ""
  if [ "$FAILED" -eq 0 ]; then
    echo -e "${GREEN}${BOLD}All checks passed — ready for QA.${NC}"
    return 0
  else
    echo -e "${RED}${BOLD}${FAILED} check(s) failed.${NC}"
    echo ""
    warn "To fix stalled webpack:"
    warn "  kill \$(lsof -ti:${FRONTEND_PORT}) && rm -rf frontend/.next/cache/webpack"
    warn "  cd frontend && next dev --turbo --port ${FRONTEND_PORT}"
    return 1
  fi
}

echo -e "${BOLD}MetoCare Dev Health Check${NC}"
echo "Frontend: http://localhost:${FRONTEND_PORT}  Backend: ${BACKEND_URL}"

if [ "$WAIT" -gt 0 ]; then
  warn "Retry mode: checking every 5s for up to ${WAIT}s"
  while true; do
    if check_all; then break; fi
    if [ "$(date +%s)" -ge "$deadline" ]; then
      echo -e "${RED}Timed out after ${WAIT}s.${NC}"
      exit 1
    fi
    echo "  retrying in 5s…"
    sleep 5
  done
else
  check_all
fi
