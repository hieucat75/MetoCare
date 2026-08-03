# 14 — Feature Flag & Rollout Strategy (WS15)

**Date:** 2026-08-03 · Grounded in `backend/app/core/feature_flags.py` (verified) + `CREDENTIAL-READINESS-MATRIX.md`.

## Rollout stages

1. **Team-only** — engineers, dev/test env, committed dev defaults.
2. **Internal pilot** — 4 native journeys on staging APK (✅ achieved, `d25f109`).
3. **Controlled external pilot** — 10–50 vetted users, staging backend, synthetic-or-consented data, monitoring + support live.
4. **Beta** — signed distribution, production env, real secrets, backups.
5. **Public launch** — requires explicit owner authorization (out of this program's scope).

## Flag → rollout matrix

All backend flags are **fail-closed** (`is_enabled()` returns False for unknown flags; default from `_DEFAULTS`). Override via `FEATURE_<NAME>` / `MCP_FEATURE_<NAME>`.

| Feature | Flag | Default | Enable at stage | Env | Dependency | Rollback | Monitoring signal | Promotion criterion |
|---|---|---|---|---|---|---|---|---|
| Consent gate | `CONSENT_GATE` | **ON** | always | all | — | n/a (mandatory) | consent-denial rate | always on |
| Doctor review gate | `DOCTOR_REVIEW_GATE` | **ON** | always | all | — | n/a (mandatory) | — | always on |
| Meto AI chat | `AI_ASSISTANT` | OFF | controlled pilot | staging on; prod off | AI provider key; consent | flip OFF (no redeploy) | AI latency/error/block rate | AI-safety eval (WS7) pass |
| Lab/doc OCR | `OCR` | OFF | controlled pilot | staging post-review | — (local/mock) | flip OFF | OCR latency/failure/correction rate | OCR quality (WS6) thresholds met |
| **Cloud OCR fallback** | `OCR_CLOUD_FALLBACK` | **OFF** | **public beta only** | — | **Azure DI key + owner PHI-to-cloud authorization** | flip OFF | cloud-OCR calls (must be 0 until authorized) | explicit owner sign-off |
| Clinical insight (rules) | `CLINICAL_INSIGHT` | ON | internal pilot+ | all | — | flip OFF | insight endpoint errors | deterministic — safe on |
| Clinical insight AI rephrase | `CLINICAL_INSIGHT_AI` | OFF | post-beta | — | AI provider | flip OFF | — | rules-only in v1 |
| Doctor clinical copilot | `CLINICAL_COPILOT` | OFF | out of patient-pilot scope | — | LLM-over-PHI review | flip OFF | — | separate program |
| Clinic SaaS | `CLINIC_SAAS` | OFF | out of scope | — | tenant isolation audit | flip OFF | — | separate program |
| Medication knowledge / AI ingestion | `MEDICATION_*` (8 flags) | OFF | out of scope | — | — | flip OFF | — | separate program |

## Non-FeatureFlag build/config guards (fail-loud in prod — WS12)

| Control | Mechanism | Prod behavior |
|---|---|---|
| QA fixture route | `qa_fixture_enabled` config (`config.py:184`, prod-guard `:300`) | **boot refused** if set in prod; mobile omits the QA button on production builds (`IS_NON_PRODUCTION` build gate) |
| Relaxed auth | `MCP_ALLOW_RELAXED_AUTH` | staging-only override; **prod fails loud** |
| MFA off | `MCP_MFA_ENFORCEMENT_ENABLED` | must be `true` in prod (guard enforces) |
| Default JWT/Fernet secrets | secret validation | **boot refused** in any non-dev/test env (`4539a3d`) |

**Rule (verified posture):** QA-fixture and relaxed-auth flags **cannot** be enabled in a production build/environment — they fail loud. This is the single most important rollout-safety invariant; to be re-verified by the Mobile/SRE assessment (WS12) and Security assessment (WS2).

## Promotion checklist (per stage)
- Internal → controlled pilot: WS2/WS3/WS4 audits closed (no open P0/P1), crash/error monitoring live (WS5), pilot + incident runbooks (WS12/WS13), support channel, staging stable.
- Controlled pilot → beta: external signing/push/secrets supplied, production env stood up, backups verified (WS8), cost/perf validated (WS9/WS10).
