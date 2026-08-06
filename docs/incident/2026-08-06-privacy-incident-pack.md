# LEGAL REVIEW REQUIRED — NOT FOR DISTRIBUTION

# Privacy incident pack — staging PHI encrypted with a publicly published key

**2026-08-06 · MetoCare · staging environment · production not affected**

Prepared by engineering for legal/privacy review. **No notification has been
sent. No notification decision has been made.** The drafts in §14 and §15 exist
so a decision can be acted on quickly if the reviewer determines one is owed;
they are not approved text and must not be sent as written.

Contains no PHI and no secrets. Evidence:
`docs/patient-platform-program/evidence/2026-08-06-incident-evidence/`
(`INDEX.md`, SHA-256 sealed, identities pseudonymised).

---

## 1. Confirmed facts

1. Between **2026-08-06 03:46:30Z and 08:51Z (5 h 05 m)**, 103 PHI values in the
   MetoCare **staging** database were encrypted with a Fernet key committed to
   the project's **public** GitHub repository.
2. For those values, over that window, the encryption provided **no
   confidentiality** against anyone who both held the repository (i.e. anyone)
   and could read the database contents.
3. The affected data includes **real users' data**, established by a read-only
   forensic report that classified and counted without reading identifiers:
   160 of 205 rows in the affected columns belong to accounts whose address is
   not a reserved, undeliverable test domain.
4. **90 accounts** carry a self-registration audit event — created through the
   public API, not seeded. 77 of 95 accounts have deliverable addresses.
5. The repository `hieucat75/MetoCare` is **PUBLIC**, 0 forks.
6. The staging database was **not reachable from the open internet** during the
   window: three firewall rules only (Azure services + two operator IPs), and a
   password was still required.
7. The defect was **detected automatically** by the project's own post-deploy
   crypto smoke, on its first ever real execution, 1 m 52 s after the migration.
8. All 103 values were **recoverable** — 0 unreadable at any point — and were
   re-encrypted onto the correct key by 08:51Z, verified row by row.
9. **Production was never affected and has not been deployed.** The migrations
   that caused this have never run there.

## 2. Unknown facts

Stated plainly, because the gaps bound what can honestly be claimed.

| Unknown | Why it cannot be answered | Consequence |
|---|---|---|
| **Whether anyone read the affected rows** | No Postgres audit extension; no application read-audit for PHI columns | Cannot assert "no unauthorised access occurred" — only "no indication of it" |
| **Whether anyone read the encryption keys** | **Key Vault has no diagnostic settings — no access logs exist at all** | Same. Preserved as evidence (`keyvault-diagnostics-staging.json` is `[]`) |
| **Whether any staging user believes they are using a real product** | Not determinable without contacting them | Bears on whether notification is owed, and to whom |
| **Exact distinct data-subject count** | Requires joining rows to identities, deliberately avoided | Estimated §4; producible exactly on instruction |
| **Whether the public key was noticed or used by a third party** | No repository traffic analytics; 0 forks is weak evidence | Unknowable |

## 3. Affected data categories

| Column | Category | Sensitivity |
|---|---|---|
| `meto_messages.content` (70 rows, 68 real-owned) | Free-text conversation with the AI health assistant | **Highest.** Unbounded — whatever a user chose to type about their health |
| `users.full_name` (2 affected; 77 of 91 real-owned overall) | Identity | Directly identifying |
| `medication_statements.raw_drug_name` / `raw_dose` / `raw_frequency` / `payload_snapshot` (21 rows) | Prescribed medication, dose, frequency | **Health data.** Medication implies diagnosis |
| `notifications.title` / `body` (6 rows) | Medication reminder text | Health data; names the drug |
| `extraction_candidates.fields_json` (4 rows) | OCR output from uploaded prescriptions / lab reports | Health data |

Under a GDPR-style analysis these are **special category data** (Art. 9) combined
with direct identifiers. Vietnam's PDPD (Decree 13/2023) treats health
information as **sensitive personal data**. Which regime applies is for the
reviewer; both are named because the deployment region is Southeast Asia and the
user base is Vietnamese.

## 4. Estimated number of data subjects

**Fewer than 95; most likely 20–77.**

- 95 accounts exist; 77 have deliverable addresses.
- 160 of 205 rows in the affected columns are owned by those accounts, but rows
  cluster per user — 70 Meto messages may be a handful of conversations.
- A precise distinct-subject count was **not** produced: it requires joining
  affected rows to identities. That is deliberate restraint, not an obstacle —
  **it can be produced in minutes on legal instruction**, and should be if the
  notification decision turns on the number.

## 5. Exposure window

| | |
|---|---|
| Start | `2026-08-06T03:46:30Z` — migration completes, having written with the wrong key |
| Detection | `2026-08-06T03:48:22Z` — crypto smoke fails (**1 m 52 s**) |
| End | `2026-08-06T08:51Z` — all 103 values re-encrypted and verified |
| **Duration** | **5 h 05 m** |

The gap between detection and closure is remediation time, not ignorance time.
The defect was known from 03:48Z.

## 6. Cryptographic control failure

`Settings.encryption_keys` carries a hardcoded development default so the stack
runs unconfigured locally. The staging Alembic migration job was created with
only `MCP_DATABASE_URL` and `MCP_ENV`, so the cipher **silently fell back to that
default** instead of failing. Two data migrations then converted
previously-plaintext PHI columns to ciphertext using it.

The failure mode is the point: **a missing key did not raise, it substituted a
working one.** An existing warning knew about this key, but it only warned, only
in production, and only at application startup — so it could not see a migration
job in staging.

Now the cipher **refuses** the committed default outside development, at the one
point every encrypt and decrypt passes through; all three deploy workflows pass
the real key by secret reference; and the crypto smoke gate runs on every deploy
path before any revision goes live.

## 7. Database reachability

`psql-metocare-staging`: public network access enabled but firewall-restricted to
Azure services and two single operator IPs. Not reachable from the open internet.
Reading the affected rows required **both** the public key (which anyone had)
**and** database access (restricted and password-gated).

This is the single most mitigating fact, and it is why §1.2 is phrased as loss of
confidentiality *against someone who could already reach the data*, rather than a
public data dump.

## 8. Principals with possible access

Two distinct Azure principals — an earlier count of three was wrong; one identity
held two role assignments:

| Principal | Role | Notes |
|---|---|---|
| One human owner | Owner (subscription) | Can read Key Vault directly regardless |
| `MetoCare-GitHub-Staging` (service principal) | Contributor + Key Vault Secrets User on **both** staging and production | **No stored client secret**; OIDC federated credentials scoped to three GitHub subjects |

Also relevant: four one-off Container Apps Jobs held secrets and have been
deleted. One (`caj-metocare-pilot-seed`, created 2026-08-03) held the staging
encryption key, the JWT signing key and two account passwords, retrievable by any
principal with `listSecrets`. Both passwords were still valid; both are rotated.

## 9. Evidence of access, or its absence

**There is no evidence of unauthorised access. There is also no evidence that
could have shown it.** Different statements, and the distinction is load-bearing:

- Key Vault: **no diagnostic settings, no logs** — cannot say whether keys were read.
- Database: no `pgaudit`, no application read-audit — cannot say whether rows were read.
- Azure Activity Log: control-plane only; shows no anomalous administrative
  activity in the window.
- Repository: public, 0 forks. Weak negative evidence at best.

**A reviewer should not be told "we verified no access occurred."** The
supportable statement is: *we have no indication of access, and we lacked the
instrumentation that would have detected it.*

## 10. Containment

| Action | Status |
|---|---|
| Deploy blocked automatically by the crypto gate | Automatic, 03:48Z |
| Staging writes reduced before repair | Soft — Azure rejects a hard zero-replica stop. The repair job's optimistic locking was the real protection: 0 conflicts across 103 rewrites |
| **Staging made synthetic-only** | Registration **and login** now refuse any non-reserved-domain identity; outbound push/email suppressed; warning banner surfaced. This locks the 90 real accounts out of further use |
| All secret-bearing one-off jobs deleted | 4 jobs; **zero Container Apps Jobs now exist anywhere in the subscription** |
| Pilot credentials rotated | Both were still valid; old credentials now return 401 |
| Affected records retained | **Not deleted, not anonymised** — pending the evidence-retention decision (§17) |

## 11. Remediation

**Pipeline.** Key passed by secret reference on all three deploy paths; cipher
refuses the committed default outside development; crypto smoke on every path,
ordered migration → smoke → rollout, failing closed on both failure and timeout;
secret-bearing jobs deleted `if: always()`; static tests derive their targets
from the workflow tree, so a new deploy path is covered the day it is written.

**Data.** snapshot (359 rows) → verify (359/359) → dry-run (103 affected) → apply
(103 rewritten, 103 verified) → final scan (0 remaining). Confirmed afterwards by
the crypto smoke and 11 authenticated end-to-end flows.

## 12. Residual risk

| Risk | Level | Note |
|---|---|---|
| The 103 values were confidentiality-compromised for 5 h 05 m | **Accepted, cannot be undone** | The subject of this pack |
| Cannot prove absence of access | **Accepted** | Instrumentation did not exist; cannot be created retroactively |
| Real data remains in staging | **Contained, not resolved** | Accounts locked out; records retained for evidence. §17 |
| Recurrence via the same defect | **Closed** | Fail-loud refusal + gate ordering + tests |
| Recurrence via a hand-created job | **Open** | No test can see a job someone creates by hand. Governance G6 |
| Production | **Not affected** | Migrations never ran there |

## 13. Notification deadline calculation inputs

**For the reviewer. Engineering does not compute the deadline.**

| Input | Value |
|---|---|
| Incident start | `2026-08-06T03:46:30Z` |
| **Awareness — first automated detection** | `2026-08-06T03:48:22Z` |
| Awareness — confirmed real data involved | `2026-08-06`, same day (provenance report) |
| Containment complete | `2026-08-06T08:51Z` |
| GDPR Art. 33 clock, **if applicable** | 72 h from awareness → **2026-08-09T03:48Z** |
| Vietnam PDPD 13/2023 Art. 23, **if applicable** | 72 h from awareness → same |
| Data subjects | < 95; exact count available on instruction |
| Categories | Health data + direct identifiers (§3) |
| Environment | Non-production; users self-registered on a publicly reachable staging system |

**Which clock applies, and whether it starts at first detection or at
confirmation that real data was involved, is a legal determination.** The earlier
date is recorded so the conservative reading is available.

## 14. Draft regulator notification

> **LEGAL REVIEW REQUIRED — NOT FOR DISTRIBUTION. DO NOT SEND.**
> Placeholders in `<angle brackets>` are deliberately unfilled.

> **Subject:** Notification of a personal data breach — MetoCare, `<date>`
>
> 1. **Controller:** `<legal entity, address, DPO contact>`
> 2. **Nature of the breach.** On 2026-08-06 a software deployment defect in our
>    non-production (staging) environment caused 103 stored health-data values to
>    be encrypted with a cryptographic key published in our public source-code
>    repository. For approximately five hours that encryption did not provide
>    confidentiality against a party who also had access to the database. The
>    database was not reachable from the public internet and remained
>    password-protected throughout.
> 3. **Categories and approximate numbers.** Health data (AI-assistant
>    conversation content, medication names/doses/frequencies, medication
>    reminders, OCR output from uploaded medical documents) and identifying data
>    (names). Fewer than 95 data subjects; `<exact count>`.
> 4. **Likely consequences.** `<assessment>` We have no indication that any
>    unauthorised party accessed the data. We note that we did not have access
>    logging capable of detecting such access and therefore cannot exclude it.
> 5. **Measures taken.** Detected automatically within two minutes by our own
>    deployment verification. All affected values re-encrypted with the correct
>    key and verified within five hours. The underlying defect is fixed and is now
>    blocked on every deployment path by an automated gate. The staging
>    environment is restricted to synthetic accounts only. All credentials held in
>    transient infrastructure have been rotated or removed.
> 6. **Measures proposed.** `<see governance runbook>`
> 7. **Contact point:** `<name, role, contact>`

## 15. Draft user notification

> **LEGAL REVIEW REQUIRED — NOT FOR DISTRIBUTION. DO NOT SEND.**
> Send only if the reviewer determines notification is owed. Note §16: contacting
> these people may be the first time they learn their data was on a test system.

> **Subject:** An issue affecting your MetoCare test-environment data
>
> Dear `<name>`,
>
> We are writing to tell you about a problem we found and fixed on 6 August 2026.
>
> **What happened.** Information you entered into our test environment was stored
> using a security key that, because of a mistake on our side, was visible in our
> public software repository for about five hours. During that time the
> protection on that information was not effective.
>
> **What information.** `<tailor: conversations with the health assistant,
> medication details, reminders, uploaded document contents, your name>`
>
> **What we know.** We have no evidence that anyone accessed your information.
> The database was not reachable from the public internet and required a separate
> password. We are telling you because we cannot completely rule it out.
>
> **What we did.** We found it automatically within two minutes, corrected all
> affected records within five hours, fixed the underlying cause, and added an
> automatic check that prevents it recurring.
>
> **What you should do.** `<guidance>` You do not need to take any action to
> secure your account. `<if applicable: password guidance>`
>
> **Questions:** `<contact>`
>
> We are sorry. `<sign-off>`

## 16. Reasons for and against notification

A balance, not a recommendation. **This decision is not engineering's to make.**

**For notifying:**

- Special-category health data plus direct identifiers.
- Confidentiality was genuinely lost for the window; the key was public, not weak.
- **We cannot demonstrate that no access occurred** — the logging did not exist.
  Several regimes treat inability to exclude access as tending toward notification.
- The affected people did not know their data was on a test system. That is
  itself a transparency problem; notification would address both.
- Notifying is reversible. Not notifying, if later found wrong, is not.

**Against notifying:**

- The database was never internet-reachable; a reader needed separate,
  restricted, password-gated access. The realistic attack population is small.
- No indication of access; no forks of the repository.
- Window was short and closed the same day.
- Some regimes exempt breaches "unlikely to result in a risk to the rights and
  freedoms of natural persons"; the reachability constraint is that argument.
- Contacting users about a *test* environment may cause alarm disproportionate to
  actual risk — and raises the separate question of why their data was there,
  which needs its own answer first.

**Engineering's honest read, offered as input only:** the deciding question is
§9. We cannot say access did not happen; only that we saw no sign of it and had
no instrument that would have. A reviewer who reads that as "cannot exclude" will
likely conclude notification is owed.

## 17. Decisions required from the incident owner

1. **Is notification owed?** Regulator, users, both, neither. §13–§16.
2. **Produce the exact data-subject count?** Minutes, on instruction.
3. **Evidence-retention plan.** Affected records are retained and **must not be
   deleted or anonymised** until this is decided. Note the 90-day Activity Log
   expiry (~2026-11-04).
4. **Should staging ever hold real user data?** 90 people registered because
   nothing stopped them. Now nothing permits them — the historical records remain.
5. **Appoint** the incident owner for this pack, and an Incident Commander for the
   pending production deploy.

---

**LEGAL REVIEW REQUIRED — NOT FOR DISTRIBUTION**
