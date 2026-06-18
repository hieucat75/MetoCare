# T13 Task Card — Metabolic Score History API

**TASK_ID:** T13  
**LABEL:** Metabolic Score History — Save + Trend Endpoint  
**Branch:** `feature/t13-metabolic-score-history`  
**Base branch:** `main`  
**Repo:** `/Users/pth/Developer/Metocare`  
**Implementer:** Antigravity  
**Coordinator:** OpenClaw  
**Status:** IN PROGRESS  
**Issued:** 2026-06-18 GMT+7

---

## Objective

Currently `POST /ai/metabolic-score` computes a score but does NOT persist it. The `RiskScore` model exists but is unused. This sprint:

1. Persist score results to `risk_scores` table when a patient calls `/ai/metabolic-score`
2. Add `GET /patients/{patient_id}/metabolic-scores` — paginated history + trend
3. API tests

---

## Scope

### ALLOWED_FILES

- `backend/app/api/v1/routes/ai.py` — persist score after compute
- `backend/app/api/v1/routes/patients.py` — add new GET endpoint
- `backend/app/services/risk_score.py` — NEW: `save_score()` + `get_history()`
- `backend/app/schemas/risk_score.py` — NEW: `RiskScoreOut`, `RiskScoreHistoryResponse`
- `backend/app/schemas/__init__.py` — export new schemas
- `backend/tests/api/test_metabolic_score_history_api.py` — NEW
- `docs/agent/T13_IMPLEMENTATION_REPORT.md` — NEW

### DO NOT TOUCH

- `backend/app/models/clinical.py` (RiskScore model already exists)
- `backend/app/domain/metabolic_score.py`
- Any migration files

---

## API Design

### Modified: `POST /ai/metabolic-score`

After computing score, IF the caller is a PATIENT (has `PatientProfile`):
- Save to `risk_scores` via `risk_score.save_score(db, patient_id, result)`
- `top_risks` = JSON string of top 3 factors by points
- If caller is not PATIENT (DOCTOR, CLINIC_ADMIN calling on behalf), skip persistence silently

**No behavior change** for existing callers — same response schema.

### New: `GET /patients/{patient_id}/metabolic-scores`

**RBAC:** Same as patient profile — PATIENT (own), DOCTOR (consent-gated), INTERNAL_ADMIN/SUPER_ADMIN (any)

**Query params:**
- `limit: int = 20` (max 100)
- `offset: int = 0`

**Response:** `RiskScoreHistoryResponse`
```json
{
  "patient_id": "uuid",
  "total": 5,
  "items": [
    {
      "id": "uuid",
      "metabolic_score": 42,
      "band": "fair",
      "top_risks": [{"name": "hba1c", "points": 25, "detail": "..."}],
      "created_at": "2026-06-18T..."
    }
  ],
  "trend": "improving" | "worsening" | "stable" | "insufficient_data"
}
```

**Trend logic** (simple, deterministic):
- `< 2 records`: `insufficient_data`
- Last score vs previous score: delta > 5 → `worsening`, delta < -5 → `improving`, else `stable`

---

## Service Layer

`backend/app/services/risk_score.py`:

```python
def save_score(db, *, patient_id: str, result: MetabolicScoreResult) -> RiskScore
def get_history(db, *, patient_id: str, limit: int, offset: int) -> tuple[int, list[RiskScore]]
def compute_trend(scores: list[RiskScore]) -> str  # "improving"|"worsening"|"stable"|"insufficient_data"
```

---

## Schemas

`backend/app/schemas/risk_score.py`:
- `RiskScoreOut` — id, metabolic_score, band, top_risks (parsed list), created_at
- `RiskScoreHistoryResponse` — patient_id, total, items, trend

---

## Test Requirements

Minimum 10 tests:

1. `test_score_saved_on_patient_compute` — after POST /ai/metabolic-score, record in db
2. `test_score_not_saved_when_no_patient_profile` — doctor calling, no persistence
3. `test_patient_reads_own_history` → 200, items list
4. `test_patient_cannot_read_another_patients_history` → 403
5. `test_doctor_reads_history_with_consent` → 200
6. `test_admin_reads_any_history` → 200
7. `test_ai_service_cannot_read_history` → 403
8. `test_empty_history_returns_insufficient_data` → trend = "insufficient_data"
9. `test_trend_worsening` — scores [30, 42] → "worsening"
10. `test_trend_improving` — scores [60, 42] → "improving"

---

## Acceptance Criteria

- [ ] `POST /ai/metabolic-score` persists to `risk_scores` for PATIENT callers
- [ ] `GET /patients/{id}/metabolic-scores` returns paginated history + trend
- [ ] RBAC correct on history endpoint
- [ ] Trend logic correct for all 4 states
- [ ] `top_risks` serialized as JSON list in DB, deserialized in response
- [ ] 10 new tests pass
- [ ] Zero regressions (289 baseline → 299+ total)
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

*Task Card issued: 2026-06-18 15:40 GMT+7 | Coordinator: OpenClaw*
