# Production Readiness Checklist — MetoCare

**Created:** 2026-07-07
**Owner:** PTH
**Related:** `docs/PROD_HARDENING_AUTH.md`

---

## Deployment Targets

| Target | Status | Notes |
|--------|--------|-------|
| Azure Container Apps (ACA) | ✅ ACTIVE | Only supported production target |
| DigitalOcean VPS (146.190.83.230) | ❌ DEPRECATED | Disabled 2026-06-28. Workflow disabled 2026-07-07. |

## DigitalOcean — Confirmed Disabled

- `deploy-do.yml` has `if: false` on all jobs — cannot run
- `workflow_dispatch` trigger retained but disabled
- No DNS, no SSL, no frontend ever deployed on DO
- DO VPS migration is 8 versions behind ACA staging head
- DO must NOT be re-enabled without PTH approval and full production hardening (see `docs/PROD_HARDENING_AUTH.md`)

---

## Auth Hardening — Pre-Production Checklist

The following must be completed before any production deployment (see `docs/PROD_HARDENING_AUTH.md`):

- [ ] Item A: `MCP_PASSWORD_MIN_LENGTH` ≥ 10 set in production env (config-driven, not hardcoded)
- [ ] Item B: `MCP_MFA_ENFORCEMENT_ENABLED=true` set in production env
- [ ] Item B: `NEXT_PUBLIC_MFA_ENFORCEMENT_ENABLED=true` as frontend build-arg for production
- [ ] Item C: Preflight guard (`scripts/preflight_prod.py`) passes on production deploy
- [ ] Item C: `MCP_FEATURE_CONSENT_GATE=true` in production env
- [ ] Item C: `MCP_FEATURE_DOCTOR_REVIEW_GATE=true` in production env
- [ ] Item D: `deploy-do.yml` confirmed disabled (✅ done 2026-07-07)
- [ ] Staging values confirmed different from production values
- [ ] Frontend production build-args confirmed
- [ ] Codex review PASS on all hardening changes
- [ ] PTH approval before production deploy

---

## CI/CD Gates

- Azure staging: automatic on merge to `main`
- Azure production: manual trigger + PTH approval required
- DigitalOcean: DISABLED (see above)
