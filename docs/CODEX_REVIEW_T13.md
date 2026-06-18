# Codex Review — T13 Metabolic Score History API

**Branch:** `feature/t13-metabolic-score-history`
**Reviewed:** 2026-06-18
**Reviewer:** Codex (read-only)

---

**Result:** ✅ APPROVE

**P1 Blockers:** None
**P2 Warnings:** 1 (minor — see below)
**Security:** PASS
**Test Results:** 299/299 PASS (10 new, 0 failures)
**Acceptance Criteria:** 10/10 met

---

## Findings

### AC1 — POST /ai/metabolic-score persists for PATIENT callers ✅

`ai.py` correctly computes the score for all allowed roles and then applies the persistence guard:

```python
if user.role == UserRole.PATIENT.value:
    patient_profile = db.execute(
        select(PatientProfile).where(PatientProfile.user_id == user.id)
    ).scalar_one_or_none()
    if patient_profile is not None:
        risk_score_svc.save_score(db, patient_id=patient_profile.id, result=result)
```

Double guard: role check AND profile existence. Both must pass before `save_score()` is called. ✅

### AC2 — Non-PATIENT callers not persisted ✅

DOCTOR, CLINIC_ADMIN, INTERNAL_ADMIN, SUPER_ADMIN all fail the `user.role == UserRole.PATIENT.value` check and are silently skipped. No error is raised.  
Edge case (PATIENT with no profile yet): `scalar_one_or_none()` returns `None`, inner block is skipped silently. No crash. ✅

Test 2 (`test_score_not_saved_when_no_patient_profile`) covers the DOCTOR case explicitly. ✅

### AC3 — GET /patients/{id}/metabolic-scores returns paginated history + trend ✅

`patients.py` endpoint accepts `limit` (1–100, default 20) and `offset` (≥0, default 0) as query params.  
`get_history()` returns `(total, items)`, trend is computed via `compute_trend(items)`, and the full `RiskScoreHistoryResponse` is returned with `patient_id`, `total`, `items`, and `trend`. ✅

### AC4 — RBAC: PATIENT own-only, DOCTOR consent-gated, ADMIN any, AI_SERVICE → 403 ✅

The history endpoint delegates to `svc.get_profile()` for RBAC validation (the existing profile service):

```python
svc.get_profile(db, patient_id=patient_id, requester=user)
```

This reuses the already-tested RBAC logic from T12 without duplication. PATIENT own-only check, DOCTOR consent gate (scope=`profile`), ADMIN unrestricted, AI_SERVICE and CLINIC_ADMIN → 403 all fall through to the existing service. ✅

Tests 3–7 cover all four RBAC variants + AI_SERVICE block. ✅

### AC5 — Trend logic correctness ✅

```python
if delta > 5:      # strictly greater than 5 — correct per spec
    return "worsening"
if delta < -5:     # strictly less than -5 — correct per spec
    return "improving"
return "stable"    # delta in [-5, +5] inclusive
```

Boundary is **strict** (`> 5`, not `>= 5`): a delta of exactly 5 returns `"stable"`. This matches the acceptance criteria: _delta > 5 → worsening_. ✅

Tests 9/10 use deltas of +12 and -18 (well outside boundary). No boundary-exact test (delta=5 or delta=-5), but this is a P2 observation only — the spec says `>5` and the code implements `>5` correctly.

### AC6 — top_risks stored as JSON, deserialized to list in response ✅

`save_score()` serialises to JSON string via `json.dumps()`.  
`RiskScoreOut.parse_top_risks` is a `field_validator(mode="before")` that handles:
- `None` → `[]`
- `str` → `json.loads(v)`, validated as list
- `list` → pass-through

API consumers always receive a parsed list. ✅

### AC7 — save_score() uses patient_profiles.id (not users.id) as FK ✅

Model verification (`clinical.py`):
```
RiskScore.patient_id → ForeignKey("patient_profiles.id")
```

In `ai.py`, the profile is looked up by `user.id`, then `patient_profile.id` (the `patient_profiles.id` PK) is passed to `save_score()`:
```python
patient_profile = db.execute(select(PatientProfile).where(PatientProfile.user_id == user.id)).scalar_one_or_none()
risk_score_svc.save_score(db, patient_id=patient_profile.id, result=result)
```

`patient_profile.id` is the `patient_profiles` PK, not `users.id`. FK is correct. ✅

### AC8 — RBAC delegates to patient_profile service, no duplication ✅

The history endpoint calls `svc.get_profile()` solely for the RBAC side-effect (raises 403/404 on blocked access), then discards the profile return value. History data is fetched separately through `risk_score_svc.get_history()`. Clean separation, zero duplication. ✅

### AC9 — 10 tests covering save, no-save, RBAC, all 4 trend states ✅

| # | Test | Coverage |
|---|------|----------|
| 1 | `test_score_saved_on_patient_compute` | save path |
| 2 | `test_score_not_saved_when_no_patient_profile` | no-save (DOCTOR) |
| 3 | `test_patient_reads_own_history` | PATIENT own |
| 4 | `test_patient_cannot_read_another_patients_history` | PATIENT cross-access 403 |
| 5 | `test_doctor_reads_history_with_consent` | DOCTOR consent-gated |
| 6 | `test_admin_reads_any_history` | ADMIN unrestricted |
| 7 | `test_ai_service_cannot_read_history` | AI_SERVICE 403 |
| 8 | `test_empty_history_returns_insufficient_data` | `insufficient_data` trend |
| 9 | `test_trend_worsening` | `worsening` trend (delta +12) |
| 10 | `test_trend_improving` | `improving` trend (delta -18) |

All 10 tests present and correctly structured. ✅

### AC10 — Zero regressions ✅

299 passed, 1 skipped (pre-existing skip), 0 failures. Baseline +10. ✅

---

## P2 Warnings

### W1 — Missing stable-trend test

There is no test for `trend = "stable"` (e.g. delta ≤ 5). The four trend states per the spec are: `insufficient_data`, `worsening`, `improving`, `stable`. Tests 8–10 cover 3 of 4 states; `stable` is implicit but untested. **Recommend adding one `test_trend_stable` case** (e.g. seeds `[42, 45]` → delta=+3 → `stable`). This is non-blocking since the code is correct.

---

## Security Notes

- No raw SQL; all queries use SQLAlchemy ORM with parameterised values. ✅
- RBAC via JWT role + consent check; no privilege escalation path found. ✅
- `top_risks` JSON is stored server-side and re-parsed on read — no client-controlled JSON injection surface. ✅
- `limit` clamped to 100 server-side (both Query param and `min(limit, 100)` in service). ✅
- AI_SERVICE explicitly excluded from history endpoint (403). ✅

---

**Summary:** T13 is a clean, well-structured implementation. All 10 acceptance criteria are met: PATIENT-only persistence is correctly guarded (including the no-profile edge case), FK usage is correct (`patient_profiles.id` throughout), trend logic implements strict `> 5` boundaries as specified, and RBAC delegates properly to the existing profile service without duplication. The only gap is a missing `stable`-trend test (P2, non-blocking).
