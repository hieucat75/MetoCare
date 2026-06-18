# Codex Review — T15 Symptom Log + Medication API

**Branch:** `feature/t15-symptom-medication-api`
**Reviewed:** 2026-06-18 GMT+7
**Reviewer:** Codex (read-only, no modifications)

---

**Result:** ✅ APPROVE

**P1 Blockers:** None

**P2 Warnings:**
1. Split-transaction pattern: service commits clinical record, then route commits audit record in a second transaction — audit loss possible under partial failure (see details below)
2. No test coverage for AI_SERVICE blocked on GET (read) endpoints — the block is implemented but untested
3. `list_medications` orders oldest-first (`created_at ASC`); spec doesn't mandate order but is inconsistent with `list_symptoms` (newest-first); document or align

**Security:** PASS

**Test Results:** 16/16 PASS (full suite 331 passed, 1 skipped, 0 failures)

**Acceptance Criteria:** 13/13 met

---

## Detailed Findings

### AC1 — POST /patients/{id}/symptoms → 201, PATIENT own + DOCTOR consent-gated ✅

`_check_write_access` is called at the top of `create_symptom_log`. It blocks `AI_SERVICE` and `CLINIC_ADMIN` via `_BLOCKED_WRITE_ROLES`, enforces ownership for `PATIENT` (fetches `PatientProfile` and compares `user_id`), and calls `require_access(...)` for `DOCTOR`. Route returns 201 with `response_model=SymptomLogOut`. **Met.**

### AC2 — GET /patients/{id}/symptoms → 200 paginated, newest first ✅

`list_symptoms` orders by `SymptomLog.reported_at.desc()`. Pagination via `limit`/`offset` query params (clamped to 100). Response is a dict `{patient_id, total, items}`. Test #5 confirms structure and ordering. **Met.**

### AC3 — POST /patients/{id}/medications → 201, PATIENT own + DOCTOR consent-gated ✅

Identical RBAC path via `_check_write_access`. Route returns 201 with `response_model=MedicationOut`. **Met.**

### AC4 — GET /patients/{id}/medications → 200 paginated, active only ✅

`list_medications` filters with `Medication.deleted_at.is_(None)` — only records with `deleted_at IS NULL` are returned. Pagination present. **Met.**

### AC5 — DELETE /patients/{id}/medications/{med_id} → 204 soft-delete ✅

Route returns `status.HTTP_204_NO_CONTENT`. `delete_medication` service sets `record.deleted_at = utcnow()` and calls `db.commit()`. Idempotent (repeated calls are no-ops, not errors). **Met.**

### AC6 — AI_SERVICE blocked from ALL write endpoints (CRITICAL) ✅

`AI_SERVICE` is in `_BLOCKED_WRITE_ROLES = frozenset({UserRole.AI_SERVICE, UserRole.CLINIC_ADMIN})`. This frozenset is checked at the **route level** (inside `_check_write_access`, before any service call) for all three write endpoints. Block is applied in the route layer — **not** merely a service-layer comment. This is the correct enforcement layer. Tests #4 and #9 explicitly verify 403 for `ai_service` role on POST symptom and POST medication respectively. **Met. Critical safety requirement correctly implemented.**

### AC7 — DOCTOR cannot DELETE medications ✅

In `delete_medication` route, the very first check (before `_check_write_access`) is:
```python
if user.role == UserRole.DOCTOR:
    raise HTTPException(status_code=403, detail="Doctors are not permitted to delete...")
```
This is an **explicit positive check** — DOCTOR is not merely absent from an allowed-list but actively rejected with a clear clinical-safety error message. The check fires before the general write-access check, so a DOCTOR can't reach the ownership logic. Test #12 confirms 403. **Met.**

### AC8 — PATIENT cannot access another patient's records → 403 ✅

`_check_write_access` for `PATIENT` role fetches `PatientProfile` by `patient_id` and compares `profile.user_id != requester.id`, raising 403 if they don't match. Tests #2 and #8 verify this for symptom and medication create respectively. **Met.**

### AC9 — Soft-delete: deleted_at set, excluded from list ✅

`delete_medication` service: `record.deleted_at = utcnow()` — `SoftDeleteMixin` confirmed in `_mixins.py` (`DateTime(timezone=True), nullable=True`). `list_medications` query uses `.where(*base_filter)` where `base_filter` includes `Medication.deleted_at.is_(None)`. Test #11 verifies 204 + absence from list; test #14 verifies exclusion with two records (one kept, one deleted). **Met.**

### AC10 — Audit records on create + delete ✅

All three write routes call `audit.record(...)` with appropriate `action` strings:
- `create_symptom_log` → `action="log_symptom"`, `resource_type="symptom_log"`
- `add_medication` → `action="add_medication"`, `resource_type="medication"`
- `delete_medication` → `action="delete_medication"`, `resource_type="medication"`

`audit.record()` flushes (assigns ID) and the route calls `db.commit()` after. **Met.**

### AC11 — 404 on delete nonexistent medication ✅

`delete_medication` service:
```python
if record is None or record.patient_id != patient_id:
    raise HTTPException(status_code=404, detail="Medication not found.")
```
Also handles cross-patient requests (different patient_id) as 404 rather than 403, which is an intentional information-hiding choice. Test #13 confirms 404. **Met.**

### AC12 — Severity validation: 0-10 only (422 if > 10) ✅

`SymptomLogCreate` schema uses:
```python
severity: int | None = Field(None, ge=0, le=10)
```
Pydantic `Field(ge=0, le=10)` enforces the range at the schema layer. Payload with `severity=11` returns 422 (Pydantic validation error, not 400). Test #6 confirms 422. **Met.**

### AC13 — 16 tests all pass, 0 regressions ✅

Test results: **331 passed, 1 skipped**, baseline 315 → +16. Zero failures. **Met.**

---

## P2 Warnings (Non-Blocking)

### W1 — Split-transaction pattern (audit consistency gap)

The service functions (`add_medication`, `create_symptom`) call `db.commit()` internally before returning. The route then calls `audit.record()` (which flushes) and `db.commit()` again. This creates two sequential transactions:

1. **Transaction 1:** Clinical record committed in service
2. **Transaction 2:** Audit record committed in route

If the process crashes between T1 and T2, the clinical record exists without a corresponding audit entry. The existing `update_profile` service combines the clinical update and audit into one transaction (audit is done inside the service). The T15 pattern is functional and passes all tests, but introduces a minor audit-consistency gap under adversarial failure conditions.

**Recommendation:** In a future cleanup, consider moving `audit.record()` calls inside the service functions (before their `db.commit()`) to keep clinical record + audit in a single transaction — matching the pattern already established by `patient_profile.py`.

### W2 — AI_SERVICE read block not tested

The implementation correctly blocks `AI_SERVICE` on GET endpoints (via `_check_read_access` → `_check_write_access`). However, none of the 16 tests verify this. Tests #4 and #9 cover write endpoints only. A future test `test_ai_service_cannot_read_symptoms` and `test_ai_service_cannot_read_medications` would complete the coverage matrix.

### W3 — Medication list ordering undocumented

`list_medications` uses `created_at ASC` (oldest-first); `list_symptoms` uses `reported_at DESC` (newest-first). Neither ordering is wrong, but the inconsistency is not documented in the docstring or API spec. If a UI expects newest-first for medications (consistent with symptoms), this should be caught early. A docstring note or a matching `DESC` ordering would eliminate ambiguity.

---

## Security Summary

| Check | Result |
|-------|--------|
| AI_SERVICE write block (route-level) | ✅ PASS |
| DOCTOR DELETE block (explicit positive check) | ✅ PASS |
| PATIENT cross-record isolation | ✅ PASS |
| Unauthenticated → 401 | ✅ PASS |
| Pydantic input validation (severity, name lengths) | ✅ PASS |
| Soft-delete info hiding (404 not 403 on wrong patient) | ✅ PASS |
| Audit trail on all writes | ✅ PASS |

---

## Summary

T15 is a clean, correct implementation of the Symptom Log + Medication CRUD API. All 13 acceptance criteria are met: the critical AI_SERVICE write block is enforced at the route layer (not just in documentation), the DOCTOR DELETE prohibition is an explicit positive check with a meaningful error message, soft-delete is correctly implemented with `deleted_at IS NULL` filtering, and severity is validated via Pydantic `Field(ge=0, le=10)`. The three P2 warnings (split-transaction audit pattern, two missing AI read-block tests, and undocumented medication list ordering) are minor quality issues that do not affect correctness or safety. **Approved for merge.**
