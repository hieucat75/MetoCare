# T18A — Backend Pilot API Completion

**Branch:** `feature/t18a-backend-pilot-api`
**Owner:** Claude Code
**Created:** 2026-06-18
**Status:** COMPLETE

---

## Context

MetoCare backend has T6–T19 merged. Main is at 401 tests passed. This sprint found and filled real gaps in the pilot API surface — small, targeted PRs only.

---

## Audit Findings — Real Gaps Identified

### GAP-1: `GET /patients/{patient_id}/consents` (CRITICAL)
**Why:** Patient can grant and revoke consents but has NO way to list their active consents. This is a fundamental UX requirement — patients need to see who has access to their data (P0: data transparency per Luật BVDLCN Vietnam 2026).

### GAP-2: `POST /ai_sessions/{session_id}/close` (IMPORTANT)
**Why:** AI sessions can be created but never explicitly closed. No lifecycle endpoint to terminate a session. Without this, sessions persist indefinitely — patients can't end a session.

### GAP-3: `GET /patients/{patient_id}/lab-documents` (IMPORTANT)
**Why:** Lab documents can be uploaded and fetched individually, but there's NO endpoint to list all lab documents for a patient. Patient can't see their document history.

---

## Non-Gaps (Evaluated and Dismissed)

- `GET /patients/{id}` — already covered by `GET /patients/{id}/profile`
- Doctor review list per-patient — existing queue (`GET /doctor/review/queue`) is sufficient
- Cross-patient isolation — RBAC checks already present in all routes (verified)

---

## Implementation

### Files Changed
- `backend/app/api/v1/routes/consent.py` — added `GET` endpoint for listing patient consents
- `backend/app/api/v1/routes/ai_sessions.py` — added `POST /{session_id}/close` endpoint
- `backend/app/api/v1/routes/lab.py` — added `GET /patients/{patient_id}/lab-documents` endpoint

### Tests Added
- `backend/tests/api/test_consent_list_api.py` — 8 tests for consent list endpoint
- `backend/tests/api/test_ai_session_close_api.py` — 8 tests for AI session close endpoint
- `backend/tests/api/test_lab_list_api.py` — 8 tests for lab document list endpoint

---

## RBAC Summary

| Endpoint | PATIENT | DOCTOR | ADMIN | AI_SERVICE |
|----------|---------|--------|-------|------------|
| GET /patients/{id}/consents | Own only | 403 | Any | 403 |
| POST /ai_sessions/{id}/close | Own only | Any | Any | Any |
| GET /patients/{id}/lab-documents | Own (consent-gated) | Consent-gated | Consent-gated | 403 (blocked by require_roles) |

---

## Final Test Count

- Baseline: 401 passed, 1 skipped
- After T18A: 425 passed, 1 skipped (+24 tests)
- Ruff: PASS
