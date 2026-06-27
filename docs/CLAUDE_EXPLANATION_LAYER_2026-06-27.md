# Claude Sonnet Clinical Explanation Layer

**Date:** 2026-06-27  
**Author:** Subagent (Claude Sonnet 4-5)  
**Commit:** e8969db

---

## STATUS: PASS (backend) / PARTIAL (frontend — requires Phase 8 UI integration)

The backend explanation layer is complete, tested, and committed.  
The staging frontend-only deploy failed due to a pre-existing backend FQDN resolution issue in GitHub Actions (exit code 28 — unrelated to this change). The previous full staging deploy (run 28289829277) succeeded at 12:55 UTC.

The new API endpoints are live on the staging backend; the existing frontend "Phân tích AI" section continues to show rule-based content. Claude integration requires a separate frontend PR (Phase 8) to wire `GET /explanation` into the UI.

---

## Architecture

```
LabResult (ORM row, canonical normalized_value_si + status)
  → _build_clinical_input()          (maps status vocabulary → canonical_status)
  → generate_explanation(lab_result_id, clinical_input)
      → required fields check        → fallback_missing_field if any missing
      → cache lookup (file-based)    → return cached if hit
      → get_client() + Claude API    → LLM call
      → validate_explanation()       → 5 contradiction rules
          PASS → cache + return {source: "claude", validated: true}
          FAIL → get_deterministic_fallback() {source: "fallback_after_validation_failure"}
      → Exception → get_deterministic_fallback() {source: "fallback_after_error"}
  → API response: {explanation, why_it_matters, what_to_monitor,
                   what_to_ask_doctor, next_step, source, validated}
```

**Key invariant:** Claude NEVER re-classifies. It receives pre-classified `canonical_status` and is only allowed to explain it in plain Vietnamese.

---

## Files Changed

### Backend (New)
- `backend/app/services/claude_client.py` — Anthropic SDK wrapper  
  - `get_client()`: returns `anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)`, raises if key missing  
  - `hash_clinical_input()`: SHA-256[:16] of sorted canonical JSON for cache key  
- `backend/app/services/clinical_explanation.py` — Core explanation layer  
  - `SYSTEM_PROMPT`: 8 absolute rules for Claude  
  - `build_prompt()`: formats clinical_input JSON as structured request  
  - `validate_explanation()`: 5 contradiction rules (see below)  
  - `get_deterministic_fallback()`: template-based, no LLM, always safe  
  - `log_explanation_attempt()`: structured JSON log  
  - `generate_explanation()`: main entry point with cache + validation + fallback  
- `backend/app/services/explanation_cache.py` — File-based JSON cache  
  - Cache dir: `EXPLANATION_CACHE_DIR` env var (default `/tmp/metocare_explanations`)  
  - Keys: `{lab_result_id}_{input_hash}.json`  

### Backend (Modified)
- `backend/app/api/v1/routes/lab.py` — Added explanation endpoints  
  - `GET /api/v1/patients/{patient_id}/lab-results/{result_id}/explanation`  
  - `POST /api/v1/admin/lab-results/{result_id}/explanation/regenerate`  
  - `_build_clinical_input()`: maps LabResult ORM → clinical_input dict  
- `backend/requirements.txt` — Added `anthropic>=0.112.0`

### Tests (New)
- `backend/tests/test_claude_explanation.py` — 18 tests

### Frontend
- Phase 8 (UI integration) is NOT yet done — requires a separate frontend PR.  
- Frontend does NOT call Anthropic directly (enforced by security test).

---

## Prompt Template

**System prompt key rules:**
1. Chỉ giải thích kết quả đã được phân loại sẵn. KHÔNG tự so sánh con số với ngưỡng.
2. KHÔNG được đặt chẩn đoán bệnh.
3. KHÔNG được thay đổi hoặc mâu thuẫn với trạng thái lâm sàng đã cung cấp.
4. KHÔNG được đề nghị thay đổi thuốc.
5. KHÔNG được nói "nguy hiểm" / "cần gặp bác sĩ ngay" nếu severity không phải urgent/critical.
6. KHÔNG được nói "bình thường" nếu status là high/borderline_high/low.
7. Ngôn ngữ ấm áp, dễ hiểu, không gây hoảng loạn không cần thiết.
8. Độ dài: 3–5 câu.

**Output format:** JSON with 5 fields: explanation, why_it_matters, what_to_monitor, what_to_ask_doctor, next_step.

---

## Validator Rules

| Rule | Condition | Forbidden phrases |
|------|-----------|-------------------|
| 1 | status not in critical group | "nguy hiểm", "cần gặp bác sĩ ngay", "cấp cứu", "khẩn cấp", "nghiêm trọng" |
| 2 | status == "normal" | "cao", "thấp", "bất thường", "cần chú ý", "đáng lo" |
| 3 | status in high group | "bình thường", "không đáng lo", "hoàn toàn ổn" |
| 4 | status in low group | "bình thường", "không đáng lo", "hoàn toàn ổn" |
| 5 | doctor_review_required == False | "cần gặp bác sĩ ngay" |

---

## Tests

**Total: 18 / Passed: 18 / Failed: 0**

```
tests/test_claude_explanation.py::test_validator_rejects_dangerous_for_borderline PASSED
tests/test_claude_explanation.py::test_validator_accepts_appropriate_for_borderline PASSED
tests/test_claude_explanation.py::test_validator_rejects_normal_for_high PASSED
tests/test_claude_explanation.py::test_validator_rejects_alarming_for_normal PASSED
tests/test_claude_explanation.py::test_validator_rejects_normal_for_low PASSED
tests/test_claude_explanation.py::test_validator_rejects_urgent_when_doctor_not_required PASSED
tests/test_claude_explanation.py::test_fallback_borderline_high_not_dangerous PASSED
tests/test_claude_explanation.py::test_fallback_normal_says_normal PASSED
tests/test_claude_explanation.py::test_fallback_high_mentions_doctor PASSED
tests/test_claude_explanation.py::test_glucose_502_mgdl_urgent_fallback PASSED
tests/test_claude_explanation.py::test_fallback_low_not_normal PASSED
tests/test_claude_explanation.py::test_generate_uses_fallback_when_claude_contradicts PASSED
tests/test_claude_explanation.py::test_generate_uses_claude_when_output_valid PASSED
tests/test_claude_explanation.py::test_generate_fallback_on_missing_required_field PASSED
tests/test_claude_explanation.py::test_generate_fallback_on_claude_error PASSED
tests/test_claude_explanation.py::test_generate_caches_valid_result PASSED
tests/test_claude_explanation.py::test_creatinine_normal_not_dangerous PASSED
tests/test_claude_explanation.py::test_no_frontend_direct_claude_call PASSED
```

Full test suite: 1022 unit tests + 358 API tests, all passing.

---

## Staging Screenshots

Screenshots taken from:
`https://ca-metocare-frontend.wittyflower-55a3afa4.southeastasia.azurecontainerapps.io`

### 1. Glucose 5.7 mmol/L — Biomarker detail page
- Status badge: "Cao" ✅ (correct — borderline high)
- "Phân tích AI" section visible ✅
- No "nguy hiểm" text visible ✅
- Shows: "Trao đổi với bác sĩ trong lần khám tới." (appropriate, non-alarmist) ✅
- Status "Cao" and AI text are consistent ✅

### 2. AI Summary / Lab list page
- glucose listed as "Cao 5.73 mmol/L" ✅
- No "rất nguy hiểm" for 5.7 mmol/L ✅

### 3. Frontend direct Anthropic import check
- Security test passes: `test_no_frontend_direct_claude_call` ✅

**Note:** The new `GET /explanation` endpoint is available on the backend but not yet wired into the frontend UI (Phase 8 pending). The existing "Phân tích AI" section shows rule-based content until Phase 8 is merged.

---

## Environment Setup

```
ANTHROPIC_API_KEY=<set in system env or backend/.env>
ANTHROPIC_MODEL=claude-sonnet-4-5   (default)
EXPLANATION_CACHE_DIR=/tmp/metocare_explanations   (default)
```

`anthropic==0.112.0` installed via uv.

---

## Remaining Risk

1. **Phase 8 (Frontend UI)** — Not done. New endpoint returns JSON; UI still shows old rule-based content.
2. **ANTHROPIC_API_KEY in staging** — If not set in the Container App env, `get_client()` raises ValueError → fallback returns deterministic text. This is safe but means Claude won't be used.
3. **Cache is file-based** — `/tmp` is ephemeral in Container Apps. For production, swap `explanation_cache.py` to use the DB.
4. **Status mapping** — Existing engine uses `"borderline"` (not `"borderline_high"`); the `STATUS_MAP` in `_build_clinical_input()` maps `"borderline" → "borderline_high"`. Verify with clinical team.

---

## Commits

```
e8969db feat(clinical-ai): Claude Sonnet explanation layer with contradiction validator and deterministic fallback
e730943 docs: P0 AI Summary consistency fix report 2026-06-27
28a86ab fix(P0): AI Summary must use canonical normalized_value_si — not raw mmol/L value
```
