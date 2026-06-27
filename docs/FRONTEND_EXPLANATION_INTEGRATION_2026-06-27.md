# Frontend Integration — Claude Clinical Explanation

**Date:** 2026-06-27  
**Branch:** main  
**Commit:** 3fb95fb  

---

## STATUS: PASS (code + tests) / STAGING PENDING (infrastructure issue)

### Summary

Frontend integration of Claude clinical explanation on Biomarker Detail Page is complete:
- API client function added
- ExplanationSection component created with full safety gating
- Wired into Biomarker Detail Page at correct position
- 26 tests passing (10 required test cases, 26 assertions)
- Build: 0 errors
- Staging deploy: triggered but CI fails due to **pre-existing backend health check timeout** (exit code 28 — curl timeout connecting to ACA backend during build validation). This is NOT caused by our changes; all recent deploys exhibit the same failure.

---

## Files Changed

**Frontend:**
- `frontend/src/components/labs/ExplanationSection.tsx` — NEW: ExplanationSection component with safety gating
- `frontend/src/components/labs/__tests__/ExplanationSection.test.tsx` — NEW: 26 tests covering 10 required cases
- `frontend/src/lib/api/patient.ts` — MODIFIED: added `LabExplanation` interface + `getLabResultExplanation()`
- `frontend/src/app/(patient)/labs/[batchId]/results/[resultId]/page.tsx` — MODIFIED: wired ExplanationSection with state + useEffect + placement

---

## API Contract Used

```
GET /patients/{patient_id}/lab-results/{lab_result_id}/explanation

Response:
{
  explanation: string
  why_it_matters: string
  what_to_monitor: string
  what_to_ask_doctor: string
  next_step: string
  source: 'claude' | 'deterministic_fallback' | 'fallback_after_validation_failure' | 'fallback_after_error'
  validated: boolean
  input_hash?: string
}
```

---

## Safety Rules Applied (frontend layer)

1. **`validated=true` gate is non-negotiable** — `ExplanationSection` shows `SAFE_FALLBACK_TEXT` when `validated=false` 
2. **Frontend `isSafe()` check (belt-and-suspenders):**
   - For `nonCriticalStatuses` (normal, borderline_high, borderline_low, low): blocks `['rất nguy hiểm', 'cần cấp cứu', 'khẩn cấp']`
   - For `status === 'normal'`: also blocks `['bất thường', 'đáng lo']`
   - Critical/high statuses: urgent language is allowed and displayed
3. **No Anthropic import in frontend** — verified by structural test + source grep
4. **`biomarkerStatus` passed from LabResultEntry** — never recomputed locally; backend is single source of truth

---

## Tests

- **Total: 26 / Passed: 26 / Failed: 0**
- Test suites: 2 (ExplanationSection + labs) — both PASS

### Test cases covered:
| # | Test | Result |
|---|------|--------|
| 1 | Renders explanation when validated=true (incl. sub-sections, AI disclaimer) | ✅ 4 assertions |
| 2 | Hides and shows fallback when validated=false | ✅ 2 assertions |
| 3 | Frontend safety check — hides dangerous text for normal/borderline status | ✅ 5 assertions |
| 4 | Loading skeleton shown while fetching | ✅ 2 assertions |
| 5 | Error state with retry button (click fires onRetry) | ✅ 3 assertions |
| 6 | Null explanation renders nothing (silent) | ✅ 1 assertion |
| 7 | No @anthropic-ai SDK import in frontend | ✅ 2 assertions |
| 8 | API client calls correct backend endpoint, not anthropic.com | ✅ 2 assertions |
| 9 | Glucose 5.73 borderline — appropriate language shown, no danger phrases | ✅ 2 assertions |
| 10 | Glucose 502 critical — urgent language allowed and displayed | ✅ 3 assertions |

---

## Build

```
npm run build
✓ Compiled successfully
✓ Generating static pages (43/43)
exit code: 0, errors: 0
```

---

## Staging Deploy

- Script: `bash scripts/deploy-staging.sh` — triggered GitHub Actions workflow
- GH Actions run: `28291503889`
- **Result: FAILED** — exit code 28 (curl timeout) at "Validate API URL before build" step
- **Root cause: pre-existing infrastructure issue** — backend Azure Container Apps health endpoint is unreachable from GH Actions runner; same failure in runs `28291209129` and `28289807121` (before our changes)
- **Our code is NOT the cause** — local build passes with 0 errors, tests pass

---

## Staging Screenshots (pre-existing deployed version — our changes pending deploy)

Screenshots taken from: `https://ca-metocare-frontend.wittyflower-55a3afa4.southeastasia.azurecontainerapps.io`

### Screenshot 1 — fasting_glucose 5.73 mmol/L:
- Status badge: "Cao" ✅
- AI section: "Chỉ số tham khảo kháng insulin — không thay thế HOMA-IR hay xét nghiệm chuyên sâu." (not dangerous language) ✅
- No contradiction between status and AI text ✅
- ExplanationSection: N/A (deploy pending — but ExplanationSection would call backend, which would return `null` gracefully since endpoint may not exist yet → silent render)

### Screenshot 2 — ast 25.37 U/L (Bình thường):
- Status badge: "Bình thường" ✅
- AI section: "Chưa có phân tích AI cho chỉ số này." ✅
- No dangerous language ✅
- No red alert ✅

### Screenshot 3 — High/urgent (creatinine 87.66 mg/dL — Nguy hiểm):
- Status badge: "Nguy hiểm" ✅
- AI section: "Creatinine tăng rất cao, cần bác sĩ đánh giá chức năng thận." — appropriate urgency ✅
- Consistent with status badge ✅

### Surface consistency across all 3 pages:
- Status badge, AI section, and action cards are consistent ✅
- ExplanationSection adds a 4th surface that is gated behind validated=true ✅

---

## ExplanationSection Placement (page.tsx)

```
[1. Current Value Card: name → value → status badge → ref range → gauge]
    ↓
[ExplanationSection] ← NEW: after gauge, before AI Interpretation section
    ↓
[2. AI Clinical Interpretation (existing PatientInsight)]
    ↓
[3. Trend chart]
    ↓
[4. Next steps]
```

---

## Remaining Risk

1. **Backend endpoint** `GET /patients/{id}/lab-results/{resultId}/explanation` must exist and return `{validated: true, source: 'claude'|...}` — without it, `getLabResultExplanation` returns `null` and `ExplanationSection` renders nothing (graceful degradation)
2. **Staging deploy infra** — the backend health check timeout needs to be fixed at the CI level (ACA backend health endpoint must be reachable from GH Actions runner, or health check step should be made optional/timeout-lenient)
3. **Unit test coverage for page.tsx** — full page render tests need auth/router mocks; not added in this integration (component-level coverage is sufficient)

---

## Commits

```
3fb95fb feat(labs-ux): Claude explanation section on Biomarker Detail Page — frontend integration
```
