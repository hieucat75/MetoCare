#!/usr/bin/env bash
# =============================================================================
# MetoCare — Staging Deploy Script (frontend-only)
#
# This script triggers the GitHub Actions frontend-only staging deploy workflow.
# Prerequisite: `gh` CLI authenticated with write access to the repo.
#
# Usage: bash scripts/deploy-staging.sh [--tag <image-tag>]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

log() { echo "[$(date '+%H:%M:%S')] $*"; }
die() { echo "[ERROR] $*" >&2; exit 1; }

# ── Resolve tag ───────────────────────────────────────────────────────────────
IMAGE_TAG=""
while [[ $# -gt 0 ]]; do
  case $1 in
    --tag) IMAGE_TAG="$2"; shift 2 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

if [[ -z "$IMAGE_TAG" ]]; then
  IMAGE_TAG=$(git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || echo "")
  [[ -z "$IMAGE_TAG" ]] && die "Could not determine git SHA. Pass --tag <tag> explicitly."
fi

log "=== MetoCare Staging Deploy ==="
log "Tag: $IMAGE_TAG"

# ── Preflight ─────────────────────────────────────────────────────────────────
command -v gh >/dev/null 2>&1 || die "GitHub CLI (gh) not found. Install with: brew install gh"
gh auth status >/dev/null 2>&1 || die "Not authenticated with GitHub CLI. Run: gh auth login"

# Get repo from git remote
REPO=$(git -C "$REPO_DIR" remote get-url origin 2>/dev/null | sed 's|.*github.com[:/]||;s|\.git$||' || true)
[[ -z "$REPO" ]] && die "Could not determine GitHub repo from git remote"
log "Repo: $REPO"

# ── Check local build ─────────────────────────────────────────────────────────
log "Running local build check..."
cd "$REPO_DIR/frontend"
npm run build 2>&1 | tail -5
log "Build: OK"

# ── Trigger workflow ──────────────────────────────────────────────────────────
log "Triggering frontend-staging deploy workflow..."
gh workflow run "Frontend-only Staging Deploy" \
  --repo "$REPO" \
  --field "image_tag=$IMAGE_TAG" 2>&1

log ""
log "Workflow triggered. Monitor at:"
log "  https://github.com/$REPO/actions/workflows/frontend-staging.yml"
log ""
log "Frontend URL: https://ca-metocare-frontend.wittyflower-55a3afa4.southeastasia.azurecontainerapps.io"
log ""
log "=== DEPLOY TRIGGERED ==="
