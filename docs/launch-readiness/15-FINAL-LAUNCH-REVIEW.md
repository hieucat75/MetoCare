# 15 — Final Launch-Readiness Review & Recommendation

**Date:** 2026-08-03 · **Branch:** `feat/patient-platform-journey2` (unmerged to `main`) · **Program Lead** consolidating five independent, fresh-context audits (security, privacy, clinical safety, production/DB, SRE-observability/mobile) that inspected source directly.

**Baseline verified this session:** single Alembic head `j4_m8_consent_versioning`; full backend suite **green (exit 0)**; account/erasure subset green incl. new regression. Staging state (revision `ca-metocare-backend--d25f109f`, run `30797337153`) is DOC-ONLY pending live Azure re-verification.

---

## 1. Recommendation

> **CONTROLLED PILOT — READY (conditional), synthetic-data on staging.**
> **PUBLIC BETA / PRODUCTION — NOT READY** (enumerated external-credential + infra blockers).

The five-journey platform is **materially stronger than a typical launch candidate**. Independent adversarial review found **zero clinical P0**, **zero security P0**, and **zero privacy P0** in application code. Core safety invariants hold under source inspection (no-auto-canonical OCR, confirmed-data-only AI, enforced output safety, stopped-schedule-no-remind, consistent BOLA, signed blob tokens, no cross-patient dedup oracle, verified secrets fail-loud guard).

The two items labelled **P0 are infrastructure/deploy-config**, not app-code defects, and are **owner-gated** (project guardrail: do not modify Azure infra workflows). Neither blocks a **synthetic-data** controlled pilot on staging; both **do** block public beta/production. A short punch-list of code P1s remains — the isolated ones are fixed this session with regression tests; the rest are infra/credential/product-decision items documented with exact resolutions.

## 2. Per-workstream verdict

| WS | Area | Verdict |
|---|---|---|
| 1 | Production readiness | 🟡 Ready for pilot; storage durability + prod boot config block beta (see P0s) |
| 2 | Security | ✅ No P0; maturity above launch norm; 2 P1 (1 infra, 1 code-fixable) |
| 3 | Privacy/consent | ✅ AI consent gate production-grade; 2 P1 (F2 fixed; F1 decision) |
| 4 | Clinical safety | ✅ **Zero P0**; invariants hold; 2 mitigated P1 |
| 5 | Observability | 🟡 Strong PHI-safe log foundation; no aggregation/crash-capture (P1s → plan) |
| 6 | Analytics | ⏳ Event catalog is design-level; instrumentation is beta-scope |
| 7 | AI safety | ✅ Enforcement real+buffered; detector-coverage P1 (PS-1) |
| 8 | Backup/restore | 🟡 Postgres PITR gate solid; object-storage backup missing (tied to P0) |
| 9 | Performance/capacity | ⏳ Est. only; pilot ≤50 users well within capacity (10) |
| 10 | Cost | ✅ ≤$80/mo at 50-user pilot; AI is the abuse-sensitive lever (10) |
| 11 | Mobile distribution | 🟡 Android internal-APK real + prod-gates verified; iOS not submittable; signing/push = creds |
| 12 | Pilot ops | ✅ Runbook authored (12) |
| 13 | Incident response | ⏳ Severity model defined (13) |
| 14 | Feature rollout | ✅ Authored (14); QA/relaxed-auth fail-loud in prod verified |

## 3. Consolidated confirmed P0/P1 register + disposition

### P0 (both INFRA/DEPLOY — owner-gated; NOT edited per Azure-workflow guardrail)
| ID | Finding | Disposition |
|---|---|---|
| **PROD-F1** | `MCP_STORAGE_MODE=local` in staging+prod → medical-document blobs on **ephemeral container disk**, no volume/backup; any redeploy/scale-to-zero loses all documents. Azure Blob adapter implemented but inert. | **Blocks controlled-pilot-with-REAL-data & beta.** Tolerable for **synthetic-only** pilot with documented caveat (re-seed after redeploy). **Owner action:** set `MCP_STORAGE_MODE=azure` + connection string + Blob soft-delete/PITR before any real PHI. |
| **PROD-F2 / SEC-F1** | Prod deploy workflow omits `MCP_MFA_ENFORCEMENT_ENABLED=true`; prod code unconditionally refuses relaxed-auth boot → **production container crash-loops**. | **Blocks production only** (prod not in this program's scope). **Owner action:** add the env var + dry-run to healthy before any prod cutover. |

### P1 — CODE-FIXABLE
| ID | Finding | Status |
|---|---|---|
| **PRIV-F2** | Account deletion never erased storage blobs (GDPR erasure incomplete). | ✅ **FIXED this session** — `delete_account` now returns all backing keys (medical quarantine/accepted, page images, lab uploads); route erases them post-commit, best-effort, idempotent. Regression test added; 6/6 account tests green. |
| **SEC-F2** | Access token outlives account block/self-delete (≤15 min) — `current_user()` doesn't re-check `is_active`. | ⏳ **PLANNED** — add `is_active` check (or short-TTL revocation set) in `app/api/deps.py`. Bounded to token TTL. |
| **PRIV-F1** | `documents` consent category is patient-facing but enforced nowhere (revoking is a no-op). Not a runtime PHI leak (document-derived data is confirmed before reaching AI), but **misleading consent**. | ⏳ **DECISION/FIX** — either enforce `documents` at the OCR pipeline entry (fail-closed) or remove the category from the UI. Recommend enforce. |
| **CLIN PS-1** | Meto output-safety **enforcement is correct** (content replaced, stream buffered) but the forbidden-phrase **detector is narrow** (short VN literal list); unlisted phrasings/English could pass. | ⏳ **PLANNED** — broaden `ai/prompt/safety.py` patterns + keep system-prompt constraint. |
| **CLIN PS-2** | Prescription per-dose `quantity` ("2 viên") parsed but dropped at promotion → understated dose. Mitigated by mandatory patient confirm. | ⏳ **PLANNED** — promote `quantity` into dose/note in `mdi/promoters.py`. |
| **WS5-F2** | Mobile has **no crash/error telemetry** — uncaught JS error = silent white screen. | ⏳ **PLANNED** — root `ErrorBoundary` + `ErrorUtils.setGlobalHandler` → monitor sink. |
| **WS11-F3** | Android manifest requests `RECORD_AUDIO` + `SYSTEM_ALERT_WINDOW` with no feature justification. | ⏳ **PLANNED** — strip both from app-level manifest. |

### P1 — INFRA / CREDENTIAL / OPS (document; not app-code)
| ID | Finding | Resolution owner-side |
|---|---|---|
| PROD-F3 / SEC-F8 | In-memory rate-limit/lockout safe at 1 replica only. | Switch `MCP_RATELIMIT_BACKEND=redis` before scaling >1 replica (adapter exists). |
| PROD-F4 | Auth env (`MFA_ENFORCEMENT`/`ALLOW_RELAXED`) set outside version control (config drift). | Codify in workflow/IaC. |
| PROD-F5 | `audit_retention_*` declared but no enforcement job. | Schedule purge job (ACA cron) — query in `08`. |
| PROD-F6 | No orphan reconciliation (DB rows vs blobs). | Schedule `data_integrity_cleanup.py`; the PRIV-F2 fix logs failed blob deletes for exactly this sweep. |
| WS5-F1 | Metrics process-local, never scraped/aggregated. | Ship stdout JSON → Log Analytics baseline; add scrape/push when needed. |
| WS5-F3 | No exception aggregation either tier. | `Monitor` provider abstraction + local adapter now; Sentry DSN = credential gap. |
| WS11-F1 | Local release build is debug-signed. | Google Play upload key (credential); EAS cloud build injects managed keystore. |
| WS11-F2 | iOS not submittable (simulator-only EAS, no privacy manifest, no signing). | Apple signing identity (credential). |
| WS12-F1 | No device push wiring; reminders backend-only. | APNs/FCM keys (credential) + `expo-notifications` wiring. |

### Selected P2 (opportunistic; none blocks pilot)
DB `pool_pre_ping=True` (WS5-F5); `/info` unauth disclosure (WS5-F6/SEC-F4); register enumeration 409 (SEC-F3); exception text in log `message` (WS5-F7); MDI page-count guard bypass on malformed PDF (SEC-F6); SSRF DNS-rebinding TOCTOU (SEC-F5); JWT no iss/aud (SEC-F7); general-report `_MED_RE` re-types findings as meds (CLIN PS-3); doctor summary lacks provenance badge (CLIN PS-4); no account-recovery flow (SEC-F9).

## 4. What was fixed this session (code)
- **PRIV-F2 GDPR blob erasure** — `app/services/account.py` (pure key collection across MedicalDocument/DocumentPage/LabDocument), `app/api/v1/routes/account.py` (post-commit best-effort erase), regression test `tests/test_account_export_delete.py::test_delete_returns_object_storage_keys_for_erasure`. Full account suite 6/6 green.

## 5. Conditions to declare the controlled (synthetic) pilot GO
1. Close remaining code P1s: SEC-F2, PRIV-F1, CLIN PS-1, CLIN PS-2, WS5-F2, WS11-F3 (isolated, ~1 focused session).
2. Owner-accept the documented limitations (synthetic-only data; debug-signed internal APK; in-app reminders; local OCR; mock payment; MFA relaxed on staging).
3. Wire minimal crash/error visibility (WS5-F2 mobile + `Monitor` log adapter) — pilot needs incident detection.
4. Point the pilot APK at the staging HTTPS URL (rebuild) and confirm live staging `/info` (flags, migration head).

## 6. Conditions for PUBLIC BETA (all currently open)
Object-storage durability (PROD-F1), production MFA boot (PROD-F2), Redis rate-limit (PROD-F3), retention+orphan jobs (PROD-F5/F6), external credentials (Apple/Google signing, APNs/FCM, real secrets, optional Azure DI+PHI-authorization), backups verified (08), monitoring provisioned (04), cost/perf validated (09/10).

**Production deployment remains NOT authorized by this program.**
