# Production pre-deploy checklist

For dispatching `azure-production.yml`. Written after the 2026-08-06 staging
incident, in which a migration job encrypted PHI with the repository's default
key because nobody had checked that it received the real one.

Every mechanical item in **§A** is enforced by the workflow or by a test — they
are listed so you can see *what* is enforced, not so you can perform them. The
items that need a person are in **§B**, and they are the only reason this page
exists.

---

## A. Enforced automatically — verify, do not perform

Each row names what would happen if the control were absent.

| # | Control | Enforced by | Absent ⇒ |
|---|---|---|---|
| A1 | Dispatch only from `main` | `github.ref != refs/heads/main` → exit 1 | an unreviewed branch reaches production |
| A2 | `confirm=PRODUCTION` required, exact case | `inputs.confirm != "PRODUCTION"` → exit 1 | a mis-click deploys |
| A3 | Key Vault resolved or abort | `Resolve production Key Vault` → exit 1 | secrets silently absent |
| A4 | **Rollback target recorded before anything changes** | `Record rollback target` | on-call reads a system that has already changed |
| A5 | Pre-migration soft-delete audit | `Pre-migration soft-delete audit` | unreviewed destructive migration |
| A6 | Backup / PITR precondition, fail-closed | `Pre-migration DB backup` | no restore point |
| A7 | Migration job receives the PHI key **by secret reference** | `MCP_ENCRYPTION_KEYS=secretref:enc-keys`; `test_the_migration_job_receives_the_encryption_key` | **the 2026-08-06 incident, on production** |
| A8 | No default-key fallback anywhere | `_cipher()` refusal outside dev envs; `test_the_committed_default_key_is_refused_outside_development` | PHI encrypted with a public key |
| A9 | Missing / malformed key fails loud | `EncryptionConfigError`; two tests | silent substitution |
| A10 | Lock wait bounded, rewrite not | `SET LOCAL lock_timeout = '5s'` + `statement_timeout = 0`; `test_phi_migrations_bound_how_long_they_wait_for_a_lock` | migration queues behind a transaction and blocks every reader |
| A11 | Migration job deleted immediately after | `Remove Alembic migration job`, `if: always()` | production PHI key parked in an unwatched job |
| A12 | Crypto smoke runs **after** migration, **before** any revision | `test_every_deploy_path_gates_in_the_right_order` | a wrong key ships and the gate reports on live traffic |
| A13 | Smoke failure **and** smoke timeout both abort | two `exit 1`; `test_every_deploy_path_fails_closed_on_the_smoke` | a deploy called healthy on a check that never returned |
| A14 | Stale job reuse impossible | delete-before-create is fatal; `--job-execution-name` poll | the OLD key is verified and reported pass |
| A15 | Smoke job deleted afterwards | `Remove crypto-smoke job`, `if: always()` | production PHI key parked in a second unwatched job |
| A16 | Health can only go green **after** encrypted reads succeed | ordering: smoke → rollout → `Wait for backend healthy` | green deploy, broken reminders |
| A17 | No deploy path can bypass the smoke | `test_no_deploy_path_can_bypass_the_crypto_smoke`, derived from the workflow tree | a manual path silently skips the gate — real until 2026-08-06 |

**A17 is the one to keep honest.** It discovers deploying workflows by content
rather than from a list, so a new workflow that migrates and rolls out is
covered the day it is written. A list would have missed `azure-staging.yml`,
which is exactly what happened.

## B. Requires a person — do these

- [ ] **B1. Understand the Alembic head jump.**
      Production last migrated **2026-07-14** at build `30a65ebc`. This deploy
      runs every migration since — including `j4_m9` and `j4_m10`, the PHI
      encryption migrations, **for the first time in production**. They rewrite
      columns and briefly take `ACCESS EXCLUSIVE` (bounded by A10). This is not
      a routine deploy.
      ```bash
      cd backend && alembic history -r 30a65ebc:head | head -40
      ```

- [ ] **B2. Pick the window.** A10 aborts the migration if it cannot take the
      lock within 5s. Deploy when write traffic is low, or expect to retry.

- [ ] **B3. Confirm the PITR window covers the moment you start.**
      ```bash
      az postgres flexible-server show -g rg-metocare-prod -n psql-metocare-prod \
        --query "{tier:sku.tier,earliest:backup.earliestRestoreDate,retentionDays:backup.backupRetentionDays}"
      ```
      If the tier is **Burstable**, Azure refuses on-demand backups
      (`CustomerOnDemandBackupCannotBePerformedOnBurstableServer`) and PITR is
      the only restore path. Know that before you need it, not after.

- [ ] **B4. Delete the stale production migration job.** `caj-metocare-migrate`
      has sat in `rg-metocare-prod` since 2026-07-14 holding the production
      database URL as a job secret, from before A11 existed. A11 removes it
      during this deploy, but there is no reason to carry it in:
      ```bash
      az containerapp job delete -g rg-metocare-prod -n caj-metocare-migrate --yes
      ```

- [ ] **B5. Answer the two open questions in the incident record**
      (`2026-08-06-staging-encryption-incident-record.md` §12): is staging pilot
      data real, and were all listed principals appropriately trusted. Neither
      blocks *this* deploy; both get harder to answer the longer they wait.

- [ ] **B6. Know your rollback before you start.** After dispatch, the run's step
      summary carries the exact revision and the command (A4). Read it. And note
      that a **data** rollback is not an Alembic downgrade — the SEC-F11/j4_m10
      migrations refuse to decrypt with a wrong key and abort rather than destroy
      data. Data rollback is PITR, which discards writes since the restore point
      and is an owner decision.

- [ ] **B7. Watch the crypto smoke, not the green tick.** It is the step that
      matters. Its verdict names which key each row needs:
      `ciphertext_source_key_rows` → re-encrypt, `ciphertext_unreadable_rows` →
      restore, `plaintext_legacy_rows` → never encrypted. A pass with every
      counter at zero means it verified nothing, which is itself a failure
      (`no_legacy_rows_to_verify`).

## C. Dispatch

```bash
gh workflow run azure-production.yml --ref main -f confirm=PRODUCTION
```

Or in the UI: **Actions → Azure Production Deploy → Run workflow**, branch
`main`, `confirm` = `PRODUCTION`.

Both A1 and A2 must hold: `--ref main`, and `PRODUCTION` in exact upper case.

## D. After

- [ ] `curl -s https://<prod-fqdn>/api/v1/info` → expected `build_sha`, and
      `migration_version` advanced past the 2026-07-14 head.
- [ ] Crypto smoke step green in the run, with a **non-zero**
      `ciphertext_target_key_rows`.
- [ ] `az containerapp job list -g rg-metocare-prod` → no `caj-metocare-migrate`
      and no `caj-metocare-crypto-smoke` (A11, A15).
- [ ] One authenticated read of a `raise`-policy column — a medication timeline
      or a reminder. Under a wrong key those 500 rather than degrading, so a 200
      is the proof. `/health` is `SELECT 1` and proves nothing about encryption.
