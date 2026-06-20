# Patient App MVP — Functional Completion Backlog (Phase A)

> **Track:** Patient App MVP Functional Completion
> **Phase:** A (Audit + Backlog) — **NO code changes in this PR.**
> **Date:** 2026-06-20
> **Method:** Read code + endpoint map + test inventory (pytest baseline 535 pass / 1 skip). 3 parallel evidence-based audits (frontend routes, backend capabilities/RBAC/tests, E2E auth + API wiring). Spot-verified the headline mismatches by hand. No DO production touched, no infra reopened.
> **Source of truth:** the current system, per PTH directive.

---

## TL;DR

The **backend is essentially MVP-complete**: all 9 patient capabilities are real, DB-backed (SQLAlchemy services), RBAC-enforced (patient-owns-resource on every patient-scoped route), and test-covered (no zero-coverage capability). AI/OCR is **OFF by default** (OCR = mock, real provider raises `NotImplementedError`; AI routes role-gated and mock-logic).

The gaps are **almost entirely in the frontend wiring and UX**, not the backend. There is **no mock-data layer** in use (`src/lib/mock/index.ts` is an empty stub) — pages call the real API. But two genuine frontend↔backend contract bugs make real data render as "empty," and several routes have placeholder UX.

- **Story-level MVP score: 6 ✅ / 4 🟡 / 0 hard-🔴.** No story crashes, but 4 of the 10 MVP-Done points currently *look* broken or incomplete.
- **2 P0** (silent-broken real data on the dashboard/metrics — blocks MVP-Done points 4 & 7), **5 P1**, **5 P2**.
- **6 PRs proposed**, execution order led by **PR-C** (both P0s, frontend-only, ~1 day).

---

## Phase A.1 — E2E User-Story Walkthrough (9 stories)

| # | Story | Status | Evidence |
|---|-------|--------|----------|
| 1 | **Đăng ký** | ✅ functional | `register/page.tsx:120` → `auth.ts:53` `POST /auth/register` → `auth.py:31`. Returns access+refresh, `setTokens()` immediately → user logged in, redirect `/dashboard`. No separate login needed. |
| 2 | **Onboarding hồ sơ** | 🟡 partial | Register **auto-creates an empty** `PatientProfile` (`services/auth.py:55-57`), so `patient_profile_id` is non-null from first `/auth/me`. **But no onboarding screen/nudge** — profile starts blank; user must manually go to `/profile` → "Chỉnh sửa". No validation on the form. |
| 3 | **Nhập/chụp kết quả xét nghiệm** | 🟡 partial | Manual entry works: `labs/page.tsx:177` `POST /patients/{id}/lab-documents` with a **synthetic `storage_key`** (`pilot/manual/...`). No real **file upload** (metadata-only by design; pilot notice at `labs/page.tsx:223`). OCR off → acceptable for the "Nhập **hoặc** tải" OR-condition. |
| 4 | **Xem dashboard sức khỏe** | 🟡 partial | `dashboard/page.tsx:129-146` fans out to real metrics/meds/care-plans/notifications/labs. **BUT the metabolic-score card is permanently empty** due to a path+shape mismatch (P0-1), and metrics may not show due to taxonomy split (P0-2). |
| 5 | **Nhận care plan** | ✅ functional | `care-plan/page.tsx:125` → `GET /care_plans?patient_id=` → `care_plans.py:171`. Patient views doctor-authored plans; backend 403s cross-patient. Read-only by design. |
| 6 | **Theo dõi thuốc** | ✅ functional | `medications/page.tsx:105` → `GET /patients/{id}/medications` → `patients.py:380`. Real list. View-only (doctors prescribe). Card shows some hardcoded placeholder strings (P1-4). |
| 7 | **Theo dõi chỉ số** | 🟡 partial | Log + list real: `metrics/log` → `POST /patients/{id}/metrics` → `health.py:68`. **But trend chart is a hardcoded placeholder box** (`metrics/page.tsx:90`), and the **two metric clients use divergent type vocabularies** (P0-2) → "logged but not shown" risk. |
| 8 | **Nhận notification** | ✅ functional | `GET /notifications` + `PATCH /notifications/{id}/read` (`notifications.py:63,107`), optimistic mark-read, scoped to caller. |
| 9 | **Cập nhật hồ sơ / đăng xuất-đăng nhập lại** | ✅ functional | Profile PATCH (`patients.py:148`) works. Logout clears tokens + redirect `/login` (`context.tsx:67`); login (incl. 2-step MFA) restores session. Token in `localStorage.meto_access` (+`meto_refresh`), silent 401→refresh (`client.ts:88`). |

---

## Phase A.2 — Route Audit (9 patient routes)

Legend: **DS** = data source. All "real API" = `src/lib/api/*`, no mock layer in use.

| Route | Status | Backend endpoint(s) | Main gap |
|-------|--------|---------------------|----------|
| `/dashboard` | 🟡 | aggregates many (real) | **Metabolic-score tile dead** (404 silent, P0-1); metric tiles may miss data (P0-2). Otherwise real, graceful per-section empty states. |
| `/labs` | 🟡 | `GET/POST /patients/{id}/lab-documents` ✅ | List real; "upload" is **metadata-only** with fabricated `storage_key`. No real file binary (P1-3). |
| `/nutrition` | ✅ | `GET/POST /patients/{id}/nutrition` ✅ | Real list + AddMeal modal w/ validation. Solid. |
| `/medications` | 🟡 | `GET /patients/{id}/medications` ✅ | Card fed **hardcoded** `frequency/timing/prescribedBy/status`; "Đã hoàn thành" tab is a **permanent empty state** (backend has no status field). Refill button = no-op stub (P1-4). |
| `/care-plan` | ✅ | `GET /care_plans` (+`/{id}`) ✅ | Real, read-only. Detail page fetches list + `.find()` (works; no patient single-GET — P2-2). |
| `/metrics` | 🟡 | `GET/POST /patients/{id}/metrics`, `/trend` ✅ | **Trend chart = placeholder box** (P1-2). **Two divergent metric clients** `metrics.ts` vs `patient.ts` (P0-2). |
| `/notifications` | ✅ | `GET /notifications`, `PATCH /{id}/read` ✅ | Real, optimistic update, empty/error states present. |
| `/profile` | 🟡 | `GET/PATCH /patients/{id}/profile` ✅ | Real read+save, **no client-side validation**; several typed fields (waist, conditions, allergies) not surfaced in the form (P1-1). |
| `/settings` | 🔴 | — | Notification toggles are **local-only `[MOCK]`** (self-labeled, never persisted); "Đổi mật khẩu" button **disabled**; version hardcoded. Logout + consents link work (P1-5). |

**Backend completeness (capabilities behind these routes):** ✅ all real & RBAC-enforced. user→patient_id resolved by `GET /auth/me` querying `PatientProfile.user_id == user.id` (`auth.py:136-140`). Feature flags `AI_TRIAGE / AI_LAB_INTERPRET / AI_CARE_PLAN_DRAFT / AI_SAFETY_LAYER` default-OFF but **not enforced in code** (mitigated: OCR mock-only, AI mock-logic, AI_SERVICE role excluded) → P2-3 hygiene item.

**Out-of-9 but present:** `/ai-assistant`, `/symptoms`, `/consents` exist; `/forgot-password` is a non-functional stub (no backend `password-reset` endpoint) → P2-1.

---

## Phase A.3 — Backlog P0 / P1 / P2

### P0 — blocks an MVP-Done point (patient cannot truly achieve it)

| ID | Item | MVP point | Cluster | Scope | Depends-on |
|----|------|-----------|---------|-------|-----------|
| **P0-1** | **Metabolic-score path+shape mismatch.** FE calls `GET /patients/{id}/metabolic-score?limit=1` (singular) expecting `MetabolicScore[]`; backend is `/metabolic-scores` (plural) returning `{patient_id,total,items,trend}` → **404 every time, swallowed by try/catch** → dashboard shows "Chưa có điểm chuyển hóa" forever. | #4 | PR-C | **FE only.** Fix path → plural, parse `.items[0]`. ~1-line + parse. Add a regression test (msw/contract or e2e). | — |
| **P0-2** | **Divergent metric taxonomies.** `metrics.ts` uses `blood_pressure`/`spo2`; `patient.ts` (+dashboard) uses `blood_pressure_systolic`/`hba1c`/`cholesterol_*`. Backend `metric_type` is a free `str` (no enum), so both write OK but a value logged as `blood_pressure` never renders in a dashboard tile querying `blood_pressure_systolic`. | #4, #7 | PR-C | **FE consolidation** to one canonical `MetricType` (backend accepts any string). Pick canonical set, delete the duplicate client, update log form + tiles. Add unit test on the mapping. | open Q1 |

### P1 — important for UX / data integrity (has workaround)

| ID | Item | Cluster | Scope | Depends-on |
|----|------|---------|-------|-----------|
| **P1-1** | **Profile onboarding + validation.** Add a "complete your profile" nudge/banner (or soft redirect) when key clinical fields are empty after register; add client-side validation; surface missing fields (waist, known_conditions, allergies). | PR-A | FE form work; backend already accepts these fields (`patients.py:148` upsert). No migration. | — |
| **P1-2** | **Metrics trend chart.** Replace `TrendChartPlaceholder` grey box with a real chart bound to `GET .../metrics/trend`. | PR-C | FE (chart lib already in stack? verify). Uses canonical types from P0-2. | P0-2 |
| **P1-3** | **Real lab file upload.** Wire object-storage upload so `storage_key` is a real artifact (not fabricated). Removes dead `uploadLab()` helper. | PR-B | FE upload UI + BE pres+ storage config. **Largest.** Manual entry covers MVP point 3 in the interim → can run last. | — |
| **P1-4** | **Medication card honesty.** Stop feeding hardcoded `frequency/timing/prescribedBy/status`; either add the fields backend-side (migration) or hide them; fix/remove the permanent "Đã hoàn thành" empty tab and the no-op refill button. | PR-D | FE; **optional** small BE migration if real frequency/status wanted. | — |
| **P1-5** | **Settings real controls.** Persist notification preferences (new BE endpoint + table) and enable password change (new BE `change-password` endpoint). | PR-F | FE + BE endpoints + migration (prefs) + tests. | — |

### P2 — defer past MVP

| ID | Item | Note |
|----|------|------|
| **P2-1** | Forgot-password flow + backend `password-reset` endpoint. | Login works; not in 10-point list. |
| **P2-2** | Patient-safe single-resource GET for care-plan / medication. | Detail pages use list+`.find()` workaround (O(n), 404-safe for small lists). |
| **P2-3** | Enforce the 4 default-OFF AI flags (`AI_TRIAGE`, `AI_LAB_INTERPRET`, `AI_CARE_PLAN_DRAFT`, `AI_SAFETY_LAYER`) so routes return 503 when off — or remove misleading comments. | Defense-in-depth; mitigations already in place (mock OCR, mock AI, role gating). |
| **P2-4** | Remove dead code (`uploadLab()` in `patient.ts:185`) and brittle MFA detail-string coupling in `login/page.tsx`. | Hygiene. |
| **P2-5** | Care-plan **progress tracking** UI (vs current read-only view). | Enhancement beyond "Nhận care plan". |

---

## Phase A.4 — Proposed Execution Order

Dependency-driven, each PR ≤ 1–3 days, each a small focused PR with `[skip ci]` until the feature is complete + tests pass.

| Order | PR | Contents | Est. | Why this slot |
|-------|----|----------|------|---------------|
| **1** | **PR-C — Metrics & Dashboard Correctness** | P0-1, P0-2, P1-2 | ~1–2 d | **Both P0s.** Frontend-only, no migration, unblocks the two MVP-Done points that currently look broken. Highest value / lowest cost. |
| **2** | **PR-A — Patient Profile Completion** | P1-1 | ~1–2 d | Independent. Improves first-run experience (point 2). FE-only. |
| **3** | **PR-D — Medication Tracking** | P1-4 | ~1 d (FE) / +1 d if BE fields | Independent. Mostly FE honesty; optional small migration. |
| **4** | **PR-F — Settings & Account** | P1-5 (+ P2-1 optional) | ~2 d | Needs new BE endpoints (change-password, notification prefs) + migration + tests. |
| **5** | **PR-B — Lab Upload Flow** | P1-3 | ~2–3 d | **Largest** (object storage). Manual entry already satisfies MVP point 3, so it runs last without blocking MVP-Done. |
| **6** | **PR-E — Care Plan Progress** *(optional/P2)* | P2-5 (+ P2-2) | ~1–2 d | Care-plan already ✅ functional; progress UI is an enhancement. Defer unless desired before Phase 2. |

**Test plan per PR (uniform):**
- `pytest` must stay ≥ baseline **535 pass / 1 skip** (add tests for any new BE endpoint/migration).
- Frontend: Playwright (or manual) on the touched route(s) — load, action, persist, reload.
- After the **final** PR of a complete flow: smoke against Azure staging (deploy via "Azure Staging Deploy" workflow), drop `[skip ci]` only then. Do **not** debug on staging.

**MVP-Done mapping after backlog:** P0-1 + P0-2 → points 4 & 7 truly pass. P1-1 → point 2 robust. Points 1,3,5,6,8,9,10 already pass. Completing **PR-C + PR-A** alone takes the app from "6 ✅" to a credible **10/10 = Patient App MVP Complete**; PR-D/F/B are quality/depth, PR-E is Phase-2-adjacent.

---

## Open Questions (≤5, for PTH before Phase B)

1. **Canonical metric taxonomy (P0-2):** adopt `patient.ts` vocabulary (`blood_pressure_systolic/diastolic`, `hba1c`, `fasting_glucose`, `cholesterol_*`, `weight_kg`, …) as source of truth and add `spo2` to it? (Recommended — it's what the dashboard already reads. Backend stores free strings so no migration.)
2. **Lab file upload (P1-3):** is manual metadata entry sufficient for MVP (OCR is OFF), deferring real file-binary + object storage to Phase 2? (Recommended: defer → PR-B last.)
3. **Settings scope (P1-5):** are password-change + notification-preference persistence in MVP, or Phase 2? `/settings` isn't in the 10-point list except logout, which already works.
4. **Onboarding shape (P1-1):** lightweight "complete your profile" banner + soft redirect, or a full multi-step wizard? (Recommended: banner first, wizard later.)
5. **AI flag enforcement (P2-3):** wire the 4 unenforced default-OFF AI flags now (defense-in-depth), or accept current mitigations (mock OCR/AI + role gating) and defer? (Recommended: defer to Phase 2.)
