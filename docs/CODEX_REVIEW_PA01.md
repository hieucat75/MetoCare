# Codex Review — PA-01 Seed Admin + Onboarding Runbook

**Branch:** `feature/pa01-seed-admin` (head: `856dcee`)  
**Reviewer:** Codex (read-only)  
**Date:** 2026-06-18  
**Scope:** `backend/scripts/seed_admin.py`, `backend/scripts/seed_patient.py`, `docs/ops/PILOT_ONBOARDING_RUNBOOK.md`

---

**Result:** APPROVE

**P0 Blockers:** 0  
**P1 Blockers:** 0  
**P2 Warnings:** 1  
**Security:** PASS  
**Acceptance Criteria:** 10/10 met

---

## Acceptance Criteria Evaluation

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| AC1 | `seed_admin.py` role restriction | **PASS** | `_ALLOWED_ROLES = frozenset({UserRole.SUPER_ADMIN.value, UserRole.INTERNAL_ADMIN.value})`. `argparse choices` enforces this at CLI level; `_validate_role()` enforces it programmatically. `--role patient` triggers argparse error (exit 2). |
| AC2 | `seed_admin.py` password policy | **PASS** | `_validate_password()` checks `len >= 12` and regex `(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[special])`. Called unconditionally before `if dry_run` branch — enforced on all invocations including `--dry-run`. |
| AC3 | `seed_admin.py` idempotent | **PASS** | `scalar_one_or_none()` lookup by email. If existing: returns `action: "skipped"` with existing `user_id`, prints `[SKIP]` with id. No exception raised. |
| AC4 | `seed_admin.py` no `PatientProfile` | **PASS** | Zero references to `PatientProfile` or `patient_profile` anywhere in `seed_admin.py`. Confirmed via grep. |
| AC5 | `seed_patient.py` atomic | **PASS** | `db.add(user)` → `db.flush()` → `PatientProfile(user_id=user.id)` → `db.add(profile)` → `db.commit()`. `except Exception: db.rollback()` ensures rollback on any failure. Single transaction boundary. |
| AC6 | `seed_patient.py` outputs IDs | **PASS** | On `"created"`: prints `user_id` and `patient_profile_id`. On `"skipped"`: also prints both IDs (fetches existing profile via `scalar_one_or_none`). |
| AC7 | No secrets in code | **PASS** | No hardcoded passwords, API keys, or credentials in any of the three files. Runbook uses `<placeholder>` syntax for all secrets. Shell variables in runbook reference environment variables, not literals. |
| AC8 | Ruff clean | **PASS** | `ruff check scripts/` → `All checks passed!` (verified live). |
| AC9 | Runbook completeness | **PASS** | All 7 required sections present: §1 Prerequisites, §2 Seed Admin, §3 Seed Patient, §4 MFA Enrollment, §5 First Login Test, §6 PatientProfile Verification, §7 Troubleshooting (8 sub-items). |
| AC10 | No application code modified | **PASS** | `git diff main..feature/pa01-seed-admin --name-only` shows only: `backend/scripts/seed_admin.py`, `backend/scripts/seed_patient.py`, `docs/agent/PA01_IMPLEMENTATION_REPORT.md`, `docs/agent/PA01_TASK_CARD.md`, `docs/ops/PILOT_ONBOARDING_RUNBOOK.md`. Zero changes to `app/`, `tests/`, `alembic/`, or `requirements.txt`. |

---

## Blockers

None.

---

## P2 Warnings

### P2-01 — `seed_patient.py` does not support `--dry-run`

`seed_admin.py` has a `--dry-run` flag that validates inputs and prints a preview without touching the database. `seed_patient.py` has no equivalent. For operational consistency, a `--dry-run` mode on `seed_patient.py` would allow ops engineers to validate patient data (dob format, gender, measurement ranges) before committing to the database.

**Impact:** Low. Validation still runs on all inputs before `create_all()` / DB operations. No correctness defect.  
**Recommendation:** Add `--dry-run` to `seed_patient.py` in a follow-up. Not a blocker for this sprint.

---

## Security Assessment

| Check | Result | Notes |
|-------|--------|-------|
| Role boundary enforcement | PASS | Dual enforcement: argparse `choices` + `_validate_role()` / `_ALLOWED_ROLES` |
| Password strength | PASS | Regex enforced unconditionally, including dry-run |
| No hardcoded secrets | PASS | All secrets are environment variables or CLI args |
| No patient data mixed with admin | PASS | `seed_admin.py` cannot create `PatientProfile` records |
| Transaction safety | PASS | `seed_patient.py` rolls back on exception |
| Password exposure | PASS | Password printed as `***` mask in dry-run output; never echoed in clear text |

---

## Code Quality Notes

- Both scripts use `from __future__ import annotations` and clean imports.
- `_validate_password`, `_validate_role`, `_validate_dob`, `_validate_measurement` are properly decomposed helpers.
- `argparse` usage is idiomatic; `--role choices=sorted(_ALLOWED_ROLES)` ensures CLI help matches the programmatic guard.
- Docstrings are accurate and include return-value contracts.
- Error messages are user-actionable (include the actual bad value, the accepted range/choices).
- Runbook cross-references script output field names precisely (`user_id`, `patient_profile_id`) and calls out the common confusion between the two IDs in §7.2.

---

## Summary

PA-01 is a clean, self-contained ops tooling addition. All 10 acceptance criteria pass. The implementation is idempotent, role-restricted, password-policy-enforced, secret-free, and Ruff-clean. No application code was modified. The runbook is thorough and operationally complete.

The single P2 warning (no `--dry-run` on `seed_patient.py`) is a convenience gap, not a correctness or security issue.

**Verdict: APPROVE — ready to merge.**

---

*Review performed by Codex (read-only). No files were modified during review.*
