# Codex Review — Clinic SaaS C1 M06 Patient Management

**Reviewer:** Codex (read-only, `codex exec -s read-only`)
**Date:** 2026-07-09
**Branch:** clinic-saas/c1-m06-patient-management
**Base:** main @ `911d40e`

---

## Round 1 — Initial security review

**Scope:** tenant isolation/BOLA, PHI leakage (field-level role filtering,
consent-shared read path), consent-gate correctness, race conditions
(check-then-insert), DB constraint correctness (shell-account phone
uniqueness), RBAC completeness vs `RBAC_MATRIX.md`, Clinical Copilot guard
regression, frontend XSS/capability-bypass, test-coverage gaps against the
plan's 11-item security matrix.

**VERDICT: FAIL**

P0: 1 · P1: 1 · P2: 2

**Findings:**

1. **P0** (`app/services/clinic_patients.py:176`, `app/api/v1/routes/clinic_patients.py:161`) —
   `link_patient` trusted any submitted `patient_id` with no proof of
   legitimate contact. A receptionist/admin at Clinic B who merely learned a
   Clinic A patient's UUID (leaked id, another system's URL, cross-clinic
   staff access) could link that patient to Clinic B and immediately receive
   the full administrative record (name/DOB/address/phone) — entirely
   bypassing the phone-based dedup/consent design this milestone is built
   around.
2. **P1** (`app/api/v1/routes/clinic_patients.py:58`) — `_UPDATE_ROLES`
   excluded `ClinicRole.RECEPTIONIST`, but `RBAC_MATRIX.md`'s "Patient admin
   record (M06)" row and BRD §6.2 ("Receptionist: Tạo/sửa hồ sơ hành chính" —
   create/**edit** administrative records) both grant Receptionist full
   read+write. The status/internal_notes PATCH was incorrectly Owner/Admin-only.
3. **P2** (`app/services/consent_guard.py:63` via call site
   `app/api/v1/routes/clinic_patients.py:250`) — `ConsentGuard.require`'s
   `is_self` bypass compares `actor_id` against `patient_id`/
   `PatientProfile.user_id`; for M06's clinic-actor consent check
   (`actor_id=clinic_id`), this could theoretically self-bypass on a UUID
   collision between a `clinic_id` and a `patient_id`/`user_id`.
4. **P2** (`backend/tests/api/test_clinic_patient_management_m06_api.py`) —
   the file's docstring claimed "concurrent-race safety net" coverage, but
   only sequential duplicate flows were exercised; the `User.phone`
   IntegrityError branch in `create_patient` had no test forcing it.

---

## Fixes applied

| Fix | Detail |
|---|---|
| P0 | `link_patient` now requires a `phone` field (schema + route + frontend), re-verified server-side against the target patient's real phone (`User.phone` or, for the shared-phone override-create path, `PatientProfile.phone`) before creating the relationship. Mismatch → controlled 400, never a silent link. |
| P1 | `_UPDATE_ROLES` expanded to `(OWNER, ADMIN, RECEPTIONIST)`, matching `RBAC_MATRIX.md` + BRD §6.2. Frontend `canUpdatePatientRecord` capability updated to match. |
| P2 (self-bypass) | **Accepted risk, not code-changed.** UUID4 collision probability (~1/2^122 per comparison) is the same negligible collision space every other FK/PK relationship in this schema already relies on being safe; modifying the shared, safety-critical `ConsentGuard` (used by `ai_sessions`/`clinical_copilot`) for M06 alone is out of proportion to the threat. Documented inline at the call site. |
| P2 (test gap) | Added `test_create_patient_concurrent_phone_race_safety_net` (monkeypatches `find_by_phone` to simulate the TOCTOU loser, asserts the DB unique-constraint IntegrityError is mapped to a controlled 400) and `test_link_wrong_phone_rejected` (P0 regression). The relationship-level unique-constraint race (`_insert_relationship`'s `uq_clinic_patient_rel_clinic_patient`) was already exercised by the existing `test_link_same_patient_twice_rejected` (same code path — no separate pre-check exists that would behave differently under a true concurrent race vs. two sequential calls). |

Verification after fixes: 29 targeted tests green (26 original + 3 new),
full backend suite green, frontend 507/507 tests green, clean build,
zero new typecheck errors.

---

## Round 2 — Follow-up verification review

(recorded below once complete)
