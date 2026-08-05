# Codex Review — PR #87 Auth Policy Relaxation

**Reviewer:** Codex (read-only)
**Date:** 2026-07-07
**Branch:** `chore/auth-relax-dev-policy`
**Files reviewed:**
- `backend/app/core/config.py`
- `backend/app/api/deps.py`
- `backend/app/core/middleware.py`
- `backend/app/schemas/auth.py`
- `backend/app/schemas/admin.py`
- `backend/app/services/auth.py`
- `backend/app/api/v1/routes/auth.py` (no diff — verified intact)
- `backend/tests/conftest.py`
- `backend/tests/test_mfa_enforcement.py`
- `backend/tests/test_mfa_refresh.py`
- `backend/tests/test_doctor_api.py`
- `backend/tests/test_password_policy.py` (new file)
- `frontend/src/lib/api/auth.ts`
- `frontend/src/app/(auth)/register/page.tsx`
- `frontend/src/app/(patient)/settings/page.tsx`
- `frontend/src/app/admin/(admin-shell)/doctors/CreateDoctorModal.tsx`
- `frontend/src/app/admin/(admin-shell)/settings/page.tsx`
- `frontend/src/lib/api/adminDoctors.ts`
- `frontend/src/__tests__/authPolicy.test.ts` (new file)
- `frontend/src/__tests__/AdminDoctorsPage.test.tsx`
- `frontend/.env.example`
- `.env.example`
- `.env.internal.example`
- `.github/workflows/ci.yml`
- `.github/workflows/azure-staging.yml`
- `.github/workflows/deploy-do.yml`
- `deploy/do/docker-compose.yml`
- `deploy/do/.env.example`
- `docs/QUICKSTART_DEMO.md`

---

VERDICT: **PASS**

**P0 Blockers:** 0
**P1 High:** 1
**P2 Warnings:** 2

---

## Findings

### [P1] Password policy change is global — applies to production path, not dev/staging only

- **Files/lines:**
  - `backend/app/schemas/auth.py` → `RegisterRequest.password: min_length=8→6`, `ChangePasswordRequest.new_password: min_length=8→6`
  - `backend/app/schemas/admin.py` → `DoctorCreateRequest.password: min_length=12→6`
  - `frontend/src/app/(auth)/register/page.tsx`, `frontend/src/app/(patient)/settings/page.tsx`, `frontend/src/app/admin/(admin-shell)/doctors/CreateDoctorModal.tsx`, `frontend/src/app/admin/(admin-shell)/settings/page.tsx`

- **Evidence:**
  The `min_length=6` is a hardcoded schema-level Pydantic constraint, not gated behind any environment variable or feature flag. Unlike MFA enforcement (which reads `Settings.mfa_enforcement_enabled` at runtime and can be flipped), the password minimum length is baked into model schema and applies identically to every deployment environment — dev, staging, AND production. If this branch merges and the DigitalOcean production server (or future Azure production) deploys it, users can set 6-character passwords with no complexity requirements on production.

  The intent described in comments ("build/test phase policy") does not match the implementation: there is no conditional path that would enforce 8+ chars on prod and 6 on staging.

- **Required fix (before production deploy):**
  Introduce an environment-conditional minimum, e.g.:
  ```python
  # In config.py
  password_min_length: int = 6  # MCP_PASSWORD_MIN_LENGTH — set to 8+ in prod

  # In schemas, use a validator or Annotated type that reads from settings,
  # OR create a separate prod schema with min_length=8.
  ```
  Alternatively, document explicitly that this PR is **dev/staging-only** and gate the production deploy workflow to block unless `MCP_PASSWORD_MIN_LENGTH` is set to ≥8 via env var. Currently there is no such gate.

  **Severity rationale:** Healthcare application (PHI). 6-character passwords with no complexity on patient/doctor accounts is below HIPAA minimum reasonable security standards. Acceptable for build phase on isolated dev/staging only.

---

### [P2] `NEXT_PUBLIC_MFA_ENFORCEMENT_ENABLED` not passed as a Docker build-arg in CI/staging workflows → baked as `false` (undefined env)

- **Files/lines:**
  - `.github/workflows/ci.yml` — `Build & push frontend image` step: only passes `NEXT_PUBLIC_API_URL` as build-arg
  - `.github/workflows/azure-staging.yml` — same pattern, only `NEXT_PUBLIC_API_URL`
  - `frontend/Dockerfile` — declares only `ARG NEXT_PUBLIC_API_URL` / `ENV NEXT_PUBLIC_API_URL`

- **Evidence:**
  `NEXT_PUBLIC_*` vars in Next.js are inlined at build time (`next build`). `MFA_ENFORCEMENT_ENABLED` reads `process.env.NEXT_PUBLIC_MFA_ENFORCEMENT_ENABLED === 'true'`. Since the Dockerfile does not declare a `ARG NEXT_PUBLIC_MFA_ENFORCEMENT_ENABLED` and no workflow passes it, the value is `undefined` at build time → `undefined === 'true'` → `false`. This is the **desired behavior for dev/staging** (enforcement off).

  However, the mechanism is implicit (rely on absence of the arg = enforcement off) rather than explicit. If a future production build is added and someone forgets to set this arg to `true`, MFA enforcement will silently remain off on the frontend. The `frontend/.env.example` documents `NEXT_PUBLIC_MFA_ENFORCEMENT_ENABLED=false` (correct for dev/staging), but there is no equivalent `frontend/.env.production.example` documenting the expected production value.

- **Required fix (recommendation):**
  Add a comment in both workflow files acknowledging this intentional omission for staging, AND add a `frontend/.env.production.example` or note in deploy runbook specifying that production builds MUST pass `--build-arg NEXT_PUBLIC_MFA_ENFORCEMENT_ENABLED=true` when MFA enforcement is restored.

---

### [P2] Default `mfa_enforcement_enabled: bool = False` — production risk if env var is absent

- **Files/lines:**
  - `backend/app/core/config.py:mfa_enforcement_enabled: bool = False`
  - `deploy/do/docker-compose.yml` — `MCP_MFA_ENFORCEMENT_ENABLED` is NOT set
  - `.github/workflows/deploy-do.yml` — `MCP_MFA_ENFORCEMENT_ENABLED` is NOT set in SSH deploy script
  - `.github/workflows/ci.yml` — staging `COMMON_ENV` does NOT include `MCP_MFA_ENFORCEMENT_ENABLED`
  - `.github/workflows/azure-staging.yml` — staging `COMMON_ENV` does NOT include `MCP_MFA_ENFORCEMENT_ENABLED`

- **Evidence:**
  `Settings.mfa_enforcement_enabled` defaults to `False`. The DigitalOcean production `docker-compose.yml` and deploy workflow do NOT set `MCP_MFA_ENFORCEMENT_ENABLED=true`. If PR #87 reaches the DigitalOcean production server (requires explicit `[deploy-do]` tag or workflow_dispatch — so not automatic), MFA will silently be off in production. Azure staging deployment also omits this var, but staging-off is the deliberate intent.

  The DO production deployment is opt-in (not automatic on merge), which partially mitigates this risk. The finding is not P0 because the deploy-do workflow is explicitly opt-in and marked LEGACY/DEPRECATED in the comments. However, the lack of `MCP_MFA_ENFORCEMENT_ENABLED=true` in `deploy/do/docker-compose.yml` means a production deploy today would ship with MFA off.

- **Required fix (recommendation):**
  Add `MCP_MFA_ENFORCEMENT_ENABLED: "true"` to `deploy/do/docker-compose.yml` backend environment block. Add it to `deploy/do/.env.example` as well with an appropriate comment. This ensures the production compose config explicitly opts into enforcement rather than relying on the default.

---

## Checklist Results

### Scope Containment

| Check | Result | Evidence |
|-------|--------|----------|
| Flag default is `false` | ✅ PASS | `config.py: mfa_enforcement_enabled: bool = False` |
| No hardcode `True` in production config path | ✅ PASS | No workflow sets it to `true`; default is `false` everywhere |
| Production Azure env vars NOT setting MFA off | ✅ PASS | No `MCP_MFA_ENFORCEMENT_ENABLED` in any workflow — defaults to off (see P2 finding) |
| MFA code still intact — not deleted, only skipped when flag off | ✅ PASS | `routes/auth.py` diff is empty; enroll/verify/TOTP endpoints fully intact at lines 273-310 |
| Enrolled users still must TOTP when flag off | ✅ PASS | `routes/auth.py` login: `if user.mfa_enabled: mfa.verify_second_factor(...)` — unconditional, no flag gate |

### Password Policy

| Check | Result | Evidence |
|-------|--------|----------|
| 6-char min only for dev/staging? | ❌ **P1** | Hardcode in Pydantic schema — applies globally to all environments |
| Password validation centralized? | ✅ PASS | Three consolidated places: `RegisterRequest`, `ChangePasswordRequest`, `DoctorCreateRequest`; no scattered ad-hoc validation beyond frontend UI guards |
| Hardcode global → P1 | ✅ Flagged | See P1 finding above |

### Test Coverage

| Check | Result | Evidence |
|-------|--------|----------|
| Test flag-ON path (MFA enforcement restored) | ✅ PASS | `test_flag_on_internal_admin_blocked_until_mfa_enrolled`, `test_flag_on_require_mfa_gate_rejects_unverified_admin_session`, `test_admin_endpoint_requires_mfa_when_enforcement_enabled` (via `mfa_enforced` fixture) |
| Test voluntary MFA still works when flag off | ✅ PASS | `test_voluntary_enrollment_and_totp_login_still_work` — covers enroll→verify→TOTP login cycle; also asserts `no_code` login returns 401 |
| Test 6-char password accepted + 5-char rejected | ✅ PASS | `test_register_accepts_six_char_numeric_password`, `test_register_rejects_five_char_password`, `test_five_char_password_returns_422`, `test_change_password_accepts_six_chars_and_rejects_five` |

### Risk Assessment

| Check | Result | Evidence |
|-------|--------|----------|
| Env var missing in prod → default `false` = MFA off | ⚠️ P2 | `deploy/do/docker-compose.yml` and both ACA workflows omit `MCP_MFA_ENFORCEMENT_ENABLED` |

---

## Scope Containment Verdict

**Is the MFA-off policy guaranteed to NOT affect production?**

**CONDITIONAL** — with two qualifications:

1. **MFA bypass is safe** for staging/dev: The flag architecture is correct. `require_mfa` in `deps.py` is a no-op when `mfa_enforcement_enabled=False`. `MfaEnrollmentMiddleware` in `middleware.py` passes through when the flag is off. `issue_tokens` in `services/auth.py` skips the `enrollment_required` claim when flag is off. Enrolled users must still TOTP at login unconditionally (flag does not affect `routes/auth.py` login handler). All MFA APIs remain fully intact.

2. **Production gap**: The DigitalOcean production `deploy/do/docker-compose.yml` does NOT set `MCP_MFA_ENFORCEMENT_ENABLED=true`. If a production deploy (opt-in `[deploy-do]` tag) happens after this PR merges, production will have MFA off. This is mitigated by (a) the opt-in deploy gate, (b) DO being marked LEGACY/DEPRECATED. But the production compose config should be hardened.

3. **Password minimum is NOT contained**: The 6-char minimum applies to all environments unconditionally. This is a healthcare application; if production is deployed with this branch, patients and doctors can set 6-character passwords.

---

## Recommended Action

**SAFE_TO_MERGE** for dev/staging purposes with the following conditions:

1. **BLOCK production deploy** (`[deploy-do]` tag or workflow_dispatch on `deploy-do.yml`) until `deploy/do/docker-compose.yml` explicitly sets `MCP_MFA_ENFORCEMENT_ENABLED=true`.

2. **Acknowledge P1 password policy** before any production deploy: either gate the min_length behind an env/config variable, or document explicitly that production deploy requires `MCP_PASSWORD_MIN_LENGTH=8` (or equivalent) to be set.

3. The MFA architecture, flag wiring, test coverage for flag-on/off/voluntary paths are all sound. The decision to default off is deliberate and acceptable for the build phase.

**Summary:** PR #87 is well-structured and the MFA flag mechanism is correctly implemented. The P1 password policy change is the only substantive gap — the "dev/staging only" intent in the comments does not match the global enforcement in code. Voluntary MFA is preserved. The `mfa_enforced` test fixture correctly validates that the flag can restore enforcement. Safe to merge to `main`; block production deploy until P1 and P2 notes above are addressed.

---

## OpenClaw Disposition — 2026-07-07

**DECISION:** HOLD — do not merge until P1 resolved.

**Rationale:**
- MFA flag architecture: CLEAN — safe for staging.
- P1 password policy: GLOBAL hardcode (6-char min applies to all envs including production) — requires fix before merge.
- P2-a: Frontend MFA build-arg implicit (acceptable for staging, needs runbook doc).
- P2-b: DO docker-compose missing `MCP_MFA_ENFORCEMENT_ENABLED=true` (DO is DEPRECATED but compose must be hardened before any prod deploy).

**Required before merge:**
1. [P1] Gate `min_length` on `MCP_PASSWORD_MIN_LENGTH` config var (default 6 dev, 8 prod) — OR document explicit production deploy block in workflow.
2. [P2] Add `MCP_MFA_ENFORCEMENT_ENABLED: "true"` to `deploy/do/docker-compose.yml`.
3. [P2] Add `frontend/.env.production.example` documenting required production values.

**Assigned to:** Claude Code (TASK-03-FIX)
**Blocked on merge:** YES — pending P1 fix + Codex re-review.
