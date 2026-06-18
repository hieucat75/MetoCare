# Codex Review — T18A Backend Pilot API Completion

**Branch:** `feature/t18a-backend-pilot-api`
**Reviewer:** Codex (read-only)
**Date:** 2026-06-18
**Commit range:** `55b20d7..d4010df` (2 commits on branch)

---

## Result: ✅ APPROVE

**P1 Blockers:** None
**P2 Warnings:** 2 (see below)
**Security:** PASS
**Test Results:** 24/24 new tests pass (425 total, 1 skipped, 0 regressions)
**Acceptance Criteria:** 7/7 met

---

## Git Diff Scope Check

The `git diff main..feature/t18a-backend-pilot-api --name-only` shows 15 files across 6 dirs. Of the 8 extra files beyond the task scope (T18C safety tests, T18B/T18D docs, etc.):

- These are commits on `main` that landed **after** the T18A branch was cut (`main` fork point: `55b20d7`).
- In `main..branch` diff direction, they appear as **deletions on the branch** — they are NOT additions introduced by T18A.
- The branch itself adds exactly the 8 expected files: 3 route changes + 3 test files + 2 docs.

**✅ Branch is additive-only on the correct files.**

---

## AC-by-AC Findings

### AC1 — Consent List Endpoint: PASS

**`GET /patients/{patient_id}/consents`** in `consent.py`:

```python
allowed_roles = {UserRole.PATIENT, UserRole.INTERNAL_ADMIN, UserRole.SUPER_ADMIN}
if user.role not in allowed_roles:
    raise HTTPException(status_code=403, ...)
```

- PATIENT: ownership check via `profile.user_id != user.id` → 403 if cross-patient ✅
- ADMIN (INTERNAL_ADMIN / SUPER_ADMIN): unrestricted ✅
- DOCTOR / CLINIC_ADMIN / AI_SERVICE: explicit 403 (blocked by allowed_roles check) ✅
- `active_only=True` default: filters by `revoked_at IS NULL OR revoked_at > now()` ✅
- Patient doesn't exist → 404 (checked before ownership) ✅
- Tests: CL01–CL08 cover all branches ✅

### AC2 — AI Session Close Idempotency: PASS

**`POST /ai_sessions/{session_id}/close`** in `ai_sessions.py`:

The code order is:
1. `session = db.get(AISession, session_id)` → 404 if not found ✅
2. If `user.role == PATIENT`: ownership check (profile.user_id == user.id) ✅
3. `if session.deleted_at is not None: return` (idempotent early exit — **204 returned**) ✅
4. Set `session.deleted_at = utcnow()` + audit + commit ✅

Idempotency is correctly implemented: ownership check happens before the `deleted_at` guard, so a patient calling close a second time on their own already-closed session correctly passes ownership → early return → 204. No 409, no 500. ✅

Test SC06 explicitly covers this case. ✅

Note on AC2 task card discrepancy: The task card specified "DOCTOR with consent" but the implementation allows DOCTOR (any session, no consent check). This is consistent with the T18A_TASK_CARD.md RBAC table which says DOCTOR → "Any". Session close is a lifecycle action, not data access — no consent required for DOCTOR is a reasonable and consistent design decision.

### AC3 — Lab List vs Lab Upload Conflict: PASS (no conflict)

- `lab.router` has **no prefix** (`router = APIRouter(tags=["lab"])`)
- New route: `GET /patients/{patient_id}/lab-documents`
- Existing route: `POST /patients/{patient_id}/lab-documents`
- Same URL path, **different HTTP methods** — FastAPI handles this correctly via method dispatch ✅

No routing conflict. ✅

### AC4 — No Existing Routes Modified: PASS

Diff confirms:
- `consent.py`: only added the new `@router.get("")` endpoint and a section comment. The local import `from app.models.governance import Consent as ConsentModel` was correctly promoted to a module-level import (minor cleanup, not a behavior change). ✅
- `ai_sessions.py`: only added `close_ai_session` function and a minor `\n` spacing between existing functions. ✅
- `lab.py`: only added `list_patient_lab_documents` function; pre-existing routes untouched. ✅

### AC5 — RBAC Consistency / ConsentGuard Pattern: PASS

Lab list uses `consent.require_access()` (the lower-level consent service), not the `ConsentGuard` class from `consent_guard.py`. This is **consistent** with existing endpoints in `lab.py` — `POST /patients/{id}/lab-documents`, `/lab-documents/{id}/process`, and `GET /lab-documents/{id}` all use `consent.require_access()` in the same pattern.

The `ConsentError` raised by `require_access()` is caught by the global exception handler in `main.py` (line 101-105) and converted to HTTP 403. This is verified correct. ✅

One design note: `consent.require_access()` has **no admin bypass** in the consent service layer — admins must have a consent record. This is intentional and consistent with all existing lab endpoints (verified in `test_lab_api.py`: `test_admin_uploads_lab_document` and `test_admin_reads_any_document` both provision a consent for the admin). The new test `test_admin_with_consent_can_list_lab_documents` correctly mirrors this pattern. ✅

### AC6 — Cross-Patient Isolation: PASS

- Consent list: `profile.user_id != user.id` check before query ✅
- AI session close: `profile.user_id != user.id` check for PATIENT role ✅
- Lab list: `_require_patient_ownership()` checks `profile.user_id != user.id` for PATIENT ✅

### AC7 — 24 Tests Pass, 0 Regressions: PASS

Reported test results: 425 passed, 1 skipped (baseline 401 → +24). Ruff PASS.
All 8 tests per endpoint cover: own access, cross-patient 403, role blocks, admin access, edge cases (empty, nonexistent, idempotent), unauthenticated 401. ✅

---

## P2 Warnings

### P2-W1: `active_only` filter incomplete — does not check `valid_until`

In `list_consents()` (`consent.py` line ~95):

```python
stmt = stmt.where(
    (ConsentModel.revoked_at.is_(None)) | (ConsentModel.revoked_at > now),
)
```

The filter only checks `revoked_at`. A consent with `valid_until < now` (expired but not revoked) would still be returned by `active_only=True`. The `is_active()` method on the model also checks `valid_until`, but the SQL filter does not.

**Impact:** Patient sees expired consents in their "active" list. Not a security issue (it's over-informing, not under-restricting), but misleading UX. The consent-gate itself still correctly rejects expired consents via `is_active()`.

**Recommendation:** Add `valid_until` check to the SQL filter:
```python
stmt = stmt.where(
    (ConsentModel.revoked_at.is_(None)) | (ConsentModel.revoked_at > now),
    (ConsentModel.valid_until.is_(None)) | (ConsentModel.valid_until > now),
)
```

### P2-W2: AI session close allows AI_SERVICE to close any patient's session

The `close_ai_session` doc string says: `DOCTOR / CLINIC_ADMIN / INTERNAL_ADMIN / SUPER_ADMIN / AI_SERVICE — any session`. An AI_SERVICE principal can close any patient's AI session without a patient-ownership check. This is a broad privilege.

**Impact:** If an AI_SERVICE credential is compromised, an attacker could terminate any patient session. For the pilot scope this is acceptable, but worth documenting for post-pilot tightening (e.g., requiring AI_SERVICE to only close sessions it created).

---

## Security Assessment

| Check | Result |
|-------|--------|
| Cross-patient data isolation | ✅ PASS — ownership enforced on all 3 endpoints |
| Role-based access control | ✅ PASS — explicit allowlists, correct role comparisons |
| ConsentGuard on data access | ✅ PASS — lab list uses `consent.require_access()` consistently |
| Audit trail | ✅ PASS — AI session close audited; consent list/lab list are read-only |
| Input validation | ✅ PASS — limit/offset bounds enforced via `Query(ge=1, le=100)` |
| 401 for unauthenticated | ✅ PASS — all 3 endpoints tested |
| No secrets in diff | ✅ PASS |
| Soft delete not filterable bypass | ✅ PASS — `get_ai_session` and `list_ai_sessions` filter `deleted_at IS NULL` |

---

## Summary

All 7 acceptance criteria are met. The three new endpoints are additive, RBAC-consistent with the existing codebase, and backed by comprehensive tests. The idempotent AI session close is correctly implemented (ownership check before closed-guard, returns 204 both times). No routing conflict exists between GET and POST on the same lab-documents path. The `consent.require_access()` pattern for doctors on lab list is consistent with all pre-existing lab endpoints. Two P2 warnings are noted: (1) `active_only` filter should also check `valid_until` for correctness and (2) AI_SERVICE having unconstrained session-close privileges warrants future tightening — neither blocks merge.

**APPROVED for merge.** P2 warnings should be tracked as follow-up tasks.
