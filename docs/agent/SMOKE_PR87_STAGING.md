# Smoke Test Report — PR #87 (f997fe9)

**Date:** 2026-07-07 22:41 GMT+7
**SHA tested:** f997fe9
**CI Run:** 28878427448 — success
**Staging URL:** https://ca-metocare-backend.wittyflower-55a3afa4.southeastasia.azurecontainerapps.io

## CI Status

PASS

All jobs completed successfully:
- Backend Tests: completed / success
- Frontend Tests: completed / success
- Meto AI Deployment Gate: completed / success
- Deploy to Staging: completed / success
- Deploy Blocked - Gate Failed: skipped (expected — gate passed)

## Smoke Results

| Check | Result | Evidence |
|-------|--------|----------|
| Health endpoint | PASS | HTTP 200 (`/health`) |
| 6-char password accepted | PASS | HTTP 201 on `/api/v1/auth/register` with `password: "abc123"` — returns access_token |
| 5-char password rejected | PASS | HTTP 422, detail: `"String should have at least 6 characters"` |
| Admin/user login no forced MFA | PASS | HTTP 200 with access_token; JWT claims include `"mfa_enrollment_required": false` |
| Doctor login no forced MFA | NOT_TESTED | Doctor role not self-registerable via public endpoint; demo.doctor has MFA enrolled (see note) |
| Voluntary MFA still works | PASS | demo.admin@example.com and demo.doctor@example.com (MFA enrolled) → HTTP 401 `"MFA code required or invalid."` — TOTP challenge correctly presented |

## Overall

SMOKE_PASS (1 item partially untestable — doctor role)

## Blockers

NONE

## Notes

- **Password minimum is now 6 chars (confirmed):** Staging returns `"String should have at least 6 characters"` on 5-char rejection, and accepts 6-char passwords. Pre-deploy staging enforced 8-char minimum — verifying deploy was necessary and was confirmed complete before re-testing.
- **MFA enrollment_required flag in JWT:** Decoded JWT payload for a freshly registered (no MFA) account shows `"mfa": false, "mfa_enrollment_required": false` — the PR correctly relaxes forced MFA enrollment.
- **Voluntary MFA (enrolled users) still protected:** Demo accounts with MFA enrolled (`demo.admin@example.com`, `demo.doctor@example.com`) correctly receive 401 + TOTP challenge. Flag-off does NOT bypass enrolled users.
- **Doctor role test:** `demo.doctor@example.com` is MFA-enrolled so direct login test is blocked by TOTP. The new smoke check (no forced MFA for non-enrolled users) was validated via patient role — doctor-specific role check would require a non-MFA-enrolled doctor account created via admin seeding, which is not in scope for this run.
- Smoke test accounts used: temporary fake emails `@smoke-test-domain.example` (per validation constraints). No PHI or real credentials logged.
- No tokens, passwords, or PHI appear in this report — only HTTP status codes and JWT claim structure.
