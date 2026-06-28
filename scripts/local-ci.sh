#!/usr/bin/env bash
# local-ci.sh — Tiered local CI gate for Metocare
#
# USAGE:
#   ./scripts/local-ci.sh          # fast tier (default, ~15s)
#   ./scripts/local-ci.sh full     # full tier (backend + frontend, ~25s)
#   ./scripts/local-ci.sh backend  # backend only
#   ./scripts/local-ci.sh frontend # frontend only
#
# Called automatically by .git/hooks/pre-commit (fast tier).
# Run `./scripts/local-ci.sh full` before a major push or PR.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
BACKEND_DIR="$REPO_ROOT/backend"
FRONTEND_DIR="$REPO_ROOT/frontend"
TIER="${1:-fast}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

pass() { echo -e "${GREEN}✅ $1${NC}"; }
fail() { echo -e "${RED}❌ $1${NC}"; exit 1; }
info() { echo -e "${CYAN}▶ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠ $1${NC}"; }

BACKEND_PYTHON=""
for candidate in \
    "$BACKEND_DIR/.venv/bin/python3" \
    "/Volumes/PythonVenvs/venvs/metocare_backend/bin/python3"; do
    if [ -x "$candidate" ]; then
        BACKEND_PYTHON="$candidate"
        break
    fi
done

if [ -z "$BACKEND_PYTHON" ]; then
    warn "No backend Python venv found — skipping backend gates"
fi

FRONTEND_TSC=""
if [ -x "$FRONTEND_DIR/node_modules/.bin/tsc" ]; then
    FRONTEND_TSC="$FRONTEND_DIR/node_modules/.bin/tsc"
fi

# ── TIER: backend ──────────────────────────────────────────────────────────
run_backend_fast() {
    if [ -z "$BACKEND_PYTHON" ]; then return 0; fi

    info "Backend: ruff lint"
    (cd "$BACKEND_DIR" && "$BACKEND_PYTHON" -m ruff check . --output-format=grouped) \
        || fail "ruff lint failed — run: cd backend && source .venv/bin/activate && ruff check . --fix"
    pass "ruff lint"

    info "Backend: unit + sentinel tests (~12s)"
    # Exclude tests that require network or heavy mocks
    (cd "$BACKEND_DIR" && "$BACKEND_PYTHON" -m pytest tests/ -x -q --tb=short -p no:warnings) \
        || fail "backend tests failed"
    pass "backend tests"
}

# ── TIER: frontend ──────────────────────────────────────────────────────────
run_frontend_fast() {
    if [ -z "$FRONTEND_TSC" ]; then
        warn "tsc not found in frontend/node_modules — skipping frontend typecheck"
        return 0
    fi

    info "Frontend: TypeScript typecheck (~3s)"
    (cd "$FRONTEND_DIR" && "$FRONTEND_TSC" --noEmit -p tsconfig.build.json) \
        || fail "TypeScript errors found — run: cd frontend && npx tsc --noEmit -p tsconfig.build.json"
    pass "frontend typecheck"
}

# ── DISPATCH ──────────────────────────────────────────────────────────────

case "$TIER" in
fast)
    echo -e "\n${CYAN}=== local-ci: FAST TIER ===${NC}"
    run_backend_fast
    run_frontend_fast
    echo -e "\n${GREEN}✅ All fast checks passed${NC}\n"
    ;;
backend)
    echo -e "\n${CYAN}=== local-ci: BACKEND TIER ===${NC}"
    run_backend_fast
    echo -e "\n${GREEN}✅ Backend checks passed${NC}\n"
    ;;
frontend)
    echo -e "\n${CYAN}=== local-ci: FRONTEND TIER ===${NC}"
    run_frontend_fast
    echo -e "\n${GREEN}✅ Frontend checks passed${NC}\n"
    ;;
full)
    echo -e "\n${CYAN}=== local-ci: FULL TIER ===${NC}"
    run_backend_fast
    run_frontend_fast
    echo -e "\n${GREEN}✅ All full checks passed${NC}\n"
    ;;
*)
    echo "Usage: $0 [fast|full|backend|frontend]"
    exit 1
    ;;
esac
