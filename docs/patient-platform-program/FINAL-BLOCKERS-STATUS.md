# Final blockers — status after the schedule-lifecycle work

**Branch:** `feat/patient-platform-journey2`
**Date:** 2026-08-06
**Candidate:** `de8a308` (supersedes `4c4b28b`)

## The P0, and why the previous fix could not close it

`P1-3` (commit `a4e23f0`) made the adherence denominator deterministic: every
occurrence the schedule PRESCRIBES in a window is reconciled into existence
before counting, so the rate stopped measuring how often the patient opened the
app. That was correct and necessary, and it is what made this P0 visible — a
deterministic denominator over a schedule with no lifecycle history is
deterministically wrong in the pause case.

Reproduced on the scenario a clinician described. `fixed_daily` 08:00 + 20:00
running from 2026-07-01; a doctor instructs a 10-day hold; the patient pauses
07-10 and resumes 07-20; adherence for 07-01..08-04 returned:

```
expected_count=70  missed_count=70  adherence_rate=0.0  reconciled=True
```

`MedicationSchedule` carried only a CURRENT `status`, and `reconcile_period`
gated on it, so zero-accrual held **only while still paused**. The moment the
patient resumed — did exactly what they were told — the entire hold backfilled as
MISSED. Twenty doses of fabricated non-adherence on a compliant patient, stamped
`reconciled=True`.

The consequence is not a slightly wrong number. A clinician facing an
uncontrolled result plus "50% adherent" concludes the patient is not taking the
drug, and does not escalate therapy that needs escalating.

## Closed

### P0-1 · Persisted lifecycle intervals

New table `medication_schedule_lifecycle_events`: `activated` / `paused` /
`resumed` / `stopped` / `superseded`, with `effective_at`, `actor_id`,
`actor_role`, a closed-vocabulary `reason_code`, a PHI-minimised `note_ref`
(a pointer, never free text), a unique `idempotency_key`, and an audit row per
event. Append-only by contract: a mistake is corrected by appending the
correcting event, so what the patient was told to do, and when, survives.

**Boundary semantics**, stated once because every count downstream depends on
them:

* an active interval is half-open `[opening.effective_at, closing.effective_at)`;
* `paused` / `stopped` / `superseded` `effective_at` is **inclusive of the hold**
  — the patient told to stop "from 08:00" was not asked to take the 08:00 dose;
* `resumed` / `activated` `effective_at` **begins** the next active interval, so
  no dose is lost between two events;
* no expected dose falls inside a paused interval: a pause contributes exactly
  zero to the denominator;
* future occurrences inside a pause are never materialised, and open ones are
  cancelled when the pause is recorded — but a hold never reaches back across its
  own boundary, so an already-overdue dose is still resolved to MISSED rather
  than quietly deleted;
* historical `taken`/`skipped` rows that a later, **backdated** pause encloses are
  **never deleted**. They are reported as `excluded_paused_count`, outside both
  numerator and denominator: the dose was not prescribed in that interval, so it
  cannot be adherence to it — but the patient did assert something, and
  destroying that assertion is the same fabrication in the other direction.

Backdated and future-dated events are validated against the **merged** timeline,
not against the current status, so an event is judged by the overlap it would
actually create. Illegal transitions are refused; an identical repeated command
(a double-tapped "Tạm dừng") records one event rather than two overlapping
intervals. A future-dated hold leaves the schedule running and reminding until it
takes effect, and materialisation is interval-filtered so nothing is created on
the far side.

Migration `j3_m7_sched_lifecycle` backfills one `activated` event per existing
schedule at its `created_at`, plus a closing event at `updated_at` for schedules
currently paused/stopped. That reconstruction can only **under**-state a
historical hold, never invent one, so no patient gains fabricated non-adherence
from the migration itself.

### P1-4 · Backfill floor

`medication_schedules.tracking_start_at`, defaulted to the creation instant and
echoed in every adherence response. `start_date` is client-supplied and states
when the **prescription** began; for an imported paper prescription that is
routinely months before MetoCare saw the patient, and backfilling from it
converted "we were not observing" into "you did not take it" — up to 30×N MISSED
rows and 0.0 % on the first screen a patient ever saw.

The floor is instant-level, not date-level: a prescription imported at 13:00 must
not count this morning's 08:00 dose as missed. **Retrospective adherence is
opt-in** — a caller with real historical evidence may set `tracking_start_at`
earlier, and the value applied is always visible in the response.

### P1-3 · Grace policy

The flat 4 h `_MISSED_AFTER` applied to every cadence alike is replaced by
versioned per-cadence classification windows (`grace-1.0.0`):

| cadence | window |
|---|---|
| multiple-times-daily | 4 h |
| once-daily | 12 h |
| alternate-day / interval < 7 d | 24 h |
| weekly (interval ≥ 7 d, or a single weekday) | 48 h |
| cyclic | 12 h (rest days come from the recurrence, not from widening the window) |
| PRN | never missed |

These are **adherence-event classification windows for a tracking app**. They are
not dosing advice, not a therapeutic window, and no clinical decision follows
from the boundary. The invariant is the dosing cadence, not the drug: a window
may never run into the next scheduled dose of the same schedule. The policy
version and the window applied are surfaced in every response.

### P1-3 · Missed-dose correction

MISSED is assigned by a clock — nobody asserted it — and `due_doses_query` was
only ever called with `(pending, notified)`, so a MISSED dose appeared in no list
and the client could not obtain its id. An adherence figure a patient cannot
correct is not a measurement of the patient.

`GET /patients/{id}/doses/missed` and `POST /patients/{id}/doses/{dose_id}/correct`:

* only a MISSED dose is correctable, and a correction cannot be corrected — 422,
  never a silent overwrite;
* the machine's original verdict is preserved in `corrected_from_state`, so a
  100 % figure containing late self-reports is distinguishable from one that
  never needed correcting;
* actor, role, reason and both states go to the immutable audit trail;
* ownership is enforced in the service, not only at the route;
* roles are an **allow-list** (`patient` only at ENG-RC). Clinician-entered
  correction changes a clinical record attributed to the patient and needs its
  own consent and audit story first; the allow-list makes widening it a
  deliberate, reviewable act;
* reasons are a closed vocabulary — free text would put the patient's account of
  their own symptoms into an audit trail built to avoid PHI;
* every string records what happened. Nothing advises whether to take a late
  dose, which is a clinical decision this app does not make.

Correction stays available for a dose missed under a schedule that has since been
stopped or superseded — that is the one a patient most wants to fix.

### P1-5 · Cancelled/superseded counts, and the frozen edit gap

Reconciliation now walks the whole **schedule lineage**. Previously the old
version was stopped and superseded, which `reconcile_period` refused forever, so
whatever dormancy gap existed at the moment of an edit was sealed permanently
while the new version backfilled the same days a second time under its own id.
An edit re-describes a therapy; it does not end one.

`excluded_paused_count` and `excluded_cancelled_count` are derived from lifecycle
data and **partition** the excluded set (a hold is the more specific fact and
wins). Exclusions accumulate over instants rather than being summed from two
directions, so a three-day backdated hold over three recorded doses excludes
three, not six. Every prescribed dose in a window lands in exactly one bucket:

```
expected_count + excluded_paused_count + excluded_cancelled_count
    == doses the recurrence prescribes in the window at or after the floor
```

### P0 · Crypto smoke now runs in production

`azure-production.yml` had no crypto step, so the mis-rotation scenario was
undetected in the environment where it matters most. Added **post-migration,
pre-revision**: if the deployed key cannot read what is at rest, no revision is
created and the currently-serving revision keeps running. `--allow-production`
(the script refuses a production database without it, via an allow-list, so an
unset or misspelled `MCP_ENV` fails closed), delete-before-create (a reused job
runs the previous image and secrets and would validate the OLD key), a polling
loop where a timeout **fails**, rollback instructions for the on-call, and
secrets by `secretref:` only. Static tests pin the wiring, because the only other
way to learn it is wrong is to deploy production.

## Frontend TypeScript — attribution

The previous status recorded "`origin/main` 1761 errors, this branch 1984 (+223)"
and no gate. Like-for-like baseline (same Node, same npm, same tsconfig;
`origin/main` in an isolated worktree sharing `node_modules`):

| config | `origin/main` | candidate before | candidate now |
|---|---|---|---|
| `tsconfig.build.json` (production source) | 0 | 0 | **0** |
| `tsconfig.json` (incl. tests) | 1761 | 1986 | **0** |

**Candidate-added production-source errors: 0**, before and after. Of the 225
candidate-added errors under the full config, 216 were the pre-existing
jest-namespace class (new test files, same missing types) and 9 were genuine —
stale `ScheduleAdherence` fixtures that no longer matched the contract.

The root cause of the whole 1761 was one missing package: `@types/jest` was never
installed, so every `describe`/`test`/`expect` in every test file was an
unresolved name and the real errors sat buried under 1600+ of them. Installing it
and fixing the genuine remainder brings the full project to zero, which is what
made a gate possible. `ci.yml` now runs `tsc` against **both** configs — the build
config is what ships, and the full config catches a test that has stopped
typechecking against the client it exercises, which is how a stale fixture keeps
asserting a contract the server no longer sends.

No baseline exceptions are claimed. Nothing was suppressed, excluded or
`@ts-expect-error`'d to reach zero.

## Gates

| gate | result |
|---|---|
| CI-1 (`pytest -m "not integration"`) | 4168 passed, 0 failed, 11 skipped, exit 0 |
| CI-2 (17 integration modules, one database each, real Postgres) | 226 tests, rc=0, no module collected 0 |
| Migration round-trip | upgrade → downgrade → re-upgrade on real Postgres; backfill verified against seeded active/paused/stopped rows |
| Alembic heads | single head `j3_m7_sched_lifecycle` |
| ruff | clean |
| Frontend | 658 jest / 57 suites; `tsc` 0 on both configs; lint 0 errors; production build succeeds |
| Mobile | clean `npm ci` (1077 packages); `tsc` 0; lint 0 errors; 145 jest / 29 suites; Expo production export web + iOS + Android |
| Merge | `--no-ff` onto `origin/main` clean, 0 conflicts |

## Not in scope / owner decisions

* **Clinician-entered dose correction** is deliberately not enabled — see the
  role allow-list above.
* **Retrospective adherence** for prescriptions predating MetoCare is opt-in and
  requires a caller with real historical evidence; no UI currently sets it.
* Production deploy is **not** performed by this work. The crypto-smoke wiring is
  repo-controlled and statically tested; its first real execution is the next
  production deploy the owner runs.
