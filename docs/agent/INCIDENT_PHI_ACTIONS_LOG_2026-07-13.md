# Security incident (LOW) — clinical row content in public Actions log

**Date detected:** 2026-07-13 (UTC)
**Status:** remediated
**Severity:** LOW (no personal identifiers, no credentials; pseudonymous
clinical rows only)

## What happened

The pre-migration soft-delete audit gate (`scripts/pre_migration_audit.sh`,
introduced with the medication P0 work) printed, on its fail-closed path, the
full content of soft-deleted `medications` rows into the GitHub Actions job
log and step summary. The repository is public, so Actions logs are
world-readable.

One workflow run on `main` (2026-07-13, "Deploy to Staging" job) exposed, for
2 rows: medication UUIDs, drug names, dose/frequency-level detail in one
note field, and deletion timestamps. No patient names, contact details,
patient ids, or credentials appeared in the log. Patient linkage is not
derivable from the exposed fields alone.

## Scope check

- The gate's detail output existed in exactly one run (the first run where the
  gate reached the database). The prior run's gate failed before connecting
  (psql URL error) and printed no row data.
- PR-triggered runs never execute the deploy job, so no other runs contained
  the output.
- No artifacts carried the data; the step summary of the same run did (both
  removed with the run).

## Remediation

1. The exposing workflow run was deleted from GitHub (run + logs + summary).
2. `scripts/pre_migration_audit.sh` rewritten to a PHI-safe contract: logs
   only `soft_deleted_count`, `review_required`, and non-reversible record
   fingerprints `sha256(<id> + <secret-derived salt>)[0:12]`. Names, ids,
   notes, and timestamps are never queried by the gate anymore (ids only,
   and ids never printed raw).
3. Detailed review data is now pulled exclusively through a private Azure
   channel (one-shot Container Apps job, deleted after use).
4. Per-record allowlist override (`MEDICATION_SOFT_DELETE_MAPPINGS`, a GitHub
   secret) replaces any notion of a global bypass; see the script header.

## Follow-ups

- DB credentials were not exposed; no rotation required.
- Keep future gates to the same rule: **counts and fingerprints in CI, row
  content only via private channels.**
