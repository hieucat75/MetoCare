# Journey 3 — M6 Medication Scheduler / Reminder / Adherence — Backend Evidence

**Milestone:** M6 backend — scheduler + Notification Delivery (§1.1) + adherence (BRD §G).
**Branch:** `feat/patient-platform-journey2` (continues from J3/M5 `1a12932`).
**Date:** 2026-07-31

The reminder/adherence loop over the M5 schedule model: confirmed med → schedule →
idempotent dose materialization → reminder (deterministic + in-app) → taken/skipped → adherence.

## Deliverables
- **`medication_schedule.py`** service: `create_schedule` (confirmed-only: active canonical med,
  owned), `compute_occurrences` (tz-aware, PRN/paused/stopped → none, no history backfill),
  `materialize_due` (idempotent + concurrency-safe via `INSERT … ON CONFLICT DO NOTHING` on the
  unique `idempotency_key`), `deliver_due_reminders` (active-schedule-only, concurrency-safe claim),
  `mark_dose` (taken/skipped, BOLA, no double-act), `sweep_missed`, `pause/stop/edit` (edit =
  new-version supersession + cancel old open doses), `adherence_summary`.
- **`notification_transport.py`** (§1.1): `deliver()` fan-out — deterministic (PHI-free payload) +
  in-app (DB, patient's own record) always; push/email capability-gated (inert until credentialed).
- **API** `routes/medication_schedule.py`: schedule create/list/edit/pause, `reminders/due`,
  dose taken/skipped, adherence — all BOLA-scoped to the caller's own `PatientProfile.id`.

## Independent clinical review (§4) — healthcare-reviewer, verdict NEEDS FIXES → resolved
| # | Sev | Finding | Resolution |
|---|-----|---------|------------|
| P1-1 | Patient safety | Reminders fired for paused/stopped/superseded schedules; pause/stop only cancelled *future* doses, leaving a just-due dose to remind for a discontinued drug | `deliver_due_reminders` joins schedule and requires `active` + not-superseded; pause/stop/supersede now cancel **all** open (pending+notified) doses |
| P1-2 | Clinical | Doses never became `missed` → adherence rate inflated (1/10 taken read as 100%) | `sweep_missed` transitions overdue unacted doses → `missed`; `adherence_summary` counts missed (persisted + effective-overdue) in the denominator |
| P1-3 | Clinical | "confirmed-only" keyed on `lifecycle_status` only | Resolved by-design + documented: a canonical `Medication` row IS patient-confirmed by construction; `lifecycle_status=active` is the correct bar — doctor-verification is a separate stronger tier not required to set a personal reminder |
| P2 | Med | `edit_schedule` bypassed the med check + could resurrect a terminal schedule | edit re-runs the confirmed-only gate + rejects stopped/superseded schedules |
| P2 | Med | invalid IANA tz stored then silently fell back (wrong-time reminders) | tz validated at the API boundary → 422 |
| P2 | Med | concurrent `/reminders/due` could double-deliver | delivery claims each dose via a conditional `UPDATE … WHERE state='pending'`; only the winner delivers |

Reviewer-confirmed sound: idempotency/concurrency substrate (unique key + ON CONFLICT), no PHI in
the deterministic/push payload, BOLA, transaction atomicity. Deferred/documented (non-blocking):
no background worker (pull-based at ENG-RC — push/email + server-side missed-sweep need a worker,
DIST-RC); explicit DST fold policy for non-Vietnam tz (Vietnam has no DST).

## Test evidence
- **New:** `tests/test_medication_schedule.py` — idempotent materialization, PRN-no-doses,
  confirmed-only-rejects-terminal, reminder-delivered+notified, taken+adherence, API create + BOLA
  403, stopped-schedule-does-not-remind, missed-counted-in-adherence (not inflated), edit-rejects-
  stopped, invalid-tz-422.
- Full backend suite green (see commit); ruff clean; single Alembic head.
