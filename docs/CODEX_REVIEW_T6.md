# Codex Review — T6 Doctor Review Workflow

**Reviewer:** Codex (read-only)
**Branch:** `feature/t6-doctor-review`
**Commit:** `9bf2a7f`
**Date:** 2026-06-18
**Repo:** `/Users/pth/Developer/Metocare`

---

**Result:** ⚠️ REQUEST_CHANGES

**P1 Blockers:** 1 (see §P1-01 — `request_info` verdict silently discarded)
**P2 Warnings:** 3 (see §P2 section)
**Security:** PASS
**Test Results:** 215/215 PASS (1 skipped)
**Acceptance Criteria:** 9/10 met (AC#3 partially blocked by P1-01)

---

## P1 Blockers

### P1-01 — `request_info` verdict silently collapses to `reject`

**File:** `backend/app/api/v1/routes/doctor_review.py` lines 148–153  
**Severity:** P1 blocker

The `DoctorReviewDecision` schema accepts three valid verdicts: `"accepted"`, `"rejected"`, `"request_info"`. However the route handler maps them with a binary ternary:

```python
action_val: Literal["accept", "reject"] = (
    "accept" if payload.verdict == "accepted" else "reject"
)
```

When a doctor submits `verdict="request_info"`, this silently maps to `"reject"`, causing:
- Status transitions to `REJECTED` instead of a neutral/pending state
- `safety_cleared` is set to `False`
- Audit log records `ai.recommendation_rejected` instead of `ai.recommendation_request_info`
- The AI recommendation is permanently rejected when the doctor only wanted more info

This breaks **Acceptance Criteria #3** ("Review endpoint transitions status correctly"). There is no `REQUEST_INFO` status in `RecommendationStatus` enum, but the schema promises the verdict is valid — the correct fix is either:
1. Add `REQUEST_INFO = "request_info"` to `RecommendationStatus` and handle it in `DoctorReviewService.review()`, or
2. Remove `"request_info"` from `DoctorReviewDecision.verdict` until the status enum and service support it

**Impact:** A doctor clicking "Request More Information" will silently reject a recommendation — a clinically dangerous data corruption.

---

## P2 Warnings

### P2-01 — Duplicate `AIClinicalRecommendationOut` schema

**Files:** `backend/app/schemas/ai.py:80` and `backend/app/schemas/clinical.py:94`

Two definitions of `AIClinicalRecommendationOut` coexist. The one in `schemas/ai.py` (used by `doctor_review.py`) is **missing fields** present in the canonical `schemas/clinical.py` version:
- Missing: `encounter_id`, `content`, `key_version`, `medical_disclaimer`, `created_at`, `updated_at`

The `schemas/__init__.py` exports `AIClinicalRecommendationOut` from `schemas.clinical` (line 65), while `doctor_review.py` explicitly imports from `schemas.ai`. This creates two divergent response shapes for the same model.

**Recommendation:** Remove the definition from `schemas/ai.py` and import from `schemas/clinical.py` instead. The clinical schema is richer and consistent with existing usage in `ai_sessions` routes. This is a deferred cleanup, not a runtime crash, but it means the doctor review endpoints return fewer fields than callers may expect.

### P2-02 — `DoctorCarePlanService.approve()` stale ORM object returned

**File:** `backend/app/services/care_plan.py` lines 37–57

The `approve()` method uses `db.execute(update(...))` (bulk SQL UPDATE) to bypass ORM validators, then returns `plan` — the Python object loaded before the UPDATE. The caller in `care_plans.py` does `db.refresh(updated_plan)` which refreshes correctly. However, the service returns a potentially stale object reference. This works today because the caller always refreshes, but it's fragile — any future caller that forgets `refresh()` will receive wrong data silently.

**Recommendation:** Add a comment to the service method signature or return type indicating the caller must call `db.refresh()` on the result. Consider returning `db.get(CarePlan, care_plan_id)` after flush instead.

### P2-03 — CI workflow missing `--junit-xml` output path alignment

**File:** `.github/workflows/ci.yml` lines 26–30

The pytest command generates `test-results.xml` (relative to `backend/` working-directory), but the artifact upload path is `backend/test-results.xml` (from repo root). Since the job `defaults.run.working-directory` is `backend`, the file will be at `backend/test-results.xml` relative to the repo root only if pytest is run from repo root. Given the working directory is `backend/`, the file lands at `backend/test-results.xml` from the runner's perspective.

This is actually **correct** as written (Actions `path:` in `upload-artifact` is relative to GITHUB_WORKSPACE, not working-directory), but the intent may be ambiguous. With `continue-on-error: true`, a mis-path silently uploads nothing. Low severity but worth a comment in the YAML for clarity.

---

## Acceptance Criteria Verification

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Queue returns only PENDING_REVIEW recs accessible to requesting doctor | ✅ PASS — `get_pending_queue()` filters by status + consent/encounter scope |
| 2 | Submit endpoint creates recommendation + sets PENDING_REVIEW status | ✅ PASS — `submit_for_review()` sets status, AI_SERVICE/SUPER_ADMIN gate enforced |
| 3 | Review endpoint transitions status correctly (accepted/rejected/request_info) | ⚠️ PARTIAL — `accepted`/`rejected` work; `request_info` silently collapses to `rejected` (P1-01) |
| 4 | Approve care plan: DOCTOR only, 409 on already APPROVED/ARCHIVED, RBAC enforced | ✅ PASS — `require_roles(UserRole.DOCTOR)` at endpoint level; 409 check in route + service |
| 5 | No ADMIN or AI_SERVICE can call approve endpoint | ✅ PASS — `require_roles(UserRole.DOCTOR)` strictly denies all other roles |
| 6 | Consent check gates doctor read access to recommendations | ✅ PASS — `_check_recommendation_read_access()` checks direct assignment, encounter, and consent chain |
| 7 | Audit trail recorded for approve action | ✅ PASS — `audit.record(..., action="care_plan.approve")` in `DoctorCarePlanService.approve()` |
| 8 | Security: no JWT leak in logs, no injection, parameterized queries only | ✅ PASS — see Security section |
| 9 | CI workflow: runs pytest + ruff on push/PR to main and feature branches | ✅ PASS — triggers on `push: [main, feature/**, feature/**/**]` and `pull_request: [main]` |
| 10 | No regression vs T5 baseline (202 → 215 passed) | ✅ PASS — 215 passed, 13 net new tests, 0 failures |

---

## Security Assessment

**Overall: PASS**

- **JWT handling:** Token decoded in `deps.py:current_user()`, claims validated (type=access, sub present). No JWT material logged or exposed in responses. ✅
- **SQL injection:** All queries use SQLAlchemy ORM or parameterized `update(...).values(...)`. No string interpolation in SQL. ✅
- **RBAC enforcement:**
  - `/queue` and `/review` endpoints use `require_roles(UserRole.DOCTOR)` — hard deny at dependency level. ✅
  - `/submit` uses `require_roles(UserRole.AI_SERVICE, UserRole.SUPER_ADMIN)` — blocks doctors and patients. ✅
  - `/approve` uses `require_roles(UserRole.DOCTOR)` — blocks ADMIN, AI_SERVICE, PATIENT. ✅
  - Doctor-self check on approve: `doctor_rec.user_id != user.id` prevents approving on behalf of another doctor. ✅
- **Consent gate:** `_check_recommendation_read_access()` enforces consent for DOCTOR role before returning recommendation data. ✅
- **PHI handling:** `notes` and `content` fields are not logged. `AIClinicalRecommendationOut` in `schemas/ai.py` intentionally omits `content` (see P2-01 for schema split concern). ✅
- **Soft-delete:** Both recommendation and care plan endpoints check `deleted_at is not None`. ✅
- **Feature flag fail-closed:** Both `submit_for_review()` and `review()` raise `PermissionDenied` (503/403) when `DOCTOR_REVIEW_GATE` is disabled. ✅

---

## Code Quality

### Strengths
- Clean separation: route layer handles HTTP concerns, service layer handles business logic and SQL updates
- Bypass of ORM validators via SQL UPDATE is well-commented and intentional (C1 guard compliance)
- `assert_doctor_assigned()` reused consistently across approve and existing update endpoints
- Error propagation from service exceptions (`PermissionDenied`, `ValueError`) maps clearly to HTTP status codes
- Test coverage: 13 new tests covering happy paths and all forbidden-role paths

### Notable Design Choices
- The `review_recommendation` route maps `DoctorReviewService.review()` with `action: Literal["accept", "reject"]` — this is the source of the P1-01 bug. The service layer intentionally only supports accept/reject; the schema layer promises more. These must be reconciled.
- `DoctorCarePlanService` is imported lazily inside the route handler (`from app.services.care_plan import ...`). This works but is inconsistent with all other service imports at module level. Low impact.

---

## Summary

T6 is well-structured with solid RBAC, audit trail, consent gating, and security posture. The single P1 blocker is a schema/service contract mismatch: `DoctorReviewDecision` accepts `"request_info"` as a valid verdict, but the service has no handler for it — causing silent misclassification to `rejected`. This is clinically risky and must be resolved before merge. Once P1-01 is addressed and the `AIClinicalRecommendationOut` schema duplication is cleaned up (P2-01), this PR is ready for PTH approval.

**Recommended action:** Fix P1-01, then re-submit for Codex re-review.

---

*Reviewed by: Codex (read-only) | Mode: REVIEW, no modifications made*
