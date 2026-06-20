# Patient App — Manual lab entry cascade dropdowns v1.1.0

> **Release:** v1.1.0 (minor bump — user-facing UX overhaul + accumulated 1.0.x) · **Target:** Azure
> Container Apps staging (Singapore) · DigitalOcean production untouched.
> **Source PR:** #39 (`feat/patient-lab-entry-droplist-reference`, squash-merged `ca865ec`).

## What ships

Manual lab entry was slow + error-prone (free-text biomarker names + units). v1.1.0 rebuilds it as
**cascade dropdowns** + auto reference range + auto-classified status — the patient picks, never types
clinical terms.

- **Backend reference catalog** (`app/domain/lab_reference.json`) — PHI-free, **22 biomarkers / 6
  categories** (diabetes, lipid, liver, kidney, thyroid, hematology). Multi-unit with per-unit reference
  ranges (mg/dL + mmol/L for glucose/lipids), `value_precision`, `notes`, `higher_is_better` (HDL/eGFR).
  Biomarker keys = the OCR canonical keys, so manual entry + OCR stay consistent and promote to
  `health_metrics` (dashboard sync).
- **`GET /api/v1/lab-reference`** — auth (patient role), `Cache-Control` 24h.
- **Frontend `LabEntryModal`** — 3-level cascade (loại → chỉ số filtered → đơn vị auto-selected),
  display-only "Bình thường: …" badge, auto status badge (Bình thường/Cao/Thấp/Rất cao/Rất thấp →
  mint/amber/red), multi-row, implausible-value soft-confirm. Replaces the old free-text form on `/labs`.

## No migration / no workflow / no new deps

- **No DB migration** — the catalog is static (DB head stays `hmbk_backfill`).
- **No workflow change**; cloud OCR stays OFF. No new system/Docker deps → fast build.
- The catalog JSON lives in `app/domain/` (shipped via the image; `app/data/` is gitignored).
- DigitalOcean production is `[deploy-do]`-opt-in and untouched.

## Quality gates (local)

- Backend `pytest` **643 passed / 1 skipped** (+7 tests: catalog completeness vs OCR canonicals, shape,
  categories, RBAC); `ruff` clean.
- Frontend `tsc` / `eslint` / `build` clean.
- Live local Playwright iPhone 14 Pro: Lipid máu → Cholesterol toàn phần → mg/dL auto + "≤ 200 mg/dL"
  → 245 → "Cao"; row2 HDL 35 → "≥ 40 mg/dL" + "Thấp"; save → /labs + dashboard Glucose 140 synced.

## Note

The OCR upload **review** form (`/labs/upload`) is unchanged this release (still edits canonical rows);
only the **manual** entry form on `/labs` gained the cascade. Both still save with canonical `test_name`
so promotion / dashboard sync (v1.0.8) works.
