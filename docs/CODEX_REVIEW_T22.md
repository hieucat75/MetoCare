## Codex Review — T22 Doctor Portal Summary API

**Branch:** `feature/t22-doctor-portal`
**Reviewer:** Codex (read-only)
**Date:** 2026-06-18
**Baseline:** main @ 475 passed, 1 skipped

---

**Result:** APPROVE

**P0 Blockers:** 0
**P1 Blockers:** 0
**P2 Warnings:** 2
**Security:** PASS
**Test Results:** 485 passed, 1 skipped
**Acceptance Criteria:** 10/10 met

---

### Acceptance Criteria Evaluation

| AC | Description | Verdict | Notes |
|----|-------------|---------|-------|
| AC1 | `PatientSummaryOut` contains all 8 keys | **PASS** | All 8 keys present: `vitals`, `lab_documents`, `metabolic_score`, `medications`, `symptoms`, `nutrition`, `upcoming_appointments`, `active_care_plans`. Plus `patient_id` + `generated_at`. |
| AC2 | RBAC: DOCTOR+consent → 200; PATIENT → 403; AI_SERVICE → 403; ADMIN → 200 no consent | **PASS** | Explicit `_SUMMARY_BLOCKED` frozenset blocks PATIENT, AI_SERVICE, CLINIC_ADMIN. Admin bypasses consent. Tests 4, 5, 7 verify. |
| AC3 | DOCTOR without consent → 403/404 | **PASS** | `require_access()` raises `ConsentError` → 403. Test 6 verifies. |
| AC4 | medications excludes soft-deleted | **PASS** | `_fetch_medications` filters `Medication.deleted_at.is_(None)`. Test 3 verifies active-only. |
| AC5 | vitals has `latest` list + `trend` string | **PASS** | `VitalsSummary` schema enforces both fields. `_compute_vitals_trend` returns one of: `improving`/`stable`/`worsening`/`insufficient_data`. Test 2 verifies. |
| AC6 | `GET /doctors/me/appointments` → DOCTOR only; PATIENT/AI_SERVICE → 403 | **PASS** | Route enforces `user.role != UserRole.DOCTOR → 403`. Tests 9 and 10 verify. |
| AC7 | Appointments filter: pending/confirmed, ordered by slot_start ASC | **PASS** | `list_doctor_appointments` uses `.where(status.in_(["pending", "confirmed"]))` + `.order_by(DoctorAvailability.slot_start.asc())` via JOIN. |
| AC8 | `ruff check .` passes | **PASS** | `All checks passed!` — confirmed. |
| AC9 | Full suite: 485+ passed | **PASS** | `485 passed, 1 skipped` — meets target exactly. +10 new tests from T22. |
| AC10 | No N+1 queries | **PASS** | Each `_fetch_*` helper issues exactly 1 `SELECT`. `build_summary` calls 8 helpers = 8 bounded queries, no per-record loops. Verified by AST inspection: 1 `select()` + 1 `execute()` per helper function. |

---

### P2 Warnings

**P2-1: Vitals trend direction assumes "higher = worse"**

`_compute_vitals_trend` computes `delta_pct = (last - previous) / abs(previous) * 100` and maps `> 5%` → `worsening`, `< -5%` → `improving`. This assumption is valid for blood glucose, HbA1c, and blood pressure but **inverted** for Hb, O2 saturation, and exercise metrics. The service also short-circuits to `insufficient_data` when multiple metric types are mixed in the 5-row window, which partially mitigates the issue — but a per-metric-type trend direction map (e.g., via a lookup dict keyed on `metric_type`) would be more robust.

**Severity:** P2 (future sprint item — not a correctness bug for current MVP metrics, and the `insufficient_data` fallback prevents bad UI)

---

**P2-2: `list_doctor_appointments` does not filter by `slot_start >= now`**

`GET /doctors/me/appointments` returns pending/confirmed appointments ordered by slot_start ASC, but does **not** exclude past slots. If a confirmed appointment's slot has already passed (e.g., a no-show), it will continue to appear. The patient-facing `_fetch_upcoming_appointments` in `patient_summary.py` correctly applies `DoctorAvailability.slot_start >= now` — the doctor-facing route lacks this guard.

**Severity:** P2 (no data correctness bug; historical pending/confirmed appointments are rare in MVP; recommend adding `slot_start >= utcnow()` filter in a follow-up)

---

### Summary

T22 is a clean, well-structured implementation. The service layer is modular and readable — 8 single-query helpers called once per request, with no N+1 patterns. RBAC is correctly enforced with explicit role blocking and consent gating. All 10 acceptance criteria are met. The test suite grows by 10 targeted tests covering all RBAC paths and the medication filter edge case.

Two P2 warnings are flagged for future sprints: a metric-agnostic vitals trend direction issue and a missing future-slot filter on the doctor appointments endpoint. Neither blocks merge.

**Recommendation: APPROVE for merge to main.**
