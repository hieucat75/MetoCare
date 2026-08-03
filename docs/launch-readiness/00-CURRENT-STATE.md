# 00 — Current-State Verification (Phase 0)

**Date:** 2026-08-03 · **Verified by:** Launch-Readiness Program Lead (direct repo inspection)
**Branch:** `feat/patient-platform-journey2` · **Purpose:** Ground truth for the launch-readiness matrix. Every line below is verified against the repo/tooling this session, or explicitly marked `DOC-ONLY` (asserted by a prior evidence doc, pending live re-verification with credentials).

---

## 1. Repository & branch state (VERIFIED)

| Item | Value | Source |
|---|---|---|
| Current branch | `feat/patient-platform-journey2` | `git branch --show-current` |
| Divergence from `main` | **+35 commits ahead, 0 behind** — all patient-platform work is **unmerged to `main`** | `git rev-list --left-right --count main...HEAD` |
| Tip commit | `1116a1e docs(pilot): ANDROID INTERNAL PILOT READY` | `git log` |
| Working tree | 23 uncommitted entries (mostly untracked `docs/**` review artifacts + `.gstack/`); **no tracked source modified** at session start | `git status -s` |
| Alembic heads | **single head** `j4_m8_consent_versioning` | `alembic heads` |
| Alembic base count | 1 base (no split lineage) | grep `down_revision = None` |

**Implication:** `main` does **not** contain any of the 5-journey patient platform. Merge-to-`main` is a deliberate, owner-gated step (main→staging auto-deploy is the only production-adjacent path). Nothing here changes that.

## 2. Deployed staging (DOC-ONLY — needs live re-verification if Azure creds available)

| Item | Value | Source |
|---|---|---|
| Backend | Azure Container Apps, revision `ca-metocare-backend--d25f109f` (`RunningAtMaxScale`) | `ANDROID-PILOT-RC.md §11` |
| Migration version live | `j4_m8_consent_versioning` (matches repo single head) | pilot doc `/info` probe |
| Env | `env=staging`, `consent_gate=true` | pilot doc |
| Deploy run | `azure-staging.yml` workflow_dispatch run `30797337153` — success | pilot doc |
| Staging auth posture | `MCP_ALLOW_RELAXED_AUTH=true` set on staging (env-scoped, logged); prod always fails loud | pilot doc |
| Synthetic data | seeded inside Azure via one-shot ACA job (KV secrets; **PG firewall untouched**) | pilot doc |

## 3. Feature flags (VERIFIED — `backend/app/core/feature_flags.py`)

Fail-closed by design: unknown flag → disabled; override via `FEATURE_<NAME>` or `MCP_FEATURE_<NAME>`.

| Flag | Default | Launch-relevant note |
|---|---|---|
| `CONSENT_GATE` | **ON** (mandatory) | enforced |
| `DOCTOR_REVIEW_GATE` | **ON** (mandatory) | enforced |
| `AI_ASSISTANT` (Meto chat) | OFF | ON in staging per pilot doc; prod OFF |
| `OCR` | OFF | progressive-enable post-review |
| `OCR_CLOUD_FALLBACK` | **OFF** | opt-in only; **no PHI leaves device/region until owner authorizes** |
| `CLINICAL_INSIGHT` | ON | deterministic rules, guardrail-checked |
| `CLINICAL_INSIGHT_AI` | OFF | LLM rephrasing off in v1 |
| `CLINICAL_COPILOT` | OFF | doctor-facing LLM-over-PHI, fail-closed |
| `CLINIC_SAAS` | OFF | out of patient-pilot scope |
| All `MEDICATION_*` AI/ingestion flags | OFF | out of pilot scope |
| `qa_fixture_enabled` (config, not FeatureFlag) | **False**; **fails loud if set in prod** (`config.py:300`) | QA fixture route prod-unreachable |

## 4. Config fail-loud guards (VERIFIED — `backend/app/core/config.py`)

- Relaxed auth (`MCP_ALLOW_RELAXED_AUTH`), MFA-off (`MCP_MFA_ENFORCEMENT_ENABLED`), QA fixture: all **refuse to boot in prod** unless explicitly and loudly overridden (staging-only override path).
- Committed default JWT/Fernet (`MCP_SECRET_KEY`/`MCP_ENCRYPTION_KEYS`) → **boot refused** in any non-dev/test env (WS9 `4539a3d`).

## 5. Observability infra (VERIFIED — exists, depth TBD in WS5)

- `backend/app/main.py` wires `ObservabilityMiddleware` (`app/core/middleware.py`) + `MfaEnrollmentMiddleware`.
- `backend/app/core/metrics.py` (76 LOC), `app/core/context.py` (10 LOC — correlation context) present.
- **No** Sentry / OpenTelemetry / Prometheus / structlog integration detected by grep. → Gap to assess in WS5 (04-OBSERVABILITY.md).
- Mobile: **no crash reporter wired** (pilot doc §residual, §5). → Gap.

## 6. Test posture (partially verified — full re-run tracked in QA workstream)

| Suite | Count | Source | Status |
|---|---|---|---|
| Backend pytest | **3761 collected** (RC); pilot run "exit 0, 0 failures" | ENG-RC §3, pilot §review | Needs live full re-run → `TEST-STATUS.md` |
| Mobile Jest | **88/88** (pilot) / 62/62 (RC, earlier) | pilot §review | 21 test files in `mobile/` (verified) |
| Mobile tsc | clean | pilot §review | Needs re-run |

## 7. Mobile / distribution (VERIFIED from pilot doc; artifacts on disk TBD)

- Standalone release APK path: `mobile/android/app/build/outputs/apk/release/app-release.apk`; pkg `me.metocare.patient`.
- Signing: **debug keystore fallback** — fine for internal pilot; **Play upload key = external credential gap**.
- Remote-pilot caveat: APK bakes `API_BASE_URL` at build time; must rebuild against staging HTTPS URL for off-host testers.
- Maestro 2.8.0 flows in `mobile/.maestro/`; 4 journeys green vs staging.

## 8. Credential-readiness (VERIFIED — `CREDENTIAL-READINESS-MATRIX.md`)

6 external credentials gate DIST/production; **none blocks the internal pilot** except a reachable staging `API_BASE_URL`:
Apple signing · Google Play signing · APNs/FCM push · **Azure Document Intelligence + PHI-to-cloud authorization** · real payment gateway · real staging/prod auth secrets.
**Standing rule:** cloud PHI processing stays DISABLED until owner authorizes **and** supplies the key.

## 9. ENG-RC open decisions — RESOLUTION STATUS (VERIFIED via git log)

The 3 ENG-RC (2026-07-31) product decisions were subsequently implemented on this branch:

| ENG-RC decision | Status | Commit |
|---|---|---|
| Per-category Meto consent (fail-closed, versioned, revocable, audited) | **DONE** (+ mobile controls, + resync-safe toggle) | `714a819`, `3f24020`, `3a6a77e` |
| GDPR data export + account deletion | **DONE** | `d229c04` |
| MFA + password policy restore (env-scoped fail-loud) | **DONE** | `0b0bac8` |

## 10. What this program must still produce

Assessment + evidence across 16 workstreams → the numbered deliverables `01`–`15` in this folder, plus living tracking artifacts (`TRACKING.md`). Net-new **code** expected in: observability depth (WS5), analytics event instrumentation (WS6), OCR/AI eval harnesses (WS7/WS8), and any confirmed P0/P1 from the independent security/privacy/clinical audits.

**Production deployment is NOT authorized by this program.** Staging, internal distribution, synthetic data, security testing, and observability setup are authorized.
