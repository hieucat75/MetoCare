# Codex Independent Review — Clinic SaaS C1 M08 (Check-in & Queue)

Reviewer: OpenAI Codex CLI (`codex exec`, read-only sandbox, model gpt-5.6-terra,
reasoning effort high), adversarial security+correctness prompt over the full
`a10e675..HEAD` diff. Convention: full round history committed (findings are never
silently dropped) — same as M05–M07.

## Round 1 — FAIL (0 P0, 5 P1, 1 P2) → fixed in `56c6eb8`

| # | Sev | Finding | Fix |
|---|---|---|---|
| 1 | P1 | `_is_doctor_only` exact-set test let a `doctor+care_coordinator` membership skip own-entry enforcement (call/start/complete any doctor's entry) | `_is_doctor_scoped` = holds `doctor` AND no manage role; regression test with `["doctor","care_coordinator"]` |
| 2 | P1 | Missed-call count unbounded past `max_missed_calls` via call→missed cycles | Hard atomic bound: `missed_call_count < max` predicate inside the conditional UPDATE + fail-fast 400; reception resolves via call-again or leave |
| 3 | P1 | Whitespace-only priority `reason` satisfied `min_length=1` | Schema strips before validating + defensive service re-check |
| 4 | P1 | `set_priority` was ORM read-modify-write — concurrent toggles last-write-win with stale audit from/to | Conditional UPDATE predicated on loaded `is_priority`; loser 409 |
| 5 | P1 | Tenant-editable `queue_config` values used untyped — a string value 500s check-in | `_coerce_int` type-sanitizing + bounds with fail-safe defaults |
| 6 | P2 | WalkInModal initial fetches had no rejection handling | `.catch` → `PageError` state |

## Round 2 — FAIL (0 P0, 3 P1, 0 P2) → fixed in `4d44756`

5/6 round-1 fixes independently re-verified good; config fix incomplete + 2 new:

| # | Sev | Finding | Fix |
|---|---|---|---|
| 1 | P1 | `queue_config` as a non-dict JSON value (string/list/bool) still 500s; out-of-range ints were clamped (inventing a config) instead of reverting to defaults | `isinstance(dict)` guard on the raw value; out-of-range → default |
| 2 | P1 | `GET /queue/display` ignored the doctor own-entry scoping every other read applies | Same `_is_doctor_scoped` filter plumbed through `display_queue` |
| 3 | P1 | `transition_status` (M07 shared validator) was ORM read-then-set — an M08 check-in racing an M07 cancel could last-write-win into `cancelled`+active-queue-entry inconsistency | Conditional `UPDATE … WHERE status = <expected>` (rowcount-checked); stale loser gets a controlled error; M07 suite re-verified 51/51 |

## Round 3 — FAIL (0 P0, 2 P1, 1 P2) → fixed in `3960f3a`

All 3 round-2 fixes verified (incl. explicit confirmation that `db.expire` does not
discard cancel/reschedule attribute writes).

| # | Sev | Finding | Fix |
|---|---|---|---|
| 1 | P1 | The stale-transition loser raised generic `ClinicAppointmentError` → mapped 400 (validation) instead of 409 (conflict), so clients never trigger conflict-reload | New `ClinicAppointmentConflictError`, mapped to 409 before the generic 400 in BOTH route modules (M07's 6 mutation routes + M08's) |
| 2 | P1 | Rejected check-ins (cancelled/completed/no-show/in-queue/in-consultation appointment, or outside window) left no audit trail | `clinic_queue_checkin_denied` audit (PHI-free reason code) committed before the error propagates |
| 3 | P2 | `skip_overlap_precheck` was an unconstrained public parameter — a future scheduled-booking caller could bypass the overlap guard | Hard-bound to `created_by_source == walk_in` |

Also this round (self-caught from the diff stat, not a Codex finding):
`frontend/tsconfig.tsbuildinfo` had slipped into the branch (build artifact,
M05-incident class) — reverted to the merge-base version.

## Round 4 — FAIL (0 P0, 2 P1, 1 P2) → fixed in `c8f3715`

All 3 round-3 fixes verified.

| # | Sev | Finding | Fix |
|---|---|---|---|
| 1 | P1 | `_deny_checkin` committed the caller's whole session — a clock jump between walk-in's two `utcnow()` reads could persist the half-created walk-in appointment alongside its 400 | Rollback-FIRST pattern (shared `record_entry_denial` helper): capture audit values → `db.rollback()` → audit → commit exactly one row |
| 2 | P1 | Missed-call-cap 400 (service) and doctor over-cap-call 403 (route) had no denial audit | Both now write PHI-free denial rows (`missed_call_cap` / `over_missed_call_cap_doctor` reason codes) |
| 3 | P2 | Priority could be stamped (with free-text reason) onto terminal entries, incl. via a race with complete/leave | Active-status pre-check (audited `clinic_queue_priority_denied`) + active-status predicate repeated inside the conditional UPDATE |

## Round 5 — FAIL (0 P0, 2 P1, 0 P2) → fixed in `a9caea9`

All round-4 fixes verified ("denial callers have no legitimate pending writes except
the walk-in appointment that must be discarded"; expired-entry access after rollback
confirmed clean).

| # | Sev | Finding | Fix |
|---|---|---|---|
| 1 | P1 | Doctors were denied check-in/leave/priority outright, contradicting the RBAC matrix's `Doctor ✓ (own)` cell | Doctor own-scoped check-in (own appointment via `doctor_profile_id` match, incl. NULL-doctor appointments = not own), leave, priority; 403 on others'; walk-in stays reception-only (US-M08-02 intake has no "own" reading before an entry exists); FE gating updated |
| 2 | P1 | Flipping `queue_config.number_reset_scope` mid-day restarted a new counter identity at 1 → duplicate numbers within the same uniqueness scope (e.g. doctor A twice #1) | New counter identities seed from the day's max issued `queue_number` within exactly their own uniqueness scope (per-doctor filter for `branch_doctor_day`); steady-state per-doctor reset preserved (fresh doctor still starts at 1); cross-scope historical collisions documented as unavoidable without renumbering issued tickets |

## Round 6 — FAIL (0 P0, 2 P1, 0 P2) → fixed in the following commit

Both round-5 fixes verified (doctor check-in guard rejects other doctors' AND
NULL-doctor appointments; seed predicates correct for all three scopes).

| # | Sev | Finding | Fix |
|---|---|---|---|
| 1 | P1 | Cross-identity allocation race at a mid-day scope flip: an uncommitted old-scope allocation is invisible to the new counter's seed MAX → two identical tickets (the R5 fix's own documented residual, judged not acceptable) | `check_in_appointment` takes the clinic row `FOR UPDATE` for the whole allocation — check-ins and clinic-row config UPDATEs are now mutually exclusive until commit on Postgres (SQLite: no-op, single-writer); config is read only under the lock |
| 2 | P1 | Doctor own-priority unusable in UI: the "Ưu tiên" button rendered via `canAct` but `PriorityModal` only mounted under `canManage` — click did nothing | Modal mounts under `canAct` (walk-in modal stays `canManage`) |

## Round 7 — FAIL (0 P0, 1 P1, 1 P2) → fixed in the following commit

Both round-6 fixes verified (clinic-row FOR UPDATE precedes config reads on every
allocation path incl. walk-in delegation, no inverse counter→clinic lock ordering;
priority modal mounts for canAct).

| # | Sev | Finding | Fix |
|---|---|---|---|
| 1 | P1 | **M07's** `_is_doctor_only` exact-set guard (the same class as M08 R1, but in the merged M07 routes) let a `doctor+care_coordinator` membership read AND mutate any doctor's appointments — surfaced to the browser by M08's CheckInPanel | M07's predicate hardened to match M08's `_is_doctor_scoped` rule exactly (doctor without owner/admin/receptionist/nurse → row-scoped); M07 regression test with `["doctor","care_coordinator"]` (list scoped, detail 403, confirm 403); full M07 suite re-verified green |
| 2 | P2 | `frontend/tsconfig.tsbuildinfo` re-entered the diff (regenerated by local FE test/build runs after the round-3 revert) | Restored to merge-base again; final pre-PR diff check added to the process |

## Round 8 — FAIL (0 P0, 2 P1, 1 P2) → fixed in the following commit

Round-7's doctor+care_coordinator predicate fix verified on M07 list/detail/mutation.

| # | Sev | Finding | Fix |
|---|---|---|---|
| 1 | P1 | **M07** reschedule accepted an arbitrary `payload.doctor_id` from a doctor-scoped caller — rescheduling their own appointment ONTO another doctor bypassed the self-booking boundary | Target doctor must be omitted or the caller's own profile (403 otherwise); M07 regression test (retarget 403, self 201) |
| 2 | P1 | Reverting `number_reset_scope` (A→B→A) resumed the OLD scope's stale counter below numbers the interim scope issued — duplicate tickets | Allocation (already fully serialized by the R6 clinic-row lock) now reconciles EVERY number: `max(counter.last_number, scope's issued max) + 1`; regression test for the exact A→B→A scenario |
| 3 | P2 | CheckInPanel fetched browser-local "today" only — a valid late-night prior-day appointment disappeared after midnight despite the backend's ±12h window | Fetch window widened to ±1 day; backend enforces the real window |

## Round 9 — (recorded when complete)

Operational notes: round 6's first attempt aborted on a Codex usage-limit window and
was re-run after reset. The round-1 first attempt required upgrading the Codex CLI
0.137.0 → 0.144.1 (`gpt-5.6-terra` requires a newer CLI).
