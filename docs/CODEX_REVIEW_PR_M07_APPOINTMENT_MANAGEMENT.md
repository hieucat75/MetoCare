# Codex Review — Clinic SaaS C1 M07 Appointment Management

**Reviewer:** Codex (read-only, `codex exec -s read-only`)
**Date:** 2026-07-10
**Branch:** clinic-saas/c1-m07-appointments
**Base:** main @ `a9b346c`

---

## Pre-review self-fix pass

Before the first Codex round, an independent read-through of the initial
implementation (produced by a background implementation agent working from
`M07_IMPLEMENTATION_PLAN.md`) found two gaps the agent itself flagged for a
second look, fixed prior to requesting Codex review:

1. **Branch scoping not enforced for the caller** — branch-scoped staff
   (Reception/Nurse/Care Coordinator) could create, list, view, and mutate
   appointments at any branch of the clinic; only the assigned doctor's own
   branch scope was checked. Fixed by applying the exact
   `TenantContext.branch_ids`-derived pattern M05's `list_services` already
   established, wired into create/list/detail/every mutation route.
2. **Denied-transition audit rows not persisted** — routes only commit on
   the success path; `get_session()`'s implicit rollback-on-exception
   silently discarded the flushed-but-uncommitted denial audit entry.
   Fixed by committing the denial record immediately in `transition_status`,
   before raising (same precedent as `clinic_membership.accept_invitation`'s
   expired-token path).

## Round 1 — Initial security review

**Scope:** tenant isolation/BOLA (clinic + branch), double-booking/race
safety, state-machine correctness against BRD §7.5, RBAC completeness,
money precision, PHI/audit-log leakage, BR-M07-04 cancellation-policy flag,
BR-M07-05 no-show job idempotency, frontend capability-vs-authorization
discipline, test coverage against the plan's security matrix, legacy-system
non-regression.

**VERDICT: FAIL**

P0: 0 · P1: 2 · P2: 1

**Findings:**

1. **P1** (`app/services/clinic_appointments.py` — `transition_status`,
   `cancel_appointment`, `reschedule_appointment`) — free-text `reason`
   values (cancellation reasons, override reasons) were written verbatim
   into `AuditLog.details`, violating the established "AuditLog never
   stores sensitive content" contract (`governance.py`). A receptionist
   cancelling with a clinically-descriptive reason would make that PHI
   durable in an audit JSON blob.
2. **P1** (`app/services/clinic_appointments.py` — `run_no_show_job`) — the
   job selected all CONFIRMED candidates, then mutated each ORM row in a
   loop with no conditional update/lock. Two genuinely concurrent job
   invocations (double-click, overlapping ops retry) could both read the
   same row before either committed, both flip it, and both record a
   transition audit — duplicated side effects even though the final status
   value happened to be correct. Not genuinely idempotent under a race,
   only sequentially idempotent.
3. **P2** (`tests/api/test_clinic_appointment_management_m07_api.py`) — the
   pre-review branch-scope regression tests covered create/list only; they
   would not catch a regression removing the branch-scope check from the
   detail or mutation (confirm/cancel/reschedule/no-show/arrived-override)
   routes specifically.

**Checked, no issue:** cross-clinic create validation (branch/service/
patient-relationship/doctor-membership all checked against the path clinic);
doctor-only row scoping on list/detail/mutations; the partial unique index's
`postgresql_where`/`sqlite_where` syntax; `price_snapshot` is `Decimal`/
`Numeric(12,2)` end-to-end; frontend gating is UX-only with real backend
authorization; no legacy `care.py`/`appointment.py`/`availability.py`/
`consultation.py` file appears in the diff.

---

## Fixes applied

| Fix | Detail |
|---|---|
| P1 (PHI in audit) | `transition_status`'s success-path audit `details` now records `reason_provided: bool`, never the reason text. The cancellation-policy-violation audit record dropped its duplicated `"reason"` key entirely. The verbatim cancellation reason remains durably stored on the appointment row itself (`cancellation_reason`, already the correct non-audit-log location — same discipline `DoctorReviewDecision` uses for PHI-bearing free text). No-show/arrived-override reasons have no dedicated column and, by the same discipline, are not durably retained as free text anywhere by this milestone — only that a reason was supplied. |
| P1 (no-show job race) | `run_no_show_job` now issues a single conditional `UPDATE ... WHERE id=X AND status='confirmed'` per candidate (checked via `rowcount`), the same atomic-conditional-update pattern `accept_invitation` uses for its single-use-token race — instead of the ORM SELECT-then-mutate-each-row loop. Only the invocation that actually flips a given row records its audit entry and counts it; a losing concurrent call sees `rowcount == 0` and silently skips, exactly as if it had already run. |
| P2 (test gap) | Added `test_branch_scoped_membership_cannot_view_or_mutate_other_branch`, directly asserting 403 on both the detail route and a mutation route (confirm) for a branch-scoped caller against an appointment at a different branch. |

Verification after fixes: 51 targeted tests green (47 original + 3 pre-review
fix regressions + 1 new), full backend suite green.

---

## Round 2 — Follow-up verification review

(recorded below once complete)
