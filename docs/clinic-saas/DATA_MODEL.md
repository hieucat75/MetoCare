# MetoCare Clinic SaaS — Phase C0 Data Model

Author: Agent D (Database & Migration Architect). Design only — no migration
files, no ORM code. Scope: **Phase C0 (multi-tenant foundation) only** — the
entities in `TENANT_ARCHITECTURE.md` needed for clinic identity, membership,
invitation, service catalog, patient↔clinic linkage, and subscription. C1
(services/patients/appointments/queue/billing) and C2 (care plans/CRM) schema
are explicitly out of scope.

Every table below cites the exact source line(s) it extends (if any) and is
verified directly against `backend/app/models/*.py` (not against any doc's
paraphrase). Alembic head confirmed via `alembic heads` (backend venv,
2026-07-08): **`t13_p0_note_draft_status`** — single head, no divergence.

Column type notes: `JSON` uses `sqlalchemy.JSON`, the same type already used
for array columns elsewhere in this codebase (`drug_catalog.py:26-42`,
`meto.py:24-26`) — confirmed cross-dialect-safe (SQLite JSON1 / Postgres
`json`), so no new type-compatibility risk is introduced.

---

## 0. Ownership classification legend

- **Tenant root** — the clinic entity itself.
- **Global** — platform-wide, no clinic scoping (`users`, `subscription_plans`).
- **Clinic-owned** — belongs entirely to one clinic; the row has no meaning
  without that clinic (`clinic_branches`, `clinic_invitations`,
  `clinic_services`).
- **Clinic-linked** — references a clinic but is not owned by it; the other
  side of the reference (a user, a patient, a plan) has independent identity
  outside the clinic (`clinic_memberships`, `clinic_patient_relationships`,
  `clinic_subscriptions`).
- **Shared clinical** — patient-owned data; a clinic only ever gets a scoped
  relationship to it, never a direct `clinic_id` column (`patient_profiles`,
  untouched here, referenced only).

---

## 1. `clinics` — ALTER existing table (`care.py:60-72`)

**NEW or ALTER: ALTER.** Ownership: **Tenant root**. All existing columns
(`id`, `name`, `address`, `phone`, `email`, `specialty_tags`,
`operating_hours`, `is_active`, `is_verified`, `created_at`, `updated_at`)
are kept unchanged, no rename/drop.

| New column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `legal_name` | `String(255)` | YES | none | BR-M01-04 |
| `tax_code` | `String(20)` | YES | none | |
| `license_no` | `String(64)` | YES | none | |
| `clinic_type` | `String(32)` | YES | none | enum-like, validated at service layer not DB |
| `status` | `String(16)` | **NO** | `'trial'` (server_default) | `trial\|active\|suspended\|expired\|deactivated`. See Migration Strategy §2 for the safe single-step NOT-NULL-add pattern (precedent: `t13_p0_note_draft_status.py`'s `status` column on `consultation_notes`). **Distinct from existing `is_active: bool`**, kept as-is for backward compat with any current reader; `status` is the new authoritative field. |
| `branding` | `JSON` | YES | none | `{logo_url, primary_color, display_name}` — no PHI (enforced at write-validator) |
| `cancellation_policy` | `JSON` | YES | none | `{min_hours_before, fee}` |
| `queue_config` | `JSON` | YES | none | numbering/reset scheme |
| `overbooking_policy` | `JSON` | YES | none | `{enabled: bool, max_pct: int}` |
| `deactivated_at` | `DateTime(timezone=True)` | YES | none | terminal-state stamp |
| `restored_at` | `DateTime(timezone=True)` | YES | none | platform-approved restore stamp |

Indexes: none added (no query pattern in C0 filters clinics by these new
columns at volume; `id` PK remains the only lookup key). No new unique
constraint on `name` (multiple clinics may share a display name — confirmed
Agent C's call, unchanged).

---

## 2. `clinic_branches` — NEW table

Ownership: **Clinic-owned**.

| Column | Type | Nullable | Default | FK / ON DELETE |
|---|---|---|---|---|
| `id` | `String(36)` (UUID) | NO (PK) | `uuid4()` | |
| `clinic_id` | `String(36)` | NO | | FK → `clinics.id`, **ON DELETE CASCADE** |
| `name` | `String(255)` | NO | | |
| `address` | `JSON` | YES | none | |
| `phone` | `String(32)` | YES | none | |
| `working_hours` | `JSON` | NO | none (app-supplied at create) | per-weekday open/close incl. split shifts |
| `status` | `String(16)` | NO | `'active'` | `active\|paused\|archived` |
| `created_at` / `updated_at` | via `TimestampMixin` | NO | server `CURRENT_TIMESTAMP` | |

Indexes / constraints:
- Unique `(clinic_id, name)` — matches M02 §2.4 "unique within tenant," not global.
- Index `(clinic_id, status)` — the "list my clinic's active branches" query.

ON DELETE rationale: cascade is correct here because a branch has zero
meaning once its owning clinic is gone, and clinics are never hard-deleted in
this design (terminal state is `deactivated`, a row, not a DELETE) — so the
cascade is a safety rail for an operation that in practice never fires, not
a live risk.

---

## 3. `clinic_memberships` — NEW table (generalizes `DoctorClinic`, `care.py:106-117`)

Ownership: **Clinic-linked**. `DoctorClinic` is **not** altered or replaced in
this migration batch — it stays exactly as-is, still read by
`assert_doctor_assigned` (`rbac.py:63-105`), per Agent C's explicit
no-immediate-cutover call (`TENANT_ARCHITECTURE.md` §2.3).

| Column | Type | Nullable | Default | FK / ON DELETE |
|---|---|---|---|---|
| `id` | `String(36)` | NO (PK) | `uuid4()` | |
| `user_id` | `String(36)` | NO | | FK → `users.id`, **ON DELETE RESTRICT** |
| `clinic_id` | `String(36)` | NO | | FK → `clinics.id`, **ON DELETE RESTRICT** |
| `roles` | `JSON` | NO | none (app-supplied, must be non-empty array) | `["owner"\|"admin"\|"doctor"\|"nurse"\|"receptionist"\|"care_coordinator"\|"accountant", ...]` |
| `branch_ids` | `JSON` | NO | `[]` | array of `clinic_branches.id`; empty until branches exist |
| `doctor_profile_id` | `String(36)` | YES | none | FK → `doctors.id`, **ON DELETE SET NULL** — required-if-`doctor`-in-`roles`, enforced at service layer (cross-column conditional requirement is not DB-expressible without a CHECK referencing JSON contents, which is fragile across SQLite/Postgres — left to the service layer, consistent with how `CarePlan`'s AI-status invariant is enforced via `@validates` rather than a DB constraint) |
| `status` | `String(16)` | NO | `'invited'` | `invited\|active\|suspended\|removed` |
| `is_primary` | `Boolean` | NO | `False` | |
| `joined_at` | `Date` | YES | none | |
| `left_at` | `Date` | YES | none | |
| `invited_by_user_id` | `String(36)` | YES | none | FK → `users.id`, **ON DELETE SET NULL** |
| `created_at` / `updated_at` | via `TimestampMixin` | NO | server `CURRENT_TIMESTAMP` | |

Indexes / constraints:
- **Unique `(user_id, clinic_id)`** — one membership row per user per clinic
  (multi-role via the `roles` array, not multiple rows). This is the
  single-row lookup `TenantContext` resolution needs to stay cheap.
- Index `(clinic_id, status)` — staff-list queries.
- Index `(user_id, status)` — "which clinics does this user belong to"
  (multi-clinic switcher).

**Deviation from `TENANT_ARCHITECTURE.md` §2.3 (FK cascade behavior — Agent C
did not specify `ON DELETE` at all):** I set both `user_id` and `clinic_id`
to **RESTRICT**, not CASCADE. Rationale: `ClinicMembership` rows are
referenced indirectly by `audit_logs.clinic_id`/`actor_id` history (who did
what, at which clinic, over the membership's lifetime). If a clinic row were
ever hard-deleted with `ON DELETE CASCADE` on `clinic_id`, every membership
row — and with it the ability to resolve "who was Owner/Admin of this
now-gone clinic and when" for audit/legal purposes — would silently
disappear in the same transaction, with no application code ever deciding
that was acceptable. Since clinics are never hard-deleted in this design
(deactivation is a status flip, not a DELETE), RESTRICT costs nothing in
practice and removes a footgun if that invariant is ever violated by a future
ops script. Same reasoning applies to `user_id`: a user delete (if one is
ever added) must not silently erase clinic-membership history.

`doctor_profile_id` uses **SET NULL** deliberately (different from the two
above): unlike clinic/user identity, `Doctor` row deletion is a narrower,
already-precedented soft-touch operation elsewhere in the schema (`Doctor` is
nullable-FK'd from multiple tables already, e.g. `care.py:78`), and losing
the doctor-profile link on an already-`removed` membership is not an
audit-integrity problem the same way losing the clinic/user link would be.

**No new `ClinicMembership` rows are backfilled from `DoctorClinic` in this
migration batch** — that backfill is explicitly out of scope per
`TENANT_ARCHITECTURE.md` §2.3's own note ("out of scope for this design doc
— flagged for the implementation phase"), and this doc does not add it
either. `clinic_memberships` starts empty after C0.

---

## 4. `clinic_invitations` — NEW table

Ownership: **Clinic-owned**.

| Column | Type | Nullable | Default | FK / ON DELETE |
|---|---|---|---|---|
| `id` | `String(36)` | NO (PK) | `uuid4()` | |
| `clinic_id` | `String(36)` | NO | | FK → `clinics.id`, **ON DELETE CASCADE** |
| `invited_email` | `String(255)` | YES* | none | *at least one of email/phone required — enforced by a CHECK constraint (see below) |
| `invited_phone` | `String(20)` | YES* | none | |
| `roles` | `JSON` | NO | none | proposed roles, copied to `ClinicMembership.roles` on acceptance |
| `branch_ids` | `JSON` | NO | `[]` | proposed branch scope |
| `token_hash` | `String(255)` | NO | none | never the raw token |
| `status` | `String(16)` | NO | `'pending'` | `pending\|accepted\|revoked\|expired` |
| `expires_at` | `DateTime(timezone=True)` | NO | none (app-set, +7 days at creation) | |
| `invited_by_user_id` | `String(36)` | NO | | FK → `users.id`, **ON DELETE RESTRICT** |
| `accepted_by_user_id` | `String(36)` | YES | none | FK → `users.id`, **ON DELETE SET NULL** |
| `created_at` / `updated_at` | via `TimestampMixin` | NO | server `CURRENT_TIMESTAMP` | |

Indexes / constraints:
- **Unique `token_hash`** (already specified by Agent C).
- CHECK constraint: `invited_email IS NOT NULL OR invited_phone IS NOT NULL`.
- **Addition beyond `TENANT_ARCHITECTURE.md` §2.4** (the task explicitly
  flags this exact question — "can a clinic have duplicate invitation emails
  pending?"): **partial unique index on `(clinic_id, invited_email)` WHERE
  `status = 'pending'`**, and a matching partial unique index on
  `(clinic_id, invited_phone)` WHERE `status = 'pending'`. Without this, a
  clinic Owner could fire off the same invite twice (double-click, retried
  request) creating two live `pending` tokens for the same person, or an
  attacker could spam-invite the same address repeatedly; both are silent
  data-quality/security-review noise with no constraint to prevent them
  today. Partial (filtered) unique indexes are supported by both Postgres and
  SQLite ≥3.8.0 (confirmed pattern compatible with this project's dual-engine
  test/prod setup), so no dialect risk. This is a genuine gap in Agent C's
  design at the schema level, not a re-litigation of the invitation *product*
  flow (M03 §3.4 is unchanged).

`ON DELETE CASCADE` on `clinic_id` for the same reason as `clinic_branches`
(an invitation has no meaning without its clinic, and clinic hard-delete
doesn't practically happen).

---

## 5. `clinic_services` — NEW table

Ownership: **Clinic-owned**.

| Column | Type | Nullable | Default | FK / ON DELETE |
|---|---|---|---|---|
| `id` | `String(36)` | NO (PK) | `uuid4()` | |
| `clinic_id` | `String(36)` | NO | | FK → `clinics.id`, **ON DELETE CASCADE** |
| `branch_ids` | `JSON` | YES | none | null = all branches; non-null = restricted |
| `name` | `String(255)` | NO | | |
| `price` | `Numeric(12, 2)` | NO | | current price; historical invoices snapshot separately, never a live reference to this row |
| `package_visit_count` | `Integer` | YES | none | non-null = chronic-care package |
| `status` | `String(16)` | NO | `'active'` | `active\|inactive` |
| `created_at` / `updated_at` | via `TimestampMixin` | NO | server `CURRENT_TIMESTAMP` | |

Indexes: `(clinic_id, status)` for the catalog-listing query. Price-change
audit goes through `audit.record()` per Agent C's design (no history table
in C0 — deferred to C1 if a concrete versioned-price requirement emerges;
none exists in the BRD today).

---

## 6. `clinic_patient_relationships` — NEW table (the missing patient↔clinic link)

Ownership: **Clinic-linked**. This is the table `patient.py:18-45`
(`PatientProfile`) explicitly does **not** get a column on — confirmed by
direct read, `PatientProfile` is untouched in this migration batch, no
`clinic_id` added to it, no restructuring of its `EncryptedString` columns.

| Column | Type | Nullable | Default | FK / ON DELETE |
|---|---|---|---|---|
| `id` | `String(36)` | NO (PK) | `uuid4()` | |
| `patient_id` | `String(36)` | NO | | FK → `patient_profiles.id`, **ON DELETE RESTRICT** |
| `clinic_id` | `String(36)` | NO | | FK → `clinics.id`, **ON DELETE RESTRICT** |
| `patient_code` | `String(32)` | NO | | tenant-scoped, auto-generated, immutable |
| `status` | `String(16)` | NO | `'active'` | `active\|inactive\|merged` |
| `first_seen_at` | `DateTime(timezone=True)` | NO | server `CURRENT_TIMESTAMP` | |
| `created_at` / `updated_at` | via `TimestampMixin` | NO | server `CURRENT_TIMESTAMP` | |

Indexes / constraints:
- Unique `(clinic_id, patient_code)` (already specified by Agent C).
- **Addition beyond `TENANT_ARCHITECTURE.md` §2.7**: **unique
  `(clinic_id, patient_id)`**. Agent C's design only constrains
  `patient_code` uniqueness per clinic; it does not stop two rows from being
  created for the same `(patient, clinic)` pair under a retry/race (e.g. a
  double-submitted registration form), which would silently fork "is this
  patient known to this clinic" into two rows with two different
  `patient_code`s and two different `status` values — exactly the kind of
  BOLA-adjacent data-integrity bug THREAT_MODEL.md §1/§2 is designed to
  prevent (every patient-resource lookup joins through this table; two
  contradictory rows makes that join ambiguous). This is additive to, not a
  replacement of, the `patient_code` uniqueness rule.

ON DELETE rationale: **RESTRICT on both sides**, not CASCADE. A patient's
profile must never be silently deleted as a side effect of a clinic
hard-delete (clinics aren't hard-deleted anyway, but this table is the
literal enforcement point for BR-M06-02/Decision 2's provenance rule — if it
disappeared silently, downstream clinical-record provenance checks that key
off "does a `ClinicPatientRelationship` row exist" could false-negative in a
way that's invisible until an access-denial bug report comes in). RESTRICT
forces any future clinic-removal tooling to explicitly handle its patient
relationships rather than doing so implicitly via cascade.

**Reconfirmed alignment with Agent C**: no `clinic_id` column added to
`patient_profiles` itself — this table is the only mechanism, exactly as
designed in `TENANT_ARCHITECTURE.md` §2.7.

---

## 7. `subscription_plans` — NEW table

Ownership: **Global** (platform-wide catalog, not clinic-scoped).

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `id` | `String(36)` | NO (PK) | `uuid4()` | |
| `code` | `String(32)` | NO | | `trial\|basic\|professional\|enterprise` — stable machine key, distinct from `id` so seed rows survive an `id` regeneration |
| `name` | `String(64)` | NO | | display name |
| `entitlements` | `JSON` | NO | none | `{max_branches, max_doctors, max_active_patients, copilot_quota_per_month, crm_automation_enabled, advanced_reports_enabled, api_sso_enabled}` |
| `created_at` / `updated_at` | via `TimestampMixin` | NO | server `CURRENT_TIMESTAMP` | |

Indexes: unique `code`.

**Open question flagged, not blocking**: exact tier names/limits are a
product decision Agent C already deferred (M04 §4.2 gives the shape, not
final numbers). Technical default: seed 4 rows (`trial`, `basic`,
`professional`, `enterprise`) with placeholder entitlement values in the
implementation-phase data migration (not this schema doc), so the FK from
`clinic_subscriptions.plan_id` always has a valid target — this is a
reasonable technical default, not a business answer, and does not block C0
schema work.

---

## 8. `clinic_subscriptions` — NEW table

Ownership: **Clinic-linked**.

| Column | Type | Nullable | Default | FK / ON DELETE |
|---|---|---|---|---|
| `id` | `String(36)` | NO (PK) | `uuid4()` | |
| `clinic_id` | `String(36)` | NO | | FK → `clinics.id`, **ON DELETE RESTRICT** |
| `plan_id` | `String(36)` | NO | | FK → `subscription_plans.id`, **ON DELETE RESTRICT** (a plan in active use must never vanish out from under a live subscription) |
| `started_at` | `DateTime(timezone=True)` | NO | server `CURRENT_TIMESTAMP` | |
| `expires_at` | `DateTime(timezone=True)` | YES | none | trial = +30 days, set by app at creation |
| `status` | `String(16)` | NO | `'trial'` | `trial\|active\|expired\|cancelled` |
| `created_at` / `updated_at` | via `TimestampMixin` | NO | server `CURRENT_TIMESTAMP` | |

**Deviation from `TENANT_ARCHITECTURE.md` §2.8**: Agent C specifies
`clinic_id` as **globally unique** ("one active subscription per clinic at a
time"). I'm not carrying that forward as a plain unique constraint. A flat
unique `clinic_id` forces every plan change (trial→basic, basic→professional,
a renewal) to be an UPDATE-in-place, which destroys the clinic's billing/plan
history — the same "no hard delete, keep history" principle Agent C applies
everywhere else (`Clinic.status` state machine, `ClinicBranch.status`
archive-not-delete, `ClinicPatientRelationship.status='merged'` not a row
delete) would be violated here for exactly the table where billing history
matters most (subscription upgrades/downgrades are exactly the kind of event
a future billing dispute or entitlement-audit needs to reconstruct).

**Refinement**: replace the flat unique constraint with a **partial unique
index on `clinic_id` WHERE `status IN ('trial', 'active')`**. This still
guarantees at most one *current* subscription per clinic (the actual
invariant BR-M04 needs, and what `get_entitlements(clinic_id)` — Agent C
§2.8 — depends on to resolve unambiguously) while allowing unlimited
`expired`/`cancelled` historical rows to accumulate per clinic. Same
partial-index technique proposed for `clinic_invitations` above, same
Postgres/SQLite compatibility.

---

## 9. `audit_logs` — ALTER existing table (`governance.py:54-70`)

**NEW or ALTER: ALTER.** Ownership: **Global**, extended additively. All
existing columns unchanged.

| New column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `clinic_id` | `String(36)` | YES | none | `NULL` = platform-global event (login, non-clinic actions). No FK constraint — mirrors the existing `Consent.granted_to` (`governance.py:27`) and `AuditLog.resource_id`/`actor_id` convention of storing bare reference-id strings without FK enforcement, since `AuditLog` intentionally never has referential dependencies on entities that might later be pruned/archived independent of the log (append-only log outliving its subjects is a design goal, not an oversight). |

**Refinement beyond `TENANT_ARCHITECTURE.md` §2.10**: Agent C specifies
`clinic_id` nullable + indexed (singly). I'm adding a **composite index
`(clinic_id, timestamp)`** instead of relying on the single-column index
alone. RBAC_MATRIX.md's "Audit log (M18): R (own tenant)" row and
THREAT_MODEL.md §8's export-anomaly-detection use case both imply the actual
query pattern is "this clinic's audit trail, ordered by time" (a
time-ranged/paginated listing), not a bare existence filter — a
single-column index on `clinic_id` alone would still require a separate sort
step on every request. This is exactly the kind of "missing index that would
make [a repeated] request slow" the task calls out; the composite index
avoids that at negligible extra write cost (append-only table, no update
churn to amplify).

No backfill needed — existing rows correctly get `NULL` (they predate any
clinic concept and are genuinely platform-global).

---

## 10. Explicitly unchanged (verified, not touched)

- `users` (`user.py:39-66`) — no `clinic_id` column added, confirmed correct
  per Agent C and Agent B (a user's clinic affiliations live only in
  `clinic_memberships`, many-to-many).
- `patient_profiles` (`patient.py:18-45`) — no columns added, removed, or
  retyped; `EncryptedString` pattern on `full_name`/`dob`/`phone`/`address`/
  `known_conditions`/`allergies`/`family_history`/`lifestyle_profile`
  untouched.
- `doctors` / `doctor_clinic` (`care.py:74-117`) — untouched; `DoctorClinic`
  remains the live table backing `assert_doctor_assigned` until a
  later, explicitly out-of-scope backfill/cutover migration.
- `consents` (`governance.py:20-51`) — untouched. `granted_to` remains a
  bare unconstrained string; no FK to `clinics` added in C0 (a schema change
  here is a `Consent`-model decision, not this doc's to make, and no C0
  requirement forces it).

---

## 11. Summary — table count by ownership classification

| Classification | Tables | Count |
|---|---|---|
| Tenant root (altered) | `clinics` | 1 |
| Global (new) | `subscription_plans` | 1 |
| Global (altered) | `audit_logs` | 1 |
| Clinic-owned (new) | `clinic_branches`, `clinic_invitations`, `clinic_services` | 3 |
| Clinic-linked (new) | `clinic_memberships`, `clinic_patient_relationships`, `clinic_subscriptions` | 3 |
| Shared clinical (untouched, referenced only) | `patient_profiles` | 1 |

**New tables: 7. Altered tables: 2. Untouched-but-referenced: `users`,
`patient_profiles`, `doctors`, `doctor_clinic`, `consents`.**
