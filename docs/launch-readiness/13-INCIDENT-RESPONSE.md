# 13 — Incident Response Plan (WS13)

**Date:** 2026-08-04 · **Branch:** `feat/patient-platform-journey2` · **HEAD:** `6ab3b04`
**Scope:** controlled pilot (10–50 users) on **staging** + internally-distributed Android APK. Production is not deployed and is not authorized by this program (`TRACKING.md` D-02).
**Companions:** `12-PILOT-OPERATIONS-RUNBOOK.md` (day-to-day ops), `02-SECURITY-PRIVACY-REVIEW.md` (control state + open findings this plan must assume), `TRACKING.md §I` (rollback).

> **Honesty statement.** This plan is written against the tooling that **actually exists at this SHA**, not an aspirational SRE stack. Where a step depends on something not yet wired, it says so. Detection today is largely **human-reported**, not automated (§3).

---

## 1. Severity model

Severity is set by **impact**, not by cause, and by the *worst plausible* interpretation until evidence narrows it. Anyone may declare; only the Incident Lead may downgrade.

| Sev | Definition | Response time (pilot hours) | MetoCare examples |
|---|---|---|---|
| **SEV1** | Confirmed or strongly-suspected **PHI disclosure to an unauthorized party**, or a defect that can cause **clinical harm**, or total loss of patient data | **Immediate**, drop everything; Incident Lead + Owner paged | • A BOLA regression lets patient A read patient B's documents.<br>• Medical-document images were sent to a third-party OCR vendor without authorization or a processing agreement (this is a **live risk today** — see PRIV-F3 in `02`).<br>• **Clinical harm:** the medication reminder engine fires doses for a *stopped* schedule, or a prescription promotes at the wrong dose, and a patient reports having taken medication accordingly.<br>• Meto tells a patient to stop an antihypertensive and the patient acts on it.<br>• Object-storage volume lost with real (non-synthetic) documents and no backup (PROD-F1). |
| **SEV2** | Security control failed but no confirmed disclosure; or a core journey is broken for **all** users; or credential exposure | ≤ 2 h | • Staging DB / JWT / Fernet credential appears in a log, screenshot, chat, or tool output (this has happened once — §6.1).<br>• Consent gate stops enforcing (`CONSENT_GATE` accidentally off), so revocation becomes a no-op.<br>• Login broken platform-wide; refresh-rotation loop logs everyone out.<br>• Backend crash-loop on staging. |
| **SEV3** | Degraded or partly-broken journey with a workaround; single-user data problem; safety guardrail fired as designed but needs review | ≤ 1 business day | • OCR returns garbage for a whole hospital layout, forcing manual entry.<br>• All users share one rate-limit bucket and start seeing 429s (SEC-F10).<br>• One patient's document is stuck in `needs_review` and cannot be confirmed.<br>• Meto output-safety detector replaced a response — logged, needs a human read. |
| **SEV4** | Cosmetic, single-user annoyance, or an accepted known limitation resurfacing | next planning cycle | • Vietnamese copy error, layout break, a known-limitation complaint (debug-signed build, no push notifications). |

**Two standing rules.**
1. **A privacy question is a SEV1 until proven otherwise.** "We think it was only synthetic data" is a *finding*, not a starting assumption.
2. **Any clinical-harm report is SEV1 regardless of technical severity** — including "the app told me to…". Clinical judgement, not code diff size, sets the bar.

---

## 2. Roles for a small team

One person may hold several hats; the hats still get named out loud at declaration time so nothing is implicitly owned.

| Role | Responsibility | Pilot assignment |
|---|---|---|
| **Incident Lead (IL)** | Declares severity, owns the timeline, makes the call on user-facing action. Does **not** debug. | Whoever first confirms the incident, until handed over |
| **Operator** | Executes containment: flags, revisions, rollbacks, account blocks. The only person touching the environment. | Backend/SRE-capable engineer |
| **Scribe** | Timestamps every action + finding into the incident log, PHI-free. | Anyone not IL/Operator; IL doubles up if alone |
| **Owner (PTH)** | Sole authority for: notifying users/regulators, enabling/disabling PHI-to-cloud, touching Azure infra or the DO legacy VPS, pausing the pilot. | PTH — **must be contacted for every SEV1 and SEV2** |
| **Clinical reviewer** | Judges clinical-harm plausibility for any AI/medication/OCR incident. | Named clinician (owner to designate before cohort start) |

**Contact chain.** Pilot support channel → IL → Owner. `12-PILOT-OPERATIONS-RUNBOOK.md` notes the support address is still **to be named by the owner** — that is a prerequisite for this plan to function, because today it is the primary detection source.

---

## 3. Detection — what we actually have

| Source | Reality at this SHA | Usefulness |
|---|---|---|
| **Patient / tester reports** | Pilot bug form + support channel (`12-…RUNBOOK.md`) | **Primary detector.** Assume most incidents arrive this way. |
| **Backend structured logs** | JSON to stdout with `request_id` + opaque `user_id`, allow-listed extra fields, no PHI — `app/core/logging.py:16-45`; gunicorn access/error logs to stdout (`backend/startup.sh:20-21`) | Good *forensics*, poor *alerting* — nothing tails or alerts on them. Retrieval is `az containerapp logs`. |
| **Log aggregation** | `APPLICATIONINSIGHTS_CONNECTION_STRING` is set on the container (`.github/workflows/azure-staging.yml:204`) but **no SDK/exporter exists in `backend/app`** (grep: no `opentelemetry`/`applicationinsights` hits) | **UNVERIFIED** whether ACA ships stdout to Log Analytics by default. Confirm: `az monitor log-analytics query -w <ws> --analytics-query "ContainerAppConsoleLogs_CL | take 5"`. Until confirmed, treat logs as **container-local and lost on revision replacement**. |
| **Metrics** | In-process counters/histograms rendered at `/metrics` (`app/core/metrics.py`, `app/main.py:181-185`) | **Process-local, never scraped.** Values reset on every restart/redeploy. Manual `curl` snapshot only — and the endpoint is currently unauthenticated on a public ingress (SEC-F12). |
| **Audit log (DB)** | Append-only who/what/when/outcome/severity — `app/services/audit.py:14-45`; readable via `GET /api/v1/admin/audit-logs` (admin + MFA, `app/api/v1/routes/admin.py:107-137`) and per-user at `/admin/users/{id}/audit-log` | **The single best evidence source.** Includes `refresh_token_reuse_detected` (severity `high`, `app/services/auth.py:332-341`), consent grant/revoke, document lifecycle, login. Query it early. |
| **Mobile crash/error telemetry** | `Monitor` abstraction with redaction, global handler installed; default adapter is **local-only — console in dev, silent in prod** (`mobile/src/lib/monitor.ts:52-59,101-111`) | A crash on a tester's device produces **no signal you can see**. Recovery is `adb logcat` on that physical device, or the tester's screenshot. |
| **Uptime / health** | `/health` and `/api/v1/health` exist; no external monitor configured | Manual `curl`. A staging outage is detected when someone tries to use it. |
| **Alerting** | **None.** No pager, no threshold alerts, no anomaly detection. | Accept and staff around it: a daily manual health+log check during pilot hours. |

**Consequence for this plan:** every scenario below starts with *"establish the timeline from the audit log"*, because that is the only durable, queryable record — and includes an explicit *"capture logs before you redeploy"* step, because redeploying is what destroys them.

---

## 4. Universal first five minutes

1. **Declare.** State severity + who is IL, in the team channel. Timestamp it (UTC).
2. **Freeze the evidence** (§7) — *before* any fix, redeploy, or restart.
3. **Contain**, preferring the least destructive lever that stops the bleeding:
   - **Feature flag** (no redeploy needed on next container update; env-driven, fails closed on unknown — `app/core/feature_flags.py:97-110`): `FEATURE_AI_ASSISTANT=false`, `MCP_FEATURE_OCR=false`, `MCP_FEATURE_OCR_CLOUD_FALLBACK=false`.
   - **Block an account:** `PATCH /api/v1/admin/users/{user_id}` (status) — takes effect on the **next request** because `current_user()` re-checks `is_active` (SEC-F2 fix, `app/api/deps.py:96-105`).
   - **Kill a session:** the user's refresh tokens are revoked by account deletion (`app/services/account.py:229-239`); reuse of a stolen refresh token revokes the whole family automatically (`app/services/auth.py:329-343`).
   - **Revision rollback:** re-point the ACA container app at the previous image/revision (`TRACKING.md §I`). **Owner-gated** — Azure infra changes are not made unilaterally.
4. **Notify the Owner** for SEV1/SEV2. Do not decide on user notification alone.
5. **Open the incident log** — one markdown file, PHI-free, appended live.

---

## 5. Scenario playbooks

### 5.1 Credential leak (DB / JWT / Fernet / provider API key)
*Assume compromised the moment it is visible anywhere outside a secret store — including terminal output, a screenshot, a chat message, or a CI log.*
1. **Scope the blast radius first.** Enumerate every consumer of that secret before rotating — the 2026-07-27 incident found **two additional Container Apps jobs** holding the same alias that were not in the original list (§6.1). Under-scoping causes a second outage.
2. Rotate at the source (Key Vault secret version), then update **every** consumer, then verify the old value fails and the new one works (that incident verified both directions by deliberately running a job before and after the update).
3. Special cases:
   - **`MCP_SECRET_KEY` (JWT):** rotation invalidates all access **and** refresh tokens **and** all outstanding signed blob URLs (blob tokens derive from it — `app/services/storage/signing.py:51-58`). Expect a full re-login of the cohort; announce it. Compensating control: the boot guard refuses the committed default, so a botched injection crash-loops rather than silently running insecure (`app/core/config.py:239-262`).
   - **`MCP_ENCRYPTION_KEYS` (Fernet/PHI):** **never remove the old key** — prepend the new one, keep the old for decrypt, re-encrypt, only then drop it (`app/core/crypto.py:1-16,60-68`). Dropping first makes PHI permanently unreadable.
   - **LLM / Document-Intelligence provider keys:** rotate at the vendor, and treat any data already sent under that key as out of your control.
4. Record the rotation as an operational note in the style of `docs/agent/INCIDENT_STAGING_DB_CREDENTIAL_ROTATION_2026-07-27.md` — resources, sequence, transition window, confirmations, and an explicit "no secret value was printed or persisted" line.
5. Assess whether the exposure window admits unauthorized access (§5.2 if yes).

### 5.2 PHI exposure / unauthorized access
1. **SEV1 immediately.** Do not downgrade before evidence.
2. Answer, in writing, four questions: **What** categories (documents/labs/meds/chat/identity)? **Whose** (how many data subjects, synthetic or real)? **To whom** (another patient, an unauthenticated party, a third-party processor)? **For how long** (first-to-last timestamp)?
3. Evidence sources in priority order: DB audit log (`/admin/audit-logs`, filter by `resource_type` + `actor_id`), container logs (`request_id` correlation), the offending code path.
4. Contain: block the receiving account, revoke sessions, disable the feature flag that reaches the data, and — if the disclosure is via a signed blob URL — remember those stay redeemable for up to **900 s** and are not revocable individually (SEC-F14); rotating `MCP_SECRET_KEY` is the only immediate kill switch.
5. **Third-party-processor variant (live risk today):** if the exposure is medical images reaching a cloud OCR vendor, this is PRIV-F3 in `02-SECURITY-PRIVACY-REVIEW.md`. Containment is: remove the vendor credentials from the container env (owner-gated) — **not** the feature flag, because `run_ocr` selects the cloud engine on credential presence alone (`app/services/ocr_engine.py:491-492`). Then request deletion from the vendor and record what was sent.
6. Determine whether the affected records were **synthetic** (pilot default) or **real**. Notification obligations attach to real personal data (§8).
7. Fix, regression-test the exact access path, and only then restore the feature.

### 5.3 Unsafe AI output reported by a patient
1. **SEV1** on report. Ask the patient directly: *"Did you change anything about your medication or care because of this?"* — the answer determines whether this is a software incident or a clinical event.
2. **If they acted on it:** advise contacting their treating clinician or emergency services per the disclaimer text already required at onboarding (`12-…RUNBOOK.md`). Involve the clinical reviewer immediately. Document the advice given.
3. **Contain the population:** set `FEATURE_AI_ASSISTANT=false` — the endpoint fails closed with 503 (`app/api/v1/routes/meto.py:34-44`) — rather than trying to patch a prompt live.
4. **Reproduce from stored evidence:** the conversation is persisted (`MetoMessage`, `app/models/meto.py:61-88`) and `MetoAuditLog` records `safety_flags_detected` / `escalation_triggered` / provider metadata without content (`models/meto.py:91-117`). Determine whether the output-safety layer *missed* it (detector-coverage gap, CLIN PS-1) or *fired* and the phrasing still landed badly.
5. **Handle the message content as PHI** — do not paste it into a bug tracker, chat, or this document. Reference the conversation id only.
6. Fix = broaden the detector *and* add the exact phrasing as a regression case. Re-enable the flag only after the clinical reviewer signs off.

### 5.4 Data loss from the PROD-F1 ephemeral-storage risk
*Context: `MCP_STORAGE_MODE=local` (`.github/workflows/azure-staging.yml:209`) puts document blobs on the container's own disk. Any redeploy, scale event, or restart can destroy them. The Azure Blob adapter exists but is inert.*
1. **Severity: SEV3 if the cohort is synthetic-only; SEV1 if any real patient document was stored.** There is no backup to restore from — this is data *loss*, not data *unavailability*.
2. Confirm the scope: DB rows survive (Postgres is durable), so run the orphan check — for each `MedicalDocument` / `DocumentPage` / `LabDocument` row, test whether its storage key still resolves. Rows whose blob is gone are the loss set (`app/services/account.py:183-215` enumerates exactly these key families).
3. **User-facing consequence:** document *metadata*, extracted candidates and any **confirmed** medications/labs remain intact — only the original image is gone. Say precisely that; do not imply the clinical record was lost.
4. Ask affected users to re-upload; mark the affected documents so the UI does not offer a broken viewer.
5. **Prevention is the real fix and it is owner-gated:** set `MCP_STORAGE_MODE=azure` with a connection string and Blob soft-delete/versioning before **any** real-data cohort. Until then, `12-…RUNBOOK.md`'s "re-seed after redeploy" caveat is mandatory, not advisory.

### 5.5 Staging backend outage
1. SEV2 (all users blocked) — SEV1 only if data integrity is also implicated.
2. Triage in this order, because the failure modes are known:
   - **Crash-loop at boot →** almost certainly the startup guard doing its job (`app/main.py:43` → `config.validate_required_env_vars`). Read the very first log lines: missing/`dev-insecure` secret, committed Fernet key, relaxed auth without `MCP_ALLOW_RELAXED_AUTH`, or QA fixture enabled. The message names the exact env var (`app/core/config.py:234-305`). **This is a configuration fix, never a code fix, and never a reason to weaken the guard.**
   - **Healthy container, failing requests →** DB connectivity (check `/api/v1/health`, which touches the DB — `app/api/v1/routes/system.py:18`); note the credential-rotation failure mode from §6.1.
   - **Mass 429s →** shared rate-limit bucket (SEC-F10), not an attack. Confirm before treating it as one.
   - **Migration mismatch →** `/info` reports the live migration version; compare with `alembic heads` at the deployed SHA.
3. Rollback path: previous image/revision, then `alembic downgrade` only if a migration is implicated (single head, additive — `TRACKING.md §I`). Migrations run as a separate ACA job, so a failed migration and a failed app are distinct events.
4. Communicate to the cohort within 30 minutes with an ETA or an explicit "no ETA yet".

### 5.6 Lost or stolen pilot device
1. SEV2 by default; **SEV1 if the device held real patient data** for a real (non-synthetic) account.
2. What the attacker has: an APK plus whatever is in Keychain/Keystore. Tokens are stored **only** in SecureStore (`mobile/src/storage/secureStore.ts:1-71`, `tokenStore.ts:11-45`), hardware-backed and not in AsyncStorage. Access tokens expire in 15 min; refresh tokens last 7 days (`app/core/config.py:34-35`) — **the refresh token is the real exposure**.
3. Containment, in order: (a) block the account — effective on the next request via the `is_active` re-check (`app/api/deps.py:96-105`); (b) if the user is continuing on a new device, have them log in there and log out on the old session, or delete + recreate the account; (c) for a real-data account, consider rotating `MCP_SECRET_KEY` (invalidates *everyone's* tokens — weigh cohort disruption).
4. Note the residual: device-level backup posture is not source-controlled (SEC-F13), and real at-rest Keystore behaviour is logic-tested only, not device-verified (`02` §2 row 19).
5. Record the device, the account, the data mode (synthetic/real), and the containment timestamps.

---

## 6. Worked example — the one real incident to date

`docs/agent/INCIDENT_STAGING_DB_CREDENTIAL_ROTATION_2026-07-27.md` is the reference standard for how a MetoCare incident record should read. It is a **SEV2 credential-exposure** case: a staging PostgreSQL credential appeared in prior tool output (an operational-handling failure, not an application defect).

What it did right, and what §5.1 codifies from it:
- **Consumer audit before rotation** — the scope expanded mid-incident from one Container App to three additional Jobs holding the same `db-url` alias. Enumerate first.
- **Bidirectional verification** — proved the old credential was dead (a job run *failed* immediately after rotation) *and* the new one worked (the same job *succeeded* after the update). Both directions, with evidence.
- **A measured transition window** — ≈2 minutes (01:12:18–01:13:57 UTC), stated explicitly, with a claim that no consumer was left holding the stale value.
- **Blast-radius discipline** — production resources were read-only throughout; the DO legacy VPS and the PG firewall untouched.
- **Secret hygiene inside the response** — the new value existed only in one short-lived process's memory; nothing written to disk, shell history checked afterwards.
- **A PHI-free record** — the document itself states that no PHI, connection strings, or credential fragments are recorded in it. Every incident document must be able to make that statement.

Gap to carry forward: that record is an *operational note*, not a post-incident review — it has no contributing-cause analysis and no prevention actions. Use §9 for that half.

---

## 7. Evidence preservation

Do this **before** containment where the two conflict, and always before a redeploy — a new ACA revision replaces the container and its stdout history.

1. **Container logs:** `az containerapp logs show -g rg-metocare-staging -n ca-metocare-backend --tail 2000 > incident-<id>-backend.log` (and the same for the migration/seed jobs if implicated). Capture the **current revision name** too.
2. **Audit log:** export the relevant window via `GET /api/v1/admin/audit-logs?limit=500` (admin + MFA) and, per affected user, `/api/v1/admin/users/{id}/audit-log`. These rows are append-only and PHI-free by construction (`app/services/audit.py:14-45`) — safe to attach to the incident file.
3. **Metrics snapshot:** `curl -s https://<staging-fqdn>/metrics > incident-<id>-metrics.txt` **before** any restart — the registry is in-process and resets (`app/core/metrics.py:23-31`).
4. **Deployed identity:** record the image tag/revision, the git SHA, and `/info`'s reported migration version so the code under investigation is unambiguous.
5. **Database state:** for data-integrity incidents take a point-in-time note (row counts, ids, timestamps) rather than exporting rows — PHI must not leave the database into an incident file.
6. **Mobile:** if a device is available, `adb logcat -d > incident-<id>-device.log` *and redact it* — device logs are **not** covered by the backend's PHI-safe formatter, and the mobile redactor only sanitizes what passes through `captureException` (`mobile/src/lib/monitor.ts:74-86`).
7. **Chain of custody:** store artifacts under `docs/agent/` (or an owner-designated location) with the incident id, note who collected what and when, and **never** commit PHI, tokens, or credential fragments. If an artifact cannot be redacted, reference it rather than commit it.
8. **Do not "clean up" the affected data** until the Owner agrees the investigation is complete — soft-deletes are recoverable, blob deletions are not.

---

## 8. Communications & regulatory considerations

> **This is not legal advice.** MetoCare handles health data, which is a special category under GDPR-style regimes and is separately regulated in Vietnam (Decree 13/2023/ND-CP on personal data protection, plus sector rules on medical records). **The Owner must confirm — with qualified counsel, before the first real-data cohort — which regime applies, who the controller is, and what the notification clock actually is.** Do not rely on the timings below as the operative deadline; they are planning placeholders and must be replaced with counsel-confirmed values.

**Internal.** Declaration in-channel at t0; status update at 30 min for SEV1/SEV2 and then hourly until contained; Owner is contacted for every SEV1/SEV2, not merely informed afterwards.

**Affected users.** Notify plainly, in Vietnamese, without hedging: what happened, what data was involved, what you have done, what they should do, and how to reach a human. For a **clinical-harm** scenario, notification is immediate and individual, and includes the instruction to contact their treating clinician. Never send PHI through the notification channel to prove a point.

**Regulatory — the questions to answer, not the answers.**
- Is the data **real personal data**? A synthetic-only pilot materially changes the analysis — which is exactly why the synthetic/real distinction must be recorded per cohort (`12-…RUNBOOK.md`).
- Is MetoCare **controller** or **processor** for this data, and are there other controllers (a clinic, a doctor)?
- Does the incident meet the risk threshold that triggers **authority** notification, and separately the higher threshold that triggers **individual** notification?
- What is the **clock**, and from when does it run — discovery, or confirmation? (GDPR's familiar 72 hours is one regime's answer; **Vietnam's is different and must be confirmed.**) Record the discovery timestamp precisely at t0 so the clock is defensible whatever it turns out to be.
- Are **third-party processors** implicated (LLM provider, cloud OCR vendor)? If a processor received data without an agreement in place, that is its own compliance issue — see PRIV-F3 in `02`.
- Is there a **DPIA / record of processing** to update?

**Practical prerequisite:** the notification decision cannot be made in the middle of an incident if the controller/processor mapping and the counsel contact do not exist yet. Both are owner deliverables **before** the first real-data cohort — track them as such.

**External/public statements:** Owner only.

---

## 9. Post-incident review

Mandatory for every SEV1 and SEV2; recommended for a repeated SEV3. Held within **5 working days** while memory is fresh. **Blameless** — the target is the system that let it happen, not the person at the keyboard. Output is committed alongside the incident record.

```markdown
# Incident <YYYY-MM-DD>-<short-name> — Post-Incident Review

**Severity:** SEV_   **Status:** resolved / monitoring
**Detected:** <UTC>  by <source: tester report / log / manual check>
**Contained:** <UTC>   **Resolved:** <UTC>
**Time to detect:** __   **Time to contain:** __
**Data mode:** synthetic / real   **Data subjects affected:** __
**Roles:** IL __ · Operator __ · Scribe __ · Owner informed at __ · Clinical reviewer __

## 1. What happened
Two or three sentences, PHI-free, understandable by someone who was not there.

## 2. Impact
Users affected · journeys affected · data categories · duration · clinical impact (none / potential / actual — clinical reviewer's words).

## 3. Timeline (UTC)
| Time | Event | Actor |
|---|---|---|

## 4. Contributing causes
Not "root cause" — list every condition without which this would not have happened
(code defect, config drift, missing control, missing detection, documentation that
asserted a control that did not exist, time pressure).

## 5. Detection
How did we find out? How long did it take? **Would we have found it without a user
telling us?** If not, that is an action item.

## 6. What went well
Explicitly. Controls that fired as designed belong here.

## 7. Where we got lucky
The near-misses. If the answer to "why wasn't this worse?" is "the cohort was
synthetic", say so — that luck expires with the next cohort.

## 8. Actions
| # | Action | Type (prevent / detect / respond) | Owner | Due | Tracking |
|---|---|---|---|---|---|
Every action is code, config, or a documented procedure. "Be more careful" is not
an action. Each links to a finding id in `02`/`15` or creates a new one.

## 9. Documentation corrections
Any launch-readiness document whose claims this incident contradicted, and the
correcting edit. (Precedent: PRIV-F3 required correcting three documents.)

## 10. Evidence index
Artifacts collected (§7), where they live, PHI-free confirmation.
```

---

## 10. Readiness gaps this plan depends on

| # | Gap | Blocking for |
|---|---|---|
| 1 | Support/escalation contact not yet named (`12-…RUNBOOK.md`) | any pilot — it is the **primary** detector (§3) |
| 2 | Clinical reviewer not yet designated | §5.3 clinical-harm path |
| 3 | Counsel contact + controller/processor mapping absent | §8 — cannot decide notification mid-incident |
| 4 | No log aggregation confirmed; logs die with the revision | §7 evidence preservation |
| 5 | No mobile crash visibility off-device (`monitor.ts:52-59`) | detecting client-side SEV2/SEV3 at all |
| 6 | No alerting of any kind | every "time to detect" figure in §9 |
| 7 | PRIV-F3 open: cloud-OCR egress is not gated by the flag the docs credit | makes §5.2's third-party-processor branch a **live** scenario, not hypothetical |

Items 1–3 are **owner deliverables before the first cohort**; 4–6 are the WS5 observability plan; 7 is a code fix specified in `02-SECURITY-PRIVACY-REVIEW.md` §5.
