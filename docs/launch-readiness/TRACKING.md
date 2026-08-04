# MetoCare v1 — Launch-Readiness Tracking (living source of truth)

**Owner:** Program Lead · **Updated:** 2026-08-03 · **Do not treat Claude memory as source of truth — this file is.**

Legend: ✅ READY · 🟡 READY-WITH-ACCEPTED-LIMITATION · ⛔ BLOCKED · ⚪ N/A · ⏳ IN-PROGRESS

---

## A. Launch-Readiness Matrix (by workstream)

| WS | Area | Deliverable | Status | Gates which gate |
|---|---|---|---|---|
| 0 | Current-state verification | `00-CURRENT-STATE.md` | ✅ | — |
| 1 | Production readiness | `01-PRODUCTION-READINESS-MATRIX.md` | ✅ authored | controlled pilot |
| 2 | Security & privacy | `02-SECURITY-PRIVACY-REVIEW.md` | ✅ authored | controlled pilot |
| 3 | Clinical safety | `03-CLINICAL-SAFETY-REVIEW.md` | ✅ authored | controlled pilot |
| 4 | Observability | `04-OBSERVABILITY.md` | ✅ authored | controlled pilot |
| 5 | Analytics | `05-ANALYTICS-EVENT-CATALOG.md` | ✅ authored (design-level; instrumentation = beta scope) | controlled pilot |
| 6 | OCR quality | `06-OCR-QUALITY-REPORT.md` | 🟡 authored — **no real-image accuracy has ever been measured** | public beta |
| 7 | AI safety eval | `07-AI-SAFETY-EVALUATION.md` | ✅ authored + 24-probe red-team corpus | controlled pilot |
| 8 | Backup/restore | `08-BACKUP-RESTORE-RUNBOOK.md` | ✅ authored | public beta |
| 9 | Performance/capacity | `09-PERFORMANCE-CAPACITY.md` | 🟡 authored — estimates; only one measured figure | public beta |
| 10 | Cost model | `10-COST-MODEL.md` | 🟡 needs correction (sizes 1 vCPU/2 GiB; deployed replica is 0.5/1) | public beta |
| 11 | Mobile distribution | `11-MOBILE-DISTRIBUTION.md` | ✅ authored | public beta |
| 12 | Pilot operations | `12-PILOT-OPERATIONS-RUNBOOK.md` | ✅ | controlled pilot |
| 13 | Incident response | `13-INCIDENT-RESPONSE.md` | ✅ authored | controlled pilot |
| 14 | Feature rollout | `14-FEATURE-ROLLOUT.md` | ✅ | controlled pilot |
| 15 | Final launch review | `15-FINAL-LAUNCH-REVIEW.md` | ✅ verdict issued 2026-08-04 | — |

**Assessment method (batch 2, 2026-08-04):** six independent fresh-context assessors
inspected source directly; every material claim carries a `file:line` or command-output
citation, and unverifiable items are marked `UNVERIFIED` with the command that would
settle them. Confirmed findings were then fixed by seven separate agents under strict
file ownership, each with regression tests that failed before the fix.

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
| R-05 | ~~Cloud OCR PHI-to-cloud path exists but must stay OFF~~ **THIS WAS FALSE** | P0 | ✅ FIXED `2026-08-04` | Security | The flag never gated engine selection: `run_ocr` chose Azure DI on credential presence alone, and both workflows inject those credentials — so cloud OCR was the PRIMARY engine and Tesseract never ran. Now `azure_ocr_permitted()` gates every selection site fail-closed. See PRIV-F3/PROD-F7/OCR-F1 in `02`/`01`/`06`. | **was blocking controlled pilot** |
| R-06 | `/info.ocr_mode` does not reflect `run_ocr`'s real engine selection — it was cited as evidence that cloud OCR was off | P1 | ⏳ | SRE | Make `/info` report the effective engine, or stop citing it. Until then it is not admissible evidence. | controlled pilot |
| R-07 | Pilot APK artifact on disk predates the WS11-F3 permission strip and the batch-2 fixes | P1 | ⏳ | Mobile | `expo prebuild --clean` + rebuild, then verify the **artifact** (`unzip`/`aapt`), not the source | controlled pilot |
| R-08 | Owner has not decided the PHI-to-cloud question; `AZURE_DOC_INTEL_*` remain injected by both workflows (latent capability, now inert in code) | P1 | ⏳ owner | Owner | Remove the env/secret injection, or authorize cloud OCR with a DPA and set `OCR_CLOUD_FALLBACK` deliberately per environment | controlled pilot (real data) |
| R-09 | Backend venv lived on an external volume that unmounted mid-session | P2 | ⏳ | DevEx | Verification depends on a removable disk; move the venv into the repo or a stable path | — |

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
