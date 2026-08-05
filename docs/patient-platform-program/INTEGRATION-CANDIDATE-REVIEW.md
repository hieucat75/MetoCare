# Integration candidate review — Journey 2–5 → `main`

**Frozen candidate SHA:** `1430a3e31d99cddfafdde3b5a4d1a78ea3b76e11`
(tag `integration-candidate-freeze`, branch `feat/patient-platform-journey2`)

**Merge candidate:** the **post-fix** SHA — the P0/P1 fixes in §6 land on top of the
freeze point. See §9.

**Target:** `origin/main` @ `99a3616`
**Date:** 2026-08-05

> **Verdict: CONDITIONAL GO — merging to `main` is safe; a production deploy is not.**
> §8.

---

## 1. Freeze and divergence

```
origin/main                     99a3616
integration-candidate-freeze    1430a3e   49 ahead / 0 behind
merge-base                      99a3616
```

`origin/main` is a **strict ancestor** of the candidate. Two consequences, both verified
in an isolated worktree:

- **Merge rehearsal: 0 conflicts.** `git merge --no-commit --no-ff` reported "Automatic
  merge went well"; `git diff --diff-filter=U` returned nothing.
- **The merged tree is byte-identical to the candidate tree** — both
  `b88daacfc552dc8a74d526843e24289a2efa936a`. Verification of the branch **is**
  verification of the merge result; no separate post-merge test run is required.

The merge is a fast-forward. No rebase is needed and none should be done — rebasing 49
reviewed commits would invalidate every SHA in the evidence trail.

---

## 2. Commit classification by bounded context

49 commits (a commit touching several contexts counts in each):

| Context | Commits |
|---|---|
| Docs / evidence | 23 |
| Mobile | 15 |
| MDI / Documents (Journey 2) | 9 |
| Meto AI (Journey 4) | 6 |
| Auth / platform | 5 |
| Medication schedule + dashboard (Journey 3) | 4 |
| Web (Journey 3 parity) | 3 |
| GDPR / account | 3 |

Changed paths: `mobile` 108, `docs` 72, `backend/app` 53, `backend/tests` 32,
`backend/api` 11, `frontend` 8, `backend/alembic` 3, `.github` 1.

---

## 3. Migrations

Three tracked migrations, all additive:

| Revision | id length | Nature |
|---|---|---|
| `mdi_s0_medical_documents` | 24 | new tables (MDI) |
| `j3_m5_medication_schedule` | 25 | new tables (schedules/doses) |
| `j4_m8_consent_versioning` | 24 | `ADD COLUMN` + unique constraint |

- **Single head confirmed** in the merged git tree: `j4_m8_consent_versioning` — the same
  revision staging and production already report.
- `upgrade head` from scratch: clean. `downgrade -1` → `upgrade head`: clean.
- All revision ids ≤ 32 chars, clear of the past `alembic_version VARCHAR(32)` incident.
- Dialect guards verified: `JSON`/`JSONB` variant; partial index passing **both**
  `sqlite_where` and `postgresql_where`; `batch_alter_table` compiling to plain
  `ALTER TABLE` on Postgres (no table rewrite).

---

## 4. API / config / CI surface

**New route modules:** `documents.py`, `account.py`, `medication_schedule.py`,
`dashboard.py`, `medication_source.py`.
**Modified:** `auth.py`, `meto.py`, `lab_upload.py`, `health_timeline.py`.
**Config:** `backend/app/core/config.py` +119 lines (feature flags, storage, scan mode,
fail-loud guards). **Mobile:** `app.config.ts` +90, `eas.json` +37.
**CI:** `.github/workflows/ci.yml` — additive only (stricter Alembic single-head gate,
two new Postgres integration test targets). No gating weakened.

---

## 5. Verification at the candidate

| Check | Result |
|---|---|
| Backend suite | green, 0 failures |
| Frontend suite | 56 suites / 644 tests green |
| Frontend typecheck / lint / production build | clean |
| Mobile typecheck | clean |
| Mobile suite | **6 of 28 suites failed on a cold cache** → fixed, §6 |
| Alembic single head + up/down round-trip | clean |
| Merge rehearsal | 0 conflicts, identical tree |

---

## 6. Findings and disposition

Four independent fresh-context reviews — security/privacy, clinical safety, migration/DB,
and the integration analysis here. Findings were verified against source before acting;
several were empirically reproduced.

### Fixed in this pass

| # | Sev | Finding | Fix |
|---|---|---|---|
| 1 | **P0** | **OCR lab labels resolved to the wrong analyte.** `extractors_lab.py` used `lab_interpreter.normalize_biomarker`, whose step 4 is a bare containment scan. Reproduced: `VLDL → ldl`, `Non-HDL cholesterol → hdl`. A patient confirming the VLDL line off their own report would overwrite their real LDL with a much lower number, classified *optimal* — a false negative on cardiovascular risk, invisible at review because the card shows the printed label, not the resolved canonical. | Switched to `lab_parser._match_biomarker`, the hardened matcher `/lab-uploads` already uses (`_UNMAPPABLE_LABEL_RE` + longest-alias/shadowing). VLDL, non-HDL and lipid ratios are now **dropped**, not mis-mapped. Verified end-to-end; 5 regression tests. |
| 2 | P1 | **The lab unit-safety guard was bypassable.** `LabPromoter` gated on the stored `canonical`, which patient corrections can blank or leave stale — reaching the same silent false-normal. | Canonical is re-derived from the corrected `test_name` via the same hardened matcher before the guard runs. |
| 3 | P1 | **`j4_m8_consent_versioning` could fail the entire deploy.** Reproduced as a `UniqueViolation` on real Postgres: the `(user_id, context_type)` constraint fails on duplicates, and Alembic runs all pending revisions in one transaction, so the whole deploy rolls back. The only write path has no upsert or row lock, so duplicates are plausible. | Deterministic dedupe added before the constraint. Verified against a seeded duplicate: previously failed, now succeeds keeping one row per pair. |
| 4 | P1 | **Production could boot with no malware scanning.** `document_scan_mode` defaults to `"skip"`, which accepts an upload and promotes it to the servable container; the bytes are then parsed server-side by Pillow/pytesseract/pypdf before any human sees them. Every comparable risk factor already fails loud in prod; this one did not. | Startup guard: prod refuses to boot on `"skip"`. Scoped to prod — staging deliberately runs `"skip"` and a staging guard would break the existing deploy. 5 tests. |
| 5 | P1 | **Mobile suite failed 6 of 28 on a cold cache** — jest's 5s default is measured inside the test body while the first test pays for transforming the whole RN + Expo Router graph. CI always runs cold. | `testTimeout: 30000`. Verified: cold parallel run 28/28, 138/138. |

### Confirmed, NOT fixed — owner decision required

| # | Sev | Finding | Why deferred |
|---|---|---|---|
| 6 | P1 | **SEC-F11 half-delivered.** The `MetoMessage.content` model change is committed; its re-encryption migration is untracked. New messages encrypt; pre-existing rows stay plaintext PHI at rest indefinitely. | Committing a PHI data migration changes what the next deploy executes. Full analysis: `MIGRATION-FORENSICS-SEC-F11.md`. |
| 7 | P1 | **Malformed `recurrence` degrades a cyclic/interval schedule to daily reminders**; unparseable dose times are silently dropped, leaving an ACTIVE schedule that can never remind. | Behavioural change to a live surface; needs a decision on the validation contract. |
| 8 | P1 | **Adherence is resettable and inflatable.** `edit_schedule` deletes past-due-but-unswept doses without sweeping first, and adherence is keyed per schedule id — so changing a reminder time erases missed history and restarts the denominator. | Needs a decision on whether adherence aggregates across the supersession chain. |
| 9 | P1 | **GDPR erasure leaves PHI in four tables** — `medication_schedules`/`dose_occurrences` (incl. free-text `skip_reason`), `medication_statements` (raw OCR payload, prescriber), `notifications` (drug name in the body), `symptom_logs`. | Compliance scope decision; erasure is currently asserted complete in DIST-RC. |
| 10 | P1 | **Meto answers with an empty context when the context build fails**, so it can state "no recent labs" while a critical value exists. | Needs a decision between a visible degradation notice and refusing the turn. |
| 11 | P2 ×6 | Rate limits on GDPR export/delete; `LabDocument` not anonymised on erasure; dashboard document counts bypass the consent gate; `on_decrypt_failure="none"` on a non-nullable column; future doses markable as taken; `_merge` leaves canonical dose stale. | Non-blocking. |

### Explicitly clean (recorded so it is not re-litigated)

BOLA/IDOR on every new patient-scoped endpoint including merge-target grafting; storage
keys and signed tokens (no traversal or forgery path); server-side MIME/size
re-validation; the `documents` consent gate with no bypass across
`documents.py`/`medication_source.py`/`lab_upload.py`; no PHI in logs, plus new
log-hardening (`hide_parameters=True`, SQL-detail redaction); GDPR deletion revoking live
sessions; the record-only medication invariant; §1.9 diagnosis handling; Meto output
safety enforced on **both** chat paths, with the streaming path buffering before emitting;
no double-reminder or duplicate dose (unique `idempotency_key` + conditional claim).

---

## 7. Not covered by CI

**Mobile tests do not run in CI at all** — `grep -n "mobile" .github/workflows/ci.yml`
returns nothing, while mobile is 108 of the changed paths. Finding #5 survived because of
this. Adding a mobile job is recommended but deliberately not done here: it changes the
deploy gate, which was outside this task's scope.

---

## 8. Verdict

**CONDITIONAL GO.**

**Merging to `main` is safe now**, given the fixes above:

- fast-forward, zero conflicts, identical tree;
- single Alembic head, clean up/down;
- all suites green;
- the P0 is fixed and empirically verified;
- `MCP_FEATURE_OCR` defaults **off**, so the Journey-2 OCR surface is dormant on merge.

**A production deploy is NOT approved by this review.** Blocked on:

1. items 6–10 (each affects an already-live surface or a compliance claim);
2. the `meto_consents` duplicate audit (§6 of the environment plan);
3. `MCP_DOCUMENT_SCAN_MODE` set to a real posture — production now refuses to boot
   otherwise;
4. **`MCP_FEATURE_OCR` staying off for real patients** until items 6 and 2 are closed.

---

## 9. Exact integration plan

```bash
# 0. Record the post-fix candidate SHA.
git rev-parse HEAD                      # ← the merge SHA

# 1. Re-verify at that SHA (all must be green).
cd backend  && ./.venv/bin/python -m pytest -q
cd ../frontend && npx tsc --noEmit -p tsconfig.build.json && npx jest --watchAll=false
cd ../mobile   && npx jest --clearCache && npx jest --watchAll=false

# 2. Alembic single head.
cd ../backend && MCP_DATABASE_URL="sqlite:///:memory:" ./.venv/bin/python -m alembic heads
#    expect exactly: j4_m8_consent_versioning (head)

# 3. Push and open a PR — do NOT push straight to main.
git push origin feat/patient-platform-journey2
gh pr create --base main --head feat/patient-platform-journey2

# 4. Merge with --no-ff so the 49-commit body stays one reviewable unit.
#    Do NOT squash (loses per-milestone review provenance) and do NOT rebase
#    (invalidates every SHA in the evidence trail).
```

After merge, `main` auto-deploys to **staging** via `ci.yml`. That is expected and
already validated — the same tree runs on staging today. It does **not** deploy
production.

---

## 10. Owner approvals required

1. **Merge to `main`** — approve the CONDITIONAL GO in §8.
2. **SEC-F11 disposition** — commit the untracked migration + its test, and settle the
   `on_decrypt_failure` question (`MIGRATION-FORENSICS-SEC-F11.md` §8).
3. **Clinical P1s 7–10** — accept, schedule, or waive with rationale.
4. **Mobile in CI** — approve adding the job.
5. **Production deploy** — separate gate; blocked per §8.
6. **Environment separation** — `docs/launch-readiness/16-ENVIRONMENT-SEPARATION-PLAN.md`.
