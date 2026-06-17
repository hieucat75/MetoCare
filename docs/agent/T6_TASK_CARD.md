# T6 Task Card — Doctor Review Workflow + GitHub Actions CI

**Issued by:** OpenClaw (Coordinator)  
**Assigned to:** Antigravity  
**Date:** 2026-06-17 23:20 GMT+7  
**Governance:** AI Governance Policy v2.0 — Antigravity implements, Codex reviews, PTH approves  

---

## Objective

Implement T6 sprint:
1. GitHub Actions CI pipeline (compliance P0)
2. Doctor Review Workflow API (wire `DoctorReviewService` into HTTP endpoints)
3. CarePlan approval endpoint
4. Tests covering happy paths and forbidden paths

---

## Constraints (read before touching anything)

- **Governance Policy v2.0:** Antigravity status must be `READY FOR REVIEW` — not APPROVED, not merge-recommended
- Ruff line-length=100, target-version="py311", select=["E","F","I","UP","B"], ignore=["B008"]
- Do NOT run `alembic upgrade` — no schema changes needed (T6 is API + CI only)
- Do NOT modify existing passing tests — add new tests alongside
- Do NOT hardcode clinical thresholds
- PHI stays encrypted — do not log or expose `notes`, `content` fields in plain text
- AuditLog is append-only — no FK, resource_type + resource_id strings
- All 202 existing tests must continue to pass
- No broad refactors, no formatting churn

---

## Repo Context

- **Root:** `/Users/pth/Developer/metocare/`
- **Backend:** `/Users/pth/Developer/metocare/backend/`
- **Python venv:** `source /Users/pth/Developer/metocare/.venv/bin/activate`
- **Active branch (start from):** `main` @ `b7f3a04`
- **Target branch:** `feature/t6-doctor-review` (create from main)
- **Postgres:** `postgresql+psycopg://mcp:mcp_dev_only@localhost:5432/mcp`

---

## Phase 0 — Inspect before coding (mandatory)

Read these files before writing any code:

1. `backend/app/services/doctor_review.py` — full file; understand `submit_for_review()`, `review()`, `get_pending_queue()`
2. `backend/app/models/ai.py` — `AIClinicalRecommendation`, `RecommendationStatus`
3. `backend/app/models/care.py` — `CarePlan`, `CarePlanStatus`, `Doctor`, `DoctorClinic`
4. `backend/app/schemas/care.py` — `CarePlanApprove`, `CarePlanOut`, `EncounterOut`
5. `backend/app/api/v1/routes/encounters.py` — existing endpoint pattern to follow
6. `backend/app/api/v1/routes/care_plans.py` — existing PATCH pattern, `_DOCTOR_ONLY_STATUSES`
7. `backend/app/api/deps.py` — `current_user`, `get_session` dependency pattern
8. `backend/app/core/rbac.py` — RBAC helper functions
9. `backend/tests/unit/test_doctor_review.py` — existing test style
10. `backend/tests/conftest.py` or `tests/` root — fixtures, db setup

---

## Phase 1 — Branch

```bash
cd /Users/pth/Developer/metocare
git checkout main
git pull origin main
git checkout -b feature/t6-doctor-review
```

---

## Phase 2 — GitHub Actions CI

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main, "feature/**", "feature/**/**"]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Install dependencies
        run: pip install -e ".[dev]"   # or pip install -r requirements-dev.txt

      - name: Ruff lint
        run: ruff check .

      - name: Run tests (SQLite — no Postgres needed in CI)
        run: python -m pytest tests/ -v --tb=short
        env:
          MCP_DATABASE_URL: ""   # empty = SQLite in-memory (existing pattern)

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: pytest-results
          path: backend/test-results.xml
        continue-on-error: true
```

Notes:
- Check if project uses `pyproject.toml` or `requirements*.txt` and use correct install command
- Check if SQLite is the default when `MCP_DATABASE_URL` is unset — verify in `alembic/env.py` or `app/config.py`
- If `pytest-junit` not installed, add `--junit-xml=test-results.xml` only if plugin available; else omit artifact step

---

## Phase 3 — Doctor Review Workflow API

Create `backend/app/api/v1/routes/doctor_review.py`.

### Endpoints

#### A. GET `/api/v1/doctor/review/queue`
- Allowed: DOCTOR only
- Calls: `DoctorReviewService(db).get_pending_queue(current_user)`
- Returns: `list[AIClinicalRecommendationOut]`
- 403 if not DOCTOR role

#### B. POST `/api/v1/doctor/review/{rec_id}/submit`
- Allowed: AI_SERVICE or SUPER_ADMIN only
- Calls: `DoctorReviewService(db).submit_for_review(rec_id, current_user)`
- Returns: `AIClinicalRecommendationOut`
- 403 for other roles
- 503 if DOCTOR_REVIEW_GATE disabled

#### C. POST `/api/v1/doctor/review/{rec_id}/review`
- Allowed: DOCTOR only
- Body: `DoctorReviewDecision` (verdict: "accepted"|"rejected"|"request_info", notes: str|None)
- Calls: `DoctorReviewService(db).review(rec_id, verdict=..., notes=..., doctor=current_user)`
- Returns: `AIClinicalRecommendationOut`
- 403 for non-DOCTOR
- Audit log entry on success

#### D. GET `/api/v1/doctor/review/{rec_id}`
- Allowed: DOCTOR (assigned), INTERNAL_ADMIN, SUPER_ADMIN, MEDICAL_REVIEWER
- Returns: `AIClinicalRecommendationOut`
- 403 for PATIENT / AI_SERVICE

### Schemas needed (add to `app/schemas/` or inline)

```python
class DoctorReviewDecision(BaseModel):
    verdict: Literal["accepted", "rejected", "request_info"]
    notes: str | None = None

class AIClinicalRecommendationOut(BaseModel):
    id: str
    session_id: str
    patient_id: str
    recommendation_type: str
    status: str
    ai_confidence: float | None
    safety_cleared: bool
    reviewed_by_doctor_id: str | None
    reviewed_at: datetime | None
    model_config = {"from_attributes": True}
```

Note: `AIClinicalRecommendationOut` may already exist in `ai_sessions.py` — reuse or move to `app/schemas/ai.py`.

---

## Phase 4 — CarePlan Approve Endpoint

Add to `backend/app/api/v1/routes/care_plans.py`:

#### POST `/api/v1/care_plans/{care_plan_id}/approve`
- Allowed: DOCTOR only (not ADMIN, not AI_SERVICE)
- Body: `CarePlanApprove` (already in `app/schemas/care.py` — check fields)
- Logic:
  - Load CarePlan; 404 if not found or soft-deleted
  - RBAC: assert doctor is assigned (use `assert_doctor_assigned`)
  - Transition: `plan.status = CarePlanStatus.APPROVED`, set `plan.approved_by_doctor_id = doctor.id`
  - AuditLog: `care_plan.approve`
  - Return: `CarePlanOut`
- 403 for AI_SERVICE, PATIENT, CLINIC_ADMIN
- 409 if plan already APPROVED or ARCHIVED

---

## Phase 5 — Register Router

In `backend/app/api/v1/router.py`, add:

```python
from app.api.v1.routes import doctor_review
router.include_router(doctor_review.router, prefix="/doctor", tags=["doctor_review"])
```

Verify prefix results in `/api/v1/doctor/review/...` — check existing router prefix setup.

---

## Phase 6 — Tests

### `tests/api/test_doctor_review_api.py`

```
test_doctor_gets_pending_queue                   — DOCTOR → 200, list
test_non_doctor_cannot_get_queue                 — PATIENT → 403
test_ai_service_submits_rec_for_review           — AI_SERVICE → 201
test_patient_cannot_submit_for_review            — PATIENT → 403
test_doctor_accepts_recommendation               — DOCTOR + valid rec → 200, status=accepted
test_doctor_rejects_recommendation               — DOCTOR + valid rec → 200, status=rejected
test_non_doctor_cannot_review_recommendation     — PATIENT → 403
test_unauthenticated_cannot_access_queue         — no token → 401
```

### `tests/api/test_care_plan_approve.py`

```
test_doctor_approves_care_plan                   — DOCTOR + DRAFT plan → 200, status=APPROVED
test_patient_cannot_approve_care_plan            — PATIENT → 403
test_ai_cannot_approve_care_plan_via_approve_ep  — AI_SERVICE → 403
test_approve_already_approved_plan               — 409
test_unauthenticated_cannot_approve              — no token → 401
```

Follow test fixture pattern from `tests/api/test_encounters_api.py` exactly.

---

## Phase 7 — Local Validation

```bash
cd /Users/pth/Developer/metocare/backend
source /Users/pth/Developer/metocare/.venv/bin/activate
ruff check .
python -m pytest tests/ -v --tb=short 2>&1 | tail -5
```

Target: ≥ 202 passed (all existing + new T6 tests), Ruff clean.

Do NOT declare APPROVED. Status must be: **READY FOR REVIEW**.

---

## Phase 8 — Pull Request

```bash
git add -A
git commit -m "feat(T6): doctor review workflow API + CarePlan approve endpoint + GitHub Actions CI

Implemented By: Antigravity
Status: READY FOR REVIEW

Endpoints:
- GET  /api/v1/doctor/review/queue
- POST /api/v1/doctor/review/{rec_id}/submit
- POST /api/v1/doctor/review/{rec_id}/review
- GET  /api/v1/doctor/review/{rec_id}
- POST /api/v1/care_plans/{id}/approve

CI: .github/workflows/ci.yml (pytest + ruff on push/PR)

Tests: [N new] tests added, [total] passed total
Ruff: clean
Alembic: head unchanged (t4_m9_add_sdel)"

git push origin feature/t6-doctor-review
```

Then open PR on GitHub with title:
`T6: Doctor Review Workflow API + CarePlan Approve + CI`

PR description must include:
```
Implemented By: Antigravity
Reviewed By: [PENDING — Codex CLI]
Approved By: [PENDING — PTH]
```

---

## Deliverables (report back to OpenClaw)

1. Branch pushed: `feature/t6-doctor-review`
2. GitHub PR URL
3. Files created / modified list
4. Endpoint table (method + path + allowed roles)
5. Test count: `X new tests, Y total passed`
6. Ruff status
7. CI workflow file path
8. Any blockers or assumptions
9. **Status: READY FOR REVIEW** (mandatory — do not use any other verdict)

---

## Medical Safety Reminders

- `DoctorReviewService.review()` uses `sqlalchemy.update()` (SQL-level) to bypass ORM validators — do NOT replicate this pattern outside the service
- Do NOT expose `notes` or `content` fields in log output
- AuditLog entries: append-only, no FK, use `resource_type="recommendation"` / `resource_type="care_plan"`
- AI_SERVICE callers must pass through ConsentGuard before accessing patient data — this is enforced upstream in AISession; do not add new bypass paths

---

*Task Card issued: 2026-06-17 23:20 GMT+7 | Coordinator: OpenClaw*
