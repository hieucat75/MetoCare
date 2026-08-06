#!/usr/bin/env bash
# =============================================================================
# staging_reencrypt_job.sh — run one mode of the staging PHI re-encryption job
#
#   bash scripts/staging_reencrypt_job.sh <mode> [image-tag]
#
#   mode : dry-run | snapshot | verify-snapshot | apply | final-scan
#          | restore-snapshot
#
# Runbook: docs/runbooks/staging-phi-reencryption.md — read it first.
#
# Deliberately NOT wired into any workflow. This job decrypts PHI with a key
# committed to the repository; it must be run by a person who has decided to,
# once, with the runbook open — not on a schedule and not on merge.
#
# Why a one-off Container Apps Job and not psql from a laptop
# -----------------------------------------------------------
# The staging Postgres firewall admits Azure services, not arbitrary operator
# IPs. Punching a hole for a laptop to rewrite every PHI column would be a
# larger change, and a longer-lived one, than the remediation itself. The job
# runs inside the same Container Apps environment on the same image the
# application runs, so what it decrypts with is what the app decrypts with.
#
# Key handling
# ------------
# Both keys reach the container as `secretref:` values. Neither appears in the
# job's `--args`, and both are masked in this script's own output. The SOURCE
# key is the development default from `Settings.encryption_keys` — it is in this
# repository, which is the entire problem, but it is still never echoed, so a
# pasted log cannot be mistaken for a disclosure of the REAL key.
#
# The source key is passed as REENCRYPT_SOURCE_KEYS, never as part of
# MCP_ENCRYPTION_KEYS: registering it as a runtime decrypt key would make every
# read work instantly while leaving the PHI readable by anyone holding this
# repository, and would silence the only signal that anything is wrong. The job
# refuses to start if it finds the source key in the runtime keyset, and so
# does this script.
# =============================================================================

set -euo pipefail

MODE="${1:?Usage: $0 <dry-run|snapshot|verify-snapshot|apply|final-scan|restore-snapshot> [image-tag]}"

RG="${RG:-rg-metocare-staging}"
ENV_NAME="${ENV_NAME:-cae-metocare-staging}"
KV_NAME="${KV_NAME:-kv-metocare-stgd9e7}"
BACKEND_APP="${BACKEND_APP:-ca-metocare-backend}"
JOB="caj-metocare-phi-reencrypt"
CONFIRM_VALUE="REENCRYPT-STAGING-PHI"

case "$MODE" in
  dry-run|snapshot|verify-snapshot|apply|final-scan|restore-snapshot) ;;
  *) echo "ERROR: unknown mode '$MODE'." >&2; exit 2 ;;
esac

log() { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*"; }
die() { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] ERROR: $*" >&2; exit 1; }

az account show -o none 2>/dev/null || die "not authenticated with Azure; run 'az login'"

# The image the job runs. Defaults to whatever revision staging is CURRENTLY
# serving, so the job decrypts with exactly the code the application uses. An
# explicit tag is accepted for the case this runbook was written for: the deploy
# failed at the crypto gate, so the new image exists in the registry but no
# revision carries it yet.
IMG="${2:-}"
if [[ -z "$IMG" ]]; then
    IMG=$(az containerapp revision list -g "$RG" -n "$BACKEND_APP" \
        --query "[?properties.active]|[0].properties.template.containers[0].image" -o tsv) \
        || die "could not resolve the active staging image"
    [[ -n "$IMG" ]] || die "no active revision on $BACKEND_APP; pass an image tag explicitly"
else
    IMG="ghcr.io/hieucat75/metocare-backend:${IMG}"
fi
log "image:  $IMG"
log "mode:   $MODE"

# ---------------------------------------------------------------------------
# Secrets. Read, masked, and handed on by reference.
#
# The source key is read from the CHECKED-IN default rather than typed by hand:
# a mistyped source key produces `ciphertext_unreadable_rows` across the board,
# which reads identically to genuine corruption and would send the responder
# down the restore path for no reason.
# ---------------------------------------------------------------------------
DB_URL=$(az keyvault secret show --vault-name "$KV_NAME" -n mcp-database-url --query value -o tsv) \
    || die "could not read mcp-database-url from $KV_NAME"
ENC_KEYS=$(az keyvault secret show --vault-name "$KV_NAME" -n mcp-encryption-keys --query value -o tsv) \
    || die "could not read mcp-encryption-keys from $KV_NAME"
SRC_KEYS=$(cd "$(dirname "$0")/../backend" && python3 -c \
    'import re, pathlib; print(re.search(r"encryption_keys: str = \"([^\"]+)\"", pathlib.Path("app/core/config.py").read_text()).group(1))') \
    || die "could not read the repository default key out of app/core/config.py"
[[ -n "$SRC_KEYS" ]] || die "the repository default key resolved empty"

if [[ -n "${GITHUB_ACTIONS:-}" ]]; then
    echo "::add-mask::$DB_URL"; echo "::add-mask::$ENC_KEYS"; echo "::add-mask::$SRC_KEYS"
fi

if [[ "$ENC_KEYS" == *"$SRC_KEYS"* ]]; then
    die "the staging runtime keyset CONTAINS the repository default key. Remove it from
     Key Vault secret mcp-encryption-keys first — while it is there, every read
     'works' and staging PHI is readable by anyone holding this repository."
fi

# ---------------------------------------------------------------------------
# Delete-then-create. A reused job runs the PREVIOUS mode's arguments and the
# PREVIOUS image — and one of the modes rewrites every encrypted column, so
# "whatever the job happened to be configured for last time" is not an
# acceptable input. The delete is not allowed to fail silently.
# ---------------------------------------------------------------------------
if az containerapp job show -g "$RG" -n "$JOB" -o none 2>/dev/null; then
    az containerapp job delete -g "$RG" -n "$JOB" --yes -o none \
        || die "could not delete the previous $JOB; refusing to upsert onto it"
fi

az containerapp job create -g "$RG" -n "$JOB" \
    --environment "$ENV_NAME" --trigger-type Manual \
    --replica-timeout 1800 --replica-retry-limit 0 \
    --parallelism 1 --replica-completion-count 1 \
    --image "$IMG" --cpu 1.0 --memory 2Gi \
    --secrets db-url="$DB_URL" enc-keys="$ENC_KEYS" src-keys="$SRC_KEYS" \
    --env-vars MCP_DATABASE_URL=secretref:db-url \
      MCP_ENCRYPTION_KEYS=secretref:enc-keys \
      REENCRYPT_SOURCE_KEYS=secretref:src-keys \
      MCP_ENV=staging \
      STAGING_REENCRYPT_CONFIRM="$CONFIRM_VALUE" \
    --command "python" --args "run_reencrypt_phi.py" "$MODE" \
    -o none

# Cleanup is registered BEFORE the job starts, not after it finishes: the job
# holds the staging PHI master key as a secret, and the reason to remove it is
# not tidiness. A Ctrl-C during the poll must not leave it behind.
cleanup() {
    if az containerapp job show -g "$RG" -n "$JOB" -o none 2>/dev/null; then
        az containerapp job delete -g "$RG" -n "$JOB" --yes -o none 2>/dev/null || {
            echo "WARNING: could not delete $JOB. It holds the staging database URL,"
            echo "WARNING: MCP_ENCRYPTION_KEYS and the source key as job secrets."
            echo "WARNING: delete it manually:"
            echo "WARNING:   az containerapp job delete -g $RG -n $JOB --yes"
        }
    fi
}
trap cleanup EXIT INT TERM

az containerapp job start -g "$RG" -n "$JOB" -o none

# Poll THIS execution by name. `[0]` has no ordering guarantee, and a stale
# Succeeded from an earlier mode would be read as this run's verdict.
EXEC=$(az containerapp job execution list -g "$RG" -n "$JOB" --query "[0].name" -o tsv 2>/dev/null || echo "")
[[ -n "$EXEC" ]] || die "the job reported no execution to poll — it never started"
log "execution: $EXEC"

ST=""
for i in $(seq 1 120); do   # 120x15s = 1800s, matching --replica-timeout
    ST=$(az containerapp job execution show -g "$RG" -n "$JOB" \
        --job-execution-name "$EXEC" --query "properties.status" -o tsv 2>/dev/null || echo Running)
    echo "  $MODE $i: $ST"
    [[ "$ST" == "Succeeded" || "$ST" == "Failed" ]] && break
    sleep 15
done

echo
log "── job output ─────────────────────────────────────────────────────────"
# The output IS the evidence, and it is PHI-free and key-free by construction:
# counts, entity names, and sha256(table|id)[:16] row references.
az containerapp job logs show -g "$RG" -n "$JOB" --container "$JOB" \
    --execution "$EXEC" --tail 400 2>/dev/null || \
    echo "(logs not yet available: az containerapp job logs show -g $RG -n $JOB --execution $EXEC)"
log "───────────────────────────────────────────────────────────────────────"

if [[ "$ST" != "Succeeded" ]]; then
    die "$MODE did not succeed (last status: ${ST:-unknown}). Do NOT proceed to the
     next step. See docs/runbooks/staging-phi-reencryption.md §6."
fi
log "$MODE: Succeeded"
