# Codex Review — PR #96 feat(clinic): add multi-tenant SaaS foundation

**Reviewer:** Codex (read-only, `codex exec --sandbox read-only`)
**Date:** 2026-07-08
**Branch:** feat/clinic-saas-c0-foundation
**Base:** main

---

## Round 1 — Initial security review

**Scope:** tenant isolation, cross-clinic IDOR/BOLA, membership lifecycle, invitation abuse, PHI leakage, audit-log isolation, `CLINIC_SAAS=OFF` behavior.

**VERDICT: FAIL**

P0: 0 · P1: 2 · P2: 1

| Check | Result | Evidence |
|---|---|---|
| 1. Tenant isolation | PASS WITH CONCERNS | `get_tenant_context` resolves active memberships only and validates `X-Clinic-Id` against them (`deps_tenant.py:77,97`); routes compare path clinic to resolved tenant (`clinics.py:155`, `clinic_branches.py:54`, `clinic_members.py:59`, `clinic_services.py:44`, `clinic_subscriptions.py:51`). Concern: `branch_ids` accepted unscoped (see P1 #2). |
| 2. Cross-clinic IDOR/BOLA | PASS WITH CONCERNS | Resource lookups scoped by clinic_id throughout (`clinic_branch.py:62`, `clinic_membership.py:159,262`, `clinic_service_catalog.py:51`). Same `branch_ids` concern. |
| 3. Membership lifecycle | PASS | Only ACTIVE memberships resolve tenant context; last-owner invariant enforced (`clinic_membership.py:308`); role mutation is Owner/Admin-gated. P2: `assert_clinic_membership`'s admin bypass included `MEDICAL_REVIEWER` despite its docstring, though unused by any current route. |
| 4. Invitation abuse | **FAIL** | Strong token generation/hashing; raw token returned once; revoked/expired rejected. **P1: `accept_invitation` was not concurrency-safe** — plain SELECT-then-mutate on a single-use token. |
| 5. PHI leakage | PASS | New schemas expose clinic/membership/service/subscription metadata only; no `PatientProfile` encrypted fields anywhere; `ClinicPatientRelationship` stores ids/code only. |
| 6. Audit-log isolation | PASS | `audit_logs.clinic_id` write-only in this PR; platform override requires role + explicit `X-Clinic-Id`, audits before handler runs. |
| 7. `CLINIC_SAAS=OFF` behavior | PASS | Flag defaults false; every new router gated by `require_clinic_saas_enabled`; controlled 503; no bypass path found. |

**Findings:**
1. **P1** — `accept_invitation` race: two concurrent callers could both pass the PENDING check before either commits.
2. **P1** — `branch_ids` submitted to `create_invitation`/`update_membership`/`create_service`/`update_service` persisted with no check they belong to the tenant clinic.
3. **P2** — `assert_clinic_membership` bypassed for `_is_admin` (includes `MEDICAL_REVIEWER`), contradicting its own docstring (INTERNAL_ADMIN/SUPER_ADMIN only).

---

## Fixes applied (verified by Claude Code against source before and after Codex's re-review)

| Commit | Fix |
|---|---|
| `431fa70` | `assert_clinic_membership` now uses `_is_write_admin` (INTERNAL_ADMIN/SUPER_ADMIN only), matching its documented intent. |
| `e1d2a7e` | `accept_invitation` uses an atomic conditional `UPDATE ... WHERE status='pending'` (checks `rowcount`) instead of SELECT-then-mutate. Added `assert_branch_ids_belong_to_clinic` and wired into `create_invitation`/`update_membership`. |
| `912d2f5` | Same `branch_ids` validation wired into `create_service`/`update_service`; `clinic_services.py` route now translates the resulting error to a controlled 400 (previously had no domain-error handling at all). |
| `fb84cec` | Regression tests locking in all three fixes. |

---

## Round 2 — Follow-up verification review

**Scope:** re-verify each of the 3 findings against the actual diff, check for fixes that are cosmetic-only or that introduce new bugs.

**VERDICT: PASS**

P0: 0 · P1: 0 · P2: 0

1. **P1 invitation race: RESOLVED** — `clinic_membership.py:211` performs the atomic conditional UPDATE, checks `rowcount != 1` (line 219), refreshes the row (line 221) before building the membership from `invitation.clinic_id`/`roles`/`branch_ids`/`invited_by_user_id` (lines 223-245); refresh does not lose those values.
2. **P1 branch_ids tenant scoping: RESOLVED** — `assert_branch_ids_belong_to_clinic` (`clinic_branch.py:62`) is called from all 4 sites (`create_invitation`, `update_membership`, `create_service`, `update_service`); every call site translates the resulting error to a controlled HTTP response (409 for membership/invitation paths, 400 for the service-catalog path, which previously had no error handling at all).
3. **P2 reviewer bypass: RESOLVED** — `rbac.py:145` now uses `_is_write_admin` (INTERNAL_ADMIN/SUPER_ADMIN only); `_is_admin` (still includes MEDICAL_REVIEWER) remains available and correctly used elsewhere for read-only bypass; no current route depended on the old broader bypass on this specific function.

**New findings: none.**

---

## Overall disposition

**PASS.** All P0/P1/P2 findings from the initial review are resolved and independently re-confirmed by Codex against the fixed code. No new issues introduced by the fixes. Combined with Claude Code's own direct code verification (not just accepting Codex's report), this PR is clear on the security dimensions reviewed here.
