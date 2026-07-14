#!/usr/bin/env bash
# =============================================================================
# pre_migration_audit.sh — Pre-migration soft-delete audit gate (PHI-safe)
#
# Usage:
#   bash scripts/pre_migration_audit.sh
#
# Required environment variables:
#   DATABASE_URL          — PostgreSQL connection URL (Key Vault mcp-database-url)
#   POSTGRES_SERVER_NAME  — Azure PostgreSQL Flexible Server name (validated early)
#   RESOURCE_GROUP        — Azure resource group name (validated early)
#
# Optional:
#   MEDICATION_SOFT_DELETE_MAPPINGS — per-record review approvals, format:
#       <medication_id>:<lifecycle_status>,<medication_id>:<lifecycle_status>
#     Statuses limited to: discontinued | completed | entered_in_error.
#     Set as a GitHub Actions SECRET (never a plain env var) and REMOVE it
#     after the P0 migration has run — the gate warns when it goes stale.
#
# Behaviour:
#   1. Validates required env vars (fail fast, fail clearly — before any DB call)
#   2. If medications.lifecycle_status already exists (P0 migration applied),
#      the gate is obsolete → PASS with a notice (and a warning if the
#      mappings secret is still set).
#   3. Counts soft-deleted medications rows. count=0 → PASS.
#   4. count>0 without mappings → FAIL CLOSED. Logs count + non-reversible
#      record fingerprints ONLY.
#   5. count>0 with mappings → PASS only when the mapping set matches the DB
#      set exactly (no unreviewed record, no stale approval) AND every approved
#      status equals 'entered_in_error' (migration p0_m01 applies a blanket
#      entered_in_error UPDATE; approving any other status requires changing
#      that migration first, so the gate refuses to let a mismatch through).
#
# PHI policy (PTH 2026-07-13, public repo — Actions logs are world-readable):
#   This script NEVER prints medication names, full medication ids, patient
#   ids, notes, or row timestamps. Records are referenced only as
#   record_ref = sha256(<medication_id> + <salt>)[0:12], salt derived from
#   DATABASE_URL (secret). Detailed review data must be pulled through a
#   private Azure channel (one-shot ACA job / Cloud Shell), never through CI.
#
# Design reference: MEDICATION_P0_BLOCKER_REPORT.md §Additions (PTH 2026-07-11)
# =============================================================================

set -euo pipefail

VALID_STATUSES="discontinued completed entered_in_error"
ROW_SCAN_LIMIT=500

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
log "  DATABASE_URL:                    [set — masked]"
log "  MEDICATION_SOFT_DELETE_MAPPINGS: $([[ -n "${MEDICATION_SOFT_DELETE_MAPPINGS:-}" ]] && echo "[set — masked]" || echo "[not set]")"

# psql only understands postgresql:// URIs — strip any SQLAlchemy driver
# suffix (e.g. postgresql+psycopg://) before connecting.
PSQL_URL="$(printf '%s' "$DATABASE_URL" | sed -E 's|^postgres(ql)?\+[A-Za-z0-9_]+://|postgresql://|')"

# Read-only + bounded session for every query this script runs.
export PGOPTIONS="-c default_transaction_read_only=on -c statement_timeout=10000"

run_psql() {
    psql "$PSQL_URL" --no-psqlrc --tuples-only --no-align -c "$1" 2>&1
}

# Non-reversible record reference for logs: sha256(id + salt)[0:12].
# Salt derives from DATABASE_URL (a secret), so refs cannot be recomputed
# from public logs.
if command -v sha256sum >/dev/null 2>&1; then
    _sha256() { sha256sum | cut -d' ' -f1; }
else
    _sha256() { shasum -a 256 | cut -d' ' -f1; }
fi
FP_SALT="$(printf '%s' "$DATABASE_URL" | _sha256 | cut -c1-16)"
fp() { printf '%s%s' "$1" "$FP_SALT" | _sha256 | cut -c1-12; }

append_summary() {
    if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
        echo "$1" >> "$GITHUB_STEP_SUMMARY"
    fi
}

# ---------------------------------------------------------------------------
# Step 2: Skip on a fresh database (no medications table at all — e.g. the
# first production deploy) or when the P0 migration has already been applied
# ---------------------------------------------------------------------------
HAS_TABLE=$(run_psql \
    "SELECT 1 FROM information_schema.tables WHERE table_name = 'medications';") || {
    die "psql table probe failed. Connection error. Raw error: ${HAS_TABLE}"
}
if [[ "$HAS_TABLE" != "1" ]]; then
    log "✅ AUDIT SKIPPED — medications table does not exist yet (fresh database)."
    append_summary "## ✅ Pre-migration Soft-Delete Audit — SKIPPED (fresh database)"
    exit 0
fi

HAS_LIFECYCLE=$(run_psql \
    "SELECT 1 FROM information_schema.columns
     WHERE table_name = 'medications' AND column_name = 'lifecycle_status';") || {
    die "psql schema probe failed. Connection error. Raw error: ${HAS_LIFECYCLE}"
}

if [[ "$HAS_LIFECYCLE" == "1" ]]; then
    log "✅ AUDIT SKIPPED — medications.lifecycle_status already exists (P0 migration applied)."
    if [[ -n "${MEDICATION_SOFT_DELETE_MAPPINGS:-}" ]]; then
        warn "MEDICATION_SOFT_DELETE_MAPPINGS is still set but the migration has run."
        warn "Remove the secret — the override must not outlive the migration it approved."
    fi
    append_summary "## ✅ Pre-migration Soft-Delete Audit — SKIPPED (migration already applied)"
    exit 0
fi

# ---------------------------------------------------------------------------
# Step 3: Collect soft-deleted medication ids (ids only — never row content)
# ---------------------------------------------------------------------------
log ""
log "--- Running soft-delete audit query on medications table ---"

DB_IDS_RAW=$(run_psql \
    "SELECT id FROM medications
     WHERE deleted_at IS NOT NULL
     ORDER BY id
     LIMIT ${ROW_SCAN_LIMIT};") || {
    die "psql audit query failed. Connection error or table does not exist yet (expected if pre-P0 baseline). Raw error: ${DB_IDS_RAW}"
}

DB_IDS=()
while IFS= read -r line; do
    [[ -n "$line" ]] && DB_IDS+=("$line")
done <<< "$DB_IDS_RAW"

COUNT=${#DB_IDS[@]}
log "soft_deleted_count=${COUNT}"

if [[ "$COUNT" -ge "$ROW_SCAN_LIMIT" ]]; then
    die "soft_deleted_count hit the scan limit (${ROW_SCAN_LIMIT}) — refusing to audit a truncated set."
fi

# ---------------------------------------------------------------------------
# Step 4: count == 0 → PASS
# ---------------------------------------------------------------------------
if [[ "$COUNT" -eq 0 ]]; then
    log "review_required=false"
    log "✅ AUDIT PASSED — no soft-deleted rows; migration may proceed."
    if [[ -n "${MEDICATION_SOFT_DELETE_MAPPINGS:-}" ]]; then
        warn "MEDICATION_SOFT_DELETE_MAPPINGS is set but no soft-deleted rows exist."
        warn "Remove the stale secret."
    fi
    append_summary "## ✅ Pre-migration Soft-Delete Audit — PASSED

\`soft_deleted_count=0\` — migration may proceed."
    exit 0
fi

# ---------------------------------------------------------------------------
# Step 5: count > 0 — allowlist evaluation (fail closed by default)
# ---------------------------------------------------------------------------
if [[ -z "${MEDICATION_SOFT_DELETE_MAPPINGS:-}" ]]; then
    warn "review_required=true"
    warn "⚠️  AUDIT FAILED — ${COUNT} soft-deleted record(s) require manual review."
    warn "Record fingerprints (non-reversible; match via private Azure query, not this log):"
    for id in "${DB_IDS[@]}"; do
        warn "  record_ref=$(fp "$id")"
    done
    warn ""
    warn "WHAT TO DO:"
    warn "  1. Pull record details through a PRIVATE channel (one-shot ACA job or"
    warn "     Azure Cloud Shell) — never print row content in CI logs."
    warn "  2. Review each record with PTH and pick a lifecycle status per record."
    warn "  3. Set the MEDICATION_SOFT_DELETE_MAPPINGS secret:"
    warn "       <medication_id>:<status>,<medication_id>:<status>"
    warn "     (statuses: ${VALID_STATUSES// /|})"
    warn "  4. Re-run the pipeline. Remove the secret after the migration lands."
    warn ""
    warn "Fail closed — migration will NOT run until this is resolved."
    append_summary "## ⚠️ Pre-migration Soft-Delete Audit — MANUAL REVIEW REQUIRED

\`soft_deleted_count=${COUNT}\`, \`review_required=true\`

Record details are intentionally NOT shown here (public log). Pull them via a
private Azure channel, then set the \`MEDICATION_SOFT_DELETE_MAPPINGS\` secret.

**Migration blocked (fail closed).**"
    exit 1
fi

log "MEDICATION_SOFT_DELETE_MAPPINGS is set — validating allowlist..."

# Parallel arrays (portable to bash 3.2 — no associative arrays).
MAP_IDS=()
MAP_STATUSES=()
approved_status_for() {
    local i
    for i in "${!MAP_IDS[@]}"; do
        if [[ "${MAP_IDS[$i]}" == "$1" ]]; then
            echo "${MAP_STATUSES[$i]}"
            return 0
        fi
    done
    return 1
}

IFS=',' read -ra PAIRS <<< "$MEDICATION_SOFT_DELETE_MAPPINGS"
for pair in "${PAIRS[@]}"; do
    pair="$(echo "$pair" | tr -d '[:space:]')"
    [[ -z "$pair" ]] && continue
    if [[ ! "$pair" =~ ^([0-9a-fA-F-]{36}):([a-z_]+)$ ]]; then
        die "Malformed mapping entry (expected <uuid>:<status>). Entry ref=$(fp "$pair")"
    fi
    map_id="${BASH_REMATCH[1]}"
    map_status="${BASH_REMATCH[2]}"
    if [[ " ${VALID_STATUSES} " != *" ${map_status} "* ]]; then
        die "Invalid lifecycle status '${map_status}' for record_ref=$(fp "$map_id"). Allowed: ${VALID_STATUSES// /|}"
    fi
    MAP_IDS+=("$map_id")
    MAP_STATUSES+=("$map_status")
done

if [[ ${#MAP_IDS[@]} -eq 0 ]]; then
    die "MEDICATION_SOFT_DELETE_MAPPINGS is set but contains no valid entries."
fi

GATE_OK=true

# Every soft-deleted DB record must be explicitly approved.
for id in "${DB_IDS[@]}"; do
    if ! approved_status_for "$id" > /dev/null; then
        err "Unreviewed soft-deleted record found: record_ref=$(fp "$id") is not in the allowlist."
        GATE_OK=false
    fi
done

# Every approval must still correspond to an existing soft-deleted record.
for map_id in "${MAP_IDS[@]}"; do
    found=false
    for id in "${DB_IDS[@]}"; do
        [[ "$id" == "$map_id" ]] && { found=true; break; }
    done
    if [[ "$found" == false ]]; then
        err "Stale allowlist entry: record_ref=$(fp "$map_id") no longer matches a soft-deleted row."
        GATE_OK=false
    fi
done

# Migration p0_m01 applies a blanket entered_in_error UPDATE. Any other
# approved status would be silently mis-mapped, so refuse it here.
for i in "${!MAP_IDS[@]}"; do
    map_id="${MAP_IDS[$i]}"
    status="${MAP_STATUSES[$i]}"
    if [[ "$status" != "entered_in_error" ]]; then
        err "record_ref=$(fp "$map_id") approved as '${status}', but migration p0_m01 maps all"
        err "soft-deleted rows to 'entered_in_error'. Change the migration (or fix the data)"
        err "before approving a non-default status — the gate will not let the mismatch through."
        GATE_OK=false
    fi
done

if [[ "$GATE_OK" != true ]]; then
    err "review_required=true"
    err "Fail closed — allowlist validation failed."
    append_summary "## ⚠️ Pre-migration Soft-Delete Audit — ALLOWLIST VALIDATION FAILED

\`soft_deleted_count=${COUNT}\` — see job log for record fingerprints.

**Migration blocked (fail closed).**"
    exit 1
fi

log "review_required=false"
log "✅ AUDIT PASSED — all ${COUNT} soft-deleted record(s) explicitly approved:"
SUMMARY_ROWS=""
for id in "${DB_IDS[@]}"; do
    ref=$(fp "$id")
    status=$(approved_status_for "$id")
    log "  record_ref=${ref} approved_status=${status}"
    SUMMARY_ROWS="${SUMMARY_ROWS}| \`${ref}\` | \`${status}\` |
"
done
log "Reminder: remove the MEDICATION_SOFT_DELETE_MAPPINGS secret once the migration has run."

append_summary "## ✅ Pre-migration Soft-Delete Audit — PASSED (per-record allowlist)

\`soft_deleted_count=${COUNT}\`, all records explicitly approved:

| record_ref | approved status |
|------------|-----------------|
${SUMMARY_ROWS}
Remove the \`MEDICATION_SOFT_DELETE_MAPPINGS\` secret after the migration lands."

exit 0
