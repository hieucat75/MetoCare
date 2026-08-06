# Incident record — staging PHI encrypted with the repository's default key

**Status: TECHNICALLY REMEDIATED — DISPOSITION OPEN.** The data is repaired and
verified; the breach assessment is not done. Production never affected.
**Severity: HIGH (confidentiality, staging).** Not a production breach, but
**a confirmed disclosure of real users' PHI** — see §4.

Written to be read by someone who was not here. No PHI, no secrets and no key
material appear below; rows are referenced elsewhere only as
`sha256(table‖id)[:16]`.

---

## 1. Timeline (UTC, 2026-08-06)

| Time | Event |
|---|---|
| `03:35` | Run 31068881187 starts on `main` @ `3fd813a3` |
| `03:46:30` | Alembic job `caj-metocare-migrate-jr8pbza` **Succeeds**. `j4_m9`/`j4_m10` run for the first time and encrypt 103 PHI values with the repository's committed default key |
| `03:47:34` | Revision `be-3fd813a3-1785988025` created and takes traffic — **encrypted reads on the affected columns are now broken for every user** |
| `03:48:22` | Crypto smoke `caj-metocare-crypto-smoke-izdrob3` **Fails**. Correct detection, but **14 min after the bad revision went live**, because the staging gate ran last |
| `≈04:00` | Detection acknowledged; remediation begins. No production deploy attempted at any point |
| `08:31` | PR #137 merged (`7b619e07`) — pipeline fix + fail-loud refusal |
| `08:44–08:46` | Ciphertext snapshot taken and verified (359/359) |
| `08:49` | Dry-run: 103 rows require the default key; **0 unreadable** |
| `08:51` | `apply`: 103 rewritten, 103 verified. **Exposure window ends** |
| `08:53` | `final-scan`: 0 default-key, 0 unreadable, 0 plaintext |
| `09:02` | Deploy re-run: crypto smoke **passes**, revision `be-38301e81-1786006899` released |
| `09:2x` | 11/11 authenticated flows pass |
| `10:0x` | Live wrong-key smoke **Fails** as designed (three-state proof closed) |
| `10:3x` | Ad-hoc job `caj-metocare-pilot-seed` deleted; pilot credentials rotated |

**Exposure window: `03:46:30Z` → `08:51Z` — 5 h 05 m.**

## 2. Affected rows

103 values across 8 columns, out of 359 encrypted values scanned in 31 columns.

| Column | affected |
|---|---:|
| `meto_messages.content` | 70 |
| `medication_statements.raw_dose` | 6 |
| `medication_statements.raw_drug_name` | 6 |
| `medication_statements.raw_frequency` | 6 |
| `extraction_candidates.fields_json` | 4 |
| `medication_statements.payload_snapshot` | 3 |
| `notifications.body` | 3 |
| `notifications.title` | 3 |
| `users.full_name` | 2 |

Exactly the set `j4_m9`/`j4_m10` convert. `patient_profiles.*` was unaffected
(0 of 162) because an earlier migration had already encrypted it under the real
key — which is why the smoke flagged four hot-path columns and no profile data.

**0 rows were unreadable at any point**, so nothing was lost and no restore was
needed.

## 3. Key exposure mechanism

`Settings.encryption_keys` (`backend/app/core/config.py`) carries a hardcoded
default so the stack runs with zero configuration in development. The staging
Alembic Container Apps Job in `ci.yml` was created with only `MCP_DATABASE_URL`
and `MCP_ENV`, so `_cipher()` fell back to that default and the data migrations
encrypted with it. The application then started with the real Key Vault key and
could not read what the migration had written.

The failure was **silent by construction**: a missing key did not raise, it
substituted a working one. `warn_if_insecure` already knew about this key, but
it only *warned*, only when `is_prod`, and only at application startup — so it
could not see a migration job in staging.

**The real staging key was never disclosed.** The exposure is that 103 PHI
values sat at rest under a key published in this repository — i.e. for
confidentiality purposes, unencrypted — for 5 h 05 m.

## 4. Was the data synthetic or real?

**CONFIRMED REAL DATA PRESENT.** Determined 2026-08-06 by
`backend/scripts/provenance_report.py`, read-only, emitting only counts — no
address, name or identifier was read out of the database.

| Signal | Finding |
|---|---|
| Address markers | 95 users: **77 non-synthetic**, 18 synthetic (reserved-domain or seed-prefix) |
| Self-registration audit | **90 accounts have a `register` event** — created through the public API, not seeded. 75 of those have deliverable addresses |
| Creation clustering | 93 distinct creation seconds spread over `2026-06-20` → `2026-08-06`. Organic arrival, not a seeding burst |
| **Ownership of affected columns** | **160 of 205 rows examined belong to non-synthetic accounts** |

Per column, rows owned by a non-synthetic account:
`meto_messages.content` **68 of 70** · `users.full_name` **77 of 91** ·
`medication_statements.raw_dose` 4 of 6 · `raw_frequency` 4 of 6 ·
`raw_drug_name` 4 of 13 · `payload_snapshot` 3 of 3 ·
`extraction_candidates.fields_json` 0 of 10 · `notifications.title`/`body` 0 of 3.

(205 > 103 because the scan ran after remediation and after verification traffic.
The overlap is nonetheless decisive: all 70 `meto_messages.content` rows were
affected, and 68 of them belong to real accounts.)

**And the repository is PUBLIC** — `hieucat75/MetoCare`, visibility `PUBLIC`,
0 forks. The key in `backend/app/core/config.py` was therefore genuinely public
for the whole window, not merely known to collaborators.

**Disposition: a confirmed disclosure of real users' PHI**, not an engineering
defect with synthetic data. What limits it is reachability, not encryption: the
database was never internet-facing (§5), so reading these rows still required
database access. The correct characterisation is *anyone who obtained the
database contents during the window could read the PHI without needing the real
key* — the encryption provided no confidentiality for 5 h 05 m.

**Owner obligation:** perform the breach assessment and decide on notification.
See §12.

## 5. Access review

**Database network reachability** — `psql-metocare-staging`,
`publicNetworkAccess: Enabled`, admitted by three firewall rules only:

| Rule | Scope |
|---|---|
| `AllowAzureServices` | Azure service traffic |
| `FirewallIPAddress_2026-6-20_7-51-3` | one operator IP |
| `rehearsal-tmp` | one operator IP |

Not reachable from the open internet, and reading rows still required the
database password.

**Azure control-plane principals** holding `Microsoft.App/jobs/listSecrets` and
Key Vault access over the staging resource group:

| Principal type | Role | Scope | Notes |
|---|---|---|---|
| User | Owner ×2 | subscription | **one identity, two assignments** — not two people |
| ServicePrincipal | Contributor | `rg-metocare-staging` + `rg-metocare-prod` | `MetoCare-GitHub-Staging`, created 2026-06-20 |

**Two distinct principals, not three** — an earlier draft of this record
miscounted duplicate role assignments as separate owners.

The service principal holds **no stored client secret** (`passwordCredentials: 0`)
and authenticates by OIDC federated credential, subject-scoped to
`repo:hieucat75/MetoCare:environment:azure-staging`,
`:environment:azure-production` and `:ref:refs/heads/main`. It also holds
`Key Vault Secrets User` on **both** vaults and Contributor on **both** resource
groups, despite its name — so one identity spans both environments, and the
separation between them rests entirely on GitHub environment protection, which
is currently **not configured** (see §12).

**No indication of access by anyone else and no indication of exfiltration.**
Staging access logs were not reviewed line by line, so this is "no indication
of", not "proof of absence".

## 6. Containment

* The crypto smoke detected it automatically on its first ever real execution
  and **failed the deploy** — the pipeline stopped itself.
* Staging writes were reduced (`min-replicas` 1 → 0) before any repair. This was
  a **soft** freeze: Azure Container Apps rejects `--max-replicas 0`, and
  disabling ingress risked leaving staging unreachable. What actually protected
  the data was the re-encryption job's optimistic `UPDATE … WHERE <col> = :old`,
  which aborts rather than clobbering a value it did not resolve; it reported
  zero conflicts across all 103 rewrites.
* No production deploy was attempted.

## 7. Remediation

**Pipeline** (PR #137 `7b619e07`, PR #138 `38301e81`, and the pre-deploy
hardening change):

1. All three workflows hand `MCP_ENCRYPTION_KEYS` to the Alembic job by secret
   reference.
2. `_cipher()` refuses the committed default outside
   `{dev, development, local, test, ci}` — at the single point every encrypt and
   decrypt passes through, so no future job can reintroduce this by forgetting
   an environment variable.
3. Gate ordering fixed to `migration → smoke → rollout` on **every** deploy
   path. `azure-staging.yml` had no smoke at all and now has one.
4. Both key-bearing one-off jobs are deleted `if: always()`.
5. The smoke's metrics were rewritten (§8).

**Data**: `snapshot` → `verify-snapshot` (359/359) → `dry-run` → `apply`
(103 rewritten, 103 verified) → `final-scan` (0/0/0). Every rewrite was read
back and re-resolved under the target key before its page committed. Unreadable
rows would never have been rewritten — there were none.

**Credentials**: `caj-metocare-pilot-seed`, an ad-hoc job holding `enc-keys`,
`sec-key` and two account passwords retrievable via `listSecrets`, was deleted
and both pilot passwords rotated to values persisted nowhere.

## 8. Verification

| Check | Result |
|---|---|
| `final-scan` | pass — 374 target-key, 0 source-key, 0 unreadable, 0 plaintext |
| Crypto smoke (staging) | pass — 33 entities, 78 rows, 0 failures |
| Wrong-key smoke (live) | **Failed** as required — 79 unreadable, 19 failures |
| Deploy runs | 31085106849, 31088898130 — both success, gate green |
| Authenticated flows | 11/11 pass, synthetic data, account deleted |
| Build / migration head | `e3289393` / `j3_m7_sched_lifecycle` |

The three-state proof — correct key passes, wrong key fails, restored key passes
— was closed on the live environment, not only in tests.

**The metric that misreported it.** The smoke's own output during the incident:

```
{"entities_checked":2,"failures":4,"legacy_rows_total":0}
```

Four columns unreadable and the row counter read **zero**: it only incremented
on success, and the raise on the first bad row jumped past it. The number an
on-call reads as blast radius fell as the blast radius rose. Rows are now
classified into `plaintext_legacy_rows` / `ciphertext_target_key_rows` /
`ciphertext_source_key_rows` / `ciphertext_unreadable_rows`, all four always
emitted, across all 31 encrypted columns. Demonstrated live: the wrong-key run
above reported **79**, where the old code would have reported 0.

## 9. Residual risk

| Risk | Assessment |
|---|---|
| 103 PHI values at rest under a public key for 5 h 05 m | **Real but bounded.** Database not internet-reachable; a password was still required; control-plane access limited to 2 owners + CI. Materiality depends on §4. |
| Real staging encryption key disclosed | **No.** Never written anywhere public; `listSecrets` reachability limited to already-trusted principals. |
| Production affected | **No.** §10. |
| Data loss or corruption | **None.** 0 unreadable throughout; snapshot retained. |
| Recurrence via the same path | **Closed** — fail-loud refusal plus gate ordering on all three workflows, with static tests. |
| Recurrence via a *new* workflow | **Covered** — the bypass and cleanup tests derive their targets from the workflow tree, not from a list. |
| Recurrence via an ad-hoc job | **Not covered by any test.** `caj-metocare-pilot-seed` was created by hand; nothing in the repository creates or cleans up such jobs. |
| `rehearsal-tmp` firewall rule | Minor. A single-IP temporary rule that outlived its purpose. Left in place — infrastructure change outside this remediation. |

## 10. Production

Never affected. `j4_m9`/`j4_m10` were added **2026-08-05**; production's only
migration ran **2026-07-14** on build `30a65ebc`, and no migration other than
those two imports `app.core.crypto`. Production's active revision is still
`be-30a65ebc-1783997179` and the last `azure-production.yml` run was 2026-07-14.
Production was **not deployed** during this incident or its remediation.

## 11. Is staging PHI key rotation required?

**No — not required, and not recommended as a priority.**

The reasoning matters more than the verdict:

* The incident did **not** expose the real staging key. It used a *different*,
  public key instead. Rotating the real key does nothing about that.
* The 103 affected rows are now encrypted under the real key, which was never
  public. Rotating would re-encrypt correct data for no confidentiality gain.
* The real key **was** retrievable via `listSecrets` from unwatched jobs — but
  only by two subscription Owners and the CI service principal, all of whom can
  read Key Vault directly anyway. That adds no principal to the trusted set, and
  those jobs are now deleted and auto-cleaned.

**Rotate if, and only if,** the owner concludes any principal in §5 should not
have been trusted with staging PHI. In that case rotate `mcp-encryption-keys`
*and* `mcp-secret-key` (the JWT signing key sat in the same job), then re-run
the re-encryption job with the old key as `REENCRYPT_SOURCE_KEYS`.

This verdict is unchanged by §4 turning out to be real data. Rotation addresses
key compromise; this was not one. The disclosure is addressed by the breach
assessment, not by a new key.

Required regardless: the 103 values **are** disclosed for the window. §4 is no
longer conditional.

## 12. Owner actions

**Resolved during the precheck — no longer open:**

* Provenance (§4): **CONFIRMED REAL DATA PRESENT.**
* Principal count (§5): two principals, not three.
* All ad-hoc secret-bearing jobs: **deleted.** `caj-metocare-pilot-seed`
  (`enc-keys`, `sec-key`, two passwords — both rotated),
  `caj-metocare-seed-demo` and `caj-seed-doctor` (`db-url`, 0 executions each),
  and the stale production `caj-metocare-migrate`. **Zero Container Apps Jobs
  now exist in any resource group in the subscription.**

**Open, and requiring the owner:**

1. **Breach assessment for the 103 values.** Real users' PHI — Meto
   conversation contents and names — was encrypted with a key public on GitHub
   for 5 h 05 m. Decide notification under the applicable regime. This is the
   one genuinely unresolved item.
2. **Should staging hold real user data at all?** 90 accounts self-registered
   through a publicly reachable staging ingress with open registration. Whatever
   the answer, it is a decision that has not been made — the data arrived
   because nothing stopped it.
3. **Environment separation.** One service principal
   (`MetoCare-GitHub-Staging`) holds Contributor and Key Vault Secrets User on
   **both** resource groups, and neither the `azure-production` nor the
   `azure-staging` GitHub environment has protection rules or a branch policy.
   Production dispatch is gated only by the in-workflow `main`-only and
   `confirm=PRODUCTION` checks — real, tested, but not a second pair of eyes.
4. **`rehearsal-tmp` firewall rule** on the staging server — a single-IP
   temporary rule that outlived its purpose.

---

*Cross-references: `2026-08-06-main-merge-staging.md` (the merge that caused it),
`2026-08-06-staging-phi-remediation.md` (full technical repair record),
`docs/runbooks/staging-phi-reencryption.md` (the runbook).*
