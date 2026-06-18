# Codex Review — T19 Triage Log Persistence + History API

**Result:** ✅ APPROVE

**P1 Blockers:** None
**P2 Warnings:**
- `save_triage()` stores `red_flags=None` when `result.red_flags` is falsy (empty list `[]`); `TriageLogOut.parse_red_flags` normalises `None → []` so the API response is always a list, but the DB column can store `NULL` vs `'[]'` inconsistently for non-emergency cases. Functionally correct per AC8; cosmetically ambiguous in raw SQL queries.
- `test_triage_not_saved_for_non_patient` queries `TriageLog.patient_id == doctor["user_id"]` instead of the doctor's (non-existent) `PatientProfile.id`. The query will always return `None` regardless of any persistence bug, making the assertion vacuously true. The test title matches intent, but the assertion does not fail if a row _were_ accidentally created under a different patient_id. Low risk in practice (doctors have no PatientProfile), but a fragile assertion.

**Security:** PASS
**Test Results:** 10/10 PASS (401 total, 1 skipped, 0 failures)
**Acceptance Criteria:** 10/10 met

---

## Detailed AC Verification

### AC1 — `TriageLog` FK → `patient_profiles.id` ✅
- `triage_log.py` model: `ForeignKey("patient_profiles.id")` on `patient_id` column. Correct.
- Migration: `sa.ForeignKey("patient_profiles.id")` on `patient_id`. Matches.
- No FK to `users.id`. ✅

### AC2 — Migration `down_revision = "t18_add_ntrl"`, upgrade/downgrade correct ✅
- `down_revision: str | None = "t18_add_ntrl"` — matches requirement.
- `upgrade()`: `create_table("triage_logs", ...)` with all required columns + `create_index` on `patient_id`.
- `downgrade()`: `drop_index(...)` then `drop_table("triage_logs")` — correct reverse order.
- All ORM columns (`id`, `patient_id`, `symptom_text`, `risk_level`, `action`, `red_flags`, `message`, `created_at`, `updated_at`) are represented. ✅

### AC3 — `POST /ai/triage` persists for PATIENT only; fails silently ✅
- Route guard: `if user.role == UserRole.PATIENT.value:` — checks role enum `.value` string, matching how JWT stores roles. Correct.
- Profile lookup: `scalar_one_or_none()` — if no PatientProfile exists, `patient_profile is None` and `save_triage` is skipped silently with no exception raised.
- Non-PATIENT callers (DOCTOR, CLINIC_ADMIN, etc.) skip the entire `if` block silently. ✅
- Note: role comparison uses `UserRole.PATIENT.value` (string `"patient"`), consistent with how `user.role` is stored from JWT claims. Correct.

### AC4 — `GET /patients/{id}/triage-history` paginated, newest first ✅
- Route uses `limit` + `offset` Query params (ge=1, le=100 / ge=0).
- `get_history()` service: `order_by(TriageLog.created_at.desc())`, `limit(limit)`, `offset(offset)`.
- Returns `(total, rows)` tuple; total computed via `func.count()` on full unsliced set. ✅
- Response schema `TriageLogHistoryResponse` contains `patient_id`, `total`, `items`. ✅

### AC5 — AI_SERVICE → 403 on history endpoint ✅
- Endpoint calls `_check_read_access()` → `_check_write_access()`.
- `_BLOCKED_WRITE_ROLES` includes `UserRole.AI_SERVICE`.
- If `requester.role in _BLOCKED_WRITE_ROLES` → raises HTTP 403. ✅
- `test_ai_service_cannot_read_history` explicitly tests this. ✅

### AC6 — PATIENT cross-patient → 403 ✅
- In `_check_write_access`: for `UserRole.PATIENT`, resolves `PatientProfile` by `patient_id` and checks `profile.user_id != requester.id`. If mismatch → 403. ✅
- `test_patient_cannot_read_another_patients_history` tests patient_a → patient_b's history → 403. ✅

### AC7 — `red_flags` JSON round-trip ✅
- `save_triage()`: `json.dumps(result.red_flags, ensure_ascii=False) if result.red_flags else None` — uses `json.dumps()` with `ensure_ascii=False` (preserves Vietnamese characters). ✅
- `TriageLogOut.parse_red_flags` validator: `mode="before"`, handles `None → []`, `str → json.loads(v)`, existing `list` pass-through, and guards against `JSONDecodeError`. ✅
- Round-trip: `list[str]` → `json.dumps` → `Text` column → `json.loads` → `list[Any]`. Correct. ✅

### AC8 — Non-emergency triage → `red_flags: []` not null ✅
- `save_triage()`: when `result.red_flags` is `None` or `[]` (falsy), stores `red_flags=None` in DB.
- Schema `parse_red_flags`: `if v is None: return []` — deserialises DB `NULL` to Python `[]`.
- API response field type is `list[Any]` (not `Optional`), so Pydantic will never emit `null`. ✅
- **Minor note (P2):** A `result.red_flags = []` (empty list, not None) will also be stored as `NULL` because `[]` is falsy. This is technically correct (AC8 says `[]` or `NULL` is fine and response always returns a list), but storing `NULL` vs `'[]'` inconsistently may be confusing. Not a blocker.

### AC9 — DOCTOR consent-gated on history read ✅
- `_check_read_access()` → `_check_write_access()`: for `UserRole.DOCTOR`, calls `require_access(db, patient_id=..., requester_id=..., scope=scope)`. Raises `ConsentError` → 403 if consent absent. ✅
- `test_doctor_reads_history_with_consent` seeds a `Consent` record (scope='profile') and verifies 200. ✅
- Implicit test: no consent → 403 (covered by the `require_access` call; no explicit "no-consent" test for DOCTOR, but that is tested at the consent service level in prior tickets). ✅

### AC10 — 10 tests pass, 0 regressions ✅
- Test file contains exactly 10 test functions (test_1 through test_10 as described).
- Reported results: 401 passed (baseline 391 + 10 new), 1 skipped, 0 failures. ✅
- All fixtures isolated with randomised emails and freshly committed DB rows. ✅

---

## Additional Observations

### Strengths
1. **Service layer clean separation** — `save_triage()` and `get_history()` are pure DB functions; no HTTP concerns leak in.
2. **Limit clamping** — `get_history()` caps `limit` at 100 server-side; query param also enforces `le=100`, providing defense-in-depth.
3. **Schema validator robustness** — `parse_red_flags` handles all edge cases (None, bad JSON string, non-list JSON) without raising, preventing 500 errors on malformed data.
4. **Consistent pattern** — T19 implementation follows the same save-on-PATIENT-caller pattern established in T13 (metabolic score), reducing cognitive load.
5. **Migration reversible** — downgrade() correctly drops index before table.

### P2 Warnings (detail)

**W1 — `red_flags` NULL vs `'[]'` inconsistency:**
```python
# save_triage() — current behaviour
red_flags_json = json.dumps(result.red_flags, ensure_ascii=False) if result.red_flags else None
# result.red_flags = []  → falsy → stored as NULL
# result.red_flags = None → stored as NULL
```
Both map to `[]` in the API response (correct per AC8), but a raw `SELECT red_flags FROM triage_logs` would show NULL for both no-red-flags and empty-red-flags cases. Consider `json.dumps(result.red_flags or [])` to always store `'[]'` vs `NULL` to distinguish "field absent" from "explicitly empty." Not a bug; cosmetic.

**W2 — Fragile assertion in `test_triage_not_saved_for_non_patient`:**
```python
count = db.execute(
    select(TriageLog).where(TriageLog.patient_id == doctor["user_id"])
).scalar_one_or_none()
assert count is None
```
`doctor["user_id"]` is a User UUID, not a `PatientProfile.id`. Since doctors have no PatientProfile, no TriageLog will ever link `patient_id = user_id`. The assertion can never fail even if a bug caused spurious persistence under a real `patient_id`. Better: query `select(func.count()).select_from(TriageLog)` before/after and assert the count did not increase. Does not affect production correctness.

---

**Summary:** T19 is well-implemented — correct FK, proper migration chain, clean PATIENT-only persistence gate with silent fallback, proper JSON round-trip for `red_flags`, and consistent RBAC delegation to `_check_read_access`. Two minor P2 warnings (NULL/`[]` storage ambiguity and a vacuous test assertion) do not affect runtime correctness. All 10 acceptance criteria are met. **Approved for merge.**
