# Patient App UI Replacement — Before / After

PR #53 · branch `feat/patient-ui-replacement` · deployed to Azure staging (run 28000032851).
Staging: https://ca-metocare-frontend.wittyflower-55a3afa4.southeastasia.azurecontainerapps.io

> AFTER screenshots are local captures of the exact committed code (seed patient with real abnormal data); staging serves byte-identical code. Staging UAT requires a staging patient login.

## Dashboard — structural change (READ-REPORT → DECISION-FIRST)

| | BEFORE (origin/main, PA-11) | AFTER (this PR) |
|---|---|---|
| Paradigm | Read-report: 9 stacked sections | Decision-first: 5 blocks |
| Top of screen | Greeting + status hero | Health Score (score/risk/abnormal) scannable in 1s |
| Primary focus | Insight cards + "what changed" + trends (long text) | **Health Priority Engine** DecisionCard: #1 thing + risk + action + 52px CTA |
| Sections | Hero · Tóm tắt · Việc cần làm · Chỉ số cần chú ý (InsightCards) · Điều gì thay đổi · Xu hướng · Xét nghiệm · Thuốc | Health Score · Priority Engine · KPI Row (4) · Today's Actions · Recent Metrics 2×2 |
| Long clinical text on dashboard | Yes (insight cards, meaning/risk/advice inline) | **No** — moved to the metric detail read-mode screen |
| Metric tap | `/metrics?type=` (list filter) | `/metrics/[metricType]` read-mode detail |
| Theme | Mixed (PA-11 light + leftover) | Single Mint Liquid Glass, light only |

**AFTER:** `v3-dashboard-decision-first.png`, `v3-dashboard-kpi-row.png`

## Metric Detail — NEW read-mode screen

| BEFORE | AFTER |
|---|---|
| No dedicated detail screen (insights lived on dashboard) | `/metrics/[metricType]` read-mode: value+trend → Ý nghĩa → Nguy cơ → Khuyến nghị lối sống → Theo dõi/khám → history chart with normal-range band → disclaimer. Wired to existing `GET /insights/{metric_type}`. Bottom nav hidden; back button. |

**AFTER:** `v3-metric-detail-glucose.png`

## Labs / Medications / Profile

| Screen | BEFORE | AFTER |
|---|---|---|
| Labs | design-system mix (Card/Badge), OCR-flag gated | Mint Liquid Glass list + upload, same data layer (getLabResults, ocr flag, test_date). `v3-labs.png` |
| Medications | modal CRUD, generic list | Mint daily-schedule cards, same CRUD (add/edit/delete); local-only "Đã uống" flagged TODO(backend). `v3-medications.png` |
| Profile | PageHeader/FormField mix | Identity hero + grouped glass sections, all 12 fields + PUT preserved, DOB DD/MM/YYYY. `v3-profile.png` |

## Acceptance (decision-first)
- 3-second test: score + "Nguy cơ cao" + "Ưu tiên số 1" → patient knows status + next action. PASS
- 2-minute test: detail screen explains meaning / trend / risk / recommendation. PASS
- Bottom nav → 5 official hubs only; deep screens use back button. PASS
- Light Mint Liquid Glass, one design language per screen. PASS

## Routes removed (mockups) → official
`/home`→`/dashboard`, `/meds`→`/medications` (redirect). Removed: exercise, log, reports, my-appt, my-doctor, achievements, alerts, p-*, standalone nutrition/notifications/settings, welcome, onboarding/setup. Official patient IA unchanged.
