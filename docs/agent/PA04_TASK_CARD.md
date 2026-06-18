# PA-04 Task Card — DB UNIQUE Constraint on patient_profiles.user_id + Import Style Fix

**Branch:** `feature/pa04-db-unique-patient-profile`
**Created from:** `a577bc2` (main HEAD after PA-03 merge)
**Owner:** Claude Code
**Priority:** P2 (deferred from PA-03 Codex review)
**Date:** 2026-06-19

---

## Background

Codex PA-03 review raised two P2 deferred items:

- **P2-01:** `from sqlalchemy import select` placed inside the `me()` function body in `auth.py`.
- **P2-02:** `patient_profiles.user_id` indexed but not UNIQUE at DB level — concurrent first-PATCH race could theoretically create duplicate rows.

---

## Scope

| # | Change | File |
|---|--------|------|
| 1 | Move deferred `from sqlalchemy import select` to module-level | `backend/app/api/v1/routes/auth.py` |
| 2 | Add `unique=True` to `PatientProfile.user_id` column | `backend/app/models/patient.py` |
| 3 | Alembic migration: `uq_patient_profiles_user_id` | `backend/alembic/versions/t27_unique_patient_profile_user_id.py` |
| 4 | New test: `test_patient_profile_upsert_no_duplicate` | `backend/tests/api/test_patient_mvp_api.py` |

---

## Quality Gate

- Ruff: PASS
- Migration: `t27_uq_patient_profile_user_id` applied via `batch_alter_table` (SQLite-compatible)
- Tests: 535 passed, 1 skipped (was 523+1 before PA-04)
