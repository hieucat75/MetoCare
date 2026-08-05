# M08 — Check-in & Queue: Implementation Plan (Clinic SaaS C1)

Status: plan, self-checked against `docs/brd/v2.0/m08-checkin-queue.md` before implementation.
Baseline: `main @ a10e675` (M07 merged). Worktree `/Users/pth/Developer/metocare-worktrees/c1-m08-checkin-queue`,
branch `clinic-saas/c1-m08-checkin-queue`. Untracked-plan-doc convention (same as M05–M07: never committed).

## 1. Audit findings & boundaries (pre-implementation, per pipeline step 1)

- **No existing check-in/queue system.** The only "queue" in the codebase is the AI review
  queue (`doctor_review.py` `GET /queue`, `doctor_portal.py` unified queue) — a completely
  different concept (AI recommendations pending doctor review). Untouched.
- **Three appointment systems exist; only `ClinicAppointment` is ours.** Legacy `Appointment`
  (care.py, encounter handoff) and marketplace `BookingAppointment`/`Consultation` are
  explicitly out of scope (M07 precedent, `CURRENT_ARCHITECTURE_AUDIT.md` §5). Zero changes to them.
- **M07's shared state machine is the integration point.** `clinic_appointments.transition_status`
  already validates the full BRD §7.5 table fail-closed, including `arrived→in_queue→in_consultation→completed`
  which M07 deliberately left unrouted for M08/M09. M08 calls this validator — no parallel machine
  for appointment status.
- **BRD §7.5 has no backward transitions** out of `arrived`/`in_queue`. Therefore "patient leaves
  queue" is terminal at the **queue-entry** level only; the appointment row stays at its last
  valid status. Extending the appointment machine beyond BRD would be a Stop-Gate-#10 deviation — not done.
- **`Clinic.queue_config` JSON column already exists** (C0, DATA_MODEL.md §1) — the natural home
  for BR-M08-03 tenant numbering config. No ALTER needed on `clinics`.
- **`Encounter` (care.py) is legacy/M09 territory.** M08 does NOT create Encounter rows.
  "Start consultation" records queue-entry + appointment state only (readiness/handoff for M09).

### Boundary definitions

| Concept | Representation |
|---|---|
| Appointment | `ClinicAppointment` row (M07) |
| Patient arrival / check-in | appointment transitions `pending/confirmed → … → arrived → in_queue` (chained, each audited via shared validator) + a new `ClinicQueueEntry` row |
| Queue entry | new `clinic_queue_entries` row (this milestone) |
| Consultation start | queue entry `called → in_consultation` + appointment `in_queue → in_consultation`. **No Encounter created** — M09's job |
| Completion | queue entry `in_consultation → completed` + appointment `in_consultation → completed` (operational close-out; clinical notes are M09) |
| Cancellation/no-show | stays M07's surface (cancel / no-show / arrived-override routes). M08 adds nothing there |
| Leave queue | queue entry terminal `left`; appointment untouched (BRD has no backward transition — documented limitation) |

## 2. Schema (additive only, migration `c1_m08_queue`)

### `clinic_queue_entries` (model `ClinicQueueEntry`)

- `id` UUID PK, `created_at/updated_at` (TimestampMixin)
- `clinic_id` FK clinics RESTRICT, indexed, NOT NULL
- `branch_id` FK clinic_branches RESTRICT, indexed, NOT NULL
- `patient_id` FK patient_profiles RESTRICT, indexed, NOT NULL
- `appointment_id` FK clinic_appointments RESTRICT, NOT NULL, **UNIQUE** (hard invariant: one queue
  entry per appointment, ever — BR-M08-01 makes walk-ins create an appointment too, so every entry has one)
- `doctor_id` FK doctors RESTRICT, nullable (mirrors appointment's nullable doctor)
- `service_date` Date NOT NULL (clinic-local operational day, see §5 ADR-2)
- `queue_number` Integer NOT NULL
- `status` String(16), default `waiting` — enum `ClinicQueueEntryStatus`: `waiting|called|in_consultation|completed|left`
- `is_priority` Boolean default False; `priority_reason` Text nullable (verbatim reason lives HERE,
  not in audit details — M07 R1 P1 discipline); `priority_set_by_user_id` FK users SET NULL nullable
- `missed_call_count` Integer default 0 NOT NULL
- `source` String(16) — `scheduled|walk_in`
- `checked_in_by_user_id` FK users RESTRICT NOT NULL
- timestamps: `checked_in_at` NOT NULL, `called_at` nullable (last call), `consultation_started_at`,
  `completed_at`, `left_at` nullable — BR-M08-05 wait time = `consultation_started_at - checked_in_at`, stored data for M16

Indexes:
- `ix_clinic_queue_entries_clinic_branch_date (clinic_id, branch_id, service_date)`
- `ix_clinic_queue_entries_clinic_status (clinic_id, status)`
- **`uq_clinic_queue_entries_active_patient`** partial unique `(clinic_id, patient_id)`
  WHERE `status IN ('waiting','called','in_consultation')` (postgresql_where + sqlite_where, ClinicInvitation
  pattern) — DB-enforced "one active queue entry per patient per clinic" policy
- plain UNIQUE on `appointment_id` — DB-enforced anti-double-check-in (the INSERT is the serialization
  point; concurrent loser gets IntegrityError → controlled 409, whole tx incl. its appointment
  transition rolls back)

### `clinic_queue_counters` (model `ClinicQueueCounter`) — BR-M08-03

- `id` PK, `clinic_id` FK RESTRICT NOT NULL, `branch_id` FK RESTRICT NOT NULL,
  `scope_key` String(64) NOT NULL (e.g. `''` or `doctor:<id>` per reset scope), `counter_date` Date NOT NULL,
  `last_number` Integer NOT NULL
- UNIQUE `(clinic_id, branch_id, scope_key, counter_date)`

Allocation algorithm (PostgreSQL-safe, rollback-safe):
1. `UPDATE clinic_queue_counters SET last_number = last_number + 1 WHERE <keys> RETURNING last_number`
   (SQLAlchemy `.returning()`, supported by Postgres and SQLite ≥3.35). Postgres row lock serializes
   concurrent check-ins until commit → **no duplicate numbers**; on rollback the increment rolls back with the tx.
2. If no row: INSERT `last_number=1` inside a **SAVEPOINT** (`db.begin_nested()`); on IntegrityError
   (concurrent first-insert race) roll back the savepoint only (M06 rollback-safety lesson: never
   `db.rollback()` mid-composed-transaction) and retry step 1 once.

No cross-scope DB backstop index is possible (the reset scope is tenant-configurable), so the counter
row lock is the authoritative serializer — documented, not silently assumed.

## 3. State machine (queue entry) — fail-closed

```
waiting → called                    (call — BR-M08-04)
called  → waiting                   (missed call: missed_call_count += 1 — BR-M08-04 "gọi nhỡ")
called  → in_consultation           (start consultation; syncs appointment in_queue → in_consultation)
waiting|called → left               (leave/remove — reception-side handling)
in_consultation → completed         (syncs appointment in_consultation → completed)
```

- Implemented as `_VALID_QUEUE_TRANSITIONS` dict + a single validator, same shape as M07.
- **Every entry transition is an atomic conditional `UPDATE … WHERE id=? AND status=<expected>`
  checked via `rowcount`** (M07 no-show-job / accept_invitation pattern) — two staff
  calling/skipping/starting the same entry concurrently: exactly one wins, loser gets a controlled 409.
  Never rely on the ORM read-then-set for these.
- Denied transitions: audit row (`clinic_queue_transition_denied`, outcome=denied) committed before the
  error propagates — exact M07 `transition_status` denial-durability precedent.
- Missed-call cap: `missed_call_count >= max_missed_calls` (config, default 3) ⇒ entry is flagged
  (computed `requires_reception_action`) and further `call` is limited to Owner/Admin/Reception/Nurse
  (doctor can no longer call it) until reception resolves (call again or `leave`). BR-M08-02: the system
  never auto-escalates/auto-prioritizes — priority is exclusively a human action with a reason.

Appointment-status sync always goes through `clinic_appointments.transition_status` (shared validator,
audited per transition). Check-in chain by current status: `pending → confirmed → arrived → in_queue`,
`confirmed → arrived → in_queue`, `arrived → in_queue` (covers M07's no-show→arrived override output).
Any other appointment status (cancelled/completed/no_show/in_queue/in_consultation) ⇒ controlled 400 —
cancelled/completed/no-show appointments can never check in (validator enforces; explicit tests).

## 4. API surface (`/api/v1/clinics/{clinic_id}/queue`, flag-gated `require_clinic_saas_enabled`)

RBAC (RBAC_MATRIX.md M08 row: Owner ✓ Admin ✓ Doctor ✓(own) Nurse ✓ Reception ✓ CC R Accountant ✗):

- `_READ_ROLES` = Owner/Admin/Doctor/Nurse/Reception/CC; `_MANAGE_ROLES` = Owner/Admin/Reception/Nurse
- Doctor-only callers: row-scoped to entries with their own `doctor_profile_id` (M07 `_is_doctor_only`
  pattern) for list/detail/call/start/complete; never walk-in/leave/priority/others' entries.
- Every route: `assert_path_clinic_matches_tenant` + `require_clinic_roles` + `_assert_actor_branch_scope`
  on the entry/payload branch (branch scope ALWAYS derived from `TenantContext.branch_ids`, M05/M07 pattern).
  Multi-clinic users act through their active tenant context only; revoked/suspended membership is already
  cut off by `get_tenant_context` (regression-tested for the new resource type).

Routes:
| Route | Roles | Notes |
|---|---|---|
| `POST /clinics/{cid}/appointments/{aid}/check-in` | manage | from valid appointment (§3 chain); allocates number; creates entry (US-M08-01, BR-M08-01) |
| `POST /clinics/{cid}/queue/walk-in` | manage | body: branch_id, patient_id, service_id, doctor_id?, notes? → creates `ClinicAppointment` (start_time=now, source `walk_in`, skips the best-effort overlap pre-check — see §5 ADR-4) then same check-in chain (US-M08-02) |
| `GET /clinics/{cid}/queue?branch_id&doctor_id&service_date&status` | read | staff view, QUEUE-02 full fields (number, patient name, doctor, service, appt time, checked-in time, waiting minutes, priority, missed calls) |
| `GET /clinics/{cid}/queue/display?branch_id` | read (authenticated!) | public-screen payload: queue_number, **masked name (initials)**, status, doctor name only — no service/diagnosis/full name/patient_id (AC-M08-03, Stop Gate "PHI on public screens"); the physical screen runs an authenticated session — deliberately NOT an unauthenticated endpoint |
| `POST /clinics/{cid}/queue/{qid}/call` | manage + doctor(own) | waiting→called; blocked for doctor when over missed-call cap |
| `POST /clinics/{cid}/queue/{qid}/missed-call` | manage + doctor(own) | called→waiting, count++ |
| `POST /clinics/{cid}/queue/{qid}/start-consultation` | manage + doctor(own) | called→in_consultation + appointment sync |
| `POST /clinics/{cid}/queue/{qid}/complete` | manage + doctor(own) | in_consultation→completed + appointment sync |
| `POST /clinics/{cid}/queue/{qid}/leave` | manage only | waiting/called→left |
| `POST /clinics/{cid}/queue/{qid}/priority` | manage only | body: `{is_priority: bool, reason: str (required min_length=1)}` — reason stored on row, audit gets `reason_provided: true` + `{from,to}` priority flag (AC-M08-04, BR-M08-02, M07 PHI-audit discipline) |

Audit actions (all with `clinic_id`, zero PHI/free-text in details): `clinic_queue_checkin`,
`clinic_queue_walkin` (+ the appointment-create/transition audits from reused services),
`clinic_queue_transition` `{from,to,missed_call_count?}`, `clinic_queue_transition_denied`,
`clinic_queue_priority` `{is_priority, reason_provided}`.

Ordering (list + display): priority first, then `queue_number` asc, scoped to `service_date` (default: today).
Patient display name: reuse M06's decryption path (`clinic_patients` service) server-side; initials-mask helper for display endpoint.

## 5. Engineering ADRs (documented defaults, not silent guesses — Stop Gate #10 hygiene)

1. **`queue_config` keys** (all optional, fail-safe defaults): `number_reset_scope`:
   `"branch_day"` (default) | `"branch_doctor_day"` | `"clinic_day"` (BR-M08-03 "reset theo
   ngày/chi nhánh/bác sĩ"); `max_missed_calls`: int default 3 (BR-M08-04 "tối đa N lần cấu hình");
   `checkin_window_hours`: int default 12; `day_offset_minutes`: int default 420 (VN, UTC+7).
2. **Operational day**: `service_date = (utcnow() + day_offset_minutes).date()`. Codebase is
   naive-UTC throughout; a VN clinic's "day" boundary is midnight ICT. Default 420 documented.
3. **Check-in window**: allowed when `|now − appointment.start_time| ≤ checkin_window_hours`.
   BRD defines no explicit window; 12h default keeps same-day flexibility, blocks
   wrong-day check-ins. Late arrivals past the window use M07's existing no-show → arrived-override
   (reason required) then check-in from `arrived`.
4. **Walk-in skips the overlap pre-check** (`_has_overlapping_appointment`): a walk-in is an
   immediate arrival, not a future slot reservation — blocking it because the doctor has a
   booked slot "now" would break US-M08-02. The DB exact-start unique index still applies.
   Scheduled check-in path changes nothing about M07 booking rules.
5. **No Encounter auto-creation** — M09 will link encounters to `in_consultation` appointments.
   `consultation_started_at` is the durable handoff/readiness marker.
6. **Leave-queue leaves the appointment status untouched** (BRD §7.5 has no backward edge).
   Follow-up (if clinics need "re-queue after leave" or appointment cleanup) requires a BRD/PTH
   decision — logged in handoff, not invented here.
7. **New enum member `ClinicAppointmentSource.WALK_IN = "walk_in"`** — additive Python-only
   change (String(20) column, no migration).

## 6. Frontend (additive, M06/M07 patterns)

- New route `app/clinic/(clinic-shell)/queue/page.tsx` ("Hàng chờ"): today's queue table
  (10s polling — AC-M08-02), row actions per capability (call/missed/start/complete/leave/priority-with-reason-modal),
  check-in panel listing today's checkin-able appointments (reuses M07 list API; 1 click check-in from
  there — AC-M08-01 ≤3 thao tác), walk-in modal (patient search reuses M06 search flow), and a
  read-only "Màn hình gọi số" view rendering the masked display payload (AC-M08-03).
- `ClinicContext.tsx`: `canViewQueue`, `canManageQueue`, `canActOnOwnQueue` (doctor).
- `ClinicShell.tsx`: nav entry "Hàng chờ". `lib/api/clinics.ts`: DTOs + functions, purely additive.

## 7. Test matrix (targeted file `tests/api/test_clinic_checkin_queue_m08_api.py`)

Base matrix (MASTER_PROGRAM_PLAN §7) + user-mandated items:
1. Cross-clinic IDOR: appointment_id / patient_id / branch_id / queue entry_id from clinic B → 403/404, never data.
2. Cross-branch: branch-scoped receptionist/doctor cannot check-in/list/act outside `branch_ids`; explicit branch_id outside scope → 403.
3. Full role matrix per route (positive + negative incl. Accountant 403, CC read-yes/mutate-no).
4. Doctor row-scoping: own entries only (list filter + 403 on others' call/start/complete); doctor cannot walk-in/leave/priority.
5. Duplicate sequential check-in → 409/400 controlled; concurrent double check-in (monkeypatch race sim, M07 style) → unique(appointment_id) IntegrityError → controlled 409, appointment not double-transitioned.
6. Concurrent queue-number allocation: simulated counter race (savepoint retry path) + uniqueness of issued numbers per scope; reset scopes branch_day/branch_doctor_day/clinic_day each verified.
7. Duplicate active queue entry for same patient (2nd appointment, same clinic) → blocked by partial index → controlled 409; allowed again after first entry terminal.
8. Appointment invalid states: cancelled/completed/no_show/in_queue/in_consultation check-in → 400; pending and confirmed and arrived (post-override) all succeed with correct audit chains.
9. Check-in window: too early/too late → 400; boundary inside window OK.
10. Walk-in: happy path (creates appointment source=walk_in + entry), no active patient relationship → 400 (no bypass), cross-clinic patient → blocked, inactive service → 400, walk-in respects RBAC (doctor/CC/accountant cannot).
11. Full queue transition matrix: every valid edge + every invalid edge (fail-closed) both directions; missed-call increments + cap behavior (doctor blocked, reception can still call/leave).
12. Two staff same entry race: conditional-UPDATE rowcount loser → 409 (call, start-consultation, complete).
13. Priority: requires reason (422 without), sets flag+reason on row, audit has reason_provided only (no verbatim reason in details), appears in list ordering.
14. Display endpoint: masked initials, no service/full-name/patient_id fields in payload; requires auth + clinic membership.
15. Revoked/suspended membership → immediate loss on all queue routes.
16. Multi-clinic user: active-tenant scoping on queue resources.
17. Feature flag OFF → 503 all routes.
18. Audit: tenant isolation (clinic_id populated), completeness for every mutation, PHI-free details (scan test), denied-transition audit durably persisted (M07 denial-durability test pattern).
19. M07 regression: appointment suite still green (state machine untouched except being *called*); no-show job unaffected.
20. Legacy regression: `Appointment`/`BookingAppointment`/`Consultation`/doctor-review-queue test files untouched and green.

Then: full backend suite, frontend tests + tsc + build, migration up→down→up (`MCP_DATABASE_URL`), single Alembic head.

## 8. Deferred, not skipped

- US-M08-04 nurse vitals capture while waiting → clinical data, M09 (Encounter) scope.
- Realtime push (websocket) → polling ≤10s satisfies AC-M08-02 MVP; no push infra exists.
- Kiosk/QR self-check-in, SMS calling, hardware TV integration → not in BRD M08 → Stop-Gate items, untouched.
- BR-M08-02 "rule lâm sàng tạo gợi ý ưu tiên" (suggestion engine) → chỉ gợi ý cần chuyên môn xác nhận; no clinical rules exist in clinic scope yet — deferred to C2/C3 with BRD traceability; M08 ships the human-only priority path (the P0 half of the rule).
- M16 wait-time reporting — data (`checked_in_at`, `consultation_started_at`) stored now, reports later.

## 9. Self-check vs BRD

| BRD item | Covered by |
|---|---|
| US-M08-01 check-in nhanh | check-in route + FE panel (≤3 thao tác: mở Hàng chờ → tìm lịch hôm nay → Check-in) — AC-M08-01 ✓ |
| US-M08-02 walk-in | walk-in route (find/create patient = M06 reuse) ✓ |
| US-M08-03 doctor realtime queue + call next | doctor-scoped list + 10s polling + call/start routes — AC-M08-02 ✓ |
| US-M08-04 vitals | deferred → M09 (documented §8) |
| US-M08-05 priority + reason + audit | priority route — AC-M08-04 ✓ |
| QUEUE-02 display fields | staff list full fields; public display masked — AC-M08-03 ✓ |
| BR-M08-01 (P0) | check-in chain + walk-in creates appointment ✓ |
| BR-M08-02 (P0) | human-only priority, required reason, audited; no auto-triage ✓ (suggestion half deferred §8) |
| BR-M08-03 (P1) | counter table + tenant `queue_config.number_reset_scope`, race-safe ✓ |
| BR-M08-04 (P1) | call/missed-call/max-N/reception-handling ✓ |
| BR-M08-05 (P1) | timestamps stored for M16 ✓ |

No Stop Gate touched: flag stays OFF, no real data, no M09 Encounter schema, no kiosk/QR/SMS/hardware,
no notifications, no PHI on public display (masked + authenticated), additive-only migration.
