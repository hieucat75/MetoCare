# Patient App — Lab Exam Date (test_date) v1.0.7

> **Release:** v1.0.7 · **Target:** Azure Container Apps staging (Singapore) · DigitalOcean production untouched.
> **Source PR:** #33 (`feat/patient-lab-test-date`, squash-merged `44d1651`).

## What ships

Lab records now carry the **real exam date** (when the sample was taken), distinct from the upload
timestamp — a report can be months old, so history + trends must be chronological by exam date.

- **OCR date extraction** (`lab_parser.parse_test_date`): detects the exam date from the report text.
  Priority labels (sample/collection > test > performed > result > **printed last**), VN + EN,
  formats `DD/MM/YYYY` (`/ . -`) and `ngày DD tháng MM năm YYYY`, calendar-validated. Returns null when
  absent — **never defaults to today**.
- **`/lab-uploads` draft**: adds `extracted_test_date`, `test_date_label`, `test_date_confidence`.
- **`POST /patients/{id}/lab-results`**: `test_date` is now **required** + validated (≤ today, within 50
  years → `422`).
- **`GET …/lab-results`**: sorts by **`test_date` DESC** (nulls last), `created_at` tiebreak.
- **Frontend**: `/labs/upload` review form shows a prominent "Ngày xét nghiệm" field at the top,
  prefilled from OCR with a "Tự động phát hiện" badge (empty + required when not detected, masked
  `DD/MM/YYYY`); manual-entry modal requires it; `/labs` list shows the exam date prominently with the
  upload date muted + clearly distinct.

## No migration / no workflow / no new deps

- **No DB migration** — the `lab_results.test_date DATE` column already existed (DB head stays
  `pauth_user_phone`).
- **No workflow change** — OCR is already enabled on staging since v1.0.6 (`MCP_FEATURE_OCR=true`); cloud
  OCR stays OFF (`MCP_FEATURE_OCR_CLOUD_FALLBACK=false`, no keys). No new system/Docker dependencies, so
  the build is faster than v1.0.6.
- `/metrics` trend charts use `health_metrics`, not lab data — unaffected.

## Quality gates (local)

- Backend `pytest` **624 passed / 1 skipped** (+13 tests: date-parser priority/none/impossible, draft
  date fields, required/future/too-old 422, sort DESC); `ruff` clean.
- Frontend `tsc` / `eslint` / `build` clean.
- Live local real-Tesseract + Playwright iPhone 14 Pro: dated JPG → review prefills `15/10/2024` + badge;
  no-date JPG → empty + required; two uploads → `/labs` sorted by exam date DESC.
