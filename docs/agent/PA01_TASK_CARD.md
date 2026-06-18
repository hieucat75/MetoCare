# PA-01 — Seed Admin Script + Pilot Onboarding Runbook

| Field | Value |
|-------|-------|
| **Task ID** | PA-01 |
| **Branch** | `feature/pa01-seed-admin` |
| **Base commit** | `f2438db` |
| **Owner** | Claude Code (subagent) |
| **Created** | 2026-06-18 |
| **Status** | READY FOR CODEX REVIEW |

---

## Context

MetoCare pilot deploy is live. `POST /auth/register` enforces PATIENT-only registration — admin accounts cannot be created via the public API. Operational tooling is needed to:

1. Seed `super_admin` / `internal_admin` accounts directly into the database.
2. Seed complete patient records (User + PatientProfile) for pilot participants.
3. Document the full pilot onboarding flow for the ops team.

---

## Scope

### Deliverables

| File | Type | Purpose |
|------|------|---------|
| `backend/scripts/seed_admin.py` | NEW | Idempotent CLI to create admin accounts |
| `backend/scripts/seed_patient.py` | NEW | Idempotent CLI to create patient + profile |
| `docs/ops/PILOT_ONBOARDING_RUNBOOK.md` | NEW | Structured ops runbook for pilot onboarding |
| `docs/agent/PA01_TASK_CARD.md` | NEW | This task card |
| `docs/agent/PA01_IMPLEMENTATION_REPORT.md` | NEW | Post-implementation report |

### Explicitly Excluded

- No changes to models, migrations, routes, or tests.
- `backend/scripts/seed_demo.py` — not modified.

---

## Acceptance Criteria

- [ ] `seed_admin.py --help` exits 0 with usage text
- [ ] `seed_admin.py --dry-run` validates password + prints plan, no DB write
- [ ] `seed_admin.py` creates account and prints user_id on success
- [ ] `seed_admin.py` prints SKIP on re-run with same email (idempotent)
- [ ] `seed_admin.py` rejects weak passwords with descriptive error
- [ ] `seed_admin.py` rejects disallowed roles (only super_admin, internal_admin)
- [ ] `seed_patient.py --help` exits 0 with usage text
- [ ] `seed_patient.py` creates User + PatientProfile in single transaction
- [ ] `seed_patient.py` prints user_id and patient_profile_id on success
- [ ] `seed_patient.py` prints SKIP on re-run with same email (idempotent)
- [ ] `PILOT_ONBOARDING_RUNBOOK.md` covers all 7 required sections
- [ ] `ruff check scripts/` passes with no errors

---

## Notes

- Both scripts use `MCP_DATABASE_URL` env var (compatible with existing `config.py`).
- Works against SQLite (dev) and PostgreSQL (production) without code changes.
- Password regex requires: ≥12 chars, upper, lower, digit, special character.
- `seed_patient.py` uses `db.flush()` before creating PatientProfile so `user.id` is available within the same transaction.
- Scripts do NOT call `auth.register()` for admin seeding (that function enforces PATIENT role for PatientProfile creation). Instead, they construct `User` objects directly with the correct role.
