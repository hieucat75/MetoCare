# Clinic SaaS C1 M07 — Appointment Management — Implementation Plan

Baseline: `main` @ `a9b346c` (M06 merged, CI+staging green). Source docs:
`docs/brd/v2.0/m07-appointment.md`, `docs/clinic-saas/REQUIREMENTS_TRACEABILITY.md`
(BR-M07 rows), `docs/clinic-saas/RBAC_MATRIX.md` (Appointments row),
`docs/clinic-saas/MASTER_PROGRAM_PLAN.md` §5/§6, `docs/clinic-saas/CURRENT_ARCHITECTURE_AUDIT.md`
§5, plus a fresh audit of `app/models/care.py` (legacy `Appointment`),
`app/models/appointment.py`/`availability.py` (marketplace `BookingAppointment`/
`DoctorAvailability`), `app/models/clinic.py` (C0/M05/M06 tables).

## 1. Architecture decision (per MASTER_PROGRAM_PLAN §6, already directed)

New table `clinic_appointments` (model `ClinicAppointment`). **Neither legacy
table is touched or reused**: `Appointment` (`care.py`, table `appointments`)
is the doctor-handoff/encounter-flow entity; `BookingAppointment`/
`DoctorAvailability` (T21 scaffold) is the clinic-agnostic marketplace
booking flow, keyed to `users.id` not `doctors.id`, one-directionally linked
from `Consultation`. A third, clinic-scoped table avoids the naming/FK
confusion `CURRENT_ARCHITECTURE_AUDIT.md` §5 already flags between the first
two. No consultation/marketplace code path is modified.

## 2. Schema (additive, new migration `c1_m07_appointments`)

`ClinicAppointment`:
- `clinic_id` FK→clinics RESTRICT, `branch_id` FK→clinic_branches RESTRICT (both required — BRD field table marks both `✓`)
- `patient_id` FK→patient_profiles RESTRICT
- `doctor_id` FK→doctors RESTRICT, **nullable** (BRD: "required trừ dịch vụ không cần bác sĩ")
- `service_id` FK→clinic_services RESTRICT
- `price_snapshot: Numeric(12,2)` (Decimal, snapshotted at create — same precision discipline as M05's `ClinicService.price`)
- `start_time`/`end_time`: `DateTime(timezone=True)`, `end_time` derived from `service.duration_minutes`
- `status`: `ClinicAppointmentStatus` enum, full BRD lifecycle (`pending|confirmed|arrived|in_queue|in_consultation|completed|cancelled|no_show`) — see §4 on why the full enum ships now even though M07 only *routes* a subset of transitions
- `created_by_user_id` FK→users RESTRICT, `created_by_source` enum (`reception|doctor|patient|care_coordinator|marketplace|api_partner` — APPT-01)
- `linked_care_plan_item_id`: bare nullable string, no FK (M11 doesn't exist yet; same bare-reference convention as `AuditLog.resource_id`)
- `cancellation_reason`: nullable Text, `cancelled_by_user_id` FK→users SET NULL, `cancelled_at` nullable
- `reschedule_of_id`: self-FK→clinic_appointments RESTRICT, nullable — "đổi lịch = Cancelled(cũ) + lịch mới liên kết" is modeled as a backward pointer from the new row; the chain of appointments **is** the reschedule history (no separate `reschedule_history` JSON column — same "no redundant history table" discipline as M05's price-audit-via-AuditLog decision)
- `notes`: nullable Text, plain (non-PHI scheduling note — same precedent as legacy `BookingAppointment.notes`; clinical content stays out of scope, belongs to M09 `Encounter.notes`)

Constraints:
- Partial unique index `(doctor_id, start_time)` WHERE `status NOT IN ('cancelled','no_show')` AND `doctor_id IS NOT NULL` — the DB-level double-booking guarantee (AC-M07-02: "2 concurrent requests same slot → exactly 1 succeeds"). Portable across SQLite/Postgres via the existing `postgresql_where`/`sqlite_where` partial-index pattern (`ClinicInvitation`'s pending-email/phone indexes).
- Indexes: `(clinic_id, branch_id, start_time)`, `(clinic_id, doctor_id, start_time)`, `(clinic_id, status)`.

**Scope-bounded double-booking guarantee**: the unique index catches exact-start-time collisions (the real-world case — clinics book against discrete slots derived from `service.duration_minutes`). A service-layer pre-check additionally rejects free-form *overlapping-but-different-start-time* bookings for the same doctor as a best-effort (non-authoritative) UX guard. True DB-level range-overlap exclusion (Postgres `EXCLUDE USING gist`) is SQLite-incompatible and would break the upgrade/downgrade/upgrade-on-SQLite verification step — not used. Documented, not silently gapped.

**Working hours (BR-M07-03)**: branch hours reuse `ClinicBranch.working_hours` (existing free-form `{"mon": "08:00-17:00", ...}` JSON, single-range-or-list-per-weekday, already used with `{}` = unconfigured/permissive by every existing branch fixture — an empty/missing weekday is treated as no restriction, matching that established convention rather than inventing a stricter default). Doctor's own hours = the branch(es) their `ClinicMembership.branch_ids` covers (no new per-doctor schedule model — `DoctorAvailability` is the *other*, untouched marketplace booking system). Override (BRD: "cần quyền và lý do") is Owner/Admin only, with a required reason string.

## 3. RBAC (RBAC_MATRIX.md Appointments row: Owner/Admin/Doctor/Nurse/Reception/CareCoordinator = ✓, Accountant = ✗ — no field-level narrowing needed here, unlike M06)

- **Read** (list/detail): all 6 non-Accountant roles. **Row-level** scoping per this session's explicit instruction ("Doctor chỉ thấy... appointment được phân công"): a caller whose *only* role is `doctor` sees/updates only `doctor_id == own Doctor.id` rows; Owner/Admin/Reception/Nurse/CareCoordinator see the full clinic roster. Branch-scoped memberships (`ClinicMembership.branch_ids` non-empty) are further filtered to their own branches (mirrors M05 `list_services`'s existing branch-scope pattern).
- **Create**: Owner/Admin/Reception (any doctor at clinic) + Doctor (self-`doctor_id` only — US-M07-05, doctor books their own follow-up).
- **Confirm/Cancel/Reschedule**: Owner/Admin/Reception (any) + Doctor (own-assigned only).
- **No-show marking**: Owner/Admin/Reception (manual override) + the idempotent end-of-day job (BR-M07-05), triggered via an Owner/Admin-gated endpoint (no task-scheduler infra exists in this codebase to hook a real cron into — same "manual trigger, idempotent by construction" pattern as nothing comparable exists yet; documented as a gap for ops to wire a real cron/Task Scheduler call against).
- **Working-hours override**: Owner/Admin only, reason required.

## 4. State machine (BRD §7.5, full enum ships now, only a subset gets routes)

`transition_status(db, appointment, new_status, actor_id, reason=None)` is a
single shared, exhaustively-tested function implementing the **complete**
BRD transition table (fail-closed — anything not in the table is rejected +
audited as a denied attempt). M07 only exposes HTTP routes for the
transitions that are its own responsibility: `confirm`, `cancel`,
`reschedule`, `no_show` (manual + job), and `no_show → arrived` (BRD's
explicit late-arrival reception override, described in M07's own state-
machine section, not M08's normal check-in flow). `arrived → in_queue →
in_consultation → completed` are M08 (Check-in/Queue, depends on M07) and
M09 (Encounter)'s own dedicated action endpoints — this milestone does not
build them, but the shared validator already knows those transitions are
valid so M08/M09 can call the same function rather than re-deriving the
table. This is forward-compatibility, not scope creep: no M08/M09 route,
service, or schema is added here.

## 5. Explicitly deferred (documented, not silently dropped)

- **BR-M07-06 / US-M07-02, patient self-booking** — a separate patient-app-
  facing surface (different auth context, anonymized slot-list endpoint).
  Not in this session's explicit "Mục tiêu M07" list (which is entirely
  clinic-console-facing: owner/admin/receptionist/doctor). Fast-follow.
- **APPT-04, reminders** (push/SMS/Zalo/email at 24h/2h marks) — this is
  M15 Notifications' explicit scope per `MASTER_PROGRAM_PLAN.md` §5 ("M15
  depends on M07"). Matches the Stop Gate ("không gửi SMS/email thật").
  `created_by_source` is captured now so M15 has what it needs later.
- **GAP-R6, no-show → Care Gap Queue** — M12 doesn't exist yet (same
  precedent as M06's deferred Care Gap references).
- **Real cron/scheduler for BR-M07-05's end-of-day job** — no task-scheduler
  infrastructure exists in this codebase yet; the job itself is idempotent
  and callable, but wiring an actual periodic trigger is an ops/infra
  concern outside this milestone's backend-code scope.

## 6. Security test matrix (mandatory, per this session's instruction + MASTER_PROGRAM_PLAN §7)

Cross-clinic IDOR on patient/doctor/service/branch ids at create; branch-
scoped role access; full role matrix incl. Doctor row-level scoping;
sequential + concurrent double-booking (DB-level, via the partial unique
index + IntegrityError→controlled-error, same race pattern as every prior
milestone); invalid state transitions (full BRD table, both directions);
cancel/reschedule permission boundaries; inactive `ClinicPatientRelationship`
rejected; inactive `ClinicService` rejected; doctor not member of
clinic/branch rejected; multi-clinic active-tenant-only scoping; revoked
membership loses access immediately; feature-flag-off 503 regression;
audit tenant isolation; list/detail pagination+filtering tenant-scoped;
regression check that no marketplace/`Consultation`/legacy `Appointment`
test breaks.

## 7. Pipeline

Branch `clinic-saas/c1-m07-appointments` (worktree, same pattern as M05/M06)
→ migration/model/schema/service/routes/frontend/docs → targeted tests →
full backend suite → frontend tests/typecheck/build → SQLite
upgrade→downgrade→upgrade (`MCP_DATABASE_URL`) → Codex review loop → fix +
regression tests → PR only with explicit verdict → merge only when 0
P0/P1, no tenant/PHI/correctness blocker, CI green, migration verified, no
required test gap → post-merge main CI + staging confirmation → M07
handoff memory → M08 next.

## Self-check

No Stop Gate touched (no `CLINIC_SAAS` flip, no real tenant/patient data, no
destructive change to `Appointment`/`BookingAppointment`/`Consultation`
schema or code paths — additive-only new table, no marketplace/consultation
merge, no real payment/billing, no real SMS/email vendor). Scope matches
this session's explicit "Mục tiêu M07" list; BRD items outside that list are
deferred and documented, not silently dropped. Proceeding to branch
creation and implementation.
