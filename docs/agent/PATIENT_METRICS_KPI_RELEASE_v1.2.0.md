# Patient App — Metrics KPI redesign v1.2.0

> **Release:** v1.2.0 (minor bump — major visual overhaul of `/metrics`) · **Target:** Azure Container
> Apps staging (Singapore) · DigitalOcean production untouched.
> **Source PR:** #41 (`feat/patient-metrics-kpi-redesign`, squash-merged `b2a8189`).

## What ships

`/metrics` was a lab-printout-style list. v1.2.0 rebuilds it as **Apple Health-style KPI cards grouped by
lab category**, each category with its own pastel theme.

- **Category groups** (pastel): Đường huyết & Tiểu đường (peach), Lipid máu (butter), Chức năng gan
  (sage), Chức năng thận (sky), Tuyến giáp (lavender), Huyết học (blush), Theo dõi hàng ngày (mint).
  Only non-empty categories render.
- **Each KPI card**: icon (per biomarker), label, big value (34px bold) + unit, **trend** vs the previous
  reading (↑↓ delta + %, coloured by favourability — reversed for `higher_is_better` like HDL/eGFR), and a
  **horizontal reference bar** (green normal zone + value marker, red when out of range).
- Kept the quick-log modal + FAB; friendly empty state.

## Frontend-only — no backend / migration / workflow

- **No backend change** — trend is computed client-side from the metric history; reference ranges +
  `higher_is_better` come from the existing **v1.1.0 lab-reference catalog**.
- **No DB migration** (DB head stays `hmbk_backfill`). **No workflow change**, no new deps → fast build.
- DigitalOcean production is `[deploy-do]`-opt-in and untouched.

## Quality gates (local)

- Frontend `tsc` / `eslint` / `build` clean (`/metrics` 4.79 kB). Backend untouched (**643 passed /
  1 skipped**).
- Live local Playwright iPhone 14 Pro: 4 category groups (Đường huyết/Lipid/Gan/Thận); Glucose 140
  ↗ +5 red, Cholesterol +15 red, **HDL ↓ −3 red** (higher_is_better reverse), AST/Creatinine in-range
  green marker.

## New files

- `lib/metrics/kpi.ts` — grouping, trend, themes, ref-bar geometry.
- `components/patient/metrics/{MetricKpiCard,MetricCategoryGroup,TrendArrow,RefRangeBar}.tsx`.
