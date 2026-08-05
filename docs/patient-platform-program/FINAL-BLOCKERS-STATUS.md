# Final blockers — status after P1-3 / P1-7 and four fresh reviews

**Branch:** `feat/patient-platform-journey2`
**Date:** 2026-08-05

## Closed

### P1-3 · Deterministic adherence denominator (`a4e23f0`)
Reproduced first: twice-daily schedule 2026-07-01..08-05 prescribes **70** doses;
a patient dormant since 07-06 had **14** persisted rows (horizon 7 days) — 56
doses, 80% of therapy, invisible. Architecture A (deterministic on-read
reconciliation) chosen because there is no scheduler in this app, materialization
is already idempotent on `idempotency_key`, and `compute_occurrences` already
derives from a persisted timezone/DST-safe anchor. The only missing piece was the
window.

`expected_occurrences_in_window` + `reconcile_period` + a period-scoped
`adherence_summary`. Semantics versioned `adherence-2.0.0`. +30 tests, verified
discriminating (removing reconciliation fails 8+, including every dormancy case).

### P1-7 · Post-deploy PHI crypto smoke (`d4e30a4`)
Reproduced first: wrong-but-well-formed key → boot validation PASSED, `/health`
PASSED, authenticated encrypted read raised `UndecryptablePHIError`.
`scripts/crypto_smoke.py` as a one-shot job (not an endpoint — an HTTP route that
decrypts on demand is a crypto oracle). Verified on real PostgreSQL, four states:
correct→pass(0), **wrong→fail(1) `legacy_row_undecryptable`**, missing→fail(1),
restored→pass(0). +12 contract, +6 Postgres tests.

## Fixed from the reviews

- **CRITICAL (SRE):** the deploy step referenced `$MIGRATE_JOB`, `$ACA_ENV`,
  `$IMG` — none defined in that step's shell. It would have failed EVERY deploy
  without ever invoking the smoke, and indistinguishably from a real wrong-key
  failure, which is how a gate gets muted. Rebuilt locally, `$ENV_NAME`,
  delete-before-create (a reused job validates the PREVIOUS key), and a post-loop
  check so a timeout FAILS instead of passing silently.
- **P1 (security):** environment gate was a deny-list and failed open on an
  unset/misspelled `MCP_ENV` — now an allow-list.
- **P1 (security):** empty/all-NULL legacy tables made the mis-rotation detector
  a silent no-op reporting pass. Now fails `no_legacy_rows_to_verify`, and
  per-entity counts are emitted so "verified 5 rows" is distinguishable from
  "verified 0". Added `ORDER BY id` so sampling is deterministic.
- **P0-2 (clinical):** `reconciled` was `backfilled or denominator > 0`, i.e.
  True whenever any stale row existed — exactly the unreconciled case it marks. A
  schedule stopped after one app visit reported `rate=1.0, reconciled=True` for a
  month in which ~30 doses were prescribed and 7 taken. Now `reconciled =
  backfilled`, and an unreconciled period returns `adherence_rate=None`.

## OPEN — blockers

### P0-1 · A pause is retroactively converted into missed doses on resume
Pause intervals are **not persisted** — `MedicationSchedule` has `status` only, no
`paused_at`/`resumed_at` and no pause table (verified). `reconcile_period` gates
on CURRENT status, so zero-accrual holds only while still paused. Resume, and the
whole window backfills as MISSED.

Scenario: doctor instructs a 10-day hold; patient pauses 07-10, resumes 07-20.
Adherence for 07-01..08-04 sees `status == active`, backfills all 70 doses, and
the 20 doses of the instructed hold become MISSED. ~29 points of fabricated
non-adherence on a patient who followed instructions — and a clinician facing an
uncontrolled result plus "50% adherent" blames compliance and does not escalate
therapy that needs escalating.

Needs a schema change (pause-interval table or from/to columns) plus subtraction
in `expected_occurrences_in_window`. Interim: any window overlapping a pause must
return `reconciled=False`. `tests/test_adherence_denominator.py::test_resuming_restores_reconciliation`
currently encodes the defect as expected behaviour and must be rewritten.

### P1-4 · Backfill has no floor at `created_at`
`start_date` is client-supplied. A patient onboarding with "I started this drug in
March" gets up to 30x N MISSED rows on first read and 0.0%. No observation must
never be encoded as missed. Floor at `schedule.created_at`, or add a distinct
`tracking_start_date`.

### P1-3 · Flat 4h grace, and a MISSED dose is uncorrectable
`_MISSED_AFTER` is applied identically to weekly, alternate-day and 4x/day
schedules. A weekly GLP-1 is MISSED at noon Monday though the label permits days.
And `due_doses_query` is only ever called with `(pending, notified)`, so a MISSED
dose appears in no list and the client cannot obtain the `dose_id` to correct it.

### P1-5 · `excluded_cancelled_count` is structurally always 0; edits freeze the gap
Every dose carries its own schedule's version, so the exclusion branch is
unreachable. Separately, an edit supersedes the schedule and `reconcile_period`
then refuses it forever, so the dormancy gap at edit time can never be backfilled
— repeatable.

### P1-6 · Clients contradict the response
Web renders "kể từ {earliest start_date}" over what is now a 30-day figure;
neither client reads `reconciled`, `period_start` or `period_end`.

### P0 · Crypto smoke does not run in production
`azure-production.yml` has no crypto-smoke step. The mis-rotation scenario is
undetected in production, which is the environment where it matters most.

## Gates (before the review fixes)
CI-1 exit 0 · CI-2 17 modules / 226 tests exit 0 · ruff clean · mobile tsc clean,
jest 138/138 · frontend jest 644/644 · single Alembic head · `--no-ff` merge onto
`origin/main` clean (0 conflicts), merged tree CI-1 exit 0 and CI-2 226 tests.

Frontend `tsc` is not a CI gate; `origin/main` already has 1761 errors and this
branch 1984 (+223, concentrated in added test files, same pre-existing `jest`
namespace class).
