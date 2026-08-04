# Web Medication Parity — Status

**Owner question:** *"`https://app.metocare.me/medications/<id>` still looks unchanged even though
the medication journey was reported complete."*

**Status:** IN PROGRESS — diagnosis complete and source-verified; implementation underway.

**Working branch:** `feat/patient-platform-journey2`
**Baseline HEAD at investigation start:** `bfd6735`
**Date:** 2026-08-04

---

## 1. Deployment topology (verified at runtime, not assumed)

| Fact | Value | How verified |
|---|---|---|
| `app.metocare.me` DNS | CNAME → `ca-metocare-frontend.wittyflower-55a3afa4.southeastasia.azurecontainerapps.io` → `4.144.233.112` | `dig +short app.metocare.me` |
| Staging frontend FQDN | `ca-metocare-frontend.wittyflower-55a3afa4.southeastasia.azurecontainerapps.io` → `4.144.233.112` | `azure-staging.yml` run `30797337153` job log |
| ⇒ Conclusion | **`app.metocare.me` and "staging" are the SAME Container App.** There is one live web deployment. | same FQDN + same IP |
| Live web build | `d25f109` (branch `feat/patient-platform-journey2`), built 2026-08-03 08:27Z | `gh run view 30797337153 --json headSha` |
| Live web bundle identity | `/_next/static/chunks/app/(patient)/medications/%5Bid%5D/page-c45586326b373f44.js`, `sha256 6402410aad490c395a5a681c11882d450ac9fe2aa2d08103e02ffd2e8ae13f2b` — **byte-identical** fetched via `app.metocare.me` and via the staging FQDN | `curl` + `shasum -a 256` |
| Backend the web talks to | `https://ca-metocare-backend.wittyflower-55a3afa4.southeastasia.azurecontainerapps.io/api/v1` (baked in as `NEXT_PUBLIC_API_URL`) | string extraction from the served chunks |
| Backend build | `d25f109`, `migration_version: j4_m8_consent_versioning` | `GET /api/v1/info` |
| `rg-metocare-prod` Container App | last deployed 2026-07-14 from `30a65eb` — **no DNS points at it** | `gh run list --workflow=azure-production.yml` |

### 1.1 The "stale production deployment" hypothesis is REFUTED

An initial pass suggested production was serving a pre-`PR-M2/M3/M4` build. That was an
artefact of grepping the minified bundle with literal UTF-8 while the bundle hex-escapes
some characters (`Thêm tuỳ chọn` is emitted as `Th\xeam tuỳ chọn`). After decoding `\xNN`
and `\uNNNN` escapes, every marker is present in the live bundle:

```
PRESENT: Chi tiết thuốc            (page header)
PRESENT: Thêm tuỳ chọn             (M2 overflow menu trigger)
PRESENT: Tuỳ chọn thuốc            (M2 overflow menu)
PRESENT: Liều dùng / Tần suất      (M2 dose+frequency chips)
PRESENT: Đã uống                   (M2 primary action)
PRESENT: Tuân thủ điều trị         (adherence section)
PRESENT: Cách sử dụng              (M3 UsageInstructionsCard)
PRESENT: Ghi chú của bạn           (M3 note vs guidance split)
PRESENT: Đang tải dữ liệu tương tác thuốc   (M4 InteractionsCard)
PRESENT: Chưa có dữ liệu tương tác được kiểm chứng  (M4 empty state)
PRESENT: Đang tải dữ liệu tác dụng phụ      (M4 SideEffectsCard)
PRESENT: Dấu hiệu cần đi khám ngay          (M4 red-flag block)
PRESENT: Bác sĩ yêu cầu tạm ngừng           (PR-S3 on_hold lock copy)
PRESENT: AI tạo                             (Slice-0 AI provenance badge)
```

**The live web build is current with `origin/main`'s frontend tree. It is not stale, not
flag-gated, and not a compatibility page.**

---

## 2. Branch reality

```
origin/main                     99a3616  (2026-07-29)
feat/patient-platform-journey2  bfd6735  — 42 ahead / 0 behind main
merge-base                      99a3616
```

Files changed by those 42 commits, by tree:

```
backend/app     53      mobile/src        41      docs/patient-platform-program  43
backend/tests   28      mobile/app        20      docs/launch-readiness           6
backend/alembic  3      mobile/__tests__  24
frontend/        0      ← ZERO
```

`git diff --name-only origin/main HEAD -- frontend/` → **0 files**.

**No patient-platform branch has ever touched the web client.**

---

## 3. Root cause

The page the owner is looking at is the **current, intended M1–M4 web design**. It renders
correctly and it is deployed. What it never received is **Journey 2 (documents/OCR) and
Journey 3 (structured schedule + dose occurrences + reminders + dose-level adherence)** —
those were built for backend + mobile only.

Traced route → render:

```
route   /medications/[id]
page    frontend/src/app/(patient)/medications/[id]/page.tsx      (568 lines)
client  frontend/src/lib/api/patient.ts
calls   getMedications()           → GET   /patients/{pid}/medications
        getAdherenceHistory()      → GET   /patients/{pid}/medications/{mid}/adherence
        getAdherenceSummary()      → GET   /patients/{pid}/medications/adherence-summary
        logAdherence()             → POST  /patients/{pid}/medications/{mid}/adherence
        updateMedicationLifecycle()→ PATCH /patients/{pid}/medications/{mid}
model   LEGACY `medication_adherence` table — a free-floating "I took it" record with no
        scheduled dose, no schedule, no timezone, no missed state, no skip reason.
```

Meanwhile the **same backend the page already talks to** exposes the Journey-3 model
(`backend/app/api/v1/routes/medication_schedule.py`, live — `/reminders/due` returns
**401, not 404**):

```
POST   /patients/{pid}/medications/{mid}/schedule       create structured schedule
GET    /patients/{pid}/medications/{mid}/schedule       list schedules (all versions)
PATCH  /patients/{pid}/schedules/{sid}                  edit schedule
POST   /patients/{pid}/schedules/{sid}/pause            pause
GET    /patients/{pid}/reminders/due                    due doses (materialize+sweep+deliver)
POST   /patients/{pid}/doses/{did}/taken                dose-level taken
POST   /patients/{pid}/doses/{did}/skipped              dose-level skipped + skip_reason
GET    /patients/{pid}/schedules/{sid}/adherence        taken/skipped/missed + rate
GET    /patients/{pid}/dashboard                        action-first rollup
```

Mobile consumes all of them (`mobile/src/api/medication.ts`,
`mobile/src/features/medication/useMedicationDetail.ts`,
`mobile/app/(app)/medications/[id].tsx`). **The web client references none of them** — there
is not a single schedule/dose/reminder/document call in `frontend/src/lib/api/`.

So the mismatch is not "the change didn't deploy". It is **"the change was never written for
web"**.

---

## 4. Gap matrix

Legend: ✅ implemented · ⚠️ partial / legacy model · ❌ absent · n/a not applicable.
"Live" is the single deployment described in §1 (`app.metocare.me` == staging Container App),
evaluated for the **web** client.

| Capability | Backend | Mobile | Web (before) | Live now | Evidence |
|---|---|---|---|---|---|
| Medication list | ✅ | ✅ | ✅ | ✅ | `routes/patients.py` medications list; `frontend/src/app/(patient)/medications/page.tsx` |
| Medication detail | ✅ (derived from list — no single-med GET) | ✅ | ✅ | ✅ | `medications/[id]/page.tsx:229` |
| Active/stopped lifecycle state | ✅ | ✅ read-only | ✅ read+write | ✅ | `models/clinical.py:174`; `components/patient/medications/lifecycle.tsx` |
| Structured schedule | ✅ `medication_schedule.py:139,174` | ✅ `listSchedules` | ❌ | ❌ | no schedule call in `frontend/src/lib/api/` |
| Next due dose | ✅ `/reminders/due` | ✅ `useMedicationDetail.nextDue` | ❌ | ❌ | ditto |
| In-app reminder | ✅ `deliver_due_reminders` | ✅ `mobile/app/(app)/reminders.tsx` | ❌ | ❌ | ditto |
| Taken action | ✅ dose-level `POST /doses/{id}/taken` | ✅ | ⚠️ legacy `logAdherence` | ⚠️ | `page.tsx:269` |
| Skipped action | ✅ dose-level `POST /doses/{id}/skipped` | ✅ | ⚠️ legacy `logAdherence({skipped:true})` | ⚠️ | `page.tsx:283` |
| Skip reason | ✅ `MarkDoseIn.skip_reason` | ✅ `markDoseSkipped(reason)` | ❌ | ❌ | `page.tsx:283` sends no reason |
| Adherence summary | ✅ `AdherenceOut` taken/skipped/**missed**/rate | ✅ per-schedule | ⚠️ client-side `taken/len(history)` | ⚠️ | `page.tsx:247-248` — cannot see missed doses |
| Adherence history | ✅ dose occurrences | ⚠️ counts only | ⚠️ legacy records | ⚠️ | `AdherenceHistoryList` in `page.tsx:121` |
| Dose | ✅ | ✅ | ✅ | ✅ | `MedicationOut.dose` |
| Frequency | ✅ free-text | ✅ | ✅ | ✅ | `MedicationOut.frequency` |
| Timing (timezone-aware) | ✅ `patient_timezone`, `local_render` | ✅ | ❌ | ❌ | web has no schedule concept |
| Route (oral/…) | ❌ not modelled | ❌ | ❌ | ❌ | `models/clinical.py:158-199` — no `route` column |
| Instructions | ✅ `note` | ✅ | ✅ | ✅ | `usage-instructions.tsx` |
| Side effects | ✅ knowledge tables (on `main`) | ❌ | ⚠️ card renders, wired to `[]` | ⚠️ | `page.tsx:475` |
| Interactions | ✅ knowledge tables (on `main`) | ❌ | ⚠️ card renders, wired to `[]` | ⚠️ | `page.tsx:474` |
| Monitoring | ❌ not modelled | ❌ | ❌ | ❌ | — |
| Prescription/document source | ⚠️ data exists (`PromotionLink`) but **no read API** | ❌ | ❌ | ❌ | `models/medical_document.py:186`; no route reads it |
| OCR provenance | ⚠️ `source_type`/`verification_status` only | ✅ labels only | ⚠️ badge only | ⚠️ | `lifecycle.tsx` "AI tạo · chờ bác sĩ duyệt" |
| Loading state | n/a | ✅ | ✅ `PatientSkeleton` | ✅ | `page.tsx:323` |
| Empty state | n/a | ✅ | ⚠️ partial | ⚠️ | history list hidden when empty |
| Error state | n/a | ✅ | ✅ `PatientErrorState` + retry | ✅ | `page.tsx:329` |
| Permission / BOLA | ✅ `_require_self` 403 | ✅ | ⚠️ generic error copy | ⚠️ | `page.tsx:253` collapses all errors |
| Responsive behavior | n/a | n/a | ⚠️ `max-w-md` mobile-only, no desktop layout | ⚠️ | `page.tsx:350` |
| Accessibility | n/a | ✅ testIDs | ⚠️ partial (`aria-label` present, no live region / focus mgmt) | ⚠️ | `page.tsx:353,396` |

### 4.1 Confirmed backend gap

Nothing exposes **medication → source document**. The data exists:

```
Medication.id ← PromotionLink.canonical_id  (canonical_type='medication')
              → PromotionLink.candidate_id
              → ExtractionCandidate.document_id
              → MedicalDocument      (doc_type, source, status, created_at)
              → DocumentExtraction   (provider, model, prompt_version)  ← OCR provenance
```

`grep -rn "PromotionLink" backend/app/api/` returns **no route**. The `/documents` API only
walks forward (document → candidates → promotion). A reverse read is required for §F of the
web scope and is genuinely missing in **both** clients.

---

## 5. Implementation summary

_(updated as work lands — see §9 changelog)_

## 6. Tests

_(pending)_

## 7. Review findings

_(pending)_

## 8. Evidence

Screenshots and sanitized runtime logs:
`docs/patient-platform-program/evidence/web-medication-parity/`

Staging / live URL: `https://app.metocare.me` (== `ca-metocare-frontend.wittyflower-55a3afa4.southeastasia.azurecontainerapps.io`)

## 9. Changelog

| Date | Change |
|---|---|
| 2026-08-04 | Initial diagnosis, deployment topology, gap matrix. |

## 10. Production rollout checklist

_(pending — production deployment is NOT authorized by the current instruction)_

## 11. Known limitations

- `route`, `monitoring`, and `contraindications` are **not modelled anywhere** in the
  backend. They are out of scope for parity and must not be invented in the UI.
- Interactions/side-effects knowledge tables exist on `main` but the retrieval endpoint is
  flag-gated and carries no patient-specific pairing engine; the web cards must keep their
  "no verified data" wording rather than imply a check was performed.
- **DNS finding (§1):** `app.metocare.me` resolves to the *staging* Container App. This is a
  material infrastructure observation, reported for owner decision — not changed by this work.
