# Runbook — staging PHI re-encryption (wrong-key remediation)

Use this when the post-migration crypto smoke reports `ciphertext_source_key_rows`
against staging: rows are valid ciphertext under a key the application does not
have. It is the remediation for the 2026-08-06 incident, in which the Alembic
migration job ran without `MCP_ENCRYPTION_KEYS` and the SEC-F11 / j4_m10 data
migrations encrypted staging's PHI with the development default committed to
this repository.

**This runbook is staging-only.** The job refuses any other environment by
allow-list. Production remediation is not covered here and is not authorised.

---

## 0. Read the smoke verdict first

The gate names which key each row needs. The class decides the response, and
they are not interchangeable:

| Class | Meaning | Response |
|---|---|---|
| `ciphertext_target_key_rows` | Readable with the deployed key | Nothing. Healthy. |
| `ciphertext_source_key_rows` | Readable only with the source (repo default) key | This runbook. |
| `ciphertext_unreadable_rows` | Readable with no known key | **Stop.** Restore — §6. |
| `plaintext_legacy_rows` | Never encrypted | This runbook (`apply` encrypts them). |

If `ciphertext_unreadable_rows` is non-zero, do not run `apply`. There is no
plaintext to write back and the job will not invent one; go to §6.

---

## 1. Freeze staging writes

A live writer racing the job produces `row_changed_concurrently`, and the job
stops rather than clobber a value it never resolved. Prevent it instead:

```bash
RG=rg-metocare-staging
az containerapp update -g $RG -n ca-metocare-backend --min-replicas 0 --max-replicas 0
```

Do not seed data and do not run authenticated flow tests until §5 passes.
`/health` returning 200 is **not** evidence the data is readable — it is
`SELECT 1`, and it passed throughout the incident.

Record, for the evidence file:

```bash
az containerapp revision list -g $RG -n ca-metocare-backend \
  --query "[?properties.active].{name:name,image:properties.template.containers[0].image}" -o table
curl -s https://<backend-fqdn>/api/v1/info    # build_sha, migration_version
```

## 2. Confirm the restore point exists

Staging Postgres is a **Burstable** server. Azure refuses customer on-demand
backups on it — `CustomerOnDemandBackupCannotBePerformedOnBurstableServer` — so
there is no backup to "take". Two things stand in for one:

**(a) PITR**, for catastrophic loss. Verify the window covers the pre-migration
moment before doing anything:

```bash
az postgres flexible-server show -g $RG -n psql-metocare-staging \
  --query "{tier:sku.tier,earliest:backup.earliestRestoreDate,retentionDays:backup.backupRetentionDays}"
```

`earliest` must be **before** the bad migration ran. Restoring creates a NEW
server and rolls the whole database back:

```bash
az postgres flexible-server restore -g $RG \
  --name psql-metocare-staging-restored \
  --source-server psql-metocare-staging \
  --restore-time <UTC timestamp before the bad migration>
```

**(b) The ciphertext snapshot**, for the surgical undo — §3. PITR is the wrong
tool for putting a few columns back.

## 3. Snapshot, and verify the snapshot

```bash
bash scripts/staging_reencrypt_job.sh snapshot
bash scripts/staging_reencrypt_job.sh verify-snapshot
```

`snapshot` copies every non-NULL ciphertext value into
`phi_reencrypt_backup__<table>__<column>`, still encrypted, never decrypted.
`verify-snapshot` compares row counts and an ordered ciphertext digest against
the live column and **must pass before `apply` runs**. It only means anything
before the rewrite, because afterwards the digests are supposed to differ.

A second `snapshot` refuses rather than overwriting the first: re-running
part-way through would capture the half-repaired state and replace the only copy
of the original.

## 4. Dry run, then apply

```bash
bash scripts/staging_reencrypt_job.sh dry-run     # measures; writes nothing; always exits 0
bash scripts/staging_reencrypt_job.sh apply
bash scripts/staging_reencrypt_job.sh final-scan
```

Compare the dry-run counts against the smoke's. `apply` passes only when every
non-healthy row it found was rewritten **and** verified by reading it back.
`final-scan` is the one that proves the table: it passes only at
`plaintext_legacy_rows = ciphertext_source_key_rows = ciphertext_unreadable_rows = 0`.

`apply` is idempotent and restart-safe. If it is interrupted, run it again — it
resumes by finding what is still wrong, not by remembering where it stopped.

## 5. Re-run the gate, then unfreeze

```bash
az containerapp update -g $RG -n ca-metocare-backend --min-replicas 1 --max-replicas 1
gh workflow run "CI + Staging Auto-Deploy" --ref main     # or re-run the failed run
```

The crypto smoke must report `result: pass` with a non-zero
`ciphertext_target_key_rows`. A pass with everything at zero means it scanned
nothing and proved nothing — which is why `no_legacy_rows_to_verify` is itself a
failure.

Only then run the authenticated flow verification.

## 6. If rows remain unreadable

**Stop.** Do not continue flow testing, do not seed, do not deploy.

1. `bash scripts/staging_reencrypt_job.sh restore-snapshot` — puts the original
   ciphertext back byte for byte, so the database is exactly as the smoke found
   it and the evidence survives.
2. Record the exact table, column and count from the `final-scan` output.
3. Escalate. Unreadable rows mean a third key, or corruption. Recovery is the
   PITR restore in §2(a), which is an owner decision because it rolls back every
   write since the restore point.

The job never rewrites an unreadable row. That is deliberate: overwriting it
would destroy what a restore needs.

---

## What the job will refuse to do

| Refusal | Why |
|---|---|
| `MCP_ENV` is not exactly `staging` | Allow-list. A deny-list fails open on an env value nobody anticipated. |
| `MCP_ENV` is `prod`/`production` | Named separately, because that is the mistake worth naming. |
| `STAGING_REENCRYPT_CONFIRM` ≠ `REENCRYPT-STAGING-PHI` | Not a boolean — a value you only know from having read this page. |
| The source key is also in `MCP_ENCRYPTION_KEYS` | Registering it as a decrypt-only secondary "fixes" every read while leaving the PHI encrypted under a key published in this repository — and silences the only signal that anything is wrong. |
| The target key is the repository default | Re-encrypting onto a public key would report success and change nothing that matters. |
| An unknown mode, or no mode | Defaults to `dry-run`. A missing argument must not start writing. |

Neither key is ever printed, in any mode. Rows appear in the output only as
`sha256(table\|id)[:16]`.

## Owner decisions this runbook does NOT cover

- Any production remediation.
- The PITR restore in §6, which discards writes since the restore point.
- Rotating the staging encryption key. The repository default has been used to
  encrypt staging PHI, so that PHI should be treated as disclosed for the period
  it was at rest under that key, regardless of this repair.
