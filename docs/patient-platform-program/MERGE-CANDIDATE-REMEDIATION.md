# Merge-candidate remediation — P0-1, P0-2 and the eight P1s

**Branch:** `feat/patient-platform-journey2`
**Baseline for this round:** `c6676d4`
**Date:** 2026-08-05

Every item below was closed by a change to production code, with a regression
suite checked to actually fail without it. Where a reported finding turned out not
to be reachable, that is recorded as such rather than written up as a fix or
quietly dropped.

---

## P0 — closed

### P0-1 · One hardened analyte matcher on every path (`c12be62`, earlier work)

`lab_interpreter.normalize_biomarker` ends in a bare containment scan
(`alias in key or key in alias`). Under it "VLDL" resolves to `ldl` and "Non-HDL
cholesterol" resolves to `hdl`, because the shorter generic alias is a substring
of the longer specific label.

Only `/lab-uploads` used the hardened matcher. The document-intelligence path had
**three** entry points that did not:

| Entry point | Defect |
|---|---|
| `mdi/extractors_lab.py` | called `_match_biomarker` with **no alias index**, falling back to the bare `_ALIAS_INDEX` (under which "HDL Cholesterol" → `total_cholesterol`) |
| `mdi/promoters.py::_canonical_for` | unhardened, and fell back on failure instead of refusing |
| `lab.py::create_manual_entry` | re-derived the canonical with `normalize_biomarker`, discarding a correct upstream resolution |

**Why it is patient-safety, not data quality:** VLDL runs ~0.1–1.0 mmol/L, LDL is
high above ~3.4. Confirming the VLDL line off a printed report overwrote LDL with
a much lower number, classified it optimal, and trended it — a false negative on
cardiovascular risk, invisible at review because the confirmation card shows the
**printed** label, not the resolved canonical.

**Closed as a class:** all three paths resolve through `build_alias_index()`;
unmappable labels are **refused** (`PromotionInvalid`) rather than approximated;
`/` is excluded from the flexible-separator set so a ratio is never split into the
analytes it is a ratio *of*; the stored `canonical` is never trusted over the
label, because `_apply_corrections` merges a patient-influenced dict before
promotion.

**Coverage:** `tests/test_mdi_lab_alias_class.py`, 54 tests.

### P0-2 · Persisted anchor for phase-dependent schedules (`fa60e0f`)

`compute_occurrences` derived the cycle origin from `start_date or today_local`.
For `interval` and `cyclic` the origin **is** the phase, so a NULL `start_date`
made the anchor track the clock: `(day - anchor) % n` is 0 for today on *every*
day, and every-2-days or 21-on/7-off silently degraded to **daily**.

Weekly methotrexate dosed daily is a recognised fatal medication error. A 21/7
cycle reminded through its rest week is a wrong instruction delivered by name. It
fails silently — the reminder looks plausible every morning.

**Closed at all three layers**, because fixing one leaves the class open:

1. `create_schedule` refuses an anchor-required type with no `start_date`.
2. `edit_schedule` takes no `start_date` argument at all, inherits the old anchor,
   and validates the **resolved** shape — so a type change *into* interval/cyclic
   on an anchorless row is refused, not silently anchored to today.
3. `compute_occurrences` **fails closed** for legacy NULL rows already on disk —
   no doses, plus `needs_anchor_repair()` to surface them. Producing nothing is
   visibly wrong; dosing every day is silently wrong.

`fixed_daily` / `days_of_week` stay exempt: they are phase-independent, so the
today fallback is correct for them and only for them.

**Coverage:** `tests/test_medication_schedule_anchor.py`, 28 tests — hand-computed
calendars for 2/3/7-day intervals and 21/7 + 5/2 cycles, opposite-phase pairs the
bug made identical, missing/future/past anchors, `end_date` bounds, pause, edit,
stop, legacy NULL rows, materialisation idempotency, no rest-day rows, and DST
stability across the UK autumn transition.

---

## P1 — all eight closed

| # | Finding | Commit | Disposition |
|---|---|---|---|
| P1-1 | Promotion provenance not recorded | `a6d17b0` | fixed (+ second half proven unreachable) |
| P1-2 | `_cancel_open_doses` erased real non-adherence | `fa60e0f` | fixed |
| P1-3 | `/reminders/due` gated the counter, not the rows | `6f5be9a` | fixed (scope stated precisely below) |
| P1-4 | Meto context builders swallowed failures | `e188c93` | fixed |
| P1-5 | Residual plaintext PHI | `488d690` | fixed |
| P1-6 | SEC-F11 rewrite had no `lock_timeout` | `029f1ea` | fixed |
| P1-7 | Build-identity wiring untested | `283065b` | fixed |
| P1-8 | 11 of 16 integration modules never ran in CI | `283065b` | fixed |

### P1-1 · Resolution provenance

A stored `LabResult` names a canonical. Nothing recorded **which alias** bridged
the printed label to it, or which alias layer supplied it — so the P0-1 question
could not be answered from the data; it had to be answered against the code as it
exists *now*, which is exactly the code that has since changed.

`resolve_with_provenance()` records the verbatim original label, the canonical,
the winning alias, the alias layer (**three** layers: shared table / parser extras
/ hospital profile — collapsing them to base-or-profile would send an
investigator to the wrong lab's configuration), the profile in play, and a reason
that distinguishes a deliberate refusal (`unmappable_label`) from a coverage gap
(`no_alias_matched`).

Captured **twice**: at extraction (what the OCR read) and re-derived at promotion
(the label as confirmed). They differ whenever the patient corrects the analyte
name, and reusing the first would attribute the stored analyte to an alias that
never fired for it — worse than nothing, because it reads as authoritative.

Both live inside `fields_json`, already encrypted by SEC-F11, so no new PHI
surface and no migration.

**Second half — "no silent overwrite of an existing biomarker record" — is NOT
reachable.** `promote_lab_to_metric` deletes only prior `HealthMetric` rows whose
`source_ref` is the *same* lab row, so promotion is append-only with respect to
other analytes, and the MDI promoter never passes `force_mode`. No change made;
recorded here so the finding closes on evidence rather than being dropped.

### P1-2 · Adherence history erased by pause/stop/edit

`_cancel_open_doses` hard-deleted every open dose, including days-old ones the
sweep had not yet resolved (it only runs when the patient opens the app). A
patient who missed three days and then tapped "Tạm dừng" had that non-adherence
deleted, and pause → edit → resume made the reset repeatable. A clinician reading
adherence before escalating therapy would be acting on fabricated data.

Now unconditional: past-due resolves to `MISSED` and is **kept**; only not-yet-due
doses are dropped. The one exception is a **repudiated** record — soft-deleted or
`entered_in_error`, "this should never have existed" — which purges, because
counting missed doses for a drug the patient was never on is equally fabricated.
A lifecycle *exit* (stop/pause/discontinue/on_hold) is the opposite case and
always preserves.

### P1-3 · `/reminders/due` — scope stated precisely

The endpoint gated its `delivered` **counter** via `deliver_due_reminders` but ran
its own bare `DoseOccurrence` query for the `items` payload — no schedule join, no
medication join. Extracted `due_doses_query()`; all three read paths now call it.

**What was and was not exposed.** For medications and schedules retired through
the normal write paths the endpoint was **already safe**: pause / stop / edit /
lifecycle-exit each cancel the schedule's open doses, so no row survives for an
ungated read to return. The demonstrable residual exposure is **legacy rows** —
written before those cancel paths existed and still on disk — the same case
`reconcile_schedules_with_medication_state` exists for.

Verified by reverting the route to the bare query: exactly two of the twelve new
tests fail (paused and superseded legacy rows), the other ten pass. So this is a
real fix plus defence in depth, not a claimed fix for a leak that was already
closed.

### P1-4 · Failed context blocks read to Meto as empty ones

Every `ContextBuilder` block builder caught `Exception`, logged, and returned
`None`. `None` is also what a block holds when the patient consented but has no
rows — so a transient failure of the labs query produced a context identical to a
healthy patient's. `safety_flags` is **derived** from `recent_labs` /
`recent_metrics`, so the flag list came back empty too, and Meto answered a
patient who may have had a CRITICAL value on file as though nothing was abnormal.

Absence of evidence rendered as evidence of absence, to a patient, by a health
assistant. `missing_consents` could not express it: a *declined* block is a
different statement, and one the model reasons about correctly.

**Reachability is partly self-inflicted.** SEC-F11 sets
`on_decrypt_failure="raise"`, so one unreadable ciphertext now *raises* inside
these builders instead of yielding `None`. Hardening the crypto made this path
easier to reach — correctly, since the wrong response to unreadable PHI is to
proceed silently. That made closing this a **precondition** of shipping SEC-F11,
not a follow-up to it.

`AssembledContext.degraded_blocks` now records blocks whose query raised, with
`SAFETY_CRITICAL_BLOCKS` (labs, metrics, medications, health_summary) called out.
The assembler emits an explicit block **before** the consent note, phrased as a
**prohibition** on asserting absence rather than a disclosure — a disclosure the
model may paraphrase away does not protect the patient — plus a do-not-reassure
clause when a safety-critical block failed.

### P1-5 · Residual plaintext PHI

Nine columns across three tables, encrypted by migration
`j4_m10_p15_residual_phi`:

- `extraction_candidates.corrections_json` — the patient's **corrections**, i.e.
  the same clinical values as `fields_json` and usually *more* accurate because a
  human fixed them. Encrypting the machine's guess and leaving the confirmed
  truth readable is the wrong way round.
- `medication_statements.{raw_drug_name, normalized_name, raw_dose, raw_frequency,
  raw_prescriber, payload_snapshot}` — a drug name is PHI in the strongest sense:
  an antiretroviral, an antipsychotic or an oncology agent discloses the condition
  more directly than most diagnosis fields.
- `notifications.{title, body}` — reminders put the drug name in the body **by
  design**, so the table accumulated a plaintext, timestamped medication history
  per patient. `title` is included because `POST /notifications` accepts an
  arbitrary admin-supplied title: "titles contain no patient data" is a
  convention, not an invariant.

None of the nine is filtered, ordered or grouped by value anywhere — verified
before writing — so Fernet's non-determinism costs nothing.

`on_decrypt_failure` follows `EncryptedString`'s documented rule per column: NOT
NULL columns use `"raise"` (a silent `None` violates the column and crashes
serialization); optional overlays use `"none"` so one unreadable row degrades a
field rather than making a record unopenable.

**Verified on real PostgreSQL, 11/11**
(`tests/integration/test_p15_residual_phi_encryption.py`): ciphertext at rest for
all nine columns across >1 keyset batch; nothing recoverable by raw SQL; values
round-trip; a **new ORM write** is encrypted, not just the backfill; idempotent
re-run; upgrade→downgrade→re-upgrade preserves values; a wrong-key downgrade
**refuses** and leaves data intact; no PHI in migration output.

### P1-6 · Lock-queue hazard in the SEC-F11 rewrite

`ALTER TABLE … TYPE TEXT` takes an `ACCESS EXCLUSIVE` lock. The dangerous failure
is not that the migration waits — it is that while waiting it sits at the **head
of the lock queue**, so every later query on the table queues behind it. One
idle-in-transaction session that ran a single `SELECT` takes document review
offline for the whole application, for as long as it stays open, while the
migration merely looks slow.

`SET LOCAL lock_timeout = '5s'` bounds the **wait** (transactional DDL, so the
abort rolls back cleanly and re-running is safe). `SET LOCAL statement_timeout = 0`
covers the other side: once the lock is held, the rewrite must not be killed
partway. `_preflight_locks()` names the blocking pids and transaction ages —
"canceling statement due to lock timeout" alone tells an operator nothing
actionable at 02:00. Applied to `downgrade()` too, which carries the same hazard.

**Measured, not asserted:** with a blocking idle transaction held, the rewrite
aborts `LockNotAvailable` after **5.1 s** instead of queueing; released, it
acquires in **0.0 s**.

### P1-7 · Build identity

`/info` reports `build_sha` / `build_time` from `Settings` (`env_prefix` `MCP_`),
which `azure-{staging,production}.yml` set at deploy time. The coupling had no
test: `build_sha` defaults to `""`, so a field rename, an `env_prefix` change or a
dropped deploy step degrades silently to an empty sha — and every later
"tag == SHA" check compares against nothing, discovered during an incident.

Pinned from the backend side, plus a **read-only** assertion that the deploy
workflows still set both vars. The Azure workflows are owner-gated and were **not
modified**. This does not claim to verify a deployed environment's sha; it ensures
a backend-side change cannot break the wiring silently.

### P1-8 · Integration modules that never ran

The Postgres CI job named **five** test files explicitly; **sixteen** were on
disk. Eleven never ran in CI at all — including
`tests/integration/test_secf11_phi_encryption.py`, whose entire job is to prove
patient data is encrypted at rest.

Now globbed, so new files are gated by construction. **Per-file databases are
required, not tidy:** each module runs `alembic upgrade` / `downgrade` against
`POSTGRES_TEST_URL`, so one shared database makes one module's downgrade collide
with another's expected revision. That interference is what made the whole-suite
run unusable and is precisely why the hand-maintained list existed — the list hid
the cause rather than fixing it.

Two further findings surfaced while verifying:

- `test_secf11_phi_encryption.py` carried `skipif` but **not**
  `@pytest.mark.integration`. CI-1 (`-m "not integration"`) collected and
  **skipped** it for want of a database; CI-2 (`-m integration`) **deselected** it
  for want of the marker. It ran in neither job and reported green in both. Marked
  — and the loop now treats pytest's exit code **5** ("no tests collected") as a
  failure, so the next file to lose its marker fails loudly.
- `test_consent_gate_ai_path.py` was misfiled: it uses the SQLite `db` fixture and
  needs no Postgres. Moved to `tests/`, so `tests/integration/` now means exactly
  "requires Postgres".

**Verified locally, per file, against real PostgreSQL: 15 modules, 209 tests, all
green, zero collection failures.** Previously gated: 80. **129 tests that never
ran in CI now do.**

---

## Six independent reviews — and what they found

Run after the ten items above were closed: security/privacy, Python correctness,
clinical safety, database/migration, test integrity, CI/release readiness.

| Review | Result |
|---|---|
| Security / privacy | 0 P0, 0 P1 (2 informational) |
| Python correctness | 0 CRITICAL, 0 HIGH |
| Test integrity | every suite **SOUND** — none vacuous |
| Clinical safety | **1 P0, 6 P1, 4 P2** |
| Database / migration | **1 HIGH** (reproduced on real Postgres) |
| CI / release readiness | 1 HIGH, 2 MEDIUM, 1 LOW |

Two findings were cases where **I had claimed a class was closed and it was not** —
the exact failure the instruction "do not accept 'specific instance fixed' where
the vulnerability class remains" is about. Both are now closed and verified
empirically before and after.

### Reopened: P0-2 class — `cyclic` with `off_days` omitted degrades to daily

`_validate_schedule_shape` read `int(rec.get("off_days", 0))` and accepted 0, so
`_day_applies` computed `cycle == on` and `(day - start) % on < on` was true on
**every** day. A client sending `{"schedule_type": "cyclic", "on_days": 21}`
meaning 21-on/7-off got reminders straight through the rest week — with a
perfectly good anchor. The anchor fix closed one route into daily dosing; this was
another. Measured: 30/30 dose days before, refused after.

### Reopened: P0-1 class — urine analytes promoted as serum analytes

Every canonical in the table is a **serum** analyte and nothing downstream carries
a specimen, so `Creatinin niệu` resolved to `creatinine`, passed the unit gate
(mg/dL *is* the serum unit), and was stored, classified and trended as blood.

The ranges do not overlap, so it does not look like noise:

- urine creatinine 50–200 mg/dL against a serum reference of 0.6–1.2 (critical
  ≈ 4) → the patient is told their kidney function is catastrophic;
- urine glucose 5.5 mmol/L → `fasting_glucose` ≈ 99 mg/dL, classified **normal** →
  a fabricated normal blood sugar, and the glycosuria actually on the report is
  silently dropped.

Urinalysis is in nearly every VN check-up packet, the premise of the document path
is "photograph whatever the hospital gave you", and the review card shows the
**printed** label — so confirming it looks entirely correct.
`_UNMAPPABLE_LABEL_RE` now refuses `niệu` / `nước tiểu` / `urine` / `24h` / `ACR`
/ CSF qualifiers. Serum analytes verified unaffected.

### Merge blocker I introduced: SEC-F11's own suite was red

`tests/integration/test_secf11_phi_encryption.py` used `upgrade head` /
`downgrade -1` — "whatever the newest migration happens to be". Stacking `j4_m10`
on `j4_m9` broke both assumptions, and because P1-8 marked the file `integration`
and globbed the CI job, **it now actually runs** — so CI would have gone red on
merge. Pinned to the revision by name; 7/7 green on real Postgres.

This is the **third** instance of literal-head coupling in this repo. A migration
test must pin the revision it is about, or it becomes a tripwire for unrelated
work.

### Also closed from the reviews

- **P1-4 class left open in its own file.** `_build_today_context` still swallowed
  its query failure — at `logger.debug`, so silent in logs too. Sink threaded.
- **Grace-window mismatch.** `_cancel_open_doses` used `cutoff = now` while the
  sweep allows 4h, so completing a course ten minutes after the last dose recorded
  it MISSED — 93% instead of 100% on every finished course, and uncorrectable
  because the stopped schedule drops out of `due_doses_query`.
- **`purge_history` did not do what its docstring claimed.** It selected only
  pending/notified, but the sweep has usually already moved doses to MISSED, so
  the purge left most of them — and *which* ones vanished depended on when the
  patient last opened the app. Now includes MISSED.
- **P1-2 had no discriminating test.** The existing one stops the schedule inside
  the grace window, so it could not tell the fix from its absence. Four added;
  three fail on revert.
- **`build_alias_index` handed out the memoized mutable dict** — now a
  `MappingProxyType`.
- **`MCP_ENCRYPTION_KEYS` validated as well-formed Fernet at boot.** It was only
  discovered lazily on first encrypt/decrypt, so a bad key passed `containerapp
  update`, `/health` (a `SELECT 1` that never touches an encrypted column) and the
  unauthenticated smoke suite — the deploy was reported healthy and the first
  failure was a patient request. This branch made that worse by putting
  `raise`-on-failure columns on reminders and the medication timeline.
- **`notifications.title` downgrade could be blocked.** A >256-char row made
  `ALTER … VARCHAR(256)` fail outright (Postgres raises, it does not truncate).
  Bounded `NotificationCreate.title` and added a preflight naming the offending
  rows. Reproduced and verified on real Postgres.
- **CI diagnostics.** Setup failures (`CREATE DATABASE`, baseline migration) are
  now reported as themselves rather than falling through into a confusing pytest
  error; the now-dead shared-database baseline step is removed.

---

## Open, and deliberately NOT changed here

Each is real and verified. None is closed, and none is silently dropped.

1. **`ci.yml`'s `deploy-staging` job does not set `MCP_BUILD_SHA`/`MCP_BUILD_TIME`.**
   `azure-{staging,production}.yml` are `workflow_dispatch` (manual); the job that
   auto-deploys staging on merge is in `ci.yml`, and it sets neither — so every
   auto-deployed staging build reports an **empty** `build_sha` today.
   Pre-existing; closing it means editing the deploy job, which is owner-gated.
   The test's docstring now says so explicitly, so a green run is not misread.

2. **No post-deploy check exercises a PHI decrypt path.** `/health` is `SELECT 1`
   and the smoke suite is unauthenticated. Boot-time key validation closes the
   malformed-key case, but a *wrong-but-well-formed* key would still deploy green.
   Fixing this means an authenticated smoke step — deploy workflow, owner-gated.

3. **VN CBC units are refused outright.** `is_unit_convertible` accepts only an
   exact match on `spec.unit`/`si_unit`, and the CBC specs are `10^9/L`,
   `10^12/L`, `g/dL` with no SI alias — while VN reports print `G/L`, `T/L`,
   `g/L` (the project's own OCR sample text does exactly this). So **no CBC line
   from a typical VN report can be confirmed** through the document path, including
   platelet 20 G/L, WBC 0.8 G/L and Hb 70 g/L. Worse, the refusal asks the patient
   to "sửa đơn vị", and the obvious action is retyping `g/L` as `g/dL` **without
   converting the value** — Hb 140 g/L stored as 140 g/dL. This needs
   unit-conversion entries added under clinical sign-off, not a same-session guess.

4. **`/lab-uploads` and manual entry have no unit-convertibility guard at all.**
   `is_unit_convertible` is referenced only by the MDI promoter, so the two paths
   give different answers and the unguarded one is the more used. In-class with
   P0-1's "one hardened path" principle; adding a hard refusal to the primary
   upload flow is a behaviour change needing owner sign-off.

5. **`paused → active` never restores reminders.** The lifecycle cascade stops
   every schedule on the way out and nothing un-stops one on the way back in;
   `edit_schedule` refuses a stopped row and there is no resume route. A patient
   who pauses around a procedure and resumes gets a medication that reads `active`
   and never reminds again. Pre-existing; fixing it means a new endpoint plus
   mobile work — but it should close before pilot patients use pause.

6. **Dose deletions are not audited.** `_cancel_open_doses` deletes rows with no
   entry in `audit`/`medication_audit_log`, while `mark_dose` audits every patient
   action, so a purge is unfalsifiable after the fact.

7. **`adherence_summary`'s denominator depends on app usage.** Materialisation is
   pull-only (no server-side scheduler), so days the patient did not open the app
   never become rows and are absent from `total`/`missed`. MISSED preservation
   makes the *recorded* doses honest; the rate still under-reports.

8. **`needs_anchor_repair` is not surfaced.** Not on `ScheduleOut`, no route calls
   it, so a legacy NULL-anchor row reports `active` and silently produces no doses.
   There is also no repair path: `ScheduleEditIn` has no `start_date`, so PATCH on
   such a row 422s.

9. **Timeline dose events are not filtered by medication lifecycle**, so a
   repudiated drug's taken/skipped doses still render.

Items 3–9 are clinical-review findings on pre-existing behaviour, recorded rather
than fixed because each is either a behaviour change needing owner sign-off or new
API surface. Inventing clinical unit conversions or a resume flow unilaterally in
a remediation pass is the wrong call.

---

## Corrections made during this round

Recorded because a remediation log that lists only successes is not a useful
record.

1. **`notifications.title`** — an early code comment claimed it was a fixed
   template with no patient data. `routes/notifications.py` accepts a
   caller-supplied title, so the claim was false. The column is encrypted and the
   comment now states the actual reason.
2. **`alias_source`** — the first implementation reported `base` vs `profile`,
   which mislabelled every `_PARSER_EXTRA_ALIASES` alias as profile-contributed.
   Fixed to report all three layers.
3. **`test_meto_message_encryption`** — asserted the SEC-F11 revision *was*
   `head`, so it broke on any new migration. The same brittleness had already been
   corrected once in the k2 hardening test. Now targets the revision by name and
   additionally verifies the rest of the chain applies on top.
4. **P1-3 scope** — the first regression suite passed against the pre-fix route,
   i.e. it characterised behaviour without discriminating the fix. Replaced with
   legacy-row tests that provably fail without it, and the finding's scope is
   stated honestly above rather than overclaimed.

---

## Standing constraints observed

- No merge to `main`; no production deployment.
- No Azure infrastructure workflow or config modified; no Cloudflare DNS change;
  `app.metocare.me` not cut over.
- `on_decrypt_failure="raise"` retained on SEC-F11's columns, and applied to the
  new NOT NULL columns under the same rule.
- No credentials, real PHI, private logs or test passwords committed. All
  PHI-shaped strings in tests are invented.
