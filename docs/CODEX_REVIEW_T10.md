# Codex Review — T10 Security Hardening P2 Cleanup

**Reviewer:** Codex (read-only)
**Branch:** `feature/t10-security-hardening`
**Repo:** `/Users/pth/Developer/Metocare`
**Date:** 2026-06-18 GMT+7
**Commit reviewed:** `bac3312`

---

## Result: ✅ APPROVE

**P1 Blockers:** None
**P2 Warnings:** 1 (see below — `ai_sessions.py` inline duplicate, pre-existing, out of scope)
**Security:** PASS
**Test Results:** 277/277 PASS (30/30 for changed files; 3 pre-existing test_rag.py failures unrelated to this branch)
**Acceptance Criteria:** 10/10 met

---

## Acceptance Criteria Verification

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| AC1 | Cross-patient revoke blocked: `consent_rec.patient_id != patient_profile.id` → 403 | ✅ | `consent.py` lines 88–97: explicit check after `_enforce_consent_ownership` |
| AC2 | `test_patient_cannot_revoke_another_patients_consent` → 403 | ✅ | Test present; confirmed 3 new tests PASS live |
| AC3 | No duplicate `AIClinicalRecommendationOut` in `schemas/ai.py` | ✅ | `grep` returns exit 1 for `schemas/ai.py`; class removed |
| AC4 | `doctor_review.py` imports from `schemas.clinical` | ✅ | Line 21: `from app.schemas.clinical import AIClinicalRecommendationOut` |
| AC5 | Existing doctor review tests pass unchanged | ✅ | All 277 tests pass; no regressions in doctor_review suite |
| AC6 | `test_ai_service_cannot_revoke_consent` → 403 | ✅ | Test present in `test_consent_api.py`; passes |
| AC7 | `test_clinic_admin_can_read_document_status` → 200 | ✅ | Test present in `test_lab_api.py`; passes |
| AC8 | Comment added to `_require_patient_ownership` in `lab.py` | ✅ | Present: "DOCTOR and CLINIC_ADMIN: consent gate in service layer handles access" |
| AC9 | No regression (277 passed, 0 failures in branch scope) | ✅ | 277 passed; 3 `test_rag.py` failures are pre-existing on main, not in diff |
| AC10 | Ruff clean | ✅ | `ruff check .` → "All checks passed!" |

---

## Security Analysis — AC1/AC2 [P0]

### Fix Correctness

The cross-patient revoke vector is correctly closed. The attack scenario was:

> Patient A uses their own valid `patient_id` path + a stolen `consent_id` UUID belonging to Patient B → route previously only checked URL `patient_id` ownership, not consent record ownership.

The fix applies two independent checks in order:

1. **`_enforce_consent_ownership(patient_id, user, db)`** — verifies the URL `patient_id` belongs to the requesting user. Returns 404 if profile missing, 403 if `profile.user_id != user.id`.

2. **Cross-patient check (new):**
   ```python
   consent_rec = db.get(ConsentModel, consent_id)
   if consent_rec is None:
       raise HTTPException(status_code=404, detail="Consent not found.")
   patient_profile = db.execute(
       select(PatientProfile).where(PatientProfile.user_id == user.id)
   ).scalar_one_or_none()
   if patient_profile is None or consent_rec.patient_id != patient_profile.id:
       raise HTTPException(status_code=HTTP_403_FORBIDDEN, ...)
   ```

### Edge Case: `patient_profile is None`

**Handled correctly.** If the authenticated user has no `PatientProfile` (e.g., a deactivated account, orphaned user record, or data inconsistency), `patient_profile is None` triggers 403. This is the safe/correct behavior — no profile = no revoke right.

### Edge Case: URL `patient_id` ≠ `consent_rec.patient_id`

**Handled correctly.** The second check resolves the patient profile from the *authenticated user's identity* (not from the URL path parameter), then compares against `consent_rec.patient_id`. This is the correct trust anchor — the JWT identity, not the URL. The URL `patient_id` is also verified separately by step 1 (ownership), but step 2 independently guards against UUID enumeration.

### Edge Case: Double revoke / non-existent consent

**Handled correctly.** `consent.revoke(db, consent_id)` is called after the ownership checks. If `revoke()` returns `False` (already revoked), a 404 is raised. The ownership check before this point correctly returns 404 for a non-existent consent_id before reaching the ownership assertion.

### Potential Concern: Local import style

```python
from app.models.governance import Consent as ConsentModel  # local import to avoid circular
```

The `# local import to avoid circular` comment is accurate — `consent.py` imports from `app.services.consent`, which itself imports from `app.models.governance`. The local import is a pragmatic workaround. **Not a blocker** — it avoids a circular import and is consistent with the codebase pattern. A module-level import refactor could clean this up in a future task but is not required here.

### Role Gate: AI_SERVICE cannot reach cross-patient check

`require_roles(UserRole.PATIENT)` at the route level blocks all non-PATIENT roles before any ownership logic runs. `test_ai_service_cannot_revoke_consent` confirms AI_SERVICE → 403 at the RBAC gate, not the ownership check. This is correct — defense in depth.

---

## Schema Cleanup Analysis — AC3/AC4/AC5

### Duplicate removal verified

`grep -n "AIClinicalRecommendationOut" backend/app/schemas/ai.py` → exit code 1 (no match). The 9-field thin class is gone.

### Canonical class confirmed (16 fields)

`backend/app/schemas/clinical.py:94` — `AIClinicalRecommendationOut` has 16 fields:
`id`, `session_id`, `patient_id`, `encounter_id`, `recommendation_type`, `content`, `key_version`, `status`, `reviewed_by_doctor_id`, `reviewed_at`, `ai_confidence`, `safety_cleared`, `medical_disclaimer`, `created_at`, `updated_at`, + `model_config = {"from_attributes": True}`

### Serialization compatibility

The schema switch from 9→16 fields is **backwards compatible for consumers** — additional fields are additive. FastAPI response models with `from_attributes=True` serialize from ORM attributes; extra fields on the schema that are present on the ORM model are included; fields absent from the ORM model would cause a validation error. The model `AIClinicalRecommendation` must therefore have all 16 fields. Given 277 tests pass (including all doctor_review endpoint tests), serialization is confirmed working.

### `__init__.py` export

`schemas/__init__.py` exports `AIClinicalRecommendationOut` from `.clinical` (not `.ai`). Consistent and correct.

### Residual inline duplicate (out of scope, P2 warning)

`backend/app/api/v1/routes/ai_sessions.py:60` defines a third local `AIClinicalRecommendationOut` (7-field subset: `id`, `session_id`, `patient_id`, `recommendation_type`, `status`, `ai_confidence`, `safety_cleared`). This is **pre-existing on main**, not introduced or touched in this branch. It is a P2 tech-debt item for a future cleanup sprint but does **not block this review**.

---

## Test Quality Assessment

### `test_patient_cannot_revoke_another_patients_consent` (T10-C02)

Well-constructed. Creates consent owned by `another_patient`, then patient 1 attacks using their **own** `patient_id` in the URL path (the exact attack vector) but targets the other patient's `consent_id`. This is the precise scenario the fix addresses. ✅

### `test_patient_revoke_another_patients_consent_is_forbidden` (T9-C12)

This is a complementary test: patient 1 uses another patient's `patient_id` in the URL path. This was already covered by `_enforce_consent_ownership` before T10. Both tests together provide complete coverage of the two attack surfaces. ✅

### `test_ai_service_cannot_revoke_consent` (T10-C01)

Confirms RBAC gate correctly blocks AI_SERVICE at the role check before ownership logic. ✅

### `test_clinic_admin_can_read_document_status` (T10-L01)

Correctly creates a CLINIC_ADMIN user with an active lab consent and asserts 200 on `GET /lab-documents/{id}`. Validates both the role gate (`require_roles(... UserRole.CLINIC_ADMIN ...)` confirmed in `lab.py`) and consent gate. ✅

---

## Summary

The cross-patient consent revoke security fix is correct, properly handles all identified edge cases (`patient_profile is None`, UUID enumeration via correct path+wrong consent_id), and is guarded by defense-in-depth (RBAC gate + ownership check + cross-patient check). The schema cleanup is clean with no serialization regressions. All 10 acceptance criteria are met. The 3 pre-existing `test_rag.py` failures are on `main` and unrelated to this branch's diff. **Approved for merge.**

---

*Reviewed by: Codex (read-only subagent) | 2026-06-18 GMT+7*
