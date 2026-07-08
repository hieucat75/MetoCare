# MetoCare Clinic SaaS — Tenant Architecture

Author: Agent C (Multi-Tenant & Security Architect). Design only — no code, no
migrations. Grounded in `BRD_ANALYSIS.md`, `REQUIREMENTS_TRACEABILITY.md`,
`CURRENT_ARCHITECTURE_AUDIT.md`, `REUSE_AND_GAP_MATRIX.md` and direct reads of
the cited source files. Every reuse/replace/extend call cites a file:line.

Scope note: this document designs the **shape** of entities (columns, types,
FKs, constraints, indexes) for architecture review — it is not SQLAlchemy code
and introduces no migration.

---

## 1. Reuse-vs-replace decision on `Clinic` / `DoctorClinic`

**Decision: REUSE the existing `Clinic` (`backend/app/models/care.py:60-72`)
and `DoctorClinic` (`care.py:106-117`) table shapes as the foundation of the
tenant and doctor-membership model. Do NOT replace them. Extend their
consumers. Replace only `assert_clinic_scope` (`backend/app/core/rbac.py:108-124`).**

Rationale, each backed by the audit:

- `Clinic` (`care.py:60-72`) already has `id` (UUID PK via `UUIDPrimaryKey`),
  `name`, `address`, `phone`, `email`, `specialty_tags`, `operating_hours`,
  `is_active`, `is_verified`, plus `TimestampMixin` (created_at/updated_at).
  This is a reasonable subset of BRD M01's field table (`docs/brd/v2.0/m01-tenant.md`
  §1.5: `name`, `legal_name`, `clinic_type`, `specialties`, `phone`, `email`,
  `address`, `tax_code`, `license_no`, `status`, `branding`,
  `cancellation_policy`, `queue_config`). Nothing here needs to be torn down —
  it needs **additive columns** (see §2.1).
- `DoctorClinic` (`care.py:106-117`: `doctor_id`, `clinic_id`,
  `role_at_clinic`, `is_primary`, `is_active`, `joined_at`, `left_at`) is
  *exactly* the shape BR-M03-02 requires (independent per-clinic membership
  for a multi-clinic doctor, no cross-clinic bleed) and exactly what
  Agent B's Reuse/Gap matrix recommends reusing (`REUSE_AND_GAP_MATRIX.md`
  row "Doctor profile": *"Reuse the table; extend its consumers"*). Building
  a parallel `ClinicMembership` table for doctors while `DoctorClinic` already
  models the identical relationship would violate DRY and create two sources
  of truth for the same fact (which doctor works at which clinic).
- The gap is entirely in **usage**, not **shape**: `DoctorClinic` is read by
  exactly one legacy path — `assert_doctor_assigned`
  (`backend/app/core/rbac.py:63-105`) — itself only called from
  `encounters.py`/`care_plans.py`/`doctor_review.py`
  (`CURRENT_ARCHITECTURE_AUDIT.md` §12). Every other patient-data surface
  (Consultations, AISession, labs, meds, metrics, notifications, Meto AI)
  bypasses it entirely. Clinic SaaS work extends the *consumer* surface
  (new routes, new resource types) to call the same membership check — it
  does not need a new membership table for doctors.
- What genuinely does **not** exist and must be built new: (a) a
  **non-doctor** membership concept (Owner/Admin/Nurse/Receptionist/Care
  Coordinator/Accountant have no `DoctorClinic`-equivalent row today —
  `assert_clinic_scope` at `rbac.py:108-124` is a literal stub: *"Without a
  separate ClinicAdmin model we accept any clinic_admin role"*), and (b) a
  patient↔clinic relationship (`patient_profiles` has **zero** clinic
  columns, `CURRENT_ARCHITECTURE_AUDIT.md` §2). Both are modeled below as new
  entities that generalize the `DoctorClinic` shape rather than inventing an
  incompatible third pattern.

**What is replaced, explicitly:** `assert_clinic_scope`
(`rbac.py:108-124`) is deleted/replaced by a real membership-based check
(`assert_clinic_membership`, §4) once `ClinicMembership` exists. This is the
one piece of existing "clinic" code that is actively wrong (it authorizes
*any* `clinic_admin`-role user for *any* clinic id) and cannot be kept.

---

## 2. Entity design

All new/extended tables use the project's existing `UUIDPrimaryKey` +
`TimestampMixin` conventions (`backend/app/models/_mixins.py`, as used by
every model read during the audit) unless noted. `clinic_id` columns below
are always `ForeignKey("clinics.id")`, `NOT NULL`, indexed, per BR-M01-01.

### 2.1 `Clinic` (extend existing `clinics` table, `care.py:60-72`)

Keep every existing column. Add, additively (new nullable/defaulted columns,
no rename/drop — matches the "additive migration" precedent already used in
this codebase, e.g. `t13_p0_note_draft_status.py` adding a `status` column to
`ConsultationNote` non-destructively):

| Column | Type | Notes |
|---|---|---|
| `legal_name` | `String(255)`, nullable | BR-M01-04: Owner-only edit + audit |
| `tax_code` | `String(20)`, nullable | M01 §1.5 `tax_code` |
| `license_no` | `String(64)`, nullable | M01 §1.5 |
| `clinic_type` | `String(32)`, nullable, enum-like | phòng khám đa khoa / chuyên khoa / chuỗi |
| `status` | `String(16)`, NOT NULL, default `"trial"` | `trial\|active\|suspended\|expired\|deactivated` — state machine per M01 §1.6. **Distinct from the existing `is_active: bool`** (kept for backward compat with whatever reads it today; `status` becomes the authoritative field consumed by the new write-gate middleware, §5) |
| `branding` | `JSON`/`Text` (serialized), nullable | logo, primary_color, display_name — BR-M01-05 constraint (no PHI) enforced at the write-validator, not the column |
| `cancellation_policy` | `JSON`/`Text`, nullable | `min_hours_before`, `fee` — BR-M07-04 |
| `queue_config` | `JSON`/`Text`, nullable | numbering/reset scheme — BR-M08-03, already flagged as living on the tenant in `BRD_ANALYSIS.md` M01 NFR note |
| `overbooking_policy` | `JSON`/`Text`, nullable | resolves BRD Cross-Cutting Finding 6 (undefined overbooking toggle) — modeled here since M01 owns clinic-wide policy config, `{enabled: bool, max_pct: int}` |
| `deactivated_at` / `restored_at` | `DateTime`, nullable | supports BR-M01-03 terminal-state + platform-approved restore audit trail |

Constraint: unique `(name)` is **not** enforced (multiple clinics may share a
display name); uniqueness of `id` (PK) is the tenant boundary.

### 2.2 `ClinicBranch` (new table, generalizes M02 §2.4)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `clinic_id` | FK → `clinics.id`, NOT NULL, indexed | tenant owner |
| `name` | `String(255)`, NOT NULL | unique **within** `(clinic_id, name)`, not globally — matches M02 §2.4 "Unique trong tenant" |
| `address` | `Text`/JSON, nullable | |
| `phone` | `String(32)`, nullable | |
| `working_hours` | `JSON`, NOT NULL | per-weekday open/close, supports split shifts (BR-M02-02) |
| `status` | `String(16)`, NOT NULL, default `"active"` | `active\|paused\|archived` (BR-M02-03/04 — no hard delete once history exists) |
| `created_at`/`updated_at` | via `TimestampMixin` | |

Index: `(clinic_id, status)` for the common "list my clinic's active
branches" query.

### 2.3 `ClinicMembership` (new table — the generalized `DoctorClinic`)

This is the single membership table for **all seven clinic roles**,
including Doctor. It supersedes the narrower `DoctorClinic` at the design
level going forward but does not require dropping `DoctorClinic` immediately
(see migration note below).

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `user_id` | FK → `users.id`, NOT NULL, indexed | the platform identity (`user.py:39` — unchanged, no tenant column added to `users` per the task's explicit instruction and Agent B's "Extend, don't add clinic_id to users" call, `REUSE_AND_GAP_MATRIX.md` row "User/identity") |
| `clinic_id` | FK → `clinics.id`, NOT NULL, indexed | |
| `roles` | `JSON` array of enum strings, NOT NULL, non-empty | `owner\|admin\|doctor\|nurse\|receptionist\|care_coordinator\|accountant` — array because BR-M03/US-M03-02 explicitly requires multi-role-per-user ("Nurse + Care Coordinator") |
| `branch_ids` | `JSON` array of `ClinicBranch.id`, NOT NULL, non-empty once branches exist | scopes which branches this membership can act in (M03 §3.5 `branches`) |
| `doctor_profile_id` | FK → `doctors.id`, nullable, required-if-`doctor`-in-roles | reuses the existing `Doctor` table (`care.py:74-104`) rather than duplicating license/specialty fields — BR-M03-05 |
| `status` | `String(16)`, NOT NULL, default `"invited"` | `invited\|active\|suspended\|removed` — M03 §3.5 |
| `is_primary` | `Boolean`, default `False` | carried over from `DoctorClinic.is_primary` semantics, generalized to all roles (which clinic shows first in a multi-clinic switcher) |
| `joined_at` / `left_at` | `Date`, nullable | carried over from `DoctorClinic` |
| `invited_by_user_id` | FK → `users.id`, nullable | audit trail for who invited this member |

Constraints:
- Unique `(user_id, clinic_id)` — one membership row per user per clinic (multi-role via the `roles` array, not multiple rows), which keeps "does this user have *any* standing at clinic X" a single-row lookup — the exact operation `TenantContext` resolution (§4) needs to be cheap.
- Partial/application-level invariant: **at least one `active` membership with `owner` in `roles` per `clinic_id`** at all times (BR-M03-04, "cannot demote/lock the last Owner") — enforced in the service layer (same class of guard as `assert_doctor_assigned`), not a DB constraint, since "last owner" is a cross-row check.
- Index: `(clinic_id, status)` for staff-list queries; `(user_id, status)` for "which clinics does this user belong to" (multi-clinic switcher, doctor or otherwise).

**Migration relationship to `DoctorClinic`:** `DoctorClinic` stays as-is and
in active use by the legacy Encounter/CarePlan/AI-review path
(`assert_doctor_assigned`) to avoid a risky rewrite of working code during
the C0 build. `ClinicMembership` is the new, complete membership model used
by every new Clinic SaaS surface (M01-M18 routes). A follow-up migration
(explicitly **out of scope for this design doc** — flagged for the
implementation phase) can backfill `ClinicMembership` rows from
`DoctorClinic` and eventually make `assert_doctor_assigned` read from
`ClinicMembership` instead, retiring `DoctorClinic` as a writable table. This
avoids a "third incompatible pattern": both tables express the same
`(doctor, clinic, role, is_active)` fact, just at different points in the
migration path.

### 2.4 `ClinicInvitation` (new table — M03 §3.4)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | doubles as the invitation token's DB anchor |
| `clinic_id` | FK → `clinics.id`, NOT NULL | |
| `invited_email` / `invited_phone` | `String`, at least one NOT NULL | matches dual email/phone identity of `users` |
| `roles` | `JSON` array, NOT NULL | proposed roles, copied into `ClinicMembership.roles` on acceptance |
| `branch_ids` | `JSON` array | proposed branch scope |
| `token_hash` | `String(255)`, NOT NULL, unique, indexed | never store the raw token (same principle as password hashing already used in `users.password_hash`) |
| `status` | `String(16)`, NOT NULL, default `"pending"` | `pending\|accepted\|revoked\|expired` |
| `expires_at` | `DateTime`, NOT NULL | 7 days per M03 §3.4 |
| `invited_by_user_id` | FK → `users.id`, NOT NULL | |
| `accepted_by_user_id` | FK → `users.id`, nullable | set on acceptance — may differ from any pre-guessed identity; matching is by token, never by email/phone auto-merge (M03 §3.7 explicitly forbids auto-merge on mismatched channel) |

Threat-relevant design note: token is single-use (`status` flips on
accept/revoke) and time-boxed (`expires_at`) — see THREAT_MODEL.md
"Invitation hijacking."

### 2.5 `ClinicSettings`

Modeled as a **1:1 extension row on `Clinic`**, not a separate table, to
avoid an unnecessary join for data that is always read together with the
clinic (KISS — YAGNI against a speculative "many settings per clinic"
future). In practice this is the `branding` / `cancellation_policy` /
`queue_config` / `overbooking_policy` columns already added in §2.1. Called
out here only because the task's entity list names it explicitly; the
recommendation is: **do not create `ClinicSettings` as its own table** unless
a concrete requirement for versioned/historical settings emerges (none exists
in the BRD).

### 2.6 `ClinicService` (M05 catalog, scoped by clinic)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `clinic_id` | FK → `clinics.id`, NOT NULL, indexed | |
| `branch_ids` | `JSON` array, nullable | null = available at all branches; non-null = restricted (M05 US-M05-03) |
| `name` | `String(255)`, NOT NULL | |
| `price` | `Numeric(12,2)`, NOT NULL | current price; historical invoices snapshot this value at creation time (BR-M05-01) rather than referencing this row live |
| `package_visit_count` | `Integer`, nullable | non-null = chronic-care package (3/6/12-month) |
| `status` | `String(16)`, NOT NULL, default `"active"` | `active\|inactive` — BR-M05-03 warns before deactivation with future bookings |

Price-change audit (BR-M05-02) goes through the existing `audit.record()`
convention (§6), not a bespoke history table, consistent with how the rest
of the codebase handles "audited field change" (see `consultation_access.py`
pattern of calling `audit.record` around every state transition).

### 2.7 `ClinicPatientRelationship` (new — the missing patient↔clinic link)

This is the entity that closes the single biggest gap identified in the
audit (`CURRENT_ARCHITECTURE_AUDIT.md` §2, "Biggest Structural Risk" in
`REUSE_AND_GAP_MATRIX.md`): `patient_profiles` has no clinic column, and
every clinical table hanging off it inherits that gap.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `patient_id` | FK → `patient_profiles.id`, NOT NULL, indexed | |
| `clinic_id` | FK → `clinics.id`, NOT NULL, indexed | |
| `patient_code` | `String(32)`, NOT NULL | tenant-scoped, auto-generated, immutable (BR-M06-04) |
| `created_by_clinic` | implicit — this row's existence at a given `clinic_id` **is** "data this clinic created" | see BR-M06-02 semantics below |
| `status` | `String(16)`, NOT NULL, default `"active"` | `active\|inactive\|merged` — BR-M06-01, no hard delete |
| `first_seen_at` | `DateTime`, NOT NULL | |

Constraint: unique `(clinic_id, patient_code)`.

**Why a join table and not a `clinic_id` column directly on
`patient_profiles`:** `patient_profiles` is explicitly a **global,
platform-level** record (one per `user_id`, `patient.py:18-45`) — a patient
keeps one longitudinal profile across every clinic they've ever visited
(consistent with v1.0 §8.2's "platform-level core identity" and BR-M06-02's
model of a patient being seen at multiple clinics with per-clinic data
scoping). A single `clinic_id` FK on `PatientProfile` would force a
one-clinic-per-patient model, which directly contradicts BR-M06-02 and
US-M06 the multi-clinic patient scenario. `ClinicPatientRelationship`
mirrors `ClinicMembership`'s shape (many-to-many with per-relationship
metadata) rather than inventing a different join pattern.

**This is where BR-M06-02 (Decision 2) is operationalized**: clinical data
created during a visit at clinic A (encounters, notes, care plans, invoices,
etc. — once those tables gain `clinic_id`, itself a downstream migration
concern outside this doc's scope) is visible to clinic B *only* if (a) clinic
B is where it was created, or (b) an active `Consent` row
(`governance.py:20-51`) grants clinic B's `clinic_id` as `granted_to` with a
matching `data_scope`. No `ClinicPatientRelationship` row by itself grants
cross-clinic visibility — it only registers that the patient is *known to*
that clinic (has a patient_code there), which is necessary but not
sufficient for data access. This is intentionally the stricter v2.0 reading
per the task's Decision 2 — flagged again in THREAT_MODEL.md for PTH
awareness since it removes v1.0's "active consultation" carve-out.

### 2.8 `ClinicSubscription` + `SubscriptionPlan` + `Entitlements`

| `SubscriptionPlan` | Type | Notes |
|---|---|---|
| `id` | UUID PK / or a small fixed enum table | `trial\|basic\|professional\|enterprise` — M04 §4.2 |
| `name` | `String(64)` | |
| `entitlements` | `JSON` | the M04 §4.2 table serialized: `max_branches`, `max_doctors`, `max_active_patients`, `copilot_quota_per_month`, `crm_automation_enabled`, `advanced_reports_enabled`, `api_sso_enabled` |

| `ClinicSubscription` | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `clinic_id` | FK → `clinics.id`, NOT NULL, unique (one active subscription per clinic at a time) | |
| `plan_id` | FK → `SubscriptionPlan.id`, NOT NULL | |
| `started_at` / `expires_at` | `DateTime` | Trial = +30 days per M01 §1.6 |
| `status` | `String(16)`, NOT NULL | `trial\|active\|expired\|cancelled` |

`Entitlements` is **not** a separate persisted table beyond
`SubscriptionPlan.entitlements` — it is the *resolved, effective* limit set
for a clinic (plan entitlements today; future: per-clinic overrides/add-ons).
Model it as a service-layer read (`get_entitlements(clinic_id) -> Entitlements`
dataclass), computed from `ClinicSubscription.plan_id` joined to
`SubscriptionPlan.entitlements`, at the point BR-M04-01's `check_entitlement()`
dependency needs it — this avoids a redundant, driftable copy of the same
numbers on every clinic row (DRY).

Per-tenant feature-flag interaction: `backend/app/core/feature_flags.py` is
process-wide/env-var-only (confirmed, no per-tenant override,
`feature_flags.py:60-85`). Clinic SaaS features (Copilot, CRM automation,
advanced reports) are gated by **entitlements**, not by feature flags —
feature flags remain the global platform kill-switch (e.g. "Clinic SaaS
module is enabled at all"), while `Entitlements` is the per-tenant business
gate on top of that. Two independent, intentionally separate mechanisms —
do not conflate them.

### 2.9 `TenantContext` (request-scoped construct, not a table)

See §4 for the full resolution flow. Conceptually:

```
TenantContext:
  user_id: str
  clinic_id: str                # the ACTIVE clinic for this request
  membership_id: str
  roles: set[ClinicRole]        # roles at this specific clinic only
  branch_ids: set[str]          # branches this membership can act in
  is_platform_override: bool    # true only for audited Super/Internal Admin cross-tenant access
```

### 2.10 Clinic audit context (extends existing `AuditLog`, additive)

`AuditLog` (`governance.py:54-70`) is reused as-is per Agent B's
recommendation (`REUSE_AND_GAP_MATRIX.md` row "Audit logging": *"No PHI is
stored... no schema change strictly required (though adding an optional
`clinic_id` column would make querying easier; a pure additive migration, not
a redesign)"*). This design adopts that optional column:

| New column on `audit_logs` | Type | Notes |
|---|---|---|
| `clinic_id` | `String(36)`, nullable, indexed | populated by every clinic-scoped call to `audit.record()`; `NULL` for platform-global events (login, non-clinic actions) |

`audit.record()` (`backend/app/services/audit.py:14-40`) gets one new
optional keyword argument, `clinic_id: str | None = None`, threaded through
to the new column. No signature-breaking change for existing callers
(`consultation_access.py`, `doctor_review.py`, etc.), which simply omit it
and get `NULL` as today. Every new Clinic SaaS write path calls
`audit.record(..., clinic_id=tenant_context.clinic_id)` — the same
convention already used by `consultation_access.assert_doctor_can_view`
(audits every successful **and denied** view, `consultation_access.py:101-110`
and `:171-184`), which this design explicitly imitates for all new
clinic-scoped access checks (§4, §THREAT_MODEL BOLA section).

---

## 3. Summary table — reuse / extend / replace / new

| Entity | Call | Backing citation |
|---|---|---|
| `Clinic` | **Extend** (additive columns) | `care.py:60-72` |
| `ClinicBranch` | **New** | no prior table; M02 §2.4 |
| `ClinicMembership` | **New**, generalizes `DoctorClinic` | `care.py:106-117` (pattern), `rbac.py:108-124` (gap it closes) |
| `DoctorClinic` | **Reuse, do not remove yet** | `care.py:106-117`; consumed by `assert_doctor_assigned`, `rbac.py:63-105` |
| `ClinicInvitation` | **New** | M03 §3.4 |
| `ClinicSettings` | **No new table** — folded into `Clinic` | YAGNI |
| `ClinicService` | **New** | M05 |
| `ClinicPatientRelationship` | **New** | closes gap at `patient.py:18-45` / `CURRENT_ARCHITECTURE_AUDIT.md` §2 |
| `ClinicSubscription`/`SubscriptionPlan` | **New** | M04 |
| `Entitlements` | **Not persisted** — computed service-layer value | DRY |
| `TenantContext` | **New, request-scoped, not a table** | see §4 |
| `AuditLog.clinic_id` | **Extend** (additive column) | `governance.py:54-70`, `audit.py:14-40` |
| `assert_clinic_scope` | **Replace** | `rbac.py:108-124` (stub) |
| `assert_doctor_assigned` | **Reuse as the pattern to generalize** | `rbac.py:63-105` |
| `ConsultationAccessGrant` pattern | **Reuse as the model for scoped grants generally** | `consultation.py:217-252`, `consultation_access.py` |

---

## 4. `TenantContext` resolution flow

Modeled as a FastAPI dependency, conceptually parallel to `current_user`
(`backend/app/api/deps.py:65-89`) and layered on top of it — described here,
not coded.

```
1. current_user(request) -> CurrentUser(id, role, ...)          [existing, unchanged]
2. get_tenant_context(
     x_clinic_id: str | None = Header(None),   # or a path/query param, depending on route
     user: CurrentUser = Depends(current_user),
     db: Session = Depends(get_session),
   ) -> TenantContext:

   a. If user.role in {SUPER_ADMIN, INTERNAL_ADMIN} AND the route is an
      explicit platform-override route (see below): build a TenantContext
      with is_platform_override=True, roles=set() (no clinic role implied),
      and REQUIRE clinic_id to be present (from header/path) since even an
      override must target a specific tenant, never "all tenants" implicitly.
      audit.record(..., action="platform_cross_tenant_access", clinic_id=...)
      is called unconditionally on this path — see THREAT_MODEL.md.

   b. Otherwise (the normal case, all clinic roles):
      - Look up ClinicMembership WHERE user_id = user.id AND status = 'active'.
      - If x_clinic_id (or equivalent) is absent: if exactly one active
        membership exists, default to it; if multiple, require an explicit
        selection (400, not a silent guess) — this is the "clinic switcher"
        UX surface (BR-M02-01/M03-02).
      - If x_clinic_id is present: it MUST match one of the user's active
        membership rows' clinic_id. If it does not match any active
        membership -> 403 (never 404, to avoid leaking existence, but see
        THREAT_MODEL BOLA section for the tradeoff). This is the literal
        enforcement of BR-M01-01 / BR-M02-01's "client-sent id only SELECTS
        among the user's valid set, never trusted absolutely."
      - Resolve roles = membership.roles, branch_ids = membership.branch_ids
        (intersected with any client-requested branch_id the same way —
        BR-M02-01 applies identically to branch_id).
      - Check Clinic.status: if suspended/expired and this is a write
        request -> 403 ENTITLEMENT-adjacent error (BR-M01-02); reads still
        allowed. If deactivated -> 403 on everything except platform-override
        restore (BR-M01-03).

3. TenantContext is then the ONLY source `clinic_id` any service/query layer
   is allowed to read for authorization purposes. Route/service code must
   never read `clinic_id` out of the request body/query/path directly for an
   authorization decision — only for *display* purposes after the above
   validation, or to select among an already-validated set (e.g. "which of
   my valid branches does this specific POST belong to").
```

This directly generalizes the existing `assert_doctor_assigned` shape
(`rbac.py:63-105`: look up the caller's `DoctorClinic` row, check
`is_active`, compare against the resource's clinic) to all seven roles via
`ClinicMembership`, and is the concrete mechanism that replaces
`assert_clinic_scope`'s stubbed-out trust (`rbac.py:118-120`).

**Resource-level `clinic_id` validation** (e.g. `POST /branches/{id}` or any
body containing a `clinic_id`/`branch_id` field): the service layer loads the
target resource, reads its *actual* `clinic_id` column, and asserts it equals
`TenantContext.clinic_id` (or, for branch-level resources, that its
`branch_id` is in `TenantContext.branch_ids`). A mismatch is a 403/404 (not a
silent filter), and — per the pattern in `consultation_access.py:171-184` —
every denial is audited via `audit.record(..., outcome="denied")`.

---

## 5. Platform Super Admin / Internal Admin cross-tenant access

Distinct code path, never a silent fallthrough of the normal `TenantContext`
resolution:

- A small, explicit allowlist of routes/operations may set
  `is_platform_override=True` (tenant creation/suspend/restore per M01,
  ops-level audit query per M18 BR-M18-03, and any future support-tooling
  "view as clinic X" feature). These are NOT the same dependency used by
  ordinary clinic-role routes — they use a separate
  `require_platform_override(clinic_id)` dependency that (a) still requires
  `require_roles(SUPER_ADMIN, INTERNAL_ADMIN)` (`deps.py:96-108`, existing
  primitive, reused as-is), and (b) unconditionally calls
  `audit.record(action="platform_cross_tenant_access", severity="warning",
  clinic_id=..., actor_id=user.id)` before the handler runs, mirroring
  `_ADMIN_ROLES` bypass semantics already present in `rbac.py:24-31` but
  making the bypass **visible in the audit trail**, which today's blanket
  `_is_admin()` check (`rbac.py:40-41`) does not do on its own — it should be
  paired with an explicit audit call at each call site, exactly as this
  design requires for every new platform-override route.
- Per BR-M18-03, Internal/Platform Admin's *default* audit/reporting view
  never surfaces clinical content — it sees tenant/ops metadata only. Viewing
  clinical content cross-tenant (if ever needed for support) must be its own
  narrower, separately-audited action, not implied by the ops view.

---

## 6. Open items not resolved by this design (see THREAT_MODEL.md §"Open product/legal questions" for the full list with rationale)

- Exact transport of `clinic_id`/active-branch selection (header vs. path vs.
  session-embedded claim) is left to the implementation phase — functionally
  equivalent for this design as long as the validation-not-trust rule in §4
  holds.
- Whether `ClinicMembership` fully retires `DoctorClinic` or the two
  permanently coexist is a phase-2 migration decision, not blocking C0.
