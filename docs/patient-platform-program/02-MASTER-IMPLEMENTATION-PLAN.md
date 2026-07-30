# MetoCare Patient Platform — Master Implementation Plan

**Version:** 1.0 (single owner-approval gate)
**Date:** 2026-07-30
**Companion to:** `00-CAPABILITY-AUDIT.md`, `01-CONSOLIDATED-BRD.md`
**Governance:** After the owner approves this plan once, execution is autonomous to the release candidate. Internal milestones below are NOT owner gates.

---

## 1. Architecture

### 1.1 Bounded contexts (final)
Reuse existing contexts; add three.
- **Existing (reuse):** Identity/Auth · Patient Profile/PHI · Lab/Biomarker · Medication · Medication Knowledge (K2) · Clinical Insight · Meto AI · Consultation/Marketplace · Clinic SaaS · Audit/Consent · Notification (in-app).
- **NEW → Medical Document Intelligence (MDI):** owns document artifacts, classification, OCR orchestration, extraction, review lifecycle, and **promotion** into the existing Lab/Medication/Diagnosis contexts. MDI never owns canonical clinical data — it produces candidates the domain contexts accept.
- **NEW → Object Storage:** thin abstraction (`StorageBackend` interface) with a local-disk adapter (dev) and Azure Blob adapter (staging), signed-URL issuance, per-object authorization.
- **NEW → Notification Delivery:** transport layer (APNs/FCM push + email) behind a `NotificationTransport` interface, driven by a scheduler for reminders.

### 1.2 Mobile architecture
- **Framework (default, ADR-01):** Expo (React Native) + expo-router, TypeScript, reusing the existing Liquid Glass design tokens from `mobile/design-reference` and the web design system. Rationale: fastest path to iOS+Android internal builds, EAS build/submit, OTA for staging, matches prior design intent. *(Owner may override → native SwiftUI/Kotlin; see §Owner Decisions.)*
- **Layers:** `api/` (typed client mirroring `frontend/src/lib/api`) · `features/` (screen modules per BRD capability) · `components/` (design-system) · `store/` (lightweight; React Query for server-state) · `secure/` (Keychain/Keystore token store) · `native/` (camera, file picker, push).
- **Env separation:** `dev` (local backend) / `staging` (ACA) via EAS build profiles + `expo-constants`.

### 1.3 Final data flows
1. **Document-first ingestion:** Mobile camera/PDF → request signed upload URL → PUT bytes to Object Storage → `POST /documents` (hash, type-hint) → MDI: preprocess → classify → route to extractor (prescription | lab | general) → OCR engine (Tesseract default, cloud fallback opt-in) → entity extraction → normalization → per-field confidence → `needs_review` draft → mobile review UI → confirm → **promote** to Lab/Medication/Diagnosis + Timeline + Notification("result ready").
2. **Reminder loop:** Structured medication schedule → scheduler computes due doses → Notification Delivery (push) → patient taps → adherence logged → dashboard/timeline update.
3. **Meto:** confirmed-data context only → gateway (safety in/out) → audited response with source badges.

### 1.4 OCR / provider abstraction (staged, swappable)
Define explicit stage interfaces so any provider swaps without touching the patient domain:
`Preprocessor` → `OcrEngine` (Tesseract | AzureDocIntel | AnthropicVision | Mock) → `EntityExtractor` (per doc type) → `Normalizer` → `ConfidenceScorer` → `ReviewGate` → `Promoter`. Unify the two current OCR stacks onto this; retire skeleton `ocr.py:OCRProvider`. Deterministic **local test adapter** (`MockOcrEngine` + golden fixtures) is the CI default — cloud credentials are never a blocker for core dev.

### 1.5 Document-storage model
`MedicalDocument(id, patient_id, sha256, storage_key, doc_type, page_count, source, uploaded_at, status, superseded_by)` · `DocumentPage(document_id, page_no, storage_key, ocr_raw, blocks_json)` · `DocumentExtraction(document_id, schema_version, provider, model, prompt_version, fields_json, field_confidence_json, review_state, reviewer_id, corrections_json)` · links: `promoted_lab_result_id` / `promoted_medication_id` / `encounter_id` / `consultation_id`. **Canonical state set:** `uploaded · preprocessing · processing · needs_review · partially_confirmed · confirmed · rejected · failed · superseded`.

### 1.6 Confidence & review model
Reuse `ConfidenceDetail` (ocr/mapping/conversion/clinical → weighted). Thresholds (config, per doc type): `≥ auto_display`, `review_band → mandatory review`, `< reject → re-upload`. High-risk fields (medicine name, strength, dose, numeric lab result, unit) **always require confirmation** regardless of confidence. Unit conversion below confidence → keep original, flag, no silent normalize.

---

## 2. Backend contracts (new/changed)

- **MDI:** `POST /documents/upload-url` · `POST /documents` · `GET /documents` · `GET /documents/{id}` · `GET /documents/{id}/file` (signed) · `GET /documents/{id}/extraction` · `POST /documents/{id}/confirm` (all/selected) · `POST /documents/{id}/reject` · `DELETE /documents/{id}`.
- **Medication schedule/reminder:** `POST/GET/PATCH /patients/{id}/medications/{mid}/schedule` · `GET /patients/{id}/reminders/due` · reminder events emitted to Notification Delivery.
- **Reconciliation:** `GET /patients/{id}/medication-statements?pending=1` · `POST …/statements/{sid}/accept|merge|reject`.
- **K2 lifecycle API (admin/doctor):** wrap `knowledge_repository` writes — `POST /knowledge/drafts/{id}/submit|approve|retire|reject` + list pending. Flip `MEDICATION_KNOWLEDGE_RETRIEVAL` on in staging.
- **Notifications:** `POST /devices` (register push token) · `GET/PATCH /notification-preferences` (server-side) · internal scheduler.
- **Account:** `POST /account/export` · `POST /account/delete`.
- All new endpoints: patient-owned BOLA check via `PatientProfile.id`, audited, flag-gated where risky.

## 3. Migration strategy
Additive-first, reversible, data-preserving defaults, SQLite↔Postgres parity, real-Postgres execution, populated-data downgrade guards. **One migration per merged PR, always branched off the current single head.** New tables: `medical_documents`, `document_pages`, `document_extractions`, `medication_schedules`, `device_tokens`, `notification_preferences`. **CI single-head gate added** (`alembic heads | wc -l == 1`) — see §7.

## 4. Test strategy
Pyramid: unit · service · API-contract · migration · authorization/**BOLA matrix** · OCR deterministic-fixture (per field) · mobile component · mobile integration · E2E · device · staging smoke. Required E2E journeys (BRD §Test): onboarding · prescription→meds · reminder/adherence · lab→result→trend · report→timeline · Meto-on-confirmed · discovery/booking · consented access · consultation-with-history · revocation/masking · account export · account delete. **Autonomous review loop per batch:** implement → targeted tests → regression → independent fresh-context review (source+tests, not self-report) → classify P0/P1/P2 → fix all P0/P1 → re-review → integrate → re-run E2E. No owner return between steps.

## 5. Rollout & evidence strategy
Staging-only via existing ACA CD; internal iOS (TestFlight) + Android (internal track) via EAS. Fixture documents = synthetic/authorized VN prescriptions + lab reports (extend `ocr_dataset/`). Evidence continuously accumulated into `docs/patient-platform-program/evidence/` (test summaries, OCR field-accuracy, security review, screenshots, demo video paths, commit/PR/build IDs). No secrets or local paths in committed evidence.

## 6. Security controls (hardening backlog, P0/P1)
Fix consent fail-open (default-deny) · replace committed default `secret_key`/`encryption_keys` with fail-closed env validation · enforce MFA per policy + password policy · object-storage signed URLs + retrieval authorization · upload rate-limit + AV posture + type/size (reuse magic-byte sniff) · mobile secure token storage · Meto confirmed-data restriction + flag/consent gate · no PHI in logs/analytics · BOLA matrix · retention + export + delete.

---

## 7. Workstream ownership (persistent team)

| # | Workstream | Owner role | Primary surface | Isolation |
|---|---|---|---|---|
| WS0 | Program orchestration, integration order, decision/risk logs | **Program Lead** | this dir | — |
| WS1 | Mobile foundation + build/release | Patient Mobile Lead | `mobile/` | own branch |
| WS2 | Medical Document Intelligence + Object Storage | Medical Doc Intelligence Lead | `backend/app/{models,services,api}` MDI | worktree |
| WS3 | Prescription + General-report extractors + OCR staging | Medical Doc Intelligence Lead (2nd) | `backend/app/services/ocr*`, `domain/` | worktree |
| WS4 | Lab-report OCR mobile journey (reuse) | Backend/API Lead | labs + mobile | branch |
| WS5 | Medication schedule/reminder + reconciliation + K2 API | Medication & Clinical Data Lead | medication + knowledge | worktree |
| WS6 | Notification Delivery (push/email) + scheduler | Backend/API Lead (2nd) | notification | worktree |
| WS7 | Timeline unification + Dashboard + Meto confirmed-data | Backend/API + UX Lead | timeline/insight/meto | branch |
| WS8 | Marketplace mobile + payment abstraction | Backend/API Lead (3rd) | consultation + mobile | branch |
| WS9 | Security/consent/PHI hardening + BOLA matrix | Security & Compliance Lead | cross-cutting | serialized |
| WS10 | Test automation, E2E, CI single-head gate, staging smoke | Test/QA Lead | ci + tests | branch |
| WS11 | Independent fresh-context review (all batches) | Independent Review Lead | read-only | — |
| WS12 | Release + evidence package + internal builds | Release/Evidence Lead | evidence + EAS | — |

**Concurrency rule:** no two workstreams edit the same file without explicit ownership handoff via WS0. File-mutating parallel work uses git worktrees. WS9 (security) changes to shared config are serialized.

## 8. Dependency graph (critical path)

```
WS0 (orchestration) ─ underpins all
Foundations (parallel, week 1):
  WS1 mobile shell/auth ──┐
  WS2 MDI + Object Storage ┼─► WS3 prescription/general extractors
  WS6 Notification Delivery ┘        │
                                     ▼
  WS4 lab mobile ──────────────► M3/M4/M7 document journeys (need WS1+WS2)
  WS5 med schedule/reminder ──► needs WS6 (push) ──► M6 reminder journey
  WS7 timeline/dashboard/Meto ─► needs WS2 (docs), WS5 (adherence), confirmed-data
  WS8 marketplace mobile ──────► needs WS1 only (backend done)
  WS9 security hardening ──────► gates R release (esp. object-storage authz, consent, Meto)
  WS10 CI/E2E ────────────────► continuous; single-head gate lands week 1
  WS11 review ────────────────► per batch, continuous
  WS12 evidence/builds ───────► M1 first build early; final package at RC
```
**Longest chain:** WS1+WS2 → WS3 → prescription E2E → WS7 timeline → WS9 security sign-off → RC.

## 9. Internal milestones (not owner gates)

| M | Milestone | Depends on | Exit criterion |
|---|---|---|---|
| M0 | Audit + approved BRD/plan + team + CI single-head gate | — | this doc approved; gate merged |
| M1 | Mobile foundation + auth + first internal iOS/Android build | WS1, WS12 | login→dashboard on device |
| M2 | Object Storage + MDI foundation (artifact/classify/review lifecycle) | WS2 | upload→stored→classified→needs_review |
| M3 | Prescription OCR end-to-end (mobile) | M1,M2,WS3 | photo→confirmed meds+schedule on device |
| M4 | Lab-report OCR end-to-end (mobile) | M1,M2,WS4 | photo→confirmed result→trend on device |
| M5 | Health timeline + dashboard (mobile) | M2,M4,WS7 | unified timeline + decision-first dashboard |
| M6 | Medication reminders + adherence | M3,WS5,WS6 | scheduled push→adherence logged on device |
| M7 | General medical-report OCR | M2,WS3 | report→timeline summary+source |
| M8 | Meto AI (confirmed-data) mobile | M4,M5,WS7 | explain-confirmed-result on device |
| M9 | Doctor marketplace continuity (mobile) | M1,WS8 | booking→consultation→review on device |
| M10 | Security/ops hardening complete | WS9 (all) | P0/P1 closed; BOLA green; export/delete |
| M11 | Full regression + release candidate + evidence | all | Program DoD met; final package |

## 10. Risk register (top)

| Risk | Sev | Control |
|---|---|---|
| Parallel migrations → divergent Alembic heads | HIGH | CI single-head gate (M0); one migration/PR off current head; WS0 serializes migration merges |
| Two OCR stacks + chat-only provider registry drift | MED | Unify onto staged interface (§1.4); retire skeleton |
| Object-storage authz bug leaks PHI | HIGH | WS9 signed-URL + retrieval authz + BOLA matrix before any real doc in staging |
| Meto leaks unconfirmed data | HIGH | WS7 confirmed-data filter + flag/consent gate + existing SafetyGuard tests |
| OCR accuracy below threshold on VN docs | MED | Per-field eval harness + mandatory-review bands; ship review-gated, not auto-accept |
| No signing identity / push creds (external) | BLOCKER | Owner-provided (see §Owner Decisions); until then EAS internal-dev + simulator + email fallback |
| AI meto-gate flakiness throttles merges | MED | Deterministic mock gate in CI; cloud only in nightly |
| Suite runtime at high merge frequency | MED | Diff-based selection + sharding (WS10) |

## 11. No-production assumptions
No production deploy. Staging (ACA), preview, TestFlight/internal Android, test data, mocks, migrations on staging DB only. DigitalOcean untouched. Admin accounts not seeded. Never `--no-verify`.

---

## 12. Owner Decisions Required (single gate)

**Defaults I will proceed with unless overridden (routine → not blocking):**
1. Mobile stack = **Expo React Native** (ADR-01).
2. OCR default engine = **Tesseract local**; cloud fallback = **Azure Document Intelligence**, opt-in per upload, flag-gated.
3. Payment = **abstraction with mock adapter**; no real gateway wired in this program.
4. Object storage staging adapter = **Azure Blob** (matches ACA); local disk for dev.
5. Enable in **staging only**: `OCR`, `MEDICATION_KNOWLEDGE_RETRIEVAL`, Meto flag (post confirmed-data fix). Production untouched.

**Hard external inputs — the relevant workstream is BLOCKED without these (permitted stop conditions), all others proceed:**
- **A. Apple Developer + Google Play signing identity** → required for TestFlight / internal Android *distribution*. Until provided: build unsigned/simulator + EAS internal dev builds; distribution deferred.
- **B. APNs key + FCM project** → required for real device push. Until provided: in-app + email fallback; reminders queue but don't push to device.
- **C. Azure Document Intelligence key + PHI-to-cloud authorization (BAA/consent posture)** → required for cloud OCR fallback. Until provided: Tesseract-local only (still fully functional for the journeys).
- **D. (Optional) Real payment gateway (e.g. VNPay/MoMo) credentials** → only if you want real payments; otherwise mock abstraction ships.

**Confirm or override:** items 1–5 defaults, and provide A–D where you want them live now vs deferred.
