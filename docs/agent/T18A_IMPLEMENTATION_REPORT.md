# T18A Implementation Report

**Branch:** `feature/t18a-backend-pilot-api`
**Date:** 2026-06-18
**Status:** READY FOR CODEX REVIEW

---

## Summary

T18A audited all 51 existing routes against the P0 MVP scope, identified 3 real pilot API gaps, and filled them with minimal, additive changes.

---

## Audit Process

1. Listed all routes via FastAPI OpenAPI introspection
2. Cross-referenced against MVP_Scope_and_Roadmap.md §3.4 (P0 features)
3. Reviewed RBAC patterns in each route file
4. Identified gaps by category: patient journey, doctor review, consent, AI session lifecycle, cross-patient isolation

---

## Gaps Found and Fixed

### GAP-1: GET /patients/{patient_id}/consents
**File:** `backend/app/api/v1/routes/consent.py`
- Added `list_consents()` endpoint before POST
- PATIENT: own consents only (ownership check via user_id)
- DOCTOR/AI_SERVICE/CLINIC_ADMIN: always 403 (legal requirement — third parties must not enumerate consent access)
- INTERNAL_ADMIN/SUPER_ADMIN: unrestricted
- `active_only=True` by default (revoked consents excluded)
- Returns 404 for non-existent patient

### GAP-2: POST /ai_sessions/{session_id}/close
**File:** `backend/app/api/v1/routes/ai_sessions.py`
- Added `close_ai_session()` endpoint after `create_ai_session`
- Uses existing SoftDeleteMixin (`deleted_at`) field
- Idempotent: closing already-closed session returns 204
- PATIENT: own sessions only (profile.user_id check)
- DOCTOR/ADMIN/AI_SERVICE: any session
- Audited with `ai_session.close` action
- After close: GET returns 404 (consistent with existing soft-delete behavior)

### GAP-3: GET /patients/{patient_id}/lab-documents
**File:** `backend/app/api/v1/routes/lab.py`
- Added `list_patient_lab_documents()` endpoint before POST
- Consent-gated for all roles (consistent with existing lab endpoints)
- PATIENT: own docs + consent check (self-consent via user_id)
- DOCTOR: active lab consent required
- ADMIN: explicit consent required (matches existing GET /lab-documents/{id} behavior)
- Paginated: limit/offset, newest-first ordering

---

## Non-Gaps Evaluated

| Route | Evaluation |
|-------|------------|
| GET /patients/{id} | Covered by GET /patients/{id}/profile |
| Doctor per-patient review list | Queue + RBAC sufficient for pilot |
| Cross-patient isolation | Already enforced in all routes |
| Triage close endpoint | Not needed — triage is stateless (POST, no session) |
| AI session status field | deleted_at (SoftDelete) sufficient for close semantics |

---

## Files Changed

| File | Type | Description |
|------|------|-------------|
| `backend/app/api/v1/routes/consent.py` | Modified | +GET list endpoint |
| `backend/app/api/v1/routes/ai_sessions.py` | Modified | +POST close endpoint |
| `backend/app/api/v1/routes/lab.py` | Modified | +GET list endpoint |
| `backend/tests/api/test_consent_list_api.py` | New | 8 tests |
| `backend/tests/api/test_ai_session_close_api.py` | New | 8 tests |
| `backend/tests/api/test_lab_list_api.py` | New | 8 tests |
| `docs/agent/T18A_TASK_CARD.md` | New | Task card |

---

## Validation Results

```
Ruff: PASS (all checks passed)
Tests: 425 passed (baseline 401 → +24 new tests)
  - test_consent_list_api.py: 8 passed
  - test_ai_session_close_api.py: 8 passed
  - test_lab_list_api.py: 8 passed
Pre-existing failures: 3 (test_rag.py — environment/seed data issue, pre-dates T18A)
```

---

## READY FOR CODEX REVIEW

```
T18A — READY FOR CODEX REVIEW
Branch: feature/t18a-backend-pilot-api
Tests: 425 passed (baseline 401 → +24)
Ruff: PASS
Files changed:
  backend/app/api/v1/routes/consent.py (additive)
  backend/app/api/v1/routes/ai_sessions.py (additive)
  backend/app/api/v1/routes/lab.py (additive)
  backend/tests/api/test_consent_list_api.py (new)
  backend/tests/api/test_ai_session_close_api.py (new)
  backend/tests/api/test_lab_list_api.py (new)
  docs/agent/T18A_TASK_CARD.md (new)
```
