# Production pre-deploy checklist

> **CURRENT VERDICT: HOLD.** Every technical control passes. One item does not,
> and it is not a technical one — see **§0**. Re-read §0 before dispatching;
> the rest of this page is ready.

## 0. Owner gate — PASS/FAIL as of 2026-08-06

| Item | Verdict | Evidence |
|---|---|---|
| Data incident disposition | **FAIL — open** | Provenance: **CONFIRMED REAL DATA PRESENT**. 160 of 205 rows in the affected columns belong to non-synthetic accounts; 90 accounts self-registered through the public API; the repository holding the key is **PUBLIC**. Breach assessment not done. |
| Principal trust | **PASS with finding** | 2 principals, not 3. SP has **no stored secret**, OIDC subject-scoped. But it spans staging *and* production, and **neither GitHub environment has protection rules** — "owner approval" is convention, not control. |
| Stale job cleanup | **PASS** | **Zero** Container Apps Jobs in any resource group. Production `caj-metocare-migrate`, staging `caj-metocare-pilot-seed` (+ credentials rotated), `caj-metocare-seed-demo`, `caj-seed-doctor` all deleted. |
| Production PITR | **PASS** | `psql-metocare-prod`, GeneralPurpose `Standard_D2s_v3`, PG16, Ready. Earliest restorable `2026-07-31T02:13:21Z`, 7-day retention. **GeneralPurpose ⇒ on-demand backup works**, unlike staging. |
| Rollback target | **PASS** | `Record rollback target` captures revision + image before the migration and writes the `ingress traffic set` command to the step summary. Current target: `ca-metocare-backend--be-30a65ebc-1783997179`, image `…:30a65ebc-1783996432`. |
| Maintenance window | **FAIL — not set** | 18 migrations will run, including both PHI-encryption migrations, for the first time in production. Window and owner not yet named. See §B2. |
| Crypto smoke gate | **PASS** | Present on all three deploy paths, ordered `migrate < smoke < rollout`, fails closed on failure *and* timeout, polls its own execution. Proven live on staging in both directions. |
| Migration key secret reference | **PASS** | `MCP_ENCRYPTION_KEYS=secretref:enc-keys`; `_cipher()` refuses the committed default at `MCP_ENV=production`; production KV secret verified **not** the repo default. |
| Production-only main provenance | **PASS (workflow)** | `github.ref == refs/heads/main` → exit 1 otherwise. **Note:** `main` itself has no branch protection. |
| `confirm=PRODUCTION` requirement | **PASS** | Exact-case match → exit 1 otherwise. |

**Blocking: the data incident disposition, and the unset maintenance window.**
Neither is a defect in the deploy path.

---

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

- [x] **B4. Stale production migration job — DONE 2026-08-06.**
      `caj-metocare-migrate` deleted from `rg-metocare-prod` (created 2026-07-14,
      1 execution, held `db-url`). Zero Container Apps Jobs now exist in any
      resource group in the subscription. The production revision was untouched.

- [ ] **B5. BREACH ASSESSMENT — the one genuinely blocking item.**
      Provenance is no longer an open question: **CONFIRMED REAL DATA PRESENT**.
      160 of 205 rows in the affected columns belong to accounts with deliverable
      addresses; 90 accounts self-registered through the public staging ingress;
      and the repository holding the key is **PUBLIC**. Real users\' Meto
      conversation contents and names were readable-in-principle for 5 h 05 m to
      anyone who also obtained the database contents.
      Decide notification, and decide separately whether staging should hold real
      user data at all — 90 people registered because nothing stopped them.
      Neither
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

---

## E. Production pre-deploy package — PREPARED, NOT EXECUTED

Everything a deploy needs, assembled. **Nothing here has been run.**

### People — all three unassigned, and that is the blocker

| Role | Name | Responsibility |
|---|---|---|
| Incident Commander | `<unassigned>` | Owns the deploy while it runs; the only person who calls an abort |
| Rollback owner | `<unassigned>` | Executes the rollback command below if called |
| Legal/privacy incident owner | `<unassigned>` | Owns the notification decision — independent of, and prior to, this deploy |

A deploy with no named commander has nobody who can decide to stop it.

### Maintenance window

| | |
|---|---|
| Proposed window | `<unassigned>` |
| Expected duration | **20–40 min.** 18 migrations; the two PHI-encryption migrations rewrite columns in `extraction_candidates` and `notifications` |
| Constraint | `lock_timeout = 5s` aborts if a conflicting transaction is open. Choose a low-write period, or expect to retry |

### Current production state

| | |
|---|---|
| Active revision | `ca-metocare-backend--be-30a65ebc-1783997179` |
| Image | `ghcr.io/hieucat75/metocare-backend:30a65ebc-1783996432` |
| Deployed since | `2026-07-14T02:46:31Z` |
| Replicas | 1 |
| Postgres | `psql-metocare-prod`, PG16, **GeneralPurpose `Standard_D2s_v3`** |
| PITR earliest restorable | `2026-07-31T02:13:21Z`, 7-day retention |
| On-demand backup | **Supported** (GeneralPurpose, unlike Burstable staging) |
| Container Apps Jobs | **none** — the stale migration job was removed |

### Migration plan

**18 migrations** from production's 2026-07-14 head to `j3_m7_sched_lifecycle`,
including, for the first time in production:

- `j4_m9_secf11_phi_encryption` — encrypts Meto message bodies and OCR candidate
  fields; converts `extraction_candidates.fields_json` JSONB → TEXT
- `j4_m10_p15_residual_phi` — encrypts residual PHI surfaces; widens
  `notifications.title`

```bash
cd backend && alembic history -r 30a65ebc:head    # review before dispatch
```

### Row-count and lock preflight

Production row counts were **not** measured — doing so means pointing a job at
the production database, and the deploy is on hold. Staging's equivalent (359
encrypted values across 31 columns) is the closest available proxy; production is
a three-week-older dataset of similar shape.

Both migrations carry their own preflight: `_preflight_locks()` names the blocking
PIDs and their transaction age before attempting the lock, then `lock_timeout = 5s`
bounds the wait and `statement_timeout = 0` protects the rewrite once acquired.
Advisory only — it reports, it does not terminate anything.

### Crypto smoke

Runs after the migration and before any revision. Must report `result: pass` with
a **non-zero** `ciphertext_target_key_rows`.

### Abort criteria

Any one of these — stop, do not retry blind:

1. Crypto smoke reports non-zero `ciphertext_source_key_rows`,
   `ciphertext_unreadable_rows` or `plaintext_legacy_rows`.
2. Crypto smoke returns no verdict within 400 s.
3. A pass with **every counter at zero** — it verified nothing.
4. Migration aborts on `lock_timeout` — retry in a quieter window, never force.
5. Pre-migration backup step fails — there is no restore point.
6. Anything in `_preflight_locks` output the commander cannot explain.

### Rollback

```bash
az containerapp ingress traffic set -g rg-metocare-prod -n ca-metocare-backend \
  --revision-weight ca-metocare-backend--be-30a65ebc-1783997179=100
```

The run's step summary carries the same command with the revision confirmed at
dispatch time. **A data rollback is not an Alembic downgrade** — the
SEC-F11/j4_m10 migrations refuse to decrypt with a wrong key and abort rather
than destroy data. Data rollback is PITR, which discards writes since the restore
point, and is the incident owner's decision.

### Post-deploy authenticated flows

Only after the smoke is green. `/health` is `SELECT 1` and proves nothing about
encryption; these read `on_decrypt_failure="raise"` columns, which 500 under a
wrong key rather than degrading:

1. authentication — login, `/auth/me` returns the decrypted name
2. medication timeline — `medication_statements.raw_drug_name`
3. reminders — `notifications.title` / `body`
4. Meto conversation list — `meto_messages.content`
5. document candidate list — `extraction_candidates.fields_json`

**Use an existing production account. Do not create synthetic data in
production**, and note that `MCP_SYNTHETIC_ONLY_MODE` is deliberately **not** set
there.
