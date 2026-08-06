# Clinic SaaS C1 M06 — Patient Management — Implementation Plan

Baseline: `main` @ `911d40e` (M05 merged, CI+staging green). Source docs read before
this plan: `docs/brd/v2.0/m06-patient.md`, `docs/clinic-saas/BRD_ANALYSIS.md` (M06
section), `docs/clinic-saas/REQUIREMENTS_TRACEABILITY.md` (BR-M06 rows),
`docs/brd/v2.0/appendix-a-rbac-matrix.md`, `docs/clinic-saas/RBAC_MATRIX.md`, plus a
fresh codebase audit (models, routes, services, RBAC helpers, `TenantContext`,
frontend) — not the C0-era design docs alone, since those predate the actual code.

## 1. Boundary clarification (per instruction, before any schema work)

| Layer | Owner table | Notes |
|---|---|---|
| **Global identity** | `patient_profiles` (`PatientProfile`) | One row per platform `User`. Encrypted PHI (`full_name`, `dob`, `phone`, `address`, `known_conditions`, `allergies`, `family_history`, `lifestyle_profile`). **Never gets a `clinic_id` column** — a patient keeps one longitudinal identity across every clinic. Not altered by M06. |
| **Patient↔clinic relationship** | `clinic_patient_relationships` (`ClinicPatientRelationship`) — **already exists from C0**, currently unwired | `patient_id`, `clinic_id`, `patient_code` (unique per clinic), `status` (`active\|inactive\|merged`), `first_seen_at`. This row's existence at clinic X **is** BR-M06-02's "data this clinic created" — necessary but not sufficient for clinical-data access. |
| **Clinic-owned metadata** | New: `internal_notes` (clinic-only text, non-PHI operational note) added to `ClinicPatientRelationship` (additive column) | Nothing else — patient_code/status already modeled correctly on this table. |
| **Consent / care relationship** | `consents` (`Consent`, existing model) | `granted_to` is a bare string already designed to hold a clinic id (no FK). Cross-clinic administrative/clinical visibility beyond own-created requires an active `Consent` row here — M06 enforces the read side; a grant-creation UI is out of scope (M17's job), but the check must be real, not a stub. |
| **Clinical/PHI content** | Encounters, notes, labs, diagnoses | **Explicitly out of scope for M06.** M06's patient detail view is the administrative/roster record only. Clinical content is M09's surface. Receptionist must never receive clinical fields from any M06 endpoint (BR-M06-03, enforced at response-schema level per `RBAC_MATRIX.md`, not just route 403). |

## 2. Reuse vs. additive-build

| Concern | Call | Why |
|---|---|---|
| `PatientProfile` | **Reuse, untouched** | Confirmed no clinic dimension exists or should exist there. |
| `ClinicPatientRelationship` | **Reuse table, build the entire consumer surface** | Schema already correct (`patient_code` uniqueness, `active\|inactive\|merged` status matching BR-M06-01 exactly). Zero routes/services touch it today — this is 100% new wiring, not a retrofit. |
| `assert_clinic_membership` / `TenantContext` / `require_clinic_roles` (`rbac.py`, `deps_tenant.py`) | **Reuse as-is** | Already the correct C0/M05 pattern; M06 routes use these exactly like `clinic_services.py` does. Do **not** use `assert_doctor_assigned` (that's the deliberately-untouched legacy `DoctorClinic` path for Encounter/CarePlan). |
| Patient search/pagination over encrypted columns | **Reuse the `admin_patients.py` pattern** (SQL candidate-query on plaintext fields + capped in-Python filter/sort on decrypted fields, `_CANDIDATE_LIMIT`-style bound) | `PatientProfile`'s PHI columns are non-deterministically encrypted — cannot be filtered/sorted in SQL. This exact problem is already solved once in this codebase; don't reinvent it. Known limitation (5000-row cap) inherited as-is; a blind-index fix is flagged but out of scope. |
| Consent gate | **Reuse `Consent`/`is_active()` as-is** | Model already supports clinic-id grantees; M06 adds the query-time check, not a schema change. |
| `assert_doctor_clinic_scope_for_patient` (existing Clinical Copilot guard) | **No code change — but its behavior changes the moment M06 writes rows** | It's a documented no-op today because zero `ClinicPatientRelationship` rows exist. M06 activates it as a side effect. Must be covered by a regression test, not treated as a new integration to build. |
| Frontend `clinic/patients` route | **New — no placeholder exists** (unlike `clinic/services`, which had a stub before M05) | Fully greenfield UI. |

## 3. Scope for this PR (BRD is larger than the "minimum required" list — scoping explicitly, not silently dropping)

**In scope** (matches the standing-approval "yêu cầu chức năng tối thiểu" list):
- Clinic patient roster: list, clinic-scoped, paginated (BR-M06-06), search by phone/name (candidate-query pattern above).
- **Link an existing patient** to the clinic: search platform-wide by phone (dedup-safe — this *is* the anti-duplication mechanism), create `ClinicPatientRelationship` if not already linked.
- **Create a new patient**: dedup pre-check (phone exact match primarily, per BR-M06-02/PATIENT-02 priority order) before creating a new `PatientProfile` — warn, don't auto-block, matching AC-M06-02's "warns before create," and require an explicit reason to proceed if a candidate match exists.
- Patient detail in tenant context — administrative fields only (name/phone/dob/address from `PatientProfile`, plus `patient_code`/`status`/`internal_notes`/`first_seen_at` from `ClinicPatientRelationship`). No clinical fields.
- Clinic-specific metadata: `patient_code` (already modeled), `status`, new `internal_notes`.
- Care relationship = the `ClinicPatientRelationship` row itself (its `active` status is the relationship).
- Consent enforcement: cross-clinic administrative-record visibility requires an active `Consent` row (`granted_to=clinic_id`); own-clinic (row exists at this clinic) never needs consent.
- No wrongful duplication of global identity (dedup-on-create, per above).
- No cross-clinic read/write (tenant-scoped everywhere, BOLA test matrix below).
- Revoked/suspended `ClinicMembership` loses roster access immediately (reuses the existing `TenantContext` resolution — no new mechanism needed, just verified with a test).
- Audit on every mutation (create, link, status change, note edit) via the existing `audit.record()` convention, `clinic_id` populated.

**Explicitly deferred** (documented here, not silently dropped — reported per BR-M06 items not literally required by the "tối thiểu" list):
- **US-M06-05 / PATIENT-05, full CSV/XLSX bulk import** — a standalone background-job feature (preview, per-row validation, rollback-on-mid-batch-failure). Real scope, not needed for the minimum roster/create/search/detail requirement. Fast-follow milestone.
- **US-M06-03, full Admin merge-review queue + 30-day un-merge** — merging two *already-independently-created* duplicate records (re-pointing all history to a primary) is a heavier feature than the create-time dedup check above. The create-time check is the actual anti-duplication mechanism required by this PR's scope; the after-the-fact merge workflow is deferred.
- **BR-M06-07, national ID/CCCD** — BRD itself marks this **P2** ("nice to have"). Deferred.
- **Manual lab entry (BR-M06-05's biomarker fields)** — this is clinical content entry, more naturally M09's (Encounter/Notes) concern than M06's administrative roster. Deferred to M09.
- **Branch assignment for patients** — the BRD's M06 field table does not specify per-patient branch scoping; branch context in the BRD's own flow comes from the *appointment* (M07), not the patient record itself. Not fabricating a field the BRD doesn't ask for; noting this as a explicit "BRD doesn't call for it" rather than an oversight.

## 4. Schema (additive only)

`ClinicPatientRelationship` — ALTER (new migration `c1_m06_patient_metadata`):
- `internal_notes: Text, nullable` — clinic-only operational note, no PHI (validated at write time same class of check as clinic branding's no-PHI rule).

No changes to `PatientProfile`, no changes to `Consent`. New indexes only if the query patterns below need them (e.g. `(clinic_id, status)` already exists on the table from C0 — reused, not duplicated).

## 5. API surface (new, `clinics.py`-router-adjacent, mirrors `clinic_services.py` conventions)

- `GET /clinics/{clinic_id}/patients` — roster, paginated, `?search=`. Roles: Owner/Admin/Doctor/Reception full or `L (care context)` per `RBAC_MATRIX.md` row (**response-schema filtered per role** — Care Coordinator gets the narrow care-context shape, never the full administrative record with phone/address).
- `POST /clinics/{clinic_id}/patients/link` — link existing `PatientProfile` (found by phone search) to this clinic. Roles: Owner/Admin/Reception.
- `POST /clinics/{clinic_id}/patients` — create new `PatientProfile` + `ClinicPatientRelationship` in one transaction, dedup-checked. Roles: Owner/Admin/Reception.
- `GET /clinics/{clinic_id}/patients/{patient_id}` — detail (administrative fields only). Roles per matrix, Care Coordinator gets care-context subset.
- `PATCH /clinics/{clinic_id}/patients/{patient_id}` — update `status`/`internal_notes` (clinic-owned fields only — never mutates `PatientProfile`'s global identity fields through this surface; that stays on the existing `/patients/{id}/profile` route, unchanged). Roles: Owner/Admin.
- `GET /clinics/{clinic_id}/patients/search-candidates?phone=` — dedup pre-check helper for the create flow. **Rate-considered and response-shape-limited** so it cannot become a patient-enumeration oracle (exact-phone-match only, no partial/fuzzy search exposed here, minimal fields returned).

## 6. Security test matrix (per instruction, all mandatory)

1. Cross-clinic BOLA: patient linked at Clinic A invisible/inaccessible from Clinic B without consent.
2. Multi-clinic membership: `TenantContext` resolution scopes strictly to active clinic; no bleed.
3. Revoked/suspended membership loses roster access immediately (reuse existing `TenantContext` mechanism — verify, don't rebuild).
4. Duplicate-patient linking: two concurrent "create new patient" calls with the same phone → dedup check + DB-level safety net (mirroring the M05 IntegrityError pattern for the parallel `(clinic_id, patient_code)`/global-phone race).
5. Search/pagination is tenant-scoped, capped, never returns the full dataset (BR-M06-06).
6. Consent missing/expired → cross-clinic record request denied.
7. Role matrix: Owner/Admin/Doctor/Reception/Care-Coordinator/Nurse/Accountant × read/write, positive+negative, **including response-schema field-level checks** (Receptionist/Care-Coordinator never receive clinical fields — though M06 doesn't expose clinical fields at all, verify the schema literally cannot carry them).
8. Feature-flag-OFF regression: `CLINIC_SAAS=False` → all M06 routes 503, zero behavior change to existing `/patients/*` routes.
9. Audit completeness + tenant isolation on audit rows.
10. Negative IDOR: `patient_id`, `clinic_id`, `branch_id`(n/a for M06) never trusted from client without server-side re-validation.
11. **New regression**: `assert_doctor_clinic_scope_for_patient` behavior change — a doctor with no `ClinicMembership` at the patient's linked clinic is now correctly blocked (was a no-op pre-M06).

## 7. Stop Gates carried forward from the standing approval (none expected to trigger, flagged if they do)

Building `ClinicPatientRelationship`'s consumer surface, adding one additive column, and gating via existing `Consent`/`ClinicMembership` mechanisms does not touch: `CLINIC_SAAS` flag, real tenant data, destructive `PatientProfile` changes, `DoctorClinic` consolidation, or the consent/PHI access model beyond what BRD already specifies. If the dedup/link flow reveals a need to actually **write** a new kind of consent grant (not just read-check existing ones), that stays log-only/manual for this PR — no new consent-granting UI is in scope, avoiding any Stop-Gate-adjacent PHI-model expansion.

## 8. Pipeline (same as M05 — full rigor, no shortcuts)

Branch `clinic-saas/c1-m06-patient-management` (isolated worktree, same pattern as M05) → schema/API/frontend/docs → targeted tests → full backend suite → frontend tests/typecheck/build → Postgres-equivalent SQLite upgrade→downgrade→upgrade (correct env var: `MCP_DATABASE_URL`) → Codex review loop (via the working `codex exec -s read-only` + kill-after pattern established in M05, **never re-include `frontend/tsconfig.tsbuildinfo` or other build artifacts in the reviewed diff**) → fix findings + regression tests → PR only once Codex has an explicit verdict → merge only when 0 P0/P1, no PHI/tenant-isolation blocker, CI green, migration verified, required test gaps closed → post-merge main CI + staging confirmation → M06 handoff memory.

## Self-check

No contradiction found against BRD (deferred items are BRD-real but outside the
explicitly-stated minimum scope, documented rather than dropped). No Stop Gate
touched by this scope. Proceeding to branch creation and implementation.
