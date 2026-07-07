# Production Auth Hardening — MetoCare

**Status:** OPEN — not started
**Created:** 2026-07-07
**Triggered by:** PR #87 merge (policy(auth): relax MFA and password requirements for build phase / `f997fe9`)
**Owner:** Claude Code (executor) → Codex (reviewer) → OpenClaw (merge gate)
**Codex review required:** YES — auth, password policy, production deploy gate (§6 mandatory)
**PTH approval required:** YES — before any production deploy

---

## Context

PR #87 introduced a deliberately relaxed auth policy for the build/staging phase:
- MFA enforcement OFF by default (`MCP_MFA_ENFORCEMENT_ENABLED=false`)
- Password minimum 6 chars (no complexity)

These defaults are acceptable for dev/staging. They are NOT acceptable for production.
This ticket tracks the hardening work required before any production deployment.

---

## Scope — 4 items (A–D)

### A. Configurable Password Policy

**Problem:** `min_length=6` is hardcoded in Pydantic schemas — applies identically to all environments.

**Required:**
- Add `MCP_PASSWORD_MIN_LENGTH: int = 6` to `backend/app/core/config.py` (Settings).
- Default 6 for dev/staging. Production deployment MUST set `MCP_PASSWORD_MIN_LENGTH=10` (minimum) or `12` (recommended).
- One shared config-driven validator used by:
  - `RegisterRequest.password`
  - `ChangePasswordRequest.new_password`
  - `ResetPasswordRequest.new_password` (if exists)
  - `DoctorCreateRequest.password`
- No duplicated hardcoded lengths anywhere else.
- Frontend: read policy from `NEXT_PUBLIC_PASSWORD_MIN_LENGTH` build arg OR from a public config endpoint (`GET /config/policy` — no auth required). Must not hardcode `6` or `8` independently.
- Tests: flag-driven validator tests for dev default (6) and prod override (10+).

### B. Production MFA Enforcement

**Problem:** `MCP_MFA_ENFORCEMENT_ENABLED` absent from all production deployment definitions → defaults `false`.

**Required:**
- `deploy/do/docker-compose.yml` backend env block: add `MCP_MFA_ENFORCEMENT_ENABLED: "true"`
- `deploy/do/.env.example`: add with comment `# Production: must be true`
- Future Azure production workflow (when created): MUST pass `MCP_MFA_ENFORCEMENT_ENABLED=true` as Container App env var.
- Frontend: `NEXT_PUBLIC_MFA_ENFORCEMENT_ENABLED=true` as Dockerfile build-arg for production builds.
- Add `frontend/.env.production.example` documenting all required production public env vars.

### C. Production Deployment Preflight Guard

**Problem:** No automated gate prevents deploying with insecure defaults to production.

**Required:**
- Add a preflight script `scripts/preflight_prod.py` (or `scripts/preflight_prod.sh`) that:
  - Reads: `MCP_MFA_ENFORCEMENT_ENABLED`, `MCP_PASSWORD_MIN_LENGTH`, `MCP_FEATURE_CONSENT_GATE`, `MCP_FEATURE_DOCTOR_REVIEW_GATE`
  - Fails (exit 1) if ANY of:
    - `MFA_ENFORCEMENT_ENABLED != true`
    - `PASSWORD_MIN_LENGTH < 10`
    - `CONSENT_GATE != true`
    - `DOCTOR_REVIEW_GATE != true`
  - Prints ONLY config names and pass/fail status — NEVER values of secrets, tokens, or keys.
- Integrate into production deploy workflow as a mandatory first step (before image build/push).
- This guard MUST NOT run on staging (gate by `ENVIRONMENT=production` check).

### D. Legacy DigitalOcean Cleanup

**Problem:** `deploy/do/` directory and `.github/workflows/deploy-do.yml` present an apparently usable production path with relaxed defaults.

**Decision (2026-07-07):** Option 1 — Disable workflow.

**Actions taken:**
- `.github/workflows/deploy-do.yml`: all jobs guarded with `if: false`
- `workflow_dispatch` inputs updated with explicit DISABLED notice
- Top-of-file deprecated comment block added
- Regression guard job added
- File retained as historical reference; will be deleted in next cleanup cycle
- PR: `chore/disable-do-deployment`

---

## Documentation Required

- Update PR #87 description / docs to label current policy:
  > "Temporary relaxed authentication policy for development and staging. NOT for production use."
- Add to `docs/ops/PRODUCTION_READINESS_CHECKLIST.md`:
  - [ ] `MCP_MFA_ENFORCEMENT_ENABLED=true` set in production env
  - [ ] `MCP_PASSWORD_MIN_LENGTH` ≥ 10 set in production env
  - [ ] `MCP_FEATURE_CONSENT_GATE=true`
  - [ ] `MCP_FEATURE_DOCTOR_REVIEW_GATE=true`
  - [ ] Preflight guard passes on production deploy
  - [ ] Staging values confirmed different from production values
  - [ ] Frontend production build-args confirmed

---

## Staging Smoke Test (Post PR #87 Merge)

After CI deploys to staging from `f997fe9`:

- [ ] Admin login without forced MFA → dashboard accessible
- [ ] Doctor login without forced MFA → portal accessible
- [ ] CLINIC_ADMIN login without forced MFA → accessible
- [ ] MEDICAL_REVIEWER login without forced MFA → accessible
- [ ] Register with 6-char password → accepted (200/201)
- [ ] Register with 5-char password → rejected (422)
- [ ] Voluntary MFA enroll → TOTP required at next login (flag-off does not bypass enrolled users)
- [ ] Admin-created doctor with 6-char password → immediate login works

**Assigned to:** Claude Code (TASK-03-SMOKE) — after CI confirms staging deploy green.

---

## Implementation Order

1. Staging smoke (TASK-03-SMOKE) — verify PR #87 merged state on staging NOW.
2. Item A (password policy) — backend first, then frontend.
3. Item B (MFA enforcement) — update DO compose + frontend .env.production.example.
4. Item C (preflight guard) — new script + workflow integration.
5. Item D (DO cleanup) — pending PTH decision on Option 1 vs 2.
6. Codex review all changes (single PR `hardening/prod-auth-gates`).
7. PTH approval before any production deploy.

---

## Merge Conditions (future PR `hardening/prod-auth-gates`)

- [ ] Claude Code implementation complete (A+B+C+D)
- [ ] Codex PASS (mandatory — auth + production deploy gate = §6 critical)
- [ ] All tests green (backend pytest + ruff + frontend typecheck + next build)
- [ ] PTH approval
- [ ] Staging smoke after merge

---

## DO NOT

- Do not deploy to production before this ticket is resolved.
- Do not set `MCP_MFA_ENFORCEMENT_ENABLED=true` on staging (breaks build-phase intent).
- Do not remove MFA code (only enforcement is relaxed).
- Do not hardcode new min lengths — must flow through config.
