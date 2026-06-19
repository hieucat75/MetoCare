## Codex Review — PA-04 DB Unique Constraint + Import Fix

**Result:** ✅ APPROVE

**P0 Blockers:** 0
**P1 Blockers:** 0
**P2 Warnings:** 1
**Tests:** 535 passed, 1 skipped / baseline 523 (+12)
**Acceptance Criteria:** 10/10 met

---

### Acceptance Criteria Detail

| # | Criterion | Status |
|---|-----------|--------|
| AC1 | `from sqlalchemy import select` at module level in `auth.py` (line 6) | ✅ PASS |
| AC2 | `PatientProfile.user_id` declares `unique=True` | ✅ PASS |
| AC3 | `down_revision = "t23_add_notifications"` (correct Alembic HEAD) | ✅ PASS |
| AC4 | `create_unique_constraint("uq_patient_profiles_user_id", ["user_id"])` in upgrade() | ✅ PASS |
| AC5 | `drop_constraint("uq_patient_profiles_user_id", type_="unique")` in downgrade() | ✅ PASS |
| AC6 | No columns or tables dropped in migration | ✅ PASS |
| AC7 | Uses `op.batch_alter_table` — compatible with both SQLite (tests) and PostgreSQL (prod) | ✅ PASS |
| AC8 | `test_patient_profile_upsert_no_duplicate` verifies exactly 1 row after 2 PATCH calls | ✅ PASS |
| AC9 | `pytest tests/` → **535 passed, 1 skipped** ≥ 524 threshold | ✅ PASS |
| AC10 | PA04 commit touches only the 4 listed backend files + 1 agent docs file (PA05 changes are in a separate commit) | ✅ PASS |

---

### P2 Warnings

**W1 — Extra files in branch diff vs `main`:**
`git diff main --name-only` shows 11 files because the branch contains two commits: PA04 and PA05. The PA05 changes (`app/api/v1/routes/ai.py`, `app/schemas/ai.py`, `tests/api/test_ai_patient_explain.py`, related docs) are in a separate later commit (`c44d260`). The PA04 commit (`46b3d35`) is clean and touches only the 4 expected files + `docs/agent/PA04_IMPLEMENTATION_REPORT.md`. No concern for this review scope, but the reviewer should be aware the branch is ahead by 2 commits when compared to `main`.

---

### File-by-File Notes

**`backend/app/api/v1/routes/auth.py`**
- `from sqlalchemy import select` correctly moved to line 6 (module-level import, after stdlib imports, following project convention).
- No other functional changes observed.

**`backend/app/models/patient.py`**
- `user_id` column: `mapped_column(ForeignKey("users.id"), index=True, unique=True, nullable=False)` — all three constraints present and correctly ordered. Column-level `unique=True` is consistent with the migration constraint; both are needed (model for ORM enforcement + migration for DB-level enforcement).

**`backend/alembic/versions/t27_unique_patient_profile_user_id.py`**
- `revision = "t27_uq_patient_profile_user_id"` / `down_revision = "t23_add_notifications"` — chain is correct.
- Upgrade uses `batch_alter_table` → safe for SQLite; PostgreSQL renders as `ALTER TABLE ... ADD CONSTRAINT`.
- Downgrade mirrors upgrade exactly. No destructive operations.
- `branch_labels = None`, `depends_on = None` — standard; no concerns.

**`backend/tests/api/test_patient_mvp_api.py`**
- `test_patient_profile_upsert_no_duplicate`: exercises the create path (PATCH with user_id) then update path (PATCH with profile UUID). Asserts `row_count == 1` via direct DB query using `func.count()` + `db.expire_all()` to flush cache. Clear failure message included.
- `from sqlalchemy import func, select` imported inside the test function — acceptable for test isolation; does not violate AC1 (which targets `auth.py`).

---

### Summary

PA-04 is a minimal, well-scoped change. The import fix is correct. The unique constraint is applied at both the ORM model layer and the database migration layer, which is the right approach for dual-environment compatibility. The `batch_alter_table` pattern correctly handles SQLite's `ALTER TABLE` limitations used in the test suite. The new test covers the regression scenario directly and validates at the DB level (not just HTTP response).

All 10 acceptance criteria are met. Test count increased from 523 to 535 (+12) — net positive, no regressions. Ruff passes clean.

**APPROVE — safe to merge to `main`.**

---

*Reviewed by: Codex (read-only reviewer)*
*Date: 2026-06-18*
*Branch: feature/pa04-db-unique-patient-profile*
*Commit: 46b3d35*
