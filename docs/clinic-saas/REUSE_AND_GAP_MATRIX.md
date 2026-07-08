# MetoCare Clinic SaaS — Reuse & Gap Matrix

Companion to `CURRENT_ARCHITECTURE_AUDIT.md`. Read-only audit; no code changed.

| Concern | Current State (file refs) | Classification | Rationale |
|---|---|---|---|
| User/identity | `backend/app/models/user.py:39-66` — single `users` table, `UserRole` enum incl. `CLINIC_ADMIN` (line 19); no tenant column | **Extend** | Identity table itself is fine to keep (email/phone dual login, MFA fields). Needs a new membership table (e.g. `ClinicMember`/`ClinicUser`) to say *which* clinic(s) a `clinic_admin`/`doctor` belongs to with what role — `users` itself should not gain a single `clinic_id` (a doctor/clinic_admin can plausibly belong to >1 clinic, matching the existing `DoctorClinic` many-to-many shape). |
| RBAC core | `backend/app/core/rbac.py` (all), `backend/app/api/deps.py:96-108` `require_roles` | **Extend** | `require_roles` (global role gate) is a solid, reusable primitive — keep as-is. `assert_doctor_assigned`/`DoctorClinic` (`rbac.py:63-105`) is the right *shape* for clinic scoping and should be generalized/extended to cover all clinic-scoped resources, not just Encounter/CarePlan. `assert_clinic_scope` (`rbac.py:108-124`) is a stub ("we accept any clinic_admin role", line 118-120) and must be replaced with a real membership check once a `ClinicAdmin`/membership model exists. |
| Audit logging | `backend/app/models/governance.py:54-70` (`AuditLog`), `backend/app/services/audit.py:14-40` (`record()`) | **Reuse** | Append-only, generic `actor_type`/`resource_type`/`resource_id`, already the established convention across doctor-review and consultation-access flows. No PHI is stored, so no encryption/consent concerns block reuse. Clinic-scoped actions should just call `audit.record()` with clinic id in `resource_id` or a descriptive `action` string — no schema change strictly required (though adding an optional `clinic_id` column would make querying easier; a pure additive migration, not a redesign). |
| Consent model | `backend/app/models/governance.py:20-51` (`Consent`), `backend/app/services/consent.py`, `backend/app/services/consent_guard.py` | **Extend** | `Consent.granted_to` is a bare unconstrained string id (no FK, `governance.py:27`) already designed to hold "doctor or clinic id" per its own comment — so granting consent to a clinic is *conceptually* supported today, but nothing populates or validates it against a real `Clinic` row, and no service resolves "is this patient's data visible to any active member of clinic X" (only exact `granted_to` match, `governance.py:48`). Needs a service-layer extension (resolve clinic membership → check consent), not a schema replacement. |
| Patient profile | `backend/app/models/patient.py:18-45` | **Extend** (add tenant boundary), **Must-Not-Touch** (PHI encryption/columns) | The encrypted PHI columns, 1:1 `user_id` FK, and `EncryptedString` pattern must be preserved exactly (touching them risks breaking decrypt-fallback contracts documented at `patient.py:24-27`). What's missing is any tenant/clinic linkage — likely needs an additive nullable `primary_clinic_id` or, more consistently with the doctor model, a separate `PatientClinic` membership table so a patient can be a member of >1 clinic (mirrors `DoctorClinic`). This is new work, not a replacement of the existing table. |
| Doctor profile | `backend/app/models/care.py:74-104` (`Doctor`), `:106-117` (`DoctorClinic`) | **Reuse** (schema), **Extend** (usage) | The schema (`Doctor` + `DoctorClinic` junction) already models multi-clinic doctor membership correctly. The gap is entirely in usage: only 2 legacy code paths query `DoctorClinic` (`doctor_review.py` route+service). Marketplace/consultation flows and AISession routes bypass it entirely (`ai_sessions.py:64-66` comments admit this explicitly). Reuse the table; extend its consumers. |
| Consultation/marketplace scoping | `backend/app/models/consultation.py` (`Consultation`, `ConsultationAccessGrant`), `backend/app/services/consultation_access.py` (`assert_doctor_can_view`, lines 56-112) | **Reuse as the pattern; Must-Not-Touch the invariants** | This is the best-designed access-control primitive in the codebase: time-boxed, revocable, single-relationship grants + mandatory audit on every read (`consultation_access.py:101-110`), verified-doctor defense-in-depth check (lines 80-88). A Clinic SaaS "doctor sees patients at their clinic" feature should be modeled the same way — a `ClinicAccessGrant`-style construct, not a blanket "any doctor at clinic X sees all patients" bypass. Do not weaken `ConsultationNote`'s append-only invariant (`consultation.py:159-163`, no update/delete function exists by design) or `ConsultationAccessGrant.is_active()` semantics (`consultation.py:240-252`) — these are explicit safety invariants called out in the module docstring. |
| Feature flags | `backend/app/core/feature_flags.py` (all) | **Extend** | `FeatureFlag` enum + env-var-driven `is_enabled()` (fail-closed, line 73) is a clean, reusable convention for a global `CLINIC_SAAS` on/off switch. It has **no per-tenant override** mechanism, though — gating C0 rollout per-clinic needs a new layer on top (e.g. a `clinic_feature_overrides` table checked before falling back to the global default), not a change to the existing enum/env pattern. |
| Admin shell | `frontend/src/app/admin/(admin-shell)/layout.tsx` (role guard `ADMIN_ROLES`, lines 25, 104-121) | **Reuse** | `AppShell`/`Sidebar`/`TopNav` composition + `useAuth()` + role-array redirect guard + MFA-enrollment redirect is a clean, working pattern. A clinic-admin-specific view can reuse this shell (it already includes `clinic_admin` in `ADMIN_ROLES`, line 25) — likely just needs new nav items and page routes, not a new shell. |
| Doctor shell | `frontend/src/app/doctor/(doctor-shell)/layout.tsx` (role guard `CLINICAL_ROLES`, line 20) | **Reuse** | Same `PortalShell` + `useAuth()` + role-array guard pattern, simpler (no MFA-enrollment step). This is the closest existing analog to a future `ClinicShell` for clinic staff — copy this file's structure almost verbatim for a new clinic-scoped portal. |
| Shared API client | `frontend/src/lib/api/client.ts` (`apiFetch`, `api.{get,post,patch,put,del}`, `apiUpload`) | **Reuse** | Token refresh dedup, structured `ApiError`, multipart upload variant — all domain-agnostic and already used by every existing `lib/api/*.ts` file. A new `lib/api/clinics.ts` should be a thin wrapper around this, exactly like `lib/api/marketplace.ts`/`lib/api/consultations.ts`. |
| Existing "clinics" admin page | `frontend/src/app/admin/(admin-shell)/clinics/page.tsx` (full file, 27 lines) | **Replace** | Confirmed: this is a **static placeholder** — an `Alert` saying "feature under development" and an `EmptyState`, no API call, no data. It currently means "a nav link exists"; it does NOT mean a clinic list/tenant UI exists. Full replacement expected, not extension of existing logic (there is none to extend). |
| Alembic migration conventions | `backend/alembic/versions/t13_p0_note_draft_status.py`, `t12_merge_p0_m1_heads.py`, 45 files total | **Reuse** | Explicit `revision`/`down_revision`/`branch_labels`/`depends_on` + both `upgrade()`/`downgrade()` per file, `tNN_pM/mM_description` naming, single-head discipline (enforced by an explicit merge migration when heads diverged). Follow this convention for Clinic SaaS migrations. **Caveat from prior incident** (see project memory): keep new revision ids short — a previous production migration failed because its revision id exceeded Postgres's `alembic_version` `varchar(32)` column (fixed in PR #93). |
| Notifications | `backend/app/models/notification.py:40-73` | **Extend** | Per-user, admin-only creation (docstring line 47). No clinic-scoped broadcast exists; would need either a new `type`/`metadata_` convention (e.g. `metadata_` JSON carrying `clinic_id`) or a genuinely new fan-out service — additive, not a redesign. |
| AI Clinical Copilot / Meto | `backend/app/api/v1/routes/clinical_copilot.py`, `backend/app/services/clinical_copilot.py`, `backend/app/ai/`, `backend/app/knowledge/` | **Extend** (access control), **Reuse** (provider/gateway infra) | The provider registry/circuit-breaker/RAG infra (`ai/registry.py`, `ai/providers/`, `knowledge/`) is tenant-agnostic infrastructure and should be reused as-is. What's missing is any clinic-scoped access check on the 4 Clinical Copilot endpoints (`clinical_copilot.py:102-187`) — today gated only by `FeatureFlag.CLINICAL_COPILOT` (global) plus whatever role dependency wraps the router, not by a `ConsultationAccessGrant`-style scoped check. If Clinic SaaS doctors should only copilot on their clinic's patients, this needs a new guard modeled on `consultation_access.assert_doctor_can_view`. |

## In-Flight Work / Overlap Risk

- `git branch -a` (66 local + matching remote branches) and
  `gh pr list --state open` were both checked. **Only 2 PRs are open**:
  - PR #53 `feat/patient-ui-replacement` — "Decision-First UI replacement
    (Mint Liquid Glass) — frontend only" (patient app UI, updated
    2026-07-01).
  - PR #48 `feat/patient-care-plan-liquid-glass` — "Care Plan screen →
    Liquid Glass per-screen rebuild" (patient app UI, updated 2026-07-01).
  Neither touches clinic/tenant/RBAC/backend data model. **No overlap risk
    found** for Clinic SaaS work as of this audit (2026-07-08).
- Many stale local/remote feature branches exist (`feat/doctor-*`,
  `feature/t*-*`, etc.) but none are open PRs and none reference
  clinic/tenant work in their names. Recommend a quick `git log
  <branch> --oneline -5` spot-check only if Clinic SaaS work is assigned to
  reuse one of these branch names, otherwise safe to ignore.
- Per project memory (`MEMORY.md`), the most recent merged work (PR #93,
  #94-ish "doctor" feature `ec25db4` Meto Clinical Copilot, and PR #87
  relaxed-auth-policy) all touch `core/feature_flags.py`,
  `core/rbac.py`-adjacent auth code, and `users`/MFA — worth a rebase check
  before starting Clinic SaaS branch work to avoid trivial merge conflicts
  in `feature_flags.py` and `api/deps.py`, even though no *open PR* conflicts
  today.

## Biggest Structural Risk (see agent's final summary for the one-line version)

No table anywhere in the clinical data model (`patient_profiles`,
`health_metrics`, `lab_documents`, `care_plans`, `encounters`,
`appointments`/`booking_appointments`, `consultations`, `notifications`,
`meto_conversations`, `ai_sessions`, `audit_logs`) carries a tenant/clinic
column. The one partial "Clinic" concept that exists (`Clinic`,
`Doctor.clinic_id`, `DoctorClinic`, `assert_clinic_scope`/
`assert_doctor_assigned`) is wired into exactly one legacy, currently-dormant
flow (Encounter/CarePlan/AI-recommendation review) and explicitly skipped
elsewhere (`ai_sessions.py:64-66` comments this outright). Retrofitting
multi-tenant clinic scoping is therefore a genuine cross-cutting change
touching most of the schema and both existing authorization patterns — not
a bolt-on.
