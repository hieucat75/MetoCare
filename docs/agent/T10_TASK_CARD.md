# T10 Task Card — Security Hardening: P2 Cleanup Sprint

**TASK_ID:** T10  
**LABEL:** Security Hardening — Consent Cross-Patient Fix + P2 Deferred Cleanup  
**Branch:** `feature/t10-security-hardening`  
**Base branch:** `main`  
**Repo:** `/Users/pth/Developer/Metocare`  
**Implementer:** Antigravity  
**Coordinator:** OpenClaw  
**Status:** IN PROGRESS  
**Issued:** 2026-06-18 GMT+7

---

## Objective

Fix deferred P2 security items accumulated from T6–T9 reviews. Primary target is the consent cross-patient revoke vulnerability (Codex T9 P2-2). Secondary items are code quality cleanup.

---

## Items to Fix

### Item 1 — Consent Cross-Patient Revoke [SECURITY — P2→fix now]

**Source:** Codex T9 P2-2

**Problem:**
`consent.revoke(db, consent_id)` in `app/services/consent.py` revokes by UUID alone without verifying `consent.patient_id == patient_id`. A patient who knows another patient's consent UUID (via UUID guessing or data leak) could revoke it via their own profile path.

**Fix:**
In `backend/app/api/v1/routes/consent.py` route `DELETE /consents/{consent_id}`, add a cross-patient check after loading the consent record:

```python
consent_rec = db.get(Consent, consent_id)
if consent_rec is None:
    raise HTTPException(status_code=404, detail="Consent not found.")
# Cross-patient ownership check
patient_profile = db.execute(
    select(PatientProfile).where(PatientProfile.user_id == user.id)
).scalar_one_or_none()
if patient_profile is None or consent_rec.patient_id != patient_profile.id:
    raise HTTPException(status_code=403, detail="You may only revoke your own consents.")
```

Then call `consent.revoke(db, consent_id)` as before.

**Alternatively:** add the check directly in `consent.revoke()` by accepting `patient_id` param and verifying ownership there.

Use the safer route-level approach to avoid changing service signature.

### Item 2 — Duplicate `AIClinicalRecommendationOut` schema [P2 cleanup]

**Source:** Codex T6 P2-01

**Problem:**
`backend/app/schemas/ai.py` has a local `AIClinicalRecommendationOut` class. The canonical one is in `backend/app/schemas/clinical.py` (exported via `schemas/__init__.py`). The local version has fewer fields.

**Fix:**
- Remove `AIClinicalRecommendationOut` from `backend/app/schemas/ai.py`
- Import it from `app.schemas.clinical` in `backend/app/api/v1/routes/doctor_review.py`
- Verify no tests break

### Item 3 — Missing AI_SERVICE revoke consent test [P2 test gap]

**Source:** Codex T9 P2-1

**Fix:**
Add 1 test to `backend/tests/api/test_consent_api.py`:
- `test_ai_service_cannot_revoke_consent` → 403

### Item 4 — Missing CLINIC_ADMIN lab document test [P2 test gap]

**Source:** Codex T7 P2-1

**Fix:**
Add 1–2 tests to `backend/tests/api/test_lab_api.py`:
- `test_clinic_admin_can_read_document_status` → 200 (with consent fixture)

### Item 5 — `_require_patient_ownership` DOCTOR passthrough comment [P2 clarity]

**Source:** Codex T7 P2-2

**Fix:**
Add comment in `backend/app/api/v1/routes/lab.py` helper function:
```python
# DOCTOR and CLINIC_ADMIN: consent gate in service layer handles access — no ownership check here
```

---

## Scope

### ALLOWED_FILES

- `backend/app/api/v1/routes/consent.py` — Item 1 cross-patient check
- `backend/app/schemas/ai.py` — Item 2 schema cleanup
- `backend/app/api/v1/routes/doctor_review.py` — Item 2 import fix
- `backend/tests/api/test_consent_api.py` — Item 3 new test
- `backend/tests/api/test_lab_api.py` — Item 4 new test
- `backend/app/api/v1/routes/lab.py` — Item 5 comment only
- `docs/agent/T10_IMPLEMENTATION_REPORT.md` — NEW

### DO NOT TOUCH

- Any model files
- Any migration files
- `app/services/consent.py` internal logic (only route-level check needed)
- Domain files

---

## Acceptance Criteria

- [ ] Item 1: Cross-patient consent revoke blocked (patient A cannot revoke patient B's consent)
- [ ] Item 1: Test added: `test_patient_cannot_revoke_another_patients_consent` → 403
- [ ] Item 2: No duplicate `AIClinicalRecommendationOut` in `schemas/ai.py`
- [ ] Item 2: `doctor_review.py` imports from `schemas.clinical` (richer schema)
- [ ] Item 2: All existing doctor review tests pass unchanged
- [ ] Item 3: `test_ai_service_cannot_revoke_consent` → 403 passes
- [ ] Item 4: `test_clinic_admin_can_read_document_status` → 200 passes
- [ ] Item 5: Comment added to `_require_patient_ownership` in `lab.py`
- [ ] Zero existing tests broken (274 baseline → 277+ total)
- [ ] Ruff clean

---

## Validation Commands

```bash
cd /Users/pth/Developer/Metocare/backend
source ../.venv/bin/activate
ruff check .
pytest tests/ --tb=short
```

---

## Required Final Status

```
READY FOR CODEX REVIEW
```

---

*Task Card issued: 2026-06-18 05:31 GMT+7 | Coordinator: OpenClaw*
