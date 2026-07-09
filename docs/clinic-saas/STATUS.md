# Clinic SaaS — Phase Status

## Phase C0 (multi-tenant foundation): **MERGED — DORMANT — NOT YET ENABLED**

- **Merged to `main`:** 2026-07-08, commit `819466d60dcfab40d1933c2dec2c13caa0825811` (PR #96, squash merge).
- **Feature flag:** `CLINIC_SAAS` — default `False` (fail-closed) in `backend/app/core/feature_flags.py`. Confirmed absent from every CI workflow, deploy config, and env file repo-wide — no environment (dev/staging/production) sets it to `true`. Every new Clinic SaaS route 503s until this flag is explicitly turned on somewhere.
- **Schema:** 7 new tables + 2 additive ALTERs (`clinics`, `audit_logs`) are live on `main`'s migration chain (single Alembic head: `c0_m9_audit_log_clinic_id`). No data has been created in any of the new tables — the module is schema-present but functionally inert until the flag is enabled.
- **Security review:** Codex independent review — PASS (0 P0/P1/P2) after 3 findings (invitation-accept race, unscoped `branch_ids`, RBAC docstring/code mismatch) were found and fixed. Full record: `docs/CODEX_REVIEW_PR96_CLINIC_SAAS.md`.
- **Test coverage:** 2656 backend tests (0 failures), 507 frontend tests (0 failures) as of merge.

## Rollback caution

**Do not run `alembic downgrade` past `c0_m1_clinic_extend_columns` once real Clinic SaaS data exists (any clinic/membership/branch/etc. row), without a backup and an explicit decision to accept data loss.** The downgrade path is destructive by nature (drops the 7 new tables and the `clinics`/`audit_logs` additive columns) — safe and reversible only while the tables remain empty, which is the current state.

## Next steps (not started)

- Enabling `CLINIC_SAAS` in any environment (explicit decision, not yet made).
- Phase C1 (Clinic Operations MVP: services/patients/appointments/checkin/queue/consultation/notes/billing/dashboard) — planning only so far, not started.
