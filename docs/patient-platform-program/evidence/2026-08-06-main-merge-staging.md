# Main merge + staging verification — 2026-08-06

## Merge

| item | value |
|---|---|
| Base before merge | `99a36168a8bf345826c4833d08da8a07cc71d39e` (verified unmoved immediately before merging) |
| Candidate | `3aa5595963b6cc6838e84afb6eb77768fce18d32` |
| Tag | `rc-j3m7-lifecycle-3aa5595` → dereferences to `3aa5595` |
| Merge commit | **`3fd813a33873188790a30e1347c8ee2a7c398e41`** |
| Parents | `99a3616` (main), `3aa5595` (candidate) — true `--no-ff`, not squashed or rebased |
| Merged tree | byte-identical to the candidate (`git diff 3aa5595 3fd813a` empty) |

## CI — run [31068881187](https://github.com/hieucat75/MetoCare/actions/runs/31068881187), head SHA `3fd813a`

| job | result |
|---|---|
| Backend Tests | success |
| Backend PostgreSQL Integration Tests | success |
| Frontend Tests (incl. the two new `tsc` gates) | success |
| Mobile Tests | success |
| Meto AI Deployment Gate | success |
| Deploy to Staging | **failure** — at `Post-deploy PHI crypto smoke` |
| Deploy Blocked - Gate Failed | skipped (the test gate passed) |

Every step of `Deploy to Staging` before the crypto smoke succeeded: image build,
Key Vault read, pre-migration audit, pre-migration backup, Alembic migration,
backend + frontend deploy, both health gates, and the OpenAPI-driven smoke suite.

## Deployed staging build

`GET /api/v1/info`:

```
env               = staging
build_sha         = 3fd813a3      ← the exact merge commit
build_time        = 2026-08-06T03:47:05Z
migration_version = j3_m7_sched_lifecycle   ← single Alembic head, applied
```

`GET /api/v1/health` → 200. Frontend `/` → 200.

## Crypto smoke — FAILED (first ever real execution)

Container Apps job `caj-metocare-crypto-smoke`, execution
`caj-metocare-crypto-smoke-izdrob3`, status `Failed`. Its own output, from the
environment's Log Analytics workspace:

```json
{"build_sha":"3fd813a3","entity":"meto_message.content","reason":"legacy_row_undecryptable","result":"fail"}
{"build_sha":"3fd813a3","entity":"extraction_candidate.fields_json","reason":"legacy_row_undecryptable","result":"fail"}
{"build_sha":"3fd813a3","entity":"medication_statement.raw_drug_name","reason":"legacy_row_undecryptable","result":"fail"}
{"build_sha":"3fd813a3","entity":"notification.body","reason":"legacy_row_undecryptable","result":"fail"}
{"entities_checked":2,"failures":4,"legacy_rows_total":0,"legacy_rows_verified":{},"result":"fail"}
```

`entities_checked: 2` are the two round-trips, and both PASSED — the deployed key
encrypts and decrypts its own writes. Every PRE-EXISTING row failed, including in
`meto_messages.content`, the same column whose round-trip succeeded. That
isolates the fault to rows written earlier.

### Root cause

`Settings.encryption_keys` (`backend/app/core/config.py:38`) carries a hardcoded
default committed to this repository. The Alembic migration job was created with

```
--env-vars "MCP_DATABASE_URL=secretref:db-url" "MCP_ENV=staging"
```

and no `MCP_ENCRYPTION_KEYS`, so `_cipher()` fell back to that default. The
SEC-F11 (`j4_m9`) and P1-5 (`j4_m10`) data migrations — which convert
previously-plaintext PHI columns to ciphertext, and ran for the first time in
this deploy — encrypted all of staging's Meto messages, OCR candidate fields,
medication statements and notification bodies with a **public** key. The
application then started with the real Key Vault key and could not read them.

`warn_if_insecure` already knew about this key, but it only WARNS, only when
`is_prod`, and only at application startup — so it could not see a migration job
running in staging.

`azure-production.yml`'s migration job carried the **identical** definition, so
the next production deploy would have done this to real patients' records.

### Repair

PR **#137**, branch `fix/migration-phi-key-p0`, commit `2a38a16`:

* both workflows pass `enc-keys=$ENC_KEYS` / `MCP_ENCRYPTION_KEYS=secretref:enc-keys`
  to the Alembic job, by secret reference;
* `_cipher()` refuses the committed default whenever `env` is outside
  `{dev, development, local, test, ci}` — at the one point every encrypt and
  decrypt passes through, so a future job cannot reintroduce it by forgetting an
  environment variable;
* +15 tests. Backend 4231 pass / 0 fail, ruff clean.

`main` was not rewritten or force-pushed.

## Flow verification NOT performed

Authentication, medication schedule/adherence, pause/resume lifecycle, lab
normalization, OCR promotion, Meto and marketplace were **not** exercised.

Two reasons, both deliberate:

1. Four of those flows read the columns the smoke just proved unreadable
   (`meto_messages.content` → Meto; `extraction_candidates.fields_json` → OCR
   promotion; `medication_statements.raw_drug_name` → medication timeline;
   `notifications.body` → reminders). All four are `on_decrypt_failure="raise"`,
   so they raise on pre-existing rows. Running them would re-derive what the
   smoke already established.
2. Exercising them requires authenticating and writing new records into a staging
   database whose PHI encryption is in a known-broken state. Adding data there
   before the key question is resolved would make the eventual remediation
   harder.

## Residual — owner decisions

* **Staging data.** Rows already encrypted with the committed default key remain
  unreadable. This is data remediation, not a code change: either add the default
  key as a decrypt-only secondary in `mcp-encryption-keys` and re-encrypt, or
  discard the affected demo rows. Note that once PR #137 lands, `_cipher()`
  refuses a keyring containing the default even as a secondary — so a re-encrypt
  job needs the guard's dev-env allowance or a deliberate, reviewed exception.
* **Production deploy.** Must not run until #137 lands. Its migration job has the
  same defect today.
* The production crypto smoke still has never executed against real Azure.
