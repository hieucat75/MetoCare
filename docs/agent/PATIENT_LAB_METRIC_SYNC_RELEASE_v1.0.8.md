# Patient App — Lab → Dashboard/Metrics sync v1.0.8

> **Release:** v1.0.8 · **Target:** Azure Container Apps staging (Singapore) · DigitalOcean production untouched.
> **Source PR:** #35 (`feat/patient-lab-to-health-metrics-sync`, squash-merged `b9eb29b`).

## What ships

After a patient confirms lab results (OCR upload or manual entry), the overlapping biomarkers are
**promoted into `health_metrics`** so the dashboard tiles + trend charts reflect the new values
immediately — previously lab data was siloed in `lab_results`.

- `lab.promote_lab_rows_to_metrics`: each confirmed lab row that maps to a known biomarker AND has a
  value → a `health_metric` (`metric_type=canonical`, `measured_at=test_date` **not today**,
  `source='lab_result'`, `source_ref=lab_result_id`, status auto-classified). **Idempotent** per lab row.
- `create_manual_entry` resolves `canonical_name` + promotes before commit.
- `MetricOut` exposes `source` so the UI distinguishes lab vs self-report.
- Frontend `/metrics` reading list shows a **"Từ xét nghiệm"** flask badge on lab-sourced readings; the
  dashboard reads `health_metrics` so the Glucose tile auto-updates.

## ⚠️ Migration in this release

This release **includes an Alembic migration** — the first since `pauth_user_phone`:

- **`hm_source_ref`** — adds `health_metrics.source_ref` (nullable, indexed) for idempotent + traceable
  lab→metric promotion linkage. The `source` column already existed (no change). Existing rows keep
  `source_ref` NULL.
- On deploy, the Azure staging **Alembic one-shot job** applies it; the DB head moves
  **`pauth_user_phone` → `hm_source_ref`**. Verify `/api/v1/info` `migration_version` = `hm_source_ref`
  post-deploy.

## No workflow / no new deps

- **No workflow change** — OCR already enabled on staging since v1.0.6; cloud OCR stays OFF (no keys).
- No new system/Docker dependencies.
- DigitalOcean production is `[deploy-do]`-opt-in and untouched.

## Quality gates (local)

- Backend `pytest` **631 passed / 1 skipped** (+7 tests: promotion correctness, measured_at=test_date,
  unmapped/no-value skip, idempotency, surfaces via metrics API, status classified); `ruff` clean.
- Frontend `tsc` / `eslint` / `build` clean. Migration applies cleanly on a fresh SQLite DB.
- Live local: lab Glucose 140 + HbA1c 7.2 → `/dashboard` Glucose tile 140 + `/metrics` 140 @ 15/10/2024
  with the "Từ xét nghiệm" badge; metrics API returns `source=lab_result`, `measured_at=2024-10-15`.
