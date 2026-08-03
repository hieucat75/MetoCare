# MetoCare v1 — Launch-Readiness Tracking (living source of truth)

**Owner:** Program Lead · **Updated:** 2026-08-03 · **Do not treat Claude memory as source of truth — this file is.**

Legend: ✅ READY · 🟡 READY-WITH-ACCEPTED-LIMITATION · ⛔ BLOCKED · ⚪ N/A · ⏳ IN-PROGRESS

---

## A. Launch-Readiness Matrix (by workstream)

| WS | Area | Deliverable | Status | Gates which gate |
|---|---|---|---|---|
| 0 | Current-state verification | `00-CURRENT-STATE.md` | ✅ | — |
| 1 | Production readiness | `01-PRODUCTION-READINESS-MATRIX.md` | ⏳ | controlled pilot |
| 2 | Security & privacy | `02-SECURITY-PRIVACY-REVIEW.md` | ⏳ | controlled pilot |
| 3 | Clinical safety | `03-CLINICAL-SAFETY-REVIEW.md` | ⏳ | controlled pilot |
| 4 | Observability | `04-OBSERVABILITY.md` | ⏳ | controlled pilot |
| 5 | Analytics | `05-ANALYTICS-EVENT-CATALOG.md` | ⏳ | controlled pilot |
| 6 | OCR quality | `06-OCR-QUALITY-REPORT.md` | ⏳ | public beta |
| 7 | AI safety eval | `07-AI-SAFETY-EVALUATION.md` | ⏳ | controlled pilot |
| 8 | Backup/restore | `08-BACKUP-RESTORE-RUNBOOK.md` | ⏳ | public beta |
| 9 | Performance/capacity | `09-PERFORMANCE-CAPACITY.md` | ⏳ | public beta |
| 10 | Cost model | `10-COST-MODEL.md` | ⏳ | public beta |
| 11 | Mobile distribution | `11-MOBILE-DISTRIBUTION.md` | ⏳ | public beta |
| 12 | Pilot operations | `12-PILOT-OPERATIONS-RUNBOOK.md` | ⏳ | controlled pilot |
| 13 | Incident response | `13-INCIDENT-RESPONSE.md` | ⏳ | controlled pilot |
| 14 | Feature rollout | `14-FEATURE-ROLLOUT.md` | ⏳ | controlled pilot |
| 15 | Final launch review | `15-FINAL-LAUNCH-REVIEW.md` | ⏳ | — |

## B. Release Gates

| Gate | State | Blocking items |
|---|---|---|
| **Internal pilot ready** | ✅ ACHIEVED (`d25f109`, APK vs staging, 4 journeys green) | verify no regression |
| **Controlled pilot ready** | ⏳ IN ASSESSMENT | see Risk Register open P0/P1 |
| **Public beta ready** | ⛔ | external credentials (App/Play signing, push, real secrets), production env, backups, cost/perf validation |
| **Production** | ⛔ NOT AUTHORIZED by this program | explicit owner authorization required |

## C. Risk Register

| ID | Risk / hazard | Sev | Status | Owner | Resolution | Gate impact |
|---|---|---|---|---|---|---|
| R-01 | Full backend suite not re-run live this program | P2 | ⏳ | QA Lead | re-run pytest, record in TEST-STATUS.md | controlled pilot |
| R-02 | Mobile crash/log capture not wired (no crash reporter) | P1 | ⏳ | Mobile+SRE | add crash reporting or documented adb-logcat SOP before wide pilot | controlled pilot |
| R-03 | Remote-pilot APK bakes `API_BASE_URL` at build; localhost default | P1 | 🟡 | Mobile | rebuild against staging HTTPS URL; documented in runbook | controlled pilot |
| R-04 | Live staging state (revision/flags) is DOC-ONLY this session | P2 | ⏳ | SRE | live re-verify via Azure if creds present | controlled pilot |
| R-05 | Cloud OCR PHI-to-cloud path exists but must stay OFF | P0-if-flipped | ✅ controlled | Security | flag OFF + fail-closed; owner authorization required to enable | public beta |
| _additional risks appended by assessment team below_ | | | | | | |

## D. Decision Log

| # | Decision | Date | By | Rationale |
|---|---|---|---|---|
| D-01 | Launch-readiness program begins with Phase 0 direct verification (not trusting prior summaries) | 2026-08-03 | Program Lead | prompt mandate; grounds the matrix |
| D-02 | No merge to `main` and no production deploy during this program | 2026-08-03 | Program Lead | prompt: production not authorized |
| D-03 | Assessment done by fresh-context independent agents inspecting source directly; P0/P1 fixed by Lead to avoid concurrent edits | 2026-08-03 | Program Lead | prompt: independent review + no concurrent edits |

## E. Environment Matrix

| Env | Purpose | Auth posture | Flags | Data |
|---|---|---|---|---|
| dev/test | local + CI | committed dev defaults OK | defaults | synthetic |
| staging (ACA) | pilot backend | relaxed-auth override (logged) | `AI_ASSISTANT` on, `OCR` per-review | synthetic (ACA-seeded, PG firewall untouched) |
| production | NOT in scope | fail-loud on all relaxations/default secrets | real secrets required | none — not deployed |

## F. Test Status
See `TEST-STATUS.md` (created by QA workstream). Snapshot: backend 3761 collected (RC); mobile Jest 88/88 (pilot). Live re-run pending.

## G. Open Incidents
None open. Historical: dev Postgres credential rotation (`c3446b0`, `7fd8582`) — remediated. See `docs/agent/INCIDENT_STAGING_DB_CREDENTIAL_ROTATION_2026-07-27.md`.

## H. Known Limitations (accepted for internal pilot)
- Debug-keystore APK (no Play upload key yet) — internal distribution only.
- No remote push (APNs/FCM) — in-app + deterministic transports only.
- Local/mock OCR only — cloud OCR disabled (no PHI to cloud).
- Mock payment — no real money movement.
- MFA enforcement relaxed on staging (env-scoped, fail-loud elsewhere).

## I. Rollback (summary — full runbook in `08` + `13`)
- **App:** `adb install -r <prev app-release.apk>` / uninstall + reinstall prior build (RN stateless beyond SecureStore).
- **Backend:** redeploy prior image via `azure-staging.yml` / ACA revision rollback; `alembic downgrade -1` reverses consent-versioning (single-head, additive).
- **Flags:** disable `AI_ASSISTANT`/`OCR` to dark-launch without redeploy.
