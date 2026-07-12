#!/usr/bin/env bash
# =============================================================================
# pre_migration_audit.sh — Pre-migration soft-delete audit gate
#
# Usage:
#   bash scripts/pre_migration_audit.sh
#
# Required environment variables:
#   DATABASE_URL          — PostgreSQL connection URL (same pattern as migration job)
#   POSTGRES_SERVER_NAME  — Azure PostgreSQL Flexible Server name (validated early)
#   RESOURCE_GROUP        — Azure resource group name (validated early)
#
# Behaviour:
#   1. Validates required env vars (fail fast, fail clearly — before any DB call)
#   2. Runs soft-delete audit query against medications table
#   3. If soft_deleted_count = 0 → prints summary, writes to $GITHUB_STEP_SUMMARY
#      if in CI, exits 0 (auto-pass — migration may proceed)
#   4. If soft_deleted_count > 0 → prints each soft-deleted row in detail,
#      writes WARNING to $GITHUB_STEP_SUMMARY, exits 1 (fail closed —
#      requires manual review before migration runs)
#
# Design reference: MEDICATION_P0_BLOCKER_REPORT.md §Additions (PTH 2026-07-11)
# Replaces the manual "run query, check result" step from MEDICATION_SOFT_DELETE_AUDIT.md
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------
log()  { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*"; }
err()  { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] ERROR: $*" >&2; }
warn() { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] WARNING: $*"; }
die()  { err "$*"; exit 1; }

# ---------------------------------------------------------------------------
# Step 1: Validate required environment variables (fail early, fail clearly)
# ---------------------------------------------------------------------------
log "=== Pre-migration soft-delete audit gate ==="
log "Validating required environment variables..."

MISSING_VARS=()

if [[ -z "${DATABASE_URL:-}" ]]; then
    MISSING_VARS+=("DATABASE_URL")
fi

if [[ -z "${POSTGRES_SERVER_NAME:-}" ]]; then
    err "POSTGRES_SERVER_NAME secret is not configured"
    MISSING_VARS+=("POSTGRES_SERVER_NAME")
fi

if [[ -z "${RESOURCE_GROUP:-}" ]]; then
    err "RESOURCE_GROUP secret is not configured"
    MISSING_VARS+=("RESOURCE_GROUP")
fi

if [[ ${#MISSING_VARS[@]} -gt 0 ]]; then
    err "The following required environment variables are not set: ${MISSING_VARS[*]}"
    err "Configure these secrets in the GitHub Actions azure-staging environment before running."
    err "Cannot proceed — exiting (fail fast)."
    exit 1
fi

log "All required environment variables present."
log "  POSTGRES_SERVER_NAME: ${POSTGRES_SERVER_NAME}"
log "  RESOURCE_GROUP:       ${RESOURCE_GROUP}"
log "  DATABASE_URL:         [set — masked]"

# ---------------------------------------------------------------------------
# Step 2: Run summary audit query
# ---------------------------------------------------------------------------
log ""
log "--- Running soft-delete audit query on medications table ---"

SUMMARY_RESULT=$(psql "$DATABASE_URL" --no-psqlrc --tuples-only --csv -c \
    "SELECT COUNT(*) FILTER (WHERE deleted_at IS NULL)     AS live_count,
            COUNT(*) FILTER (WHERE deleted_at IS NOT NULL) AS soft_deleted_count,
            COUNT(*)                                        AS total
     FROM medications;" 2>&1) || {
    die "psql audit query failed. Connection error or table does not exist yet (expected if pre-P0 baseline). Raw error: ${SUMMARY_RESULT}"
}

# Parse CSV output (header row + data row)
# CSV format: live_count,soft_deleted_count,total (row 1 is header, row 2 is data)
DATA_ROW=$(echo "$SUMMARY_RESULT" | tail -n 1)
LIVE_COUNT=$(echo "$DATA_ROW" | cut -d',' -f1)
SOFT_DELETED_COUNT=$(echo "$DATA_ROW" | cut -d',' -f2)
TOTAL=$(echo "$DATA_ROW" | cut -d',' -f3)

log "Audit result:"
log "  live_count:          ${LIVE_COUNT}"
log "  soft_deleted_count:  ${SOFT_DELETED_COUNT}"
log "  total:               ${TOTAL}"

# ---------------------------------------------------------------------------
# Step 3: Branch on soft_deleted_count
# ---------------------------------------------------------------------------
if [[ "$SOFT_DELETED_COUNT" -eq 0 ]]; then

    # ── PASS: No soft-deleted rows — migration may proceed ──────────────────
    log ""
    log "✅ AUDIT PASSED — soft_deleted_count = 0"
    log "   No soft-deleted rows found in medications table."
    log "   Migration may proceed. The lifecycle_status mapping will correctly"
    log "   default all rows to 'active' (no entered_in_error updates needed)."
    log ""
    log "Summary:"
    log "  Live rows (deleted_at IS NULL):         ${LIVE_COUNT}"
    log "  Soft-deleted (deleted_at IS NOT NULL):  ${SOFT_DELETED_COUNT}"
    log "  Total:                                  ${TOTAL}"

    if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
        cat >> "$GITHUB_STEP_SUMMARY" << SUMMARY
## ✅ Pre-migration Soft-Delete Audit — PASSED

The \`medications\` table has **no soft-deleted rows** (soft_deleted_count = 0).  
The P0 migration lifecycle_status mapping is safe to run.

| Metric | Value |
|--------|-------|
| Live rows (\`deleted_at IS NULL\`) | \`${LIVE_COUNT}\` |
| Soft-deleted (\`deleted_at IS NOT NULL\`) | \`${SOFT_DELETED_COUNT}\` |
| Total | \`${TOTAL}\` |
| POSTGRES_SERVER_NAME | \`${POSTGRES_SERVER_NAME}\` |
| RESOURCE_GROUP | \`${RESOURCE_GROUP}\` |

**Migration may proceed.**
SUMMARY
        log "GitHub Step Summary updated."
    fi

    exit 0

else

    # ── FAIL: Soft-deleted rows found — manual review required ──────────────
    warn ""
    warn "⚠️  AUDIT FAILED — soft_deleted_count = ${SOFT_DELETED_COUNT}"
    warn "   ${SOFT_DELETED_COUNT} soft-deleted row(s) found in medications table."
    warn "   These rows WILL be mapped to lifecycle_status='entered_in_error' by the migration."
    warn "   Manual review required before migration runs."
    warn ""
    warn "Soft-deleted rows:"
    warn "---"

    # Retrieve each soft-deleted row with full detail
    DETAIL_RESULT=$(psql "$DATABASE_URL" --no-psqlrc --tuples-only --csv -c \
        "SELECT id, name, deleted_at, deleted_by, note
         FROM medications
         WHERE deleted_at IS NOT NULL
         ORDER BY deleted_at DESC;" 2>&1) || {
        err "Failed to retrieve soft-deleted row details: ${DETAIL_RESULT}"
        err "Summary still shows soft_deleted_count = ${SOFT_DELETED_COUNT}."
        err "Fail closed — exiting 1."
        exit 1
    }

    # Print each detail row
    ROW_NUM=0
    while IFS=',' read -r row_id row_name row_deleted_at row_deleted_by row_note; do
        # Skip CSV header row
        if [[ "$row_id" == "id" ]]; then continue; fi
        ROW_NUM=$(( ROW_NUM + 1 ))
        warn "  Row ${ROW_NUM}:"
        warn "    id:         ${row_id}"
        warn "    name:       ${row_name}"
        warn "    deleted_at: ${row_deleted_at}"
        warn "    deleted_by: ${row_deleted_by}"
        warn "    note:       ${row_note}"
    done <<< "$DETAIL_RESULT"

    warn "---"
    warn ""
    warn "WHAT THIS MEANS:"
    warn "  The P0 migration will UPDATE these ${SOFT_DELETED_COUNT} row(s):"
    warn "    UPDATE medications"
    warn "    SET lifecycle_status = 'entered_in_error'"
    warn "    WHERE deleted_at IS NOT NULL;"
    warn ""
    warn "WHAT TO DO:"
    warn "  1. Review the rows above with PTH."
    warn "  2. Confirm the data belongs to patients and is correctly soft-deleted."
    warn "  3. If the mapping is correct (soft-deleted → entered_in_error), re-run"
    warn "     the pipeline with explicit approval (set AUDIT_OVERRIDE_SOFT_DELETE=1)."
    warn "  4. If any row is incorrect, fix the data before running migration."
    warn ""
    warn "Fail closed — migration will NOT run until this is resolved."

    if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
        # Build detail rows for summary
        DETAIL_TABLE=""
        while IFS=',' read -r row_id row_name row_deleted_at row_deleted_by row_note; do
            if [[ "$row_id" == "id" ]]; then continue; fi
            DETAIL_TABLE="${DETAIL_TABLE}| \`${row_id}\` | ${row_name} | ${row_deleted_at} | ${row_deleted_by} | ${row_note} |\n"
        done <<< "$DETAIL_RESULT"

        cat >> "$GITHUB_STEP_SUMMARY" << SUMMARY
## ⚠️ Pre-migration Soft-Delete Audit — WARNING: MANUAL REVIEW REQUIRED

**${SOFT_DELETED_COUNT} soft-deleted row(s) found.** Migration will map these to \`lifecycle_status='entered_in_error'\`.

**PTH must review before migration proceeds.**

### Summary

| Metric | Value |
|--------|-------|
| Live rows (\`deleted_at IS NULL\`) | \`${LIVE_COUNT}\` |
| Soft-deleted (\`deleted_at IS NOT NULL\`) | \`${SOFT_DELETED_COUNT}\` |
| Total | \`${TOTAL}\` |

### Soft-deleted rows requiring review

| id | name | deleted_at | deleted_by | note |
|----|------|------------|------------|------|
$(echo -e "$DETAIL_TABLE")

### Action Required

1. Review the rows above.
2. Confirm mapping \`soft-deleted → entered_in_error\` is correct for each row.
3. Fix data or re-trigger with explicit approval if safe.

**Migration blocked (fail closed).**
SUMMARY
        log "GitHub Step Summary updated with WARNING."
    fi

    exit 1

fi
