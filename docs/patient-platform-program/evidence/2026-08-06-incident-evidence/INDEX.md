# Evidence index — 2026-08-06 staging PHI encryption incident

**Handling: RESTRICTED.** Incident and legal/privacy review only. Do not
redistribute. Contains no PHI and no secrets; identities are pseudonymised.

**Do not rewrite Git history, purge logs or delete anything referenced here
without the written direction of the appointed legal/privacy incident owner.**

## Integrity

`sha256.txt` carries a SHA-256 for every artefact in this directory. Verify:

```bash
cd docs/patient-platform-program/evidence/2026-08-06-incident-evidence
shasum -a 256 -c sha256.txt          # macOS
sha256sum -c sha256.txt              # Linux
```

The artefacts are committed to Git, so the commit hash is a second, independent
timestamped seal. Both would have to be forged together.

## Pseudonymisation

Every `caller`, `principalName`, `principalId`, `signInName` and any address in
free text was replaced with `principal:<sha256[:12]>` before these files were
written. The mapping is **stable** — one identity produces the same token across
every file, so activity can still be correlated — and **not reversible from
these files**. The underlying identities remain available in Azure to anyone
with the access to read them; nothing here destroys evidence, it avoids
duplicating identity data into a public repository.

## Artefacts

| File | What it is | Why it matters |
|---|---|---|
| `activity-log-staging.json` | Azure Activity Log, `rg-metocare-staging`, 2026-08-05 → 08-07 | Control-plane record of the window: job create/start/delete, secret operations, scale changes |
| `activity-log-prod.json` | Azure Activity Log, `rg-metocare-prod`, 2026-07-01 → 08-07 | **Shows production was not deployed**, and records the stale migration job's deletion |
| `role-assignments-staging.json` | RBAC on the staging RG | Who could reach the data and the keys — 2 principals, see pack §5 |
| `role-assignments-prod.json` | RBAC on the production RG | Same, and shows the staging-named SP holds production scope |
| `firewall-staging.json` | Postgres firewall rules | Establishes the database was **not** internet-reachable during the window |
| `keyvault-diagnostics-staging.json` | Key Vault diagnostic settings | **Empty (`[]`).** Preserved *because* it is empty — see below |
| `workflow-runs.json` | Last 30 `main` workflow runs | Deploy timeline: failing gate, remediation, green re-run |
| `commit-history.txt` | Commits since 2026-08-05 | Code timeline, including the fix and the public-repository history |
| `repo-visibility.json` | Repository visibility | **`PUBLIC`** — the fact that makes the committed key a real disclosure rather than an internal one |

## The most important artefact is the empty one

`keyvault-diagnostics-staging.json` is `[]`. **Key Vault has no diagnostic
settings, so no Key Vault access logs exist**, and there is therefore **no way
to determine whether anyone read `mcp-encryption-keys`, `mcp-secret-key` or the
job secrets** during or before the incident window.

It is preserved as evidence of an *absence of evidence*. In the incident pack it
is the reason the access findings say "no indication of access" rather than "no
access occurred" — different claims, and only one of them is supportable here.

Enabling that logging is a governance action for the owner
(`docs/runbooks/environment-and-access-governance.md`, G7). It cannot be applied
retroactively: no configuration now will produce logs for 2026-08-06.

## Known gaps in this collection

Recorded so nobody later mistakes the collection for exhaustive.

| Gap | Consequence |
|---|---|
| No Key Vault access logs | Cannot establish whether the keys were read |
| No Postgres audit extension (`pgaudit`) | Cannot establish which rows were read, by whom, or whether the affected rows were touched at all during the window |
| No application-level read audit for PHI columns | `AuditLog` records writes and auth events, not reads |
| Activity Log retention is 90 days | Everything here expires ~2026-11-04 unless exported. **If the legal timeline may exceed that, export before then.** |
| Container Apps job execution history | The jobs were deleted as containment; their executions went with them. The Activity Log retains create/start/delete, which is what the timeline needs |
| GitHub audit log | Not collected — requires an organisation plan; this is a user-owned repository |

## Chain of custody

| When | What | By |
|---|---|---|
| 2026-08-06 | Collected and pseudonymised during the remediation session, via `az` / `gh` / `git` | Single operator, automated commands |
| 2026-08-06 | Committed to `main`; digests recorded in `sha256.txt` | — |

Any later addition must append to `sha256.txt` and note the reason here, rather
than replacing an existing artefact.
