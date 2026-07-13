#!/usr/bin/env bash
# =============================================================================
# pre_migration_backup.sh — Pre-migration Azure PostgreSQL backup gate
#
# Usage:
#   bash scripts/pre_migration_backup.sh <ENV> <TIMESTAMP> <GIT_SHA>
#
# Arguments:
#   ENV       — deployment environment (e.g. staging, production)
#   TIMESTAMP — ISO-8601 compact timestamp (e.g. 20260711T153000)
#   GIT_SHA   — git commit SHA (full or short — used in backup name)
#
# Required environment variables:
#   POSTGRES_SERVER_NAME  — Azure PostgreSQL Flexible Server name
#                           (e.g. psql-metocare-staging)
#   RESOURCE_GROUP        — Azure resource group (e.g. rg-metocare-staging)
#   AZURE_CREDENTIALS     — (optional) JSON credentials for az login --service-principal
#                           If not set, assumes az is already authenticated (OIDC in CI).
#
# Behaviour:
#   1. Validates all required inputs (fail fast, fail clearly)
#   2. Triggers az postgres flexible-server backup create (async request)
#   3. Polls az postgres flexible-server backup show until provisioningState == Succeeded
#   4. Timeout: 10 minutes (600 seconds), poll every 30 seconds
#   5. On timeout or failure: exits 1 (fail closed — migration does NOT run)
#   6. On success: prints backup name, writes to $GITHUB_STEP_SUMMARY if in CI
#   7. Returns 0 only on confirmed Succeeded
#
# IMPORTANT: Exit code 0 from `az postgres flexible-server backup create` means
# the backup REQUEST was accepted, NOT that the backup is complete or usable.
# This script polls until provisioningState == Succeeded (or fails).
# Do NOT treat az exit code 0 alone as evidence of a valid restore point.
#
# Design reference: MEDICATION_P0_PRE_VALIDATION.md §RISK-4 (PTH decision 2026-07-11)
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------
ENV="${1:?Usage: $0 <ENV> <TIMESTAMP> <GIT_SHA>}"
TIMESTAMP="${2:?Usage: $0 <ENV> <TIMESTAMP> <GIT_SHA>}"
GIT_SHA="${3:?Usage: $0 <ENV> <TIMESTAMP> <GIT_SHA>}"

# Truncate SHA to 8 chars for backup name length limits
SHORT_SHA="${GIT_SHA:0:8}"

# Backup name: must match Azure naming rules (alphanumeric + hyphen, ≤ 63 chars)
# Format: pre-migration-{env}-{timestamp}-{sha8}
BACKUP_NAME="pre-migration-${ENV}-${TIMESTAMP}-${SHORT_SHA}"

# ---------------------------------------------------------------------------
# Early secret validation — fail before any az call if secrets are missing
# ---------------------------------------------------------------------------
MISSING_SECRETS=()

if [[ -z "${POSTGRES_SERVER_NAME:-}" ]]; then
    echo "ERROR: POSTGRES_SERVER_NAME secret is not configured" >&2
    MISSING_SECRETS+=("POSTGRES_SERVER_NAME")
fi

if [[ -z "${RESOURCE_GROUP:-}" ]]; then
    echo "ERROR: RESOURCE_GROUP secret is not configured" >&2
    MISSING_SECRETS+=("RESOURCE_GROUP")
fi

if [[ ${#MISSING_SECRETS[@]} -gt 0 ]]; then
    echo "ERROR: The following required secrets are not set: ${MISSING_SECRETS[*]}" >&2
    echo "Configure these in the GitHub Actions azure-staging environment before running." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Required environment variables
# ---------------------------------------------------------------------------
POSTGRES_SERVER_NAME="${POSTGRES_SERVER_NAME}"
RESOURCE_GROUP="${RESOURCE_GROUP}"

# ---------------------------------------------------------------------------
# Polling config
# ---------------------------------------------------------------------------
MAX_WAIT_SECONDS=600   # 10 minutes
POLL_INTERVAL_SECONDS=30
MAX_POLLS=$(( MAX_WAIT_SECONDS / POLL_INTERVAL_SECONDS ))

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------
log()  { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*"; }
err()  { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] ERROR: $*" >&2; }
die()  { err "$*"; exit 1; }

# ---------------------------------------------------------------------------
# Azure login (only if AZURE_CREDENTIALS is set and az not already logged in)
# In GitHub Actions with OIDC, az login is handled by the azure/login action.
# In local/manual runs, set AZURE_CREDENTIALS to a JSON service principal.
# ---------------------------------------------------------------------------
if [[ -n "${AZURE_CREDENTIALS:-}" ]]; then
    log "Authenticating with Azure using AZURE_CREDENTIALS..."
    CLIENT_ID=$(echo "$AZURE_CREDENTIALS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['clientId'])")
    CLIENT_SECRET=$(echo "$AZURE_CREDENTIALS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['clientSecret'])")
    TENANT_ID=$(echo "$AZURE_CREDENTIALS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['tenantId'])")
    az login --service-principal \
        --username "$CLIENT_ID" \
        --password "$CLIENT_SECRET" \
        --tenant "$TENANT_ID" \
        --output none \
        || die "az login failed — cannot proceed without Azure authentication"
    log "Azure login succeeded."
else
    # Verify az is already authenticated (OIDC or local az login)
    if ! az account show --output none 2>/dev/null; then
        die "Not authenticated with Azure. Set AZURE_CREDENTIALS or run 'az login' first."
    fi
    log "Using existing Azure authentication."
fi

# ---------------------------------------------------------------------------
# Validate that the Postgres server exists and is reachable
# ---------------------------------------------------------------------------
log "Verifying PostgreSQL server: ${POSTGRES_SERVER_NAME} (RG: ${RESOURCE_GROUP})"
SERVER_STATE=$(az postgres flexible-server show \
    --name "$POSTGRES_SERVER_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query "state" \
    --output tsv 2>/dev/null) || die "Cannot find Postgres server '${POSTGRES_SERVER_NAME}' in RG '${RESOURCE_GROUP}'. Aborting."

log "Server state: ${SERVER_STATE}"
if [[ "$SERVER_STATE" != "Ready" ]]; then
    die "Postgres server is not in 'Ready' state (current: '${SERVER_STATE}'). Cannot take backup. Aborting migration."
fi

# ---------------------------------------------------------------------------
# Burstable tier: Azure rejects customer on-demand backups
# (CustomerOnDemandBackupCannotBePerformedOnBurstableServer). Verify the
# automated-backup PITR window and record the pre-migration restore point
# instead (PTH decision 2026-07-13). Higher tiers keep the on-demand path.
# ---------------------------------------------------------------------------
SERVER_META=$(az postgres flexible-server show \
    --name "$POSTGRES_SERVER_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query "[sku.tier, backup.earliestRestoreDate, backup.backupRetentionDays]" \
    --output tsv 2>/dev/null || echo "Unknown")
SKU_TIER=$(echo "$SERVER_META" | awk 'NR==1{print $1}')
EARLIEST_RESTORE=$(echo "$SERVER_META" | awk 'NR==1{print $2}')
RETENTION_DAYS=$(echo "$SERVER_META" | awk 'NR==1{print $3}')
log "Server tier: ${SKU_TIER}"

if [[ "$SKU_TIER" == "Burstable" ]]; then
    log "On-demand backups are not supported on Burstable — verifying PITR instead."

    if [[ -z "${EARLIEST_RESTORE:-}" ]] || [[ "${RETENTION_DAYS:-0}" -lt 1 ]]; then
        die "PITR is not available (earliestRestoreDate='${EARLIEST_RESTORE:-}', retention=${RETENTION_DAYS:-0}d). No restore point exists — aborting migration (fail closed)."
    fi

    RESTORE_POINT=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
    log "✅ PITR verified — pre-migration restore point recorded."
    log "   Restore point (UTC):   ${RESTORE_POINT}"
    log "   Earliest restorable:   ${EARLIEST_RESTORE}"
    log "   Retention:             ${RETENTION_DAYS} days"
    log "   Environment:           ${ENV}"
    log "   Git SHA:               ${GIT_SHA}"
    log ""
    log "To roll back to the pre-migration state:"
    log "  az postgres flexible-server restore \\"
    log "     --resource-group <rg> \\"
    log "     --name <new-server-name> \\"
    log "     --source-server ${POSTGRES_SERVER_NAME} \\"
    log "     --restore-time ${RESTORE_POINT}"

    if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
        cat >> "$GITHUB_STEP_SUMMARY" << SUMMARY
## ✅ Pre-migration Restore Point — PITR (Burstable tier)

On-demand backups are not supported on Burstable servers; the automated-backup
PITR window was verified instead.

| Item | Value |
|------|-------|
| Restore point (UTC) | \`${RESTORE_POINT}\` |
| Retention | \`${RETENTION_DAYS} days\` |
| Git SHA | \`${SHORT_SHA}\` |

Roll back with \`az postgres flexible-server restore --restore-time ${RESTORE_POINT} ...\`.
SUMMARY
    fi

    exit 0
fi

# ---------------------------------------------------------------------------
# Trigger the backup
# ---------------------------------------------------------------------------
log "Triggering pre-migration backup..."
log "  Server:      ${POSTGRES_SERVER_NAME}"
log "  Resource RG: ${RESOURCE_GROUP}"
log "  Backup name: ${BACKUP_NAME}"
log "  Environment: ${ENV}"
log "  Git SHA:     ${GIT_SHA}"

az postgres flexible-server backup create \
    --server-name "$POSTGRES_SERVER_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --name "$BACKUP_NAME" \
    --output none \
    || die "az postgres flexible-server backup create failed (request rejected). Aborting migration."

log "Backup create request accepted. Polling for completion..."
log "  Timeout: ${MAX_WAIT_SECONDS}s (max ${MAX_POLLS} polls every ${POLL_INTERVAL_SECONDS}s)"

# ---------------------------------------------------------------------------
# Poll until Succeeded or timeout
# ---------------------------------------------------------------------------
POLL_COUNT=0
while [[ $POLL_COUNT -lt $MAX_POLLS ]]; do
    POLL_COUNT=$(( POLL_COUNT + 1 ))
    ELAPSED=$(( POLL_COUNT * POLL_INTERVAL_SECONDS ))

    # Query the backup status
    PROVISIONING_STATE=$(az postgres flexible-server backup show \
        --server-name "$POSTGRES_SERVER_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --name "$BACKUP_NAME" \
        --query "backupType" \
        --output tsv 2>/dev/null || echo "Querying")

    # The backup show command returns provisioningState via a different path
    # depending on the az CLI version. Try both paths.
    if [[ "$PROVISIONING_STATE" == "Querying" ]] || [[ -z "$PROVISIONING_STATE" ]]; then
        PROVISIONING_STATE=$(az postgres flexible-server backup show \
            --server-name "$POSTGRES_SERVER_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --name "$BACKUP_NAME" \
            --query "properties.backupType" \
            --output tsv 2>/dev/null || echo "Unknown")
    fi

    # Also check provisioningState directly
    PROV_STATE=$(az postgres flexible-server backup show \
        --server-name "$POSTGRES_SERVER_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --name "$BACKUP_NAME" \
        --query "provisioningState || properties.provisioningState" \
        --output tsv 2>/dev/null || echo "Unknown")

    log "  Poll ${POLL_COUNT}/${MAX_POLLS} (${ELAPSED}s elapsed): provisioningState='${PROV_STATE}'"

    if [[ "$PROV_STATE" == "Succeeded" ]]; then
        log "✅ Backup completed successfully!"
        log "   Backup name: ${BACKUP_NAME}"
        log "   Server:      ${POSTGRES_SERVER_NAME}"
        log "   Environment: ${ENV}"
        log "   Timestamp:   ${TIMESTAMP}"
        log "   Git SHA:     ${GIT_SHA}"

        # Write summary to GitHub Actions step summary if in CI
        if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
            cat >> "$GITHUB_STEP_SUMMARY" << SUMMARY
## ✅ Pre-migration DB Backup Succeeded

| Field | Value |
|-------|-------|
| Backup name | \`${BACKUP_NAME}\` |
| Server | \`${POSTGRES_SERVER_NAME}\` |
| Resource group | \`${RESOURCE_GROUP}\` |
| Environment | \`${ENV}\` |
| Timestamp | \`${TIMESTAMP}\` |
| Git SHA | \`${GIT_SHA}\` |
| Provisioning state | \`Succeeded\` |

**Migration may proceed.** To restore this backup if migration fails:
\`\`\`
az postgres flexible-server restore \\
  --name <new-server-name> \\
  --resource-group ${RESOURCE_GROUP} \\
  --source-server ${POSTGRES_SERVER_NAME} \\
  --restore-time <restore-point-in-time>
\`\`\`
SUMMARY
            log "GitHub Step Summary updated."
        fi

        exit 0
    fi

    if [[ "$PROV_STATE" == "Failed" ]] || [[ "$PROV_STATE" == "Canceled" ]]; then
        # Retrieve full backup details for error context
        DETAILS=$(az postgres flexible-server backup show \
            --server-name "$POSTGRES_SERVER_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --name "$BACKUP_NAME" \
            --output json 2>/dev/null || echo "{}")
        err "Backup failed with provisioningState='${PROV_STATE}'"
        err "Backup details: ${DETAILS}"
        die "Pre-migration backup failed. Aborting migration (fail closed)."
    fi

    # Still running / unknown — wait and retry
    if [[ $POLL_COUNT -lt $MAX_POLLS ]]; then
        sleep "$POLL_INTERVAL_SECONDS"
    fi
done

# ---------------------------------------------------------------------------
# Timeout — fail closed
# ---------------------------------------------------------------------------
err "Pre-migration backup did not reach 'Succeeded' state within ${MAX_WAIT_SECONDS}s."
err "Last known provisioningState: '${PROV_STATE}'"
err "Backup name: ${BACKUP_NAME}"
err ""
err "FAIL CLOSED: Migration will NOT run."
err "Options:"
err "  1. Check backup status manually:"
err "     az postgres flexible-server backup show \\"
err "        --server-name ${POSTGRES_SERVER_NAME} \\"
err "        --resource-group ${RESOURCE_GROUP} \\"
err "        --name ${BACKUP_NAME}"
err "  2. If backup eventually succeeded, re-trigger the pipeline."
err "  3. If Azure backup service is degraded, escalate to PTH before proceeding."
exit 1
