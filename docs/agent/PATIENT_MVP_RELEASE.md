# Patient App MVP — Functional Completion Release

> **Status:** MVP GATE **10/10 PASS** (local, 2026-06-20)
> **Track:** Patient App MVP Functional Completion (Phase B execution)
> **Target env:** Azure Container Apps **staging** (Singapore). DigitalOcean production untouched.

## MVP-Done — 10/10

E2E verified against the real backend with feature flags at **production defaults (AI/OCR OFF)**:

| # | Point | Status | Backed by |
|---|-------|--------|-----------|
| 1 | Tạo tài khoản | ✅ | register → tokens → `/auth/me` patient_id |
| 2 | Hoàn thiện hồ sơ | ✅ | `/onboarding` wizard + profile PATCH (extended fields) — PR-A |
| 3 | Nhập / tải xét nghiệm | ✅ | manual structured lab entry (no OCR) — PR-B |
| 4 | Dashboard chỉ số | ✅ | metabolic-score plural-path fix + metric tiles — PR-C |
| 5 | Nhận care plan | ✅ | patient views ACTIVE care plans |
| 6 | Theo dõi thuốc | ✅ | add/edit/delete + frequency — PR-D |
| 7 | Theo dõi tiến triển chỉ số | ✅ | metric log + trend chart — PR-C |
| 8 | Nhận notification | ✅ | list + mark-read + persisted prefs — PR-F |
| 9 | Đăng xuất / đăng nhập lại | ✅ | logout revoke + re-login |
| 10 | Toàn flow không AI thật | ✅ | AI/OCR flags OFF → 503; mock mode — PR-B |

## PRs in this release (all merged to main)

| PR | Title | Backlog |
|----|-------|---------|
| #15 | metrics: metabolic-score 404 fix + taxonomy consolidation + trend chart | P0-1, P0-2, P1-2 |
| #16 | profile: onboarding wizard + extended profile fields | P1-1 |
| #17 | medications: real add/edit/delete + frequency | P1-4 |
| #18 | settings: password/email change + notification prefs | P1-5 |
| #19 | labs: manual lab-result entry + AI/OCR feature-flag gating | P1-3, open-Q2/Q5 |

**Deferred (P2):** PR-E care-plan progress UI; medication adherence (mark-as-taken); real lab file upload + OCR; forgot-password; single-resource GET endpoints.

## Quality gates

- Backend `pytest`: **555 passed / 1 skipped** (baseline was 535/1).
- Frontend: `tsc --noEmit` clean · `next build` pass · `next lint` clean.
- 3 additive migrations (medications.frequency; users.notify_*). All nullable/defaulted — safe on existing rows.

## Deploy notes

- Deploy to Azure staging via the **"Azure Staging Deploy"** workflow (`workflow_dispatch`). DigitalOcean production is opt-in only (`[deploy-do]` tag) and is **not** touched by this release.
- Keep the AI/OCR feature flags **unset** on staging → default OFF (no real AI; OCR/AI routes return 503). To enable later: `FEATURE_OCR` / `FEATURE_AI_ASSISTANT` / `FEATURE_AI_RECOMMENDATION` (or `MCP_FEATURE_*`).
- Post-deploy: run the 10-point smoke against staging.
