# T10 Implementation Report — Security Hardening: P2 Cleanup Sprint

**Task ID:** T10  
**Branch:** `feature/t10-security-hardening`  
**Implementer:** Antigravity (subagent)  
**Coordinator:** OpenClaw  
**Date:** 2026-06-18 GMT+7  
**Status:** READY FOR CODEX REVIEW

---

## Summary

All 5 items from the T10 task card have been implemented, tests pass (277/274 baseline → +3), and ruff is clean.

---

## Item 1 — Consent Cross-Patient Revoke [SECURITY fix]

**File:** `backend/app/api/v1/routes/consent.py`

**Problem:** `revoke_consent()` called `_enforce_consent_ownership()` which only verified the URL `patient_id` path parameter matched the token's `user_id`. A patient who obtained another patient's `consent_id` UUID could revoke it by using the correct `patient_id` path for their own account but passing the victim's `consent_id`.

**Fix:** Added an explicit cross-patient ownership check after `_enforce_consent_ownership`:
1. Load `consent_rec = db.get(ConsentModel, consent_id)` — return 404 if not found.
2. Resolve `patient_profile` via `select(PatientProfile).where(PatientProfile.user_id == user.id)`.
3. If `patient_profile is None` or `consent_rec.patient_id != patient_profile.id` → raise HTTP 403.

**Test added:** `test_patient_cannot_revoke_another_patients_consent` → 403

---

## Item 2 — Duplicate `AIClinicalRecommendationOut` schema [P2 cleanup]

**Files:**
- `backend/app/schemas/ai.py` — removed duplicate local class (had fewer fields: missing `encounter_id`, `content`, `key_version`, `medical_disclaimer`, `created_at`, `updated_at`)
- `backend/app/api/v1/routes/doctor_review.py` — changed import from `app.schemas.ai` to `app.schemas.clinical`

**Before:** `doctor_review.py` imported the thin 9-field version from `schemas.ai`.  
**After:** Routes now use the full 16-field canonical schema from `schemas.clinical`. All existing doctor review tests pass unchanged.

---

## Item 3 — Missing AI_SERVICE revoke consent test [P2 test gap]

**File:** `backend/tests/api/test_consent_api.py`

**Test added:** `test_ai_service_cannot_revoke_consent` → verifies that AI_SERVICE role receives 403 when attempting to call `DELETE /patients/{patient_id}/consents/{consent_id}`.

---

## Item 4 — Missing CLINIC_ADMIN lab document status test [P2 test gap]

**File:** `backend/tests/api/test_lab_api.py`

**Test added:** `test_clinic_admin_can_read_document_status` → creates a CLINIC_ADMIN user, grants them an active lab consent, then verifies `GET /lab-documents/{id}` returns 200 with correct `id`, `status`, `ocr_status` fields.

---

## Item 5 — `_require_patient_ownership` DOCTOR/CLINIC_ADMIN passthrough comment [clarity]

**File:** `backend/app/api/v1/routes/lab.py`

**Change:** Added clarifying comment in `_require_patient_ownership()`:
```python
# DOCTOR and CLINIC_ADMIN: consent gate in service layer handles access
# — no ownership check here
```

This explains why DOCTOR and CLINIC_ADMIN roles are not explicitly handled by the helper (they fall through to the consent service layer check).

---

## Validation Results

```
ruff check .  →  All checks passed!
pytest tests/ →  277 passed, 1 skipped in 5.28s  (baseline: 274 → +3 new tests)
```

### New tests (+3):
| Test | File | Expected | Result |
|------|------|----------|--------|
| `test_patient_cannot_revoke_another_patients_consent` | test_consent_api.py | 403 | ✅ PASS |
| `test_ai_service_cannot_revoke_consent` | test_consent_api.py | 403 | ✅ PASS |
| `test_clinic_admin_can_read_document_status` | test_lab_api.py | 200 | ✅ PASS |

---

## Acceptance Criteria Checklist

- [x] Item 1: Cross-patient consent revoke blocked (patient A cannot revoke patient B's consent)
- [x] Item 1: Test added: `test_patient_cannot_revoke_another_patients_consent` → 403
- [x] Item 2: No duplicate `AIClinicalRecommendationOut` in `schemas/ai.py`
- [x] Item 2: `doctor_review.py` imports from `schemas.clinical` (richer schema)
- [x] Item 2: All existing doctor review tests pass unchanged
- [x] Item 3: `test_ai_service_cannot_revoke_consent` → 403 passes
- [x] Item 4: `test_clinic_admin_can_read_document_status` → 200 passes
- [x] Item 5: Comment added to `_require_patient_ownership` in `lab.py`
- [x] Zero existing tests broken (274 baseline → 277 total)
- [x] Ruff clean

---

*Report generated: 2026-06-18 GMT+7 | Implementer: Antigravity subagent*
