# Codex Review — T16: Care Plan + Encounter Full RBAC Test Coverage

**Branch:** `feature/t16-care-plan-encounter-tests`
**Reviewed:** 2026-06-18
**Reviewer:** Codex (read-only)

---

## Codex Review — T16 Care Plan + Encounter Full RBAC Test Coverage

**Result:** ✅ APPROVE

**P1 Blockers:** None

**P2 Warnings:**
- `test_doctor_creates_care_plan` sends a create request without `encounter_id` in the body. If the API requires an encounter link for care plan creation, this test would fail with a validation error. Since test results show 359 pass, the API likely allows optional `encounter_id` at creation — but consider adding a complementary test for create-with-encounter-id to document that path explicitly.
- CLINIC_ADMIN blocked-from-encounter-create is not tested (only PATIENT and AI_SERVICE are). Not required by stated AC6, but good coverage to add in a follow-up.

**Security:** PASS

**Test Results:** 359/360 PASS (1 pre-existing skip, 0 failures, +28 new)

**Acceptance Criteria:** 10/10 met

---

## Detailed Findings

### AC1 — Care Plan Endpoints (5/5) ✅
All five endpoints covered:
- `POST /api/v1/care_plans` → `test_doctor_creates_care_plan`
- `GET /api/v1/care_plans/{id}` → `test_doctor_reads_care_plan`, `test_patient_reads_own_care_plan`, `test_patient_cannot_read_other_patients_care_plan`
- `GET /api/v1/care_plans` → `test_doctor_lists_care_plans`
- `PATCH /api/v1/care_plans/{id}` → `test_doctor_updates_care_plan`, `test_patient_cannot_update_care_plan`
- `POST /api/v1/care_plans/{id}/approve` → 4 tests (doctor, patient, ai, nonexistent)

### AC2 — Care Plan RBAC (all role paths) ✅
| Role | Test | Expected | Verdict |
|---|---|---|---|
| DOCTOR create | `test_doctor_creates_care_plan` | 201 | ✅ |
| PATIENT own read | `test_patient_reads_own_care_plan` | 200 | ✅ |
| PATIENT cross read | `test_patient_cannot_read_other_patients_care_plan` | 403 | ✅ |
| AI_SERVICE create | `test_ai_service_cannot_create_care_plan` | 403 | ✅ |
| CLINIC_ADMIN create | `test_clinic_admin_cannot_create_care_plan` | 403 | ✅ |
| Unauthenticated read | `test_unauthenticated_cannot_access_care_plan` | 401 | ✅ |

Cross-patient 403 is genuine: `other_patient_setup` fixture creates a **separate User + PatientProfile** with a different `patient_id`. The test reads `seeded_care_plan.id` (owned by `patient_setup`) using the second patient's token — correctly exercises ownership enforcement.

### AC3 — Approve edge cases ✅
- `test_patient_cannot_approve_care_plan` → 403
- `test_ai_cannot_approve_care_plan` → 403
- `test_approve_nonexistent_plan` → 404 (uses literal string `"nonexistent-plan-id-t16"`)

### AC4 — PATCH PATIENT→403 ✅
`test_patient_cannot_update_care_plan` covers this.

### AC5 — Encounter Endpoints (4/4) ✅
All four endpoints covered:
- `POST /api/v1/encounters` → 3 tests (doctor, patient forbidden, ai forbidden, all-fields)
- `GET /api/v1/encounters/{id}` → `test_doctor_reads_own_encounter`, `test_patient_reads_own_encounter`, `test_patient_cannot_read_another_patients_encounter`, `test_admin_reads_any_encounter`
- `GET /api/v1/encounters` → `test_doctor_lists_encounters`, `test_patient_lists_own_encounters`
- `PATCH /api/v1/encounters/{id}` → `test_doctor_updates_encounter`, `test_patient_cannot_update_encounter`

### AC6 — Encounter RBAC ✅
| Role | Test | Expected | Verdict |
|---|---|---|---|
| DOCTOR create/read | multiple | 201/200 | ✅ |
| PATIENT own read/list | `test_patient_reads_own_encounter`, `test_patient_lists_own_encounters` | 200 | ✅ |
| PATIENT cross read | `test_patient_cannot_read_another_patients_encounter` | 403 | ✅ |
| AI_SERVICE create | `test_ai_service_cannot_create_encounter` | 403 | ✅ |
| ADMIN read | `test_admin_reads_any_encounter` | 200 | ✅ |
| Unauthenticated | `test_unauthenticated_cannot_access_encounter` | 401 | ✅ |

Cross-patient 403 is genuine: `other_patient_setup` creates a distinct patient with no ownership of `seeded_encounter`.

### AC7 — Create with all fields ✅
`test_encounter_create_with_all_fields` sends `chief_complaint`, `notes`, `encounter_type=follow_up`, `encounter_date`, and asserts all three optional fields are preserved in the response.

### AC8 — 28 new tests, 0 regressions ✅
15 care plan + 13 encounter = 28 new tests. Baseline 331 → 359 total (+28). No failures.

### AC9 — No production code modified ✅
Only two new test files added:
- `backend/tests/api/test_care_plans_full.py`
- `backend/tests/api/test_encounters_full.py`

### AC10 — Fixture ordering (PRIORITY) ✅
`seeded_care_plan` fixture correctly creates an `Encounter` first (via `db.flush()`), captures `enc.id`, then creates the `CarePlan` with `encounter_id=enc.id`. The dependency chain is:

```
seeded_care_plan
  └─ patient_setup   (creates User + PatientProfile)
  └─ doctor_setup    (creates Clinic + User + Doctor + DoctorClinic)
  └─ [fixture body]  creates Encounter → flush → creates CarePlan
```

Care plan endpoints are **flat** (`/api/v1/care_plans`), not nested under encounters. `encounter_id` is set at DB-seed level, so no URL nesting issue exists. Ordering is correct.

---

## Minor Notes

1. **Token freshness for `clinic_admin_setup` and `admin_setup`:** These fixtures do not create DB records; they only generate bearer tokens. This is intentional for RBAC-guard tests (the guard fires before any DB lookup). Acceptable pattern for 403-path tests.

2. **`seeded_care_plan` status is `DRAFT`:** The approve test calls `POST /approve` on a DRAFT plan and expects `status == "APPROVED"`. This is correct behavior. No pre-approval state change needed.

3. **`test_patient_lists_own_encounters`** passes `patient_id` as a query param and asserts all returned encounters belong to that patient — good scope-enforcement check.

4. **Ruff clean:** No linting issues per CI.

---

**Summary:** All 10 acceptance criteria are met. Fixture setup is correct — encounter is created before care plan within `seeded_care_plan`, cross-patient 403 tests use genuinely separate patient records, and all RBAC paths are exercised. No production code was modified. Two minor P2 suggestions (create-with-encounter-id coverage, CLINIC_ADMIN encounter block test) are non-blocking nice-to-haves for a follow-up ticket.
