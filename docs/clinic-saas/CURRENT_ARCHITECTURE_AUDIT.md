# MetoCare — Current Architecture Audit (for Clinic SaaS design)

Audited 2026-07-08 by Agent B (read-only). Every claim below is backed by a file
reference to the actual source (no assumptions). "Global" = one row per whole
platform; "per-user" = scoped by `users.id`/`patient_profiles.id`; "per-relationship"
= scoped by an explicit link table (doctor↔patient, doctor↔clinic, etc.).

---

## 1. Identity Model

- `backend/app/models/user.py:16-36` — `User` (table `users`) is the single
  identity table for every actor: patients, doctors, clinic_admin,
  internal_admin, medical_reviewer, super_admin, ai_service
  (`UserRole` enum, line 16-23). Patients identify by `phone`, staff by `email`
  (both nullable, `user.py:44-46`) — no tenant/organization column anywhere on
  `users`.
- `MFA_REQUIRED_ROLES` (`user.py:29-36`) hard-codes which roles must MFA —
  `CLINIC_ADMIN` is already in that set even though there is no working
  clinic-admin UI/backend yet (see §11, §14).
- **Data ownership**: global table, no tenant boundary. A `clinic_admin` role
  value exists but nothing today scopes *which* clinic a `clinic_admin` user
  administers — `assert_clinic_scope` (`core/rbac.py:108-124`) explicitly
  says "we accept any clinic_admin role" (no `ClinicAdmin` link model exists).
  **This is a real gap a Clinic SaaS design must close.**

## 2. Patient Profile

- `backend/app/models/patient.py:18-45` — `PatientProfile` (table
  `patient_profiles`), 1:1 with `users` via `user_id` (unique FK, line 21-23).
  All PHI columns (`full_name`, `dob`, `phone`, `address`,
  `known_conditions`, `allergies`, `family_history`, `lifestyle_profile`) are
  field-level encrypted via `EncryptedString` (`core/crypto.py`). Plaintext
  fields used in scoring (`gender`, `height_cm`, `weight_kg`, `waist_cm`,
  `risk_segment`) are NOT encrypted.
- **Data ownership**: per-user, global — **no `clinic_id` column at all**.
  Every clinical table that hangs off `patient_profiles.id` (HealthMetric,
  LabDocument, LabUploadBatch, CarePlan, Encounter, Appointment,
  ConsultationNote, notifications, Meto conversations, etc.) inherits this:
  none of them carry a tenant boundary. This is the single biggest structural
  gap for multi-tenant clinic scoping (see Reuse/Gap matrix, §"Patient
  profile").

## 3. Doctor Profile

- `backend/app/models/care.py:74-104` — `Doctor` (table `doctors`), optional
  `user_id` FK and optional `clinic_id` FK (`care.py:77-78`, both nullable).
  Marketplace fields (`verification_status`, `rating_avg`, `consultation_fee`,
  etc.) were added later for the Doctor Marketplace (T10, see §4).
- `backend/app/models/care.py:106-117` — `DoctorClinic` junction table
  (`doctor_clinic`) already exists: `doctor_id`, `clinic_id`, `role_at_clinic`,
  `is_primary`, `is_active`, `joined_at`/`left_at`. **This is a real,
  many-to-many doctor↔clinic membership model that already exists in the
  schema** — but see §11: it is only consumed by one legacy code path
  (AI-recommendation review queue), not by the primary patient/consultation
  flows.
- **Data ownership**: `Doctor` is a global row per doctor; `clinic_id` is a
  single nullable pointer (not the source of truth — `DoctorClinic` is meant
  to be that, per the junction table's existence), but almost nothing reads
  `DoctorClinic` today (see §11).

## 4. Consultations / Marketplace (closest existing analog to clinic-scoped access)

- `backend/app/models/consultation.py` — a self-contained bounded context
  (T10, "Doctor Marketplace MVP"): `Consultation` (patient_id, doctor_id,
  status machine REQUESTED→CONFIRMED→PAID→IN_PROGRESS→COMPLETED/CANCELLED,
  `consultation.py:32-49`), `ConsultationPayment` (1:1, mock payment,
  `consultation.py:129-148`), `ConsultationNote` (append-only PHI note,
  `consultation.py:156-184`, draft/finalize added in migration
  `t13_p0_note_draft_status.py`), `ConsultationReview` (1:1 rating,
  `consultation.py:192-209`), and **`ConsultationAccessGrant`**
  (`consultation.py:217-252`) — a scoped, revocable, time-boxed grant from one
  doctor to one patient's data, tied to one consultation.
- Access control lives in `backend/app/services/consultation_access.py`:
  `assert_doctor_can_view` (line 56-112) checks (a) consultation ownership,
  (b) doctor `VERIFIED` + active status, (c) an active
  `ConsultationAccessGrant`, and audits every successful/denied view
  (`_audit_denied`, line 171-184). Grants are created on payment
  (`create_grant`, line 25-35) and revoked on COMPLETED/CANCELLED
  (`revoke_on_end`, line 115-138) or doctor suspension
  (`revoke_all_for_doctor`, line 141-168).
- **This is the best existing pattern to imitate for clinic-scoped access**:
  narrow, time-boxed, auditable, revocable grants scoped to one
  relationship — NOT a broad role-based "doctor can see all patients at
  clinic X" bypass. A Clinic SaaS design should study this file closely.
- **Data ownership**: per-relationship (consultation ↔ doctor ↔ patient), no
  clinic/tenant dimension at all — a marketplace consultation is
  clinic-agnostic today.

## 5. Appointments

Two unrelated appointment concepts exist — a real risk of confusion for new
design work:
- `backend/app/models/care.py:120-131` — legacy `Appointment` (table
  `appointments`): patient_id, doctor_id, scheduled_at, mode, status,
  `handoff_reason`. Used for the older doctor-handoff/encounter flow.
- `backend/app/models/appointment.py` (T21 "Booking Scaffold") —
  `BookingAppointment` (table `booking_appointments`, distinct table
  explicitly to avoid name collision, see docstring lines 5-8): patient_id,
  `doctor_id` (→ `users.id`, not `doctors.id` — inconsistent with
  `Consultation.doctor_id` which points to `doctors.id`), `availability_id`
  (→ `DoctorAvailability`, `backend/app/models/availability.py:28`), status
  pending/confirmed/cancelled/completed.
  `Consultation.booking_appointment_id` (`consultation.py:111-113`) is the
  **only** link between the two, and it's one-directional/optional.
- **Data ownership**: per-relationship, global — no clinic scoping on either
  table.

## 6. Notes

- `ConsultationNote` (§4) is the only "clinical note" model with an explicit
  append-only invariant enforced by convention (no update/delete function
  exists anywhere, `consultation.py:156-165`) plus a draft/finalize `status`
  column added non-destructively in `t13_p0_note_draft_status.py`.
- `Encounter.notes` (`care.py:153-155`) and `CarePlan.content`
  (`care.py:181-183`) are separate encrypted free-text fields on mutable
  rows (soft-delete only, via `SoftDeleteMixin`) — not append-only.
- `DoctorReviewDecision` (`care.py:276-294`) stores encrypted
  `comment`/`internal_note` for AI-recommendation review decisions,
  deliberately kept OUT of `AuditLog` because `AuditLog` must never contain
  PHI (see docstring lines 277-284).

## 7. Consent

Three distinct, non-overlapping consent models — a Clinic SaaS design must
decide how (or whether) clinic-level consent maps onto these:
- `backend/app/models/governance.py:20-51` — `Consent` (table `consents`):
  patient→(consent_type, data_scope, granted_to) with validity window +
  revocation; `is_active()` (line 34-51) checks time window + exact
  `granted_to`/`data_scope` match. `granted_to` is a bare string id
  (doctor or clinic id) — **no FK constraint**, so nothing enforces it points
  at a real `Doctor`/`Clinic` row.
- `backend/app/models/consent.py` — `TermsConsent` (table `terms_consents`):
  one-time Terms/Privacy version acceptance per user, unrelated to data
  sharing (docstring lines 3-9 explicitly distinguishes it from
  `governance.Consent` and `meto.MetoConsent`).
- `backend/app/models/meto.py:120-136` — `MetoConsent`: granular per
  `context_type` (health_data/medications/labs/metrics/care_plan/chat_history)
  consent gating what the Meto AI assistant may read.
- Service layer: `backend/app/services/consent.py` (`grant`/`revoke`/
  `has_access`, lines 24-60+) and `backend/app/services/consent_guard.py`
  (`ConsentGuard`, referenced from `ai_sessions.py:38`) wrap `Consent` for
  AI-session creation.
- **Data ownership**: per-patient rows pointing at an arbitrary grantee id;
  no clinic dimension.

## 8. Audit

- `backend/app/models/governance.py:54-70` — `AuditLog` (table
  `audit_logs`): append-only (docstring: "No update/delete in application
  code. No sensitive content."), generic `actor_type`/`actor_id`/`action`/
  `resource_type`/`resource_id`/`outcome`/`severity`. No clinic/tenant column.
- `backend/app/services/audit.py:14-40` — thin `record()` helper, used
  throughout (`consultation_access.py`, `doctor_review.py`, etc.) — this is
  the established convention any new clinic-scoped action should follow
  (call `audit.record(...)` with a descriptive `action` string, never put
  PHI in `resource_id`/details).
- Separately, `backend/app/models/meto.py:91-118` — `MetoAuditLog` is a
  parallel, AI-specific audit trail (explicitly "does NOT store message
  content or raw health data", line 94-95).
- **Data ownership**: global, flat log. Adding clinic scoping would mean
  adding a `clinic_id` (or deriving it via joins) with no schema support
  today.

## 9. Marketplace

See §4 (Consultations) — the "Doctor Marketplace" *is* the consultation
bounded context. Doctor-facing marketplace profile fields live directly on
`Doctor` (§3): `is_verified`, `verification_status`, `rating_avg`,
`rating_count`, `consultation_fee`, `years_experience`, `languages`,
`hospital_name`, `consultation_methods` (`care.py:93-103`). No clinic
grouping/filtering exists in the marketplace listing today (confirmed no
`clinic_id` filter references in `backend/app/services/doctor_marketplace.py`
during this audit's route/service enumeration, §"api/v1" list).

## 10. Notifications

- `backend/app/models/notification.py:40-73` — `Notification` (table
  `notifications`): `user_id` FK (cascade delete), `type` (open string,
  soft-enforced by `NOTIFICATION_TYPES` frozenset, lines 28-37), title/body,
  read state. Creation restricted to INTERNAL_ADMIN/SUPER_ADMIN per docstring
  (line 47).
- **Data ownership**: per-user, global. No clinic dimension; a clinic-scoped
  notification (e.g. "broadcast to all patients of Clinic X") has no
  supporting column or service today.

## 11. Clinical Copilot / AI ("Meto")

Two AI surfaces exist, both entirely user/patient-scoped, neither
clinic-aware:
- **Meto conversational assistant** (patient-facing): `backend/app/ai/`
  (registry.py — `ModelRegistry`/`RoutingPolicy`/`CircuitBreaker`, lines
  1-60+; `providers/` — claude.py, openai_provider.py, nine_router.py, mock.py;
  `context/builder.py`; `prompt/assembler.py` + `safety.py`), backed by
  `backend/app/models/meto.py` (`MetoConversation`, `MetoMessage`,
  `MetoAuditLog`, `MetoConsent` — all keyed only by `user_id`, no clinic
  column, §7/§8/§10 above).
- **Meto Clinical Copilot** (doctor-facing, `feat/doctor` — commit `ec25db4`
  per git log): `backend/app/api/v1/routes/clinical_copilot.py` (4 endpoints:
  ai-summary, ai-analysis, ai-questions, ai-advice, lines 102-187) and
  `backend/app/services/clinical_copilot.py` (~1370 lines). Gated by
  `FeatureFlag.CLINICAL_COPILOT` (default OFF, `feature_flags.py:34,56`
  — "fail-closed — calls a real LLM over PHI"). No route-level check ties
  copilot access to a doctor's clinic membership; access is presumably
  gated by whatever RBAC dependency wraps these routes (not
  clinic/consultation-scoped like §4's `ConsultationAccessGrant` pattern).
- **RAG/Knowledge**: `backend/app/knowledge/` (`knowledge_base.py`,
  `retrieval.py`, `embedding.py`, `vector_store.py`) — "Clinical Knowledge
  Platform (CKP) v1" per `knowledge/__init__.py:1`; global knowledge base,
  not tenant-partitioned.
- **`AISession`/`AIClinicalRecommendation`** (`backend/app/models/ai.py`,
  older T5/C3 AI-triage feature, all flags default OFF in
  `feature_flags.py:38-41`): `backend/app/api/v1/routes/ai_sessions.py:47-72`
  (`_check_session_read_access`) **explicitly documents the gap**: "Doctor /
  Clinic Admin: allow (clinic scope check would require DoctorClinic
  lookup — for simplicity any authenticated doctor can read...)" — i.e. the
  code already acknowledges clinic scoping is the "right" model but
  deliberately skipped it for this legacy, currently-dormant feature.
- **Data ownership**: global provider registry + per-user
  conversations/sessions. No tenant partitioning of AI access anywhere.

## 12. RBAC

- `backend/app/core/rbac.py` (full file read) is the **only** place with an
  explicit clinic-scoping concept today:
  - `_ADMIN_ROLES`/`_WRITE_ADMIN_ROLES` (lines 24-38): INTERNAL_ADMIN/
    SUPER_ADMIN bypass everything; MEDICAL_REVIEWER read-only bypass.
  - `assert_patient_owns` (49-60): patient self-access or admin.
  - `assert_doctor_assigned` (63-105): doctor must have an **active**
    `DoctorClinic` row for the patient's clinic, OR be the directly assigned
    doctor. This is real, working clinic-scoped RBAC logic — but it is only
    invoked from `encounters.py`/`care_plans.py`/`doctor_review.py`
    (confirmed via grep: only those 3 route files + `doctor_review.py`
    service call these RBAC helpers), i.e. the **legacy Encounter/CarePlan/
    AI-recommendation flow**, not Consultations, not AISession, not any
    patient-owned clinical table (labs, meds, metrics, notifications).
  - `assert_clinic_scope` (108-124): explicitly a stub — "Without a separate
    ClinicAdmin model we accept any clinic_admin role" (comment, line 118-120).
    **There is no `ClinicAdmin` membership model** — any user with role
    `clinic_admin` passes this check for any clinic.
- `backend/app/api/deps.py` — `current_user`/`require_roles`/`require_mfa`
  (lines 65-127) are pure role-based (deny-by-default per role set), no
  clinic/resource-scoping at the dependency level; per-resource scoping (like
  §4's grant check or §12's `assert_doctor_assigned`) is done inside route
  handlers/services, not centrally.
- **Conclusion**: MetoCare has TWO parallel authorization patterns today —
  (a) global role check (`require_roles`) + admin-bypass, used almost
  everywhere; (b) narrow scoped-grant / DoctorClinic check, used only in the
  legacy Encounter/CarePlan/AI-recommendation path (§12) and the Consultation
  access-grant path (§4). Neither is a general multi-tenant clinic boundary.

## 13. Feature Flags

- `backend/app/core/feature_flags.py` (full file read): `FeatureFlag` StrEnum
  (11-34) + `_DEFAULTS` dict (37-57) + `is_enabled()` (60-85). Fail-closed on
  unknown flag (line 73). Reads `FEATURE_<NAME>` or `MCP_FEATURE_<NAME>` env
  var, else falls back to the hardcoded default (lines 78-85).
  **Global, process-wide only** — no per-clinic or per-tenant flag
  overrides; a Clinic SaaS rollout gate (e.g. "C0 enabled for clinic X only")
  has no existing mechanism and would need a new per-tenant flag layer
  (e.g. a `clinic_feature_overrides` table or a flag key suffixed by
  clinic id) — nothing to reuse here beyond the enum/env-var convention.

## 14. Migrations (convention only)

- 45 files in `backend/alembic/versions/`. Naming mixes a hash-based
  legacy scheme (`1ec6f403fced_add_meto_tables.py`) with a newer
  `tNN_[pM|mM]_description.py` convention (`t13_p0_note_draft_status.py`,
  `t12_p0_doctor_review_decisions.py`, `t12_m1_meto_conv_review.py`,
  `t10_m1_consultation_marketplace.py`, `a1_terms_consents.py`).
  `t` = ticket/track number, `p0`/`m1` = phase/milestone-ish suffixes seen in
  filenames, not formally documented in the files themselves.
- Every migration file sets `revision`/`down_revision`/`branch_labels`/
  `depends_on` explicitly (`t13_p0_note_draft_status.py:21-24`) and provides
  both `upgrade()`/`downgrade()`.
  `t12_merge_p0_m1_heads.py` exists specifically to merge two divergent heads
  (`t12_p0_doctor_review_decisions` + `t12_m1_meto_conv_review`) back to one —
  i.e. the project has hit multi-head problems before and merges them
  explicitly rather than leaving multiple heads. Single-head discipline is
  enforced by convention/review, not by tooling seen in this audit.
  (Recall from memory: a previous production incident was an oversized
  revision id exceeding Postgres `alembic_version` varchar(32) — keep new
  Clinic SaaS revision ids short.)
- No naming or tooling artifact enforces per-tenant migration concerns (e.g.
  row-level security, schema-per-tenant) — a Clinic SaaS multi-tenant model
  would be a first for this migration history.

## 15. Frontend Shells (admin / doctor / patient)

- **Admin shell**: `frontend/src/app/admin/(admin-shell)/layout.tsx` (full
  file read). Route guard: `ADMIN_ROLES = ['internal_admin', 'super_admin',
  'clinic_admin']` (line 25); redirects unauthenticated → `/login`,
  wrong-role → `getRoleHomePath(user.role)`, and unenrolled-MFA admins →
  `/mfa-setup` (lines 104-121). Nav includes a **"Phòng khám" (Clinics)**
  item (lines 40-45) pointing at `/admin/clinics`.
  - `frontend/src/app/admin/(admin-shell)/clinics/page.tsx` (full file
    read): **confirmed placeholder** — renders an `Alert` "Tính năng đang
    phát triển" ("Feature under development") and an `EmptyState` "Chưa có
    dữ liệu phòng khám" ("No clinic data yet"). **No API call, no data
    fetching, no clinic list/CRUD UI exists.** This is purely a nav
    placeholder, not a tenant model.
- **Doctor shell**: `frontend/src/app/doctor/(doctor-shell)/layout.tsx` (full
  file read). Route guard: `CLINICAL_ROLES = ['doctor', 'medical_reviewer']`
  (line 20); same auth/role/redirect pattern as admin shell but simpler (no
  MFA-enrollment redirect here). Nav has Dashboard/Queue/Patients/
  Appointments/Notes/Consultations/Marketplace-profile — **no clinic
  switcher or clinic-scoped view of any kind**. This is the closest existing
  analog to a future `ClinicShell`: same `PortalShell` component, same
  `useAuth()` + role-array guard pattern — reuse this shape directly.
- **Patient routes**: `frontend/src/app/(patient)/` — lower priority per
  task scope; large route tree (dashboard, labs, medications, consultations,
  marketplace, ai-copilot, etc.), no clinic concept present.

## 16. Shared API Client

- `frontend/src/lib/api/client.ts` (full file read): single `apiFetch<T>()` +
  `api.{get,post,patch,put,del}` wrapper (lines 96-211). Handles bearer token
  attach, single-flight refresh-on-401 (`tryRefreshTokens`, lines 83-89,
  dedupes concurrent refreshes to avoid triggering backend refresh-token
  reuse detection — see comment lines 56-58), redirect-to-login on refresh
  failure, and structured error parsing into `ApiError`
  (`toPageError`, lines 25-33). `apiUpload<T>()` (152-184) is the multipart
  variant.
- Per-domain files sit alongside it: `lib/api/{doctor,marketplace,meto,
  admin,consultations,patient,doctorMarketplace,adminDoctors,...}.ts` — the
  established convention is one file per bounded-context domain calling
  through the shared `api` object. A future `lib/api/clinics.ts` (or
  similar) should follow this exact pattern.

---

## Cross-Cutting Observations

1. **A partial "Clinic" concept already exists in the schema** (`Clinic`,
   `Doctor.clinic_id`, `DoctorClinic`, `assert_clinic_scope`/
   `assert_doctor_assigned` in rbac.py) but it is **not wired into the
   primary patient data model or the primary auth path** — it only backs one
   legacy, currently-dormant AI-triage/Encounter/CarePlan flow. There is no
   `ClinicAdmin` membership model, no clinic CRUD API (schemas `ClinicCreate`/
   `ClinicOut` exist in `schemas/care.py` but are not wired to any route —
   confirmed no `/clinics` path in any router file), and the frontend
   admin "Clinics" page is a placeholder.
2. **No table in the entire clinical data model carries a tenant/clinic
   column** — `patient_profiles`, `health_metrics`, `lab_documents`,
   `care_plans`, `encounters`, `appointments`/`booking_appointments`,
   `consultations`, `notifications`, `meto_conversations`, `ai_sessions`,
   `audit_logs` are ALL global/per-user or per-relationship only.
3. **Two authorization patterns coexist** without a unifying tenant concept:
   role-bypass RBAC (`api/deps.py`) used almost everywhere, and
   narrow scoped-grant RBAC (`consultation_access.py`, `rbac.py`'s
   DoctorClinic check) used only in two isolated features.
4. **Feature flags are global**, no per-tenant override mechanism exists yet.
