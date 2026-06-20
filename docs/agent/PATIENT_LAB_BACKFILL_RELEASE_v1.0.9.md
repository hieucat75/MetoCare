# Patient App — Lab metric backfill + all-path promote v1.0.9

> **Release:** v1.0.9 · **Target:** Azure Container Apps staging (Singapore) · DigitalOcean production untouched.
> **Source PR:** #37 (`fix/patient-lab-metric-backfill-orphans`, squash-merged `ecfb77f`).

## What ships — bug fix

v1.0.8 synced lab → `health_metrics` **only on the `create_manual_entry` path**. Labs created **before
v1.0.8** or via the **`interpret_document` / async pipeline** paths had no `health_metric`, so the
dashboard + `/metrics` showed **empty** even though `lab_results` existed (PTH's symptom — labs uploaded
during v1.0.6/v1.0.7 testing).

- **`backfill_lab_metrics(db)`** — promotes every orphan `lab_result` (value present, not yet linked by
  `health_metrics.source_ref`). Idempotent (already-synced rows skipped).
- **`interpret_document` + `lab_pipeline.process_document`** now also promote (close the ongoing orphan
  sources; previously only `create_manual_entry` did).
- Refactor: `_promote_row` + `_measured_at_for` shared by all callers.

## ⚠️ Data migration in this release

- **`hmbk_backfill`** (revises `hm_source_ref`) — a **data migration** that runs `backfill_lab_metrics`
  at deploy, promoting existing orphan labs (incl. PTH's). Idempotent. On deploy the Azure staging
  **Alembic one-shot job** applies it; DB head moves **`hm_source_ref` → `hmbk_backfill`**, and the job
  logs `[hmbk_backfill] promoted N orphan lab metrics`.
- Verify `/api/v1/info` `migration_version = hmbk_backfill` post-deploy.

## No workflow / no new deps

- **No workflow change** — OCR already enabled on staging since v1.0.6; cloud OCR stays OFF.
- DigitalOcean production is `[deploy-do]`-opt-in and untouched.

## Quality gates (local)

- Backend `pytest` **636 passed / 1 skipped** (+5 tests: backfill promote/idempotent/skip-synced/
  no-test_date, interpret promotes); `ruff` clean.
- Migration test: insert orphan labs → `alembic upgrade head` → `[hmbk_backfill] promoted 2 ...` → metrics
  present (`source=lab_result`, `measured_at=test_date`).

## Post-deploy verification

- **Orphan patient `0f5cd8cd…`** (created via the interpret path): **pre-deploy 4 lab_results / 0 metrics**
  → **post-deploy 4 lab_results / ≥3 metrics** = hard proof the backfill ran on real data.
- **PTH:** after this deploy, reloading `/dashboard` + `/metrics` shows the values from labs uploaded
  before v1.0.8.
