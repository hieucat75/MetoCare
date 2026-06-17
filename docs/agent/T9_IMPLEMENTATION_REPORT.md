# T9 Implementation Report — Health Metrics + Consent Routes RBAC Hardening

**TASK_ID:** T9  
**Branch:** `feature/t9-health-consent-rbac`  
**Implementer:** Antigravity (Claude Code subagent)  
**Date:** 2026-06-18 GMT+7  
**Status:** ✅ READY FOR CODEX REVIEW

---

## Summary

Both route files that previously used bare `current_user_id` (no RBAC) have been hardened with `CurrentUser` + `require_roles`. All 5 routes are now enforced. 26 new API tests added; 274 total (baseline 248).

---

## Changes Made

### 1. `backend/app/api/v1/routes/health.py` — RBAC Hardened

**Before:** All 3 routes used `requester_id: str = Depends(current_user_id)` — no role check.

**After:**

| Endpoint | Allowed Roles |
|----------|---------------|
| `POST /patients/{id}/metrics` | PATIENT, DOCTOR, INTERNAL_ADMIN, SUPER_ADMIN |
| `GET /patients/{id}/metrics` | PATIENT, DOCTOR, CLINIC_ADMIN, INTERNAL_ADMIN, SUPER_ADMIN |
| `GET /patients/{id}/metrics/trend` | PATIENT, DOCTOR, CLINIC_ADMIN, INTERNAL_ADMIN, SUPER_ADMIN |

**AI_SERVICE:** Blocked from all 3 routes.

**PATIENT ownership enforcement:** Added `_enforce_patient_ownership()` helper that:
- Looks up the `PatientProfile` by `patient_id`
- Checks `profile.user_id == user.id`
- Raises 403 if mismatch (only for PATIENT role)
- DOCTOR/ADMIN bypass ownership (service-layer consent gate handles their access)

**Service-layer consent gate preserved:** `health_metrics.create_metric`, `list_metrics`, and `trend` still call `consent.require_access(...)` internally.

---

### 2. `backend/app/api/v1/routes/consent.py` — RBAC Hardened (P0 Legal)

**Before:**
- Both routes used `requester_id: str = Depends(current_user_id)`
- Ownership check: fragile `consent.has_access(scope="__owner__")` which relied on a scope string that didn't correspond to a real scope

**After:**

| Endpoint | Allowed Roles |
|----------|---------------|
| `POST /patients/{id}/consents` (grant) | **PATIENT only** |
| `DELETE /patients/{id}/consents/{id}` (revoke) | **PATIENT only** |

**DOCTOR / CLINIC_ADMIN / INTERNAL_ADMIN / SUPER_ADMIN / AI_SERVICE:** All return 403. This is a P0 legal requirement under Luật BVDLCN Vietnam 2026.

**PATIENT ownership enforcement:** Added `_enforce_consent_ownership()` helper:
- Looks up `PatientProfile` by `patient_id`
- Checks `profile.user_id == user.id`
- Raises 404 if profile not found, 403 if user doesn't own it

**Audit records preserved:** `audit.record()` for `grant_consent` and `revoke_consent` kept intact, now using `user.id` from `CurrentUser` (same semantic as before).

---

### 3. `backend/tests/api/test_health_api.py` — NEW (14 tests)

| Test ID | Test Name | Expected |
|---------|-----------|---------|
| H01 | `test_patient_creates_own_metric` | 201 |
| H02 | `test_doctor_creates_metric_for_patient` | 201 (with consent) |
| H03 | `test_patient_cannot_create_metric_for_another_patient` | 403 |
| H04 | `test_ai_service_cannot_create_metric` | 403 |
| H05 | `test_unauthenticated_cannot_create_metric` | 401 |
| H06 | `test_patient_lists_own_metrics` | 200, list |
| H07 | `test_patient_cannot_list_another_patients_metrics` | 403 |
| H08 | `test_admin_lists_any_patient_metrics` | 200 |
| H09 | `test_unauthenticated_cannot_list_metrics` | 401 |
| H10 | `test_patient_gets_own_trend` | 200, has `count` |
| H11 | `test_patient_cannot_get_another_patients_trend` | 403 |
| H12 | `test_unauthenticated_cannot_get_trend` | 401 |
| H13 | `test_trend_returns_empty_when_no_data` | 200, count=0 |
| H14 | `test_clinic_admin_can_read_metrics` | 200 (with consent) |

---

### 4. `backend/tests/api/test_consent_api.py` — NEW (12 tests)

| Test ID | Test Name | Expected |
|---------|-----------|---------|
| C01 | `test_patient_grants_consent_for_own_data` | 201 |
| C02 | `test_patient_cannot_grant_consent_for_another_patient` | 403 |
| C03 | `test_doctor_cannot_grant_consent` | **403 (P0)** |
| C04 | `test_admin_cannot_grant_consent` | **403 (P0)** |
| C05 | `test_ai_service_cannot_grant_consent` | 403 |
| C06 | `test_unauthenticated_cannot_grant_consent` | 401 |
| C07 | `test_patient_revokes_own_consent` | 200 |
| C08 | `test_doctor_cannot_revoke_consent` | **403 (P0)** |
| C09 | `test_admin_cannot_revoke_consent` | **403 (P0)** |
| C10 | `test_revoke_nonexistent_consent` | 404 |
| C11 | `test_unauthenticated_cannot_revoke_consent` | 401 |
| C12 | `test_patient_revoke_another_patients_consent_is_forbidden` | 403 |

---

## Validation Results

```
ruff check .        → All checks passed
pytest tests/       → 274 passed, 1 skipped (baseline 248, +26 new)
```

---

## Acceptance Criteria Checklist

- [x] All 5 routes use `CurrentUser` (not bare `current_user_id`)
- [x] `require_roles` applied with correct sets per endpoint
- [x] PATIENT ownership enforced for health metrics (403 on mismatch)
- [x] PATIENT-only enforcement on consent grant/revoke (403 for DOCTOR/ADMIN/AI_SERVICE)
- [x] AI_SERVICE blocked from all 5 routes
- [x] Existing service-layer consent gate preserved in health routes
- [x] Audit records preserved for grant_consent + revoke_consent
- [x] All 26 test cases pass
- [x] Zero existing tests broken (274 total, 248 baseline)
- [x] Ruff clean
- [x] `docs/agent/T9_IMPLEMENTATION_REPORT.md` written

---

## Security Notes

- **P0 Legal Compliance:** Tests C03, C04, C08, C09 explicitly verify that DOCTOR and INTERNAL_ADMIN cannot grant or revoke patient consent. These are enforced at the route level via `require_roles(UserRole.PATIENT)` before any service logic executes.
- **Defense in depth:** Route-level ownership check + service-layer consent gate. Even if the route check were bypassed, the service would reject unauthorized access.
- **AI_SERVICE isolation:** `AI_SERVICE` is excluded from all 5 routes by role allowlist — it never appears in the allowed sets.

---

*Report generated: 2026-06-18 GMT+7 | Branch: feature/t9-health-consent-rbac*
