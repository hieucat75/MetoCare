# 2026-08-06 — staging PHI re-encryption: remediation and verification

**Outcome: MAIN HOTFIX MERGED — STAGING REMEDIATED AND VERIFIED. Production was
not deployed.**

The Alembic migration job encrypted staging's PHI with the development default
key committed to this repository. 103 rows across 8 columns. All 103 were
recoverable, all 103 were re-encrypted onto the real Key Vault key, and the
post-deploy crypto smoke now passes against them. No row was lost, no restore
was needed, and no plaintext PHI or key material appears in any artefact below.

---

## 1. What went wrong

`Settings.encryption_keys` (`backend/app/core/config.py:38`) has a hardcoded
default. The staging Alembic Container Apps Job in `ci.yml` was created with
only `MCP_DATABASE_URL` and `MCP_ENV`, so `_cipher()` fell back to that default.
The SEC-F11 / j4_m10 data migrations — which convert previously-plaintext PHI
columns to ciphertext, and ran for the first time in that deploy — encrypted
every affected row with a key anyone holding this repository can read. The
application then started with the real key and could not read any of it.

| | |
|---|---|
| Migration job execution | `caj-metocare-migrate-jr8pbza`, Succeeded `2026-08-06T03:46:30Z` |
| Revision created | `ca-metocare-backend--be-3fd813a3-1785988025`, `2026-08-06T03:47:34Z` |
| Crypto smoke execution | `caj-metocare-crypto-smoke-izdrob3`, **Failed** `2026-08-06T03:48:22Z` |
| Run | 31068881187 (build `3fd813a3`) |

**Staging served the broken build for fourteen minutes before the gate spoke**,
because `ci.yml` ran the smoke last while `azure-production.yml` ran it between
the migration and the first revision. That ordering gap is fixed below.

---

## 2. Code landed

| PR | Merge SHA | What |
|---|---|---|
| #137 | `7b619e079c78f6503d0dfddf2cc53149e06ecb55` | The P0 fix, plus four further P1s found in review |
| #138 | `38301e814c97aacda97665f085273031b911b281` | Unblocked the deploy; third-workflow key cleanup |

### Already in #137 before review — verified correct

* Both workflows pass `MCP_ENCRYPTION_KEYS=secretref:enc-keys` to the Alembic
  job, by secret reference, never as a literal.
* `_cipher()` refuses the committed default whenever `env` is outside
  `{dev, development, local, test, ci}`. Development keeps working with the
  default; breaking that would push people toward disabling the check.

The key does still appear in the **runner's** `az` argv (`--secrets
"enc-keys=$ENC_KEYS"`). That is unavoidable with the Azure CLI, is identical to
the pre-existing `db-url` handling, is `::add-mask::`ed, and the runner is
ephemeral. Not a new exposure class. The *job's* `--args` are `upgrade head`.

### Found in review and fixed

**P1 — the staging gate ran after the revision it guarded.** Now
`migrate → smoke → deploy`, matching production. Pinned by
`test_staging_runs_the_smoke_after_migration_and_before_any_revision`.

**P1 — staging polled `[0]` for its verdict and swallowed a failed delete.**
`[0]` has no ordering guarantee, so a stale `Succeeded` reads as this run's
verdict; and `|| true` on delete-before-create lets the create upsert onto a job
carrying the previous image and secrets, verifying the *old* key. Staging now
resolves and polls its own execution by name and treats a failed delete as fatal.

**P1 — the migration job held the PHI master key and nothing removed it.**
Giving it `enc-keys` (the fix for the P0) parked the database URL *and*
`MCP_ENCRYPTION_KEYS` in an unwatched Container Apps Job between deploys,
readable by anything with `Microsoft.App/jobs/listSecrets`. Both one-off jobs are
now deleted with `if: always()` in all three workflows. Generalised test: any
workflow that hands a job `enc-keys=` must also delete a job unconditionally.

**P1 — the smoke reported the damage as zero.** Its own output during the
incident:

```
{"entity":"meto_message.content","reason":"legacy_row_undecryptable","result":"fail"}   ×4
{"entities_checked":2,"failures":4,"legacy_rows_total":0}
```

Four columns unreadable and the row counter said **zero** — it only incremented
on success, and the raise on the first bad row jumped past it. The number an
on-call reads as blast radius went *down* as the blast radius went *up*.
`legacy_row_undecryptable` also conflated three states needing three different
responses: wrong key → re-encrypt, no known key → restore, never encrypted →
backfill.

`app/core/phi_keyscan.py` now classifies every row into one named bucket —
`plaintext_legacy_rows` / `ciphertext_target_key_rows` /
`ciphertext_source_key_rows` / `ciphertext_unreadable_rows` — all four emitted
every time, zeros included. Coverage went from 4 hardcoded hot paths to **all 31
encrypted columns** discovered from the ORM, each inside its own `SAVEPOINT`
(without one, a single missing table aborts the transaction and every later
column reports `InFailedSqlTransaction` — one absent table reading as total loss).

### Defects found and fixed along the way

* **`adherenceReconciled.test.tsx` never awaited `render`.** `render` is async in
  RNTL v14 (React 19 concurrent); the error pointed at the assertion line rather
  than the render. It passed for months because the un-awaited microtask usually
  wins the race — under a parallel cold-cache run it does not, which is the only
  condition CI runs in. **This failure skipped Deploy to Staging and blocked the
  remediation**, so it is a genuine finding, not incidental flake.
* **`azure-staging.yml` (manual dispatch)** already passed `enc-keys` to its
  Alembic job — the auto-deploy path was the only one missing it — but never
  deleted the job. Cleanup added.

---

## 3. State before remediation

| | |
|---|---|
| Active revision | `ca-metocare-backend--be-3fd813a3-1785988025` (unchanged; the gate blocked the new one) |
| `build_sha` / migration head | `3fd813a3` / `j3_m7_sched_lifecycle` (repo head matches) |
| Postgres | `psql-metocare-staging`, PG16, **Burstable B1ms**, Ready |
| Write freeze | `min-replicas` 1 → 0 (see caveat, §7) |

---

## 4. Backup and recovery proof

Azure **refuses** on-demand backups on Burstable servers. Verified against the
live server, not assumed:

```
(CustomerOnDemandBackupCannotBePerformedOnBurstableServer)
You cannot take customer on-demand backups on burstable servers.
```

Two mechanisms stand in for one:

**(a) PITR**, for catastrophic loss — earliest restorable
`2026-07-31T01:27:51Z`, retention 7 days. Covers the bad migration at
`2026-08-06T03:46:30Z`. Restores to a *new* server and rolls back the whole
database, so it is the sledgehammer, not the plan.

**(b) In-place ciphertext snapshot**, for the surgical undo. Every value the job
would touch, copied still-encrypted into `phi_reencrypt_backup__<table>__<column>`.

| Mode | Result |
|---|---|
| `snapshot` | **pass** — 359 rows / 31 columns; execution `caj-metocare-phi-reencrypt-2drdjzk`, `2026-08-06T08:45Z` |
| `verify-snapshot` | **pass — 359/359 verified** against the live columns *before* any write |

PHI-free per-column ciphertext checksums (`sha256(id‖ciphertext)` in id order,
first 32 hex): `users.full_name` 90 rows `5ad86a6cb30b01a66630a1871aa6d55f` ·
`patient_profiles.full_name` 82 `78122a281252962db56311486147872c` ·
`meto_messages.content` 70 `ae723c284fb51abae20daa88584bbf30` ·
`patient_profiles.dob` 21 `e04b1ef9e8501d56eeca82934eedf499` ·
`patient_profiles.known_conditions` 17 `5e40c7595b43e5038ac75fef82ad3005` ·
`patient_profiles.lifestyle_profile` 15 `3a8112281f23c84d06b9555b96191784` ·
`patient_profiles.family_history` 12 `3ef29eb5f8fa1d7046d2eae2e03e2792` ·
`patient_profiles.allergies` 11 `23b3077776363afdba67fc89d2ed128d` ·
`medication_statements.raw_drug_name` 6 `f9218a99f69f97d6fe428931803f5c93`.

`restore-snapshot` was executed and proven byte-identical during the local
PostgreSQL rehearsal (§6) — the undo is tested, not described.

---

## 5. Dry-run counts, and the repair

```
dry-run:    359 scanned · 103 source-key · 256 target-key · 0 unreadable · 0 plaintext
apply:      pass — 103 rewritten, 103 verified, 0 left unremediated, 0 columns unavailable
final-scan: pass — 359 target-key · 0 source-key · 0 unreadable · 0 plaintext
```

Per column, before:

| Column | scanned | needs source key | already OK |
|---|---:|---:|---:|
| `meto_messages.content` | 70 | **70** | 0 |
| `medication_statements.raw_dose` | 6 | **6** | 0 |
| `medication_statements.raw_drug_name` | 6 | **6** | 0 |
| `medication_statements.raw_frequency` | 6 | **6** | 0 |
| `extraction_candidates.fields_json` | 4 | **4** | 0 |
| `medication_statements.payload_snapshot` | 3 | **3** | 0 |
| `notifications.body` | 3 | **3** | 0 |
| `notifications.title` | 3 | **3** | 0 |
| `users.full_name` | 90 | **2** | 88 |
| 10 other columns | 162 | 0 | 162 |
| **Total** | **359** | **103** | **256** |

That set is exactly the columns `j4_m9`/`j4_m10` convert. `patient_profiles.*`
shows zero because an earlier migration had already encrypted it under the real
key — which is why the incident's smoke flagged four hot-path columns and no
profile data.

**`ciphertext_unreadable_rows: 0`** throughout: every damaged row was
recoverable, so no restore was required. Every rewrite was read back off the
database and re-resolved under the target key alone before its page committed.
No `row_changed_concurrently` occurred.

---

## 6. Rehearsed before staging was touched

The whole sequence was run first against a local PostgreSQL 16 database seeded to
reproduce the incident (120 `meto_messages`, 33 `notifications`, plus one
already-healthy row, one deliberately-corrupt row and one legacy-plaintext row):

* `apply` repaired 183/185 and refused to touch the corrupt row;
* re-running `apply` rewrote **0** — idempotent;
* `restore-snapshot` returned the database to byte-identical original state
  (scan after restore matched the pre-apply scan exactly: 181/2/2/2);
* repaired rows were read back **through the ORM's decrypting TypeDecorators**,
  and the corrupt row still raised `UndecryptablePHIError` — the job destroys no
  evidence;
* with the corrupt row removed, `final-scan` and the crypto smoke both passed.

---

## 7. Verification

| | |
|---|---|
| Staging deploy run | **31085106849 — success** |
| Build SHA | `38301e81` (`/api/v1/info`) |
| Migration head | `j3_m7_sched_lifecycle` (`/api/v1/info`; matches repo head) |
| Active revision | `ca-metocare-backend--be-38301e81-1786006899` |
| Image | `ghcr.io/hieucat75/metocare-backend:38301e81-1786006553` |

**Crypto smoke — pass:**

```
{"check":"crypto_smoke","result":"pass","entities_checked":33,
 "legacy_rows_total":78,"ciphertext_target_key_rows":78,
 "ciphertext_source_key_rows":0,"ciphertext_unreadable_rows":0,
 "plaintext_legacy_rows":0,"failures":0,"env":"staging","build_sha":"38301e81"}
```

Set against the incident's `{"entities_checked":2,"failures":4,"legacy_rows_total":0}`:
33 entities instead of 2, and a row count that now *means* something.

Both of the gate's states were observed on the real pipeline, in order: it
**failed before any revision existed** while the data was broken (run
31085106849, first attempt), and **passed and released the revision** once it was
repaired (same run, re-run). The reordering works in both directions, not just as
a blocker.

**Authenticated flows — 11/11 pass**, synthetic data only, account deleted at the
end. Every `on_decrypt_failure="raise"` column is exercised; under a wrong key
these do not degrade to blank, they raise and the endpoint 500s, so a 200 is the
proof.

| Flow | Result | Encrypted column proven |
|---|---|---|
| 1. authentication | PASS — register 201, login 200, `/auth/me` 200, full_name round-tripped | `users.full_name` |
| 1b. profile round-trip | PASS — allergies decrypted correctly | `patient_profiles.*` |
| 2a. medication create + read-back | PASS — 201 / 200 | `medication_statements.raw_drug_name` (raise) |
| 2b. schedule + reminders | PASS — schedule 200, `/reminders/due` 200 | `notifications.title`/`body` (raise) |
| 2c. adherence | PASS — 200 | — |
| 3. pause/resume lifecycle | PASS — 200 / 200 | — |
| 4. lab unit normalization | PASS — 201, Glucose 108 mg/dL | `lab_documents.raw_text` |
| 5. OCR candidate promotion | PASS — fixture 200, candidates 200 (n=2), confirm 200 | `extraction_candidates.fields_json` (raise) |
| 6. Meto consent + chat | PASS — consent 200, chat 200, conversations 200 | `meto_messages.content` (raise) |
| 7. marketplace booking + mock payment | PASS — book 201, pay 200, read-back 200 | `booking_health_snapshots.payload` (raise) |
| 8. account export + delete | PASS — export 200, delete 200 | every column the patient owns, in one pass |

### Caveat on the write freeze — stated plainly

Azure Container Apps rejects `--max-replicas 0`, so a hard stop was not
available, and disabling ingress risked leaving staging unreachable (the deploy
step's `az containerapp update` does not re-specify ingress). The freeze applied
was `min-replicas` 1 → 0, which removes the always-on replica but does not
prevent a request from waking one. **The actual protection was the job's
optimistic `UPDATE … WHERE <col> = :old`**, which aborts rather than clobbering a
value it did not resolve. It reported zero conflicts across all 103 rewrites, so
nothing raced it — but that guarantee came from the job's design, not from the
environment being sealed. Replicas restored to 1/1 afterwards.

---

## 8. Production

**Production was NOT deployed. No production workflow was dispatched.**

**Production PHI was never encrypted with the default key.** `j4_m9` and `j4_m10`
were added **2026-08-05**; production's only migration ran **2026-07-14** on build
`30a65ebc`, and no migration other than those two imports `app.core.crypto`. The
next production deploy is exactly when they would first run — which is what #137
makes safe.

Verified statically and against live Azure:

| Check | Status |
|---|---|
| Migration job receives the Key Vault secret | ✅ `MCP_ENCRYPTION_KEYS=secretref:enc-keys` (`azure-production.yml`) |
| Cannot fall back to the default key | ✅ `_cipher()` refuses it at `MCP_ENV=production`; the KV secret is **not** the repo default (compared without printing it) |
| Blocks on crypto smoke failure | ✅ two `exit 1` paths (explicit Failed, and no-verdict timeout) |
| Smoke runs before any revision | ✅ `migrate < smoke < deploy`, pinned by test |
| Main-only provenance | ✅ `github.ref == refs/heads/main` **and** `inputs.confirm == "PRODUCTION"` |
| Backup precondition | ✅ pre-migration backup step, fails closed |
| Cannot report healthy before the encrypted read succeeds | ✅ ordering + `if: always()` job cleanup |
| Rollback | ⚠️ documented manual path (ACA revision rollback / redeploy prior image). Pre-existing **PROD-F13** already tracks that the "auto-rollback" claim is unbacked without a readiness probe |

**Safe rehearsal.** The production path was *not* dispatched — the guards are the
thing under test, and a broken guard would have deployed production. Instead the
identical code path was exercised end-to-end against staging (§5–§7) with the
same job definitions, and the production-only properties are pinned by static
tests in `test_crypto_smoke_contract.py`.

### Open items for the owner

1. **Production `caj-metocare-migrate` still exists**, created 2026-07-14 with the
   pre-#137 definition, holding the production database URL as a job secret. The
   new cleanup removes it on the next deploy; deleting it sooner is a production
   infra action and was not taken.
2. **`azure-staging.yml` runs no crypto smoke at all.** A manual staging deploy
   bypasses the gate entirely. The auto-deploy path gates correctly, so a merge
   to main is covered; a manual dispatch is not.
3. **`caj-metocare-pilot-seed` in STAGING holds `enc-keys`, `sec-key`, `pat-pw`
   and `doc-pw`** as job secrets. Created ad-hoc on 2026-08-03 to run
   `seed_pilot_journeys.py`; nothing in the repository creates it, so nothing
   will ever clean it up. This is a live instance of the exact exposure the P1
   above fixed in the workflows — the staging PHI master key *and* the JWT
   signing key, sitting in an unwatched resource. It was **not** deleted: it is
   someone's deliberate one-off and removing it unasked could break a workflow,
   the exposure is pre-existing and unchanged by this remediation, and item 4
   below already treats staging PHI as disclosed. One command when you want it:

   ```bash
   az containerapp job delete -g rg-metocare-staging -n caj-metocare-pilot-seed --yes
   ```

   Note the generalised cleanup test only scans `.github/workflows/*.yml`, so a
   job created by hand is outside what any test can catch.
4. **Staging PHI should be treated as disclosed** for the period it was at rest
   under the repository default (2026-08-06 03:46Z → 08:51Z), regardless of this
   repair. Rotating the staging key is an owner decision.
5. **Production deploy approval.** Nothing technical now blocks it. The remaining
   gate is procedural: a human dispatching `azure-production.yml` from `main`
   with `confirm=PRODUCTION`, having accepted items 1 and 4.

---

## Artefacts

* Runbook: `docs/runbooks/staging-phi-reencryption.md`
* Job: `backend/scripts/reencrypt_phi.py`, `backend/run_reencrypt_phi.py`,
  `scripts/staging_reencrypt_job.sh`
* Classification: `backend/app/core/phi_keyscan.py`
* Tests: `test_phi_keyscan.py`, `test_reencrypt_phi_contract.py`,
  `test_migration_phi_key.py`, `test_crypto_smoke_contract.py`,
  `integration/test_crypto_smoke_postgres.py`

No plaintext PHI, credential or key material appears in this document or in any
job output it quotes. Rows are referenced only as `sha256(table‖id)[:16]`;
checksums are over ciphertext.
