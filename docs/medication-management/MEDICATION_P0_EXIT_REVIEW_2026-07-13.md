# Medication P0 — Exit Criteria Review (Agent 1)

**Date:** 2026-07-13 | **Reviewed state:** `origin/main` @ `029db64`, staging `merge_c1m08_p0med`
**Verdict: NOT READY FOR PRODUCTION** (as "P0 architecturally complete")

> Headline: the merged-and-deployed P0 is the **schema/migration layer only**.
> The planned second phase ("API + service layer", Implementation Plan §"3–5
> days after migrations") has not landed on `main`. The schema is live, correct
> and fully rolled back-able — but nothing writes or exposes the new fields yet.

---

## 1. Exit criteria scorecard

| EC | Verdict | Evidence |
|----|---------|----------|
| EC-01 Schema | ⚠️ PARTIAL | ✅ Verified live on staging (read-only job): all P0 columns present, `is_supplement` absent, 3 new tables, CHECKs `chk_lifecycle_status`/`chk_verification_status`/`chk_source_type` + `fk_medication_category` in place. ❌ "No legacy path writes `medications` directly without `medication_statements`" — the legacy write path is still the live one (`backend/app/services/medication.py:37-76`); `medication_statements` has no writer. |
| EC-02 API additive rollout | ⚠️ PARTIAL | ✅ Nothing broken — API contracts are byte-identical pre/post P0 (`MedicationOut` unchanged, `schemas/medication.py:33-42`); old payloads validate (defaults on all new NOT NULL columns, tested). Alias `status→lifecycle_status` N/A by design — `status` never existed (PRE_VALIDATION.md:128). ❌ "Endpoints return new fields" — no endpoint exposes lifecycle fields yet. |
| EC-03 Data migration | ✅ PASS | Verified live on staging: 37/37 pre-P0 rows = `active`/`patient_reported`/`patient_manual`; 0 NULL `lifecycle_status`; exactly 2 exception rows (the PTH-reviewed soft-deleted records) = `entered_in_error`, explicitly approved via `MEDICATION_SOFT_DELETE_MAPPINGS` allowlist on 2026-07-13. |
| EC-04 Mobile stability | ✅ PASS (code-level) | API responses contain zero new fields post-P0 → nothing new for any client to parse. No native mobile app code exists in-repo (`mobile/` holds design reference only). Physical device QA remains with PTH — note it exercises the web app, not a native app. |
| EC-05 ADR compliance | ⚠️ CONDITIONAL | 30-check review executed. Migration deliverable: fully compliant (ADR-01/03/09/11 clean; no triggers, FK-based category lookup, 7-state CHECK). ❌ **ADR-04 violated by live legacy write path** (D1/D2). 9 checks N-A until service phase exists (B4, B5, C2–C4, D4, D5 + audit wiring). |
| EC-06 Rollback rehearsal | ✅ PASS | Executed on a local Postgres 17 copy with seeded data mirroring staging: `merge_c1m08_p0med → c1_m08_queue → c0_m9_audit_log_clinic_id` downgrades ran clean; medications returned to exact pre-P0 columns; **zero data loss** (rows, doses, soft-delete flags preserved); P0 tables removed; re-upgrade roundtrip re-applied 7 migrations and re-mapped soft-deleted → `entered_in_error` correctly. |
| EC-07 Audit trail | ❌ FAIL | `medication_audit_log` schema verified (35/35 integration tests green on real Postgres, incl. snapshot round-trip and NULL-snapshot observational rows). But **no application code writes the table** — no model, no service hook. T-04's behavioral requirements (every lifecycle change ⇒ 1 audit row, snapshots match, `status_reason→transition_reason`, non_adherence NULL-snapshot events) are unimplemented and untestable. |
| EC-08 Documentation | 🔶 PTH | No ADR was edited during P0 (single squash commit touches `adrs/`). Caveat for sign-off: Implementation Plan §API describes response-field exposure that has not shipped. |

## 2. Blocking findings (must fix before "P0 complete")

1. **ADR-04 / EC-01 — legacy direct-write path live** (HIGH).
   `add_medication`/`update_medication` write canonical `medications` directly;
   `medication_statements` stays empty while real patients create meds on
   staging. Fix = the already-planned service-layer phase (statement-first
   ingestion + promotion).
2. **Soft-delete lifecycle drift** (HIGH, same PR).
   `delete_medication` sets `deleted_at` but not
   `lifecycle_status='entered_in_error'` and writes no audit row — every new
   soft-delete on staging contradicts the invariant the migration just
   established. Route deletion through a lifecycle transition + atomic audit write.
3. **EC-07 — audit writer missing** (HIGH, same PR).
   Implement `MedicationAuditLog` model + service hooks for lifecycle and
   verification transitions and observational events; add behavioral T-04 tests.

**Consequence for PTH acceptance testing:** items possible today on staging =
thêm/sửa/xoá thuốc + adherence (pre-P0 features) and UX review. **Not possible
yet:** lifecycle transitions (no API/UI exposes them), AI awareness of
`discontinued`/`entered_in_error` (AI context still filters only by
`deleted_at`), medication reminders (feature does not exist — notifications
cover appointments only).

## 3. Remediation plan (service-layer phase — pre-scoped in Implementation Plan §5)

1. PR-S1: ORM columns on `Medication` + `MedicationStatement`/`MedicationAuditLog` models; statement-first create/update; promotion to canonical; soft-delete → `entered_in_error` + audit row.
2. PR-S2: lifecycle/verification transition endpoints + audit hooks; API exposure of new fields (additive); T-04/T-05 behavioral tests.
3. PR-S3: AI context filter update (`lifecycle_status='active'`), frontend lifecycle UI.
4. Re-run this exit review (EC-01/02/05/07 re-verify) → then READY FOR PRODUCTION.

## 4. Production deployment plan (execute only after §3 + PTH "APPROVED")

Pre-flight: production ACA environment + Key Vault provisioned (mirror staging pipeline); Postgres tier check — **if Burstable, the backup step auto-falls back to PITR-verify; for production prefer General Purpose to get real on-demand backups**; secrets present (db-url, secret-key, enc-keys, AI keys); `MEDICATION_SOFT_DELETE_MAPPINGS` NOT set (fresh audit must run).
Sequence: (1) freeze merges; (2) tag release; (3) run deploy workflow against production env; (4) audit gate → expect `soft_deleted_count` from real data — if >0, STOP, run private review flow exactly as staging (one-shot ACA job, per-record allowlist, remove secret after); (5) backup/PITR restore point recorded; (6) Alembic migration; (7) deploy backend/frontend; (8) smoke tests (§6); (9) 48h observation window (App Insights errors, p95 latency, DB CPU).

## 5. Rollback checklist (production)

- [ ] Decision recorded (who/when/why) — trigger: failed smoke, data anomaly, P0/P1 incident.
- [ ] App rollback first: redeploy previous image tags (backend+frontend) — no DB change needed for schema-only P0.
- [ ] Schema rollback only if required: `alembic downgrade c1_m08_queue` then `alembic downgrade c0_m9_audit_log_clinic_id` (rehearsed 2026-07-13, zero data loss; note: also unapplies clinic C1 chain — on production prefer stopping at targeted revision via single-branch downgrade after review).
- [ ] If data corruption: PITR restore to recorded pre-migration restore point (`az postgres flexible-server restore --restore-time <point>` → new server → repoint secret) — accept data written after restore point is lost; export delta first if possible.
- [ ] Verify: `/health` 200, `/api/v1/info` shows expected `migration_version`, smoke pass.
- [ ] Post-mortem note in `docs/agent/`.

## 6. Production smoke test

1. `GET /health` = 200; `GET /api/v1/info` — env=production, expected `migration_version`, feature flags per plan (AI flags OFF at launch unless PTH enables).
2. Auth: register/login test patient (phone flow); token refresh.
3. Medication CRUD: create (name+dose+frequency) → list → edit dose → adherence log taken/skipped → delete → verify absent from list.
4. DB spot-check (read-only job): new row has `lifecycle_status='active'`, defaults correct; deleted row `entered_in_error` **(only after §3 lands)**.
5. Frontend: login page renders, dashboard loads with seeded metrics, medications screen lists/creates.
6. Meto AI (if enabled): ask "Tôi đang uống thuốc gì?" → answer reflects current meds only.
7. Logs: App Insights — zero 5xx in first 30 min; no PHI in any public log.

---
*Prepared by Agent 1 (Claude Code). Inputs: 30-check compliance review, mobile/API compat analysis, T-04 gate check (35/35 schema tests green), live staging schema+data verification (read-only ACA job, deleted after use), rollback rehearsal with roundtrip.*

---

# ADDENDUM — Re-run after service phase (S1→S3), same day

**Reviewed state:** `main` @ `9975775` (PR-S1 #112, PR-S2 #113, PR-S3 #114 merged; staging deploy green, `migration_version: merge_c1m08_p0med`)
**Verdict: READY FOR PRODUCTION** — pending PTH business acceptance (UAT) and the production-infra prerequisites in §4 of this document.

## Updated scorecard

| EC | Before | Now | Evidence |
|----|--------|-----|----------|
| EC-01 Schema | ⚠️ | ✅ PASS | Statement-first is the ONLY write path: service creates `medication_statements` in-transaction for create/edit/delete; repo-wide static guard test (`test_medication_write_path_guard.py`) fails CI on any bypass; seed script routed through the service. |
| EC-02 API rollout | ⚠️ | ✅ PASS | 5 fields exposed additively (frozen-shape test updated deliberately); old payloads still validate; no contract broken across S1–S3. |
| EC-03 Data migration | ✅ | ✅ PASS | Unchanged (verified live: 37 active w/ defaults, 2 PTH-approved exceptions). New soft-deletes now map consistently via the service. |
| EC-04 Mobile stability | ✅ | ✅ PASS (code-level) | Additive-only responses; web client updated; physical device QA remains PTH's UAT item. |
| EC-05 ADR compliance | ⚠️ | ✅ PASS | ADR-04 enforced (statement-first live); ADR-11 state machine universal (18 adversarial Codex rounds across S1–S3: 27 P1 + 9 P2 found & fixed in-PR); ADR-03 audit writer live. 3 PTH policy items open (below) — none violate a baseline ADR. |
| EC-06 Rollback | ✅ | ✅ PASS | No new migrations since the rehearsal; roundtrip verified. |
| EC-07 Audit trail | ❌ | ✅ PASS | Audit writer live: create/update/lifecycle_change/verification_change with before/after snapshots; observational events NULL-snapshot; T-04 items incl. `status_reason → transition_reason` covered by behavioral tests (48 new tests across S1–S3). |
| EC-08 Documentation | 🔶 | 🔶 PTH signs | No ADR edited during P0. Known plan deviations documented: §6.2 expired job NOT built (needs `end_date`); `correction` assertion_type pending taxonomy decision. |

## Open items (tracked, non-blocking for staging UAT)

1. **PTH policy (from S1):** statement backfill for 37 pre-P0 rows; flush-only service refactor; `correction` assertion_type (ADR vocabulary).
2. **Backend follow-up (from S3):** idempotency for expired re-assert statements (duplicate pending `continued_use` possible; zero risk today — nothing produces `expired` yet).
3. **Future phase:** §6.2 expired-detection job (requires `end_date` column).

## Production gate (unchanged from §4)

Provision production ACA env + Key Vault; **prefer non-Burstable Postgres tier** (real on-demand backups; Burstable auto-falls back to PITR-verify); fresh audit-gate pass on production data; smoke per §6; 48h observation; sau go-live: **freeze module Medication 1–2 tuần** thu bug/feedback/UX/performance trước khi mở Gate 2 (per PTH direction).

## Declaration readiness

All technical gates green. Per PTH's terminology ruling: "Medication **Foundation** v1.0" was implementable at schema-completion; with the application layer now shipped and verified, the original **"Medication Architecture v1.0 — Successfully Implemented"** declaration (EXIT_CRITERIA §Declaration) is signable at PTH's discretion after UAT.

*Re-run by Agent 1. Inputs: 18 Codex review rounds (S1: R4 PASS, S2: R15 PASS, S3: R3 PASS), full unit+integration suites green on every merge, staging deploys green (runs 29225358174 / 29233539626 / 29244726460).*
