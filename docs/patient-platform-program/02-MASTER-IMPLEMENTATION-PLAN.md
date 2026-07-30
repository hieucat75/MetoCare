# MetoCare Patient Platform — Master Implementation Plan

**Version:** 1.1 (one-time plan correction — ready for final single owner approval)
**Date:** 2026-07-30
**Companion to:** `00-CAPABILITY-AUDIT.md`, `01-CONSOLIDATED-BRD.md`
**Governance:** After the owner approves this plan once, execution is autonomous to the release candidate. Internal milestones below are NOT owner gates.
**Change log:** v1.1 applies the owner's one-time P1/P2 correction round (findings 1–12) and records owner default decisions. See **Appendix Z — Correction Map** for finding→section traceability.

---

## 1. Architecture

### 1.1 Bounded contexts (final)
Reuse existing contexts; add three.
- **Existing (reuse):** Identity/Auth · Patient Profile/PHI · Lab/Biomarker · Medication · Medication Knowledge (K2) · Clinical Insight · Meto AI · Consultation/Marketplace · Clinic SaaS · Audit/Consent · Notification (in-app).
- **NEW → Medical Document Intelligence (MDI):** owns document artifacts, classification, OCR orchestration, extraction, review lifecycle, and **promotion** into the existing Lab/Medication/Diagnosis contexts. MDI never owns canonical clinical data — it produces candidates the domain contexts accept.
- **NEW → Object Storage:** thin abstraction (`StorageBackend` interface) with a local-disk adapter (dev) and Azure Blob adapter (staging), signed-URL issuance, per-object authorization.
- **NEW → Notification Delivery:** a `NotificationTransport` interface with **four adapters, capability-gated** (finding 11): (1) **deterministic test transport** (records deliveries, CI default); (2) **in-app transport** (DB-backed, always available); (3) **push adapter** (APNs/FCM) — active only when device credentials are configured; (4) **email adapter** — active only when an email provider is configured. No adapter is assumed present; the scheduler always has at least the deterministic + in-app transports, so reminders function at the Engineering RC level without any external credential.

### 1.2 Mobile architecture
- **Framework (ADR-01, APPROVED):** Expo (React Native) + expo-router, TypeScript, reusing the existing Liquid Glass design tokens from `mobile/design-reference` and the web design system. Rationale: fastest path to iOS+Android internal builds, EAS build/submit, OTA for staging, matches prior design intent.
- **Authentication scope (ADR-02, finding 4):** the program uses the **existing email/password `/auth`** (JWT + refresh rotation). Sessions are stored in **Keychain/Keystore** (never AsyncStorage); **optional biometric unlock** gates re-open. Existing MFA is respected (`mfa_enforcement_enabled`). **Phone/SMS-OTP is explicitly DEFERRED** — the repository audit did not establish a phone-OTP backend, and SMS-OTP is not an implicit net-new requirement. Enabling it later requires a dedicated Identity/SMS workstream (out of scope here).
- **Layers:** `api/` (typed client mirroring `frontend/src/lib/api`) · `features/` (screen modules per BRD capability) · `components/` (design-system) · `store/` (lightweight; React Query for server-state) · `secure/` (Keychain/Keystore session store + biometric) · `native/` (camera, file picker, push registration).
- **App installation identifier (ADR-03, finding 6):** a **random UUID generated at first install**, stored in secure storage, **reset on reinstall / account unlink**. It is **never** a hardware ID, serial, IMEI, advertising ID, or device fingerprint. Used only for session/device management, push registration, and specifically justified audit events — **not** attached indiscriminately to every API call.
- **Env separation:** `dev` (local backend) / `staging` (ACA) via EAS build profiles + `expo-constants`.

### 1.3 Final data flows
1. **Document-first ingestion (secure, finding 2):** Mobile → `POST /documents/upload-session` (returns an **upload_id** + a **short-lived, write-only** signed URL to a **server-generated quarantine key**; no read/list scope) → client PUTs bytes → `POST /documents/{upload_id}/finalize` → server validates **owner + sha256 + size + magic-byte MIME + page limits**, runs **malware scan / defined quarantine posture**, and only then moves the object to an **accepted** key → OCR queue (workers process **accepted** objects only) → MDI: preprocess → classify → route to extractor (prescription | lab | general) → OCR engine (Tesseract default, cloud fallback opt-in) → entity extraction → normalization → per-field confidence → **candidate set** in `needs_review` → mobile review UI → per-candidate confirm/reject → **promote** confirmed candidates to Lab/Medication/Diagnosis + Timeline + Notification("result ready"). Full detail in **§1.7**. Every signed **read** URL is authorization-checked at issue time; quarantined/rejected objects expire and are swept.
2. **Reminder loop:** Structured medication schedule → scheduler computes due doses → Notification Delivery (push) → patient taps → adherence logged → dashboard/timeline update.
3. **Meto:** confirmed-data context only → gateway (safety in/out) → audited response with source badges.

### 1.4 OCR / provider abstraction (staged, swappable)
Define explicit stage interfaces so any provider swaps without touching the patient domain:
`Preprocessor` → `OcrEngine` (Tesseract | AzureDocIntel | AnthropicVision | Mock) → `EntityExtractor` (per doc type) → `Normalizer` → `ConfidenceScorer` → `ReviewGate` → `Promoter`. Unify the two current OCR stacks onto this; retire skeleton `ocr.py:OCRProvider`. Deterministic **local test adapter** (`MockOcrEngine` + golden fixtures) is the CI default — cloud credentials are never a blocker for core dev.

### 1.5 Document-storage & promotion model (finding 1 — explicit one-to-many)

A document/extraction promotes to **many** canonical records. Singular `promoted_*_id` fields are **removed** in favor of a dedicated candidate/promotion-link entity.

- `MedicalDocument(id, patient_id, sha256, quarantine_key, accepted_key, doc_type, page_count, source, uploaded_at, status, superseded_by)`
- `DocumentPage(document_id, page_no, storage_key, ocr_raw, blocks_json)`
- `DocumentExtraction(document_id, schema_version, provider, model, prompt_version, extraction_run_id, extracted_at, review_state)` — **immutable** raw provenance; a re-run creates a **new** `DocumentExtraction` row (never mutates the prior one).
- **`ExtractionCandidate(id, extraction_id, candidate_type, ordinal, fields_json, field_confidence_json, dedupe_key, status, corrections_json, reviewed_by, reviewed_at)`** — the one-to-many core. `candidate_type ∈ {medication, lab_result, diagnosis, procedure, finding, recommendation, follow_up}`. `status ∈ {extracted, needs_review, confirmed, rejected, merged, superseded}`. Many candidates per extraction; each independently confirmed/rejected.
- **`PromotionLink(id, candidate_id, canonical_type, canonical_id, action, promoted_at, promoted_by)`** — records the promotion of a **confirmed** candidate into a canonical record. `action ∈ {created, merged_into}`. Gives full **bidirectional provenance**: canonical record → `PromotionLink` → `ExtractionCandidate` → `DocumentExtraction` → `MedicalDocument`/page/bounding-box.

**Idempotency & no-duplicate-promotion constraints:**
- **Unique** `(candidate_id)` in `PromotionLink` where `status=confirmed` → a candidate promotes **at most once**.
- `ExtractionCandidate.dedupe_key` (e.g. hash of normalized medicine+strength+form, or analyte+specimen_date) + **unique** `(extraction_id, dedupe_key)` → re-extraction of the same document does not create duplicate candidates; a new run reconciles to existing candidates by `dedupe_key` and marks divergences `superseded`.
- **Reprocessing** a document produces a new `DocumentExtraction`; already-`confirmed`/`promoted` candidates are **carried forward, not re-promoted**; only genuinely new candidates enter `needs_review`.
- **Merge:** confirming a candidate against an existing canonical record uses `action=merged_into` (no new canonical row).
- **Supersession/correction:** superseding a document sets `superseded_by`; downstream candidates move to `superseded`; canonical records keep their `PromotionLink` history (append-only), so correction history is fully reconstructable.

**Canonical document state set:** `uploaded · preprocessing · processing · needs_review · partially_confirmed · confirmed · rejected · failed · superseded`. (`quarantined` is an object-storage state, not a document status — see §1.7.)

### 1.6 Confidence & review model
Reuse `ConfidenceDetail` (ocr/mapping/conversion/clinical → weighted). Thresholds (config, per doc type): `≥ auto_display`, `review_band → mandatory review`, `< reject → re-upload`. High-risk fields (medicine name, strength, dose, numeric lab result, unit) **always require confirmation** regardless of confidence. Unit conversion below confidence → keep original, flag, no silent normalize.

### 1.7 Secure object-storage ingestion (finding 2)

Direct client-to-blob upload, made safe by a **session → quarantine → finalize → validate → accept** pipeline.

1. **Upload session:** `POST /documents/upload-session` → server generates the **storage key** (client never chooses it), returns `{upload_id, signed_put_url, expires_at}`. The signed URL is **write-only, single-object, short-lived** (minutes), scoped to a **quarantine** container/prefix. **No read and no list** permission is ever granted on an upload URL.
2. **Client upload:** client PUTs bytes directly to the quarantine key.
3. **Finalize:** `POST /documents/{upload_id}/finalize` → server validates **owner** (session belongs to caller's `PatientProfile.id`), **sha256** (matches what the client declared), **size** (≤ cap), **magic-byte MIME** (JPEG/PNG/PDF only, reusing `lab_upload.sniff_mime`), **page limits** (PDF ≤ configured), then runs **malware scan** (or the explicitly-defined quarantine posture when no scanner is configured: object stays quarantined, flagged, never handed to a worker).
4. **Accept:** only on full pass does the server copy/move the object to an **accepted** key and set document `status`. **Workers may read accepted objects only** — the OCR queue never references quarantine keys.
5. **Authorized reads:** every signed **read** URL is issued per-request **after a BOLA check** on the owning `PatientProfile.id`; URLs are short-lived and single-object.
6. **Duplicate detection (BOLA-safe):** dedupe is scoped **within the owning patient** by `sha256` — a hash collision across patients is never treated as a duplicate and never leaks existence of another patient's document.
7. **Cleanup/expiry:** quarantined-but-never-finalized and rejected objects have a TTL and are swept by a scheduled job; accepted objects follow the retention policy.
8. **Rate limiting & abuse:** `POST /documents/upload-session` and `/finalize` are **rate-limited per user** (extending `core/ratelimit.py` to these routes); repeated invalid/oversized/failed-scan uploads trip lockout and an audit event. (Backfills the audit gap F10.)

### 1.8 Medication scheduling design (finding 3)

Only **confirmed** medication data may create a schedule; unconfirmed OCR candidates cannot.

- **`MedicationSchedule(id, medication_id, patient_timezone, schedule_type, local_dose_times[], recurrence, start_date, end_date, status, source, verification_status, dedupe_key, superseded_by, created_at)`**
  - `patient_timezone`: IANA tz (e.g. `Asia/Ho_Chi_Minh`) captured on the patient; **all instants stored in UTC, rendered in local tz**.
  - `schedule_type ∈ {fixed_daily, interval, days_of_week, cyclic, prn}`; `recurrence` holds the structured rule; `local_dose_times[]` are wall-clock times in `patient_timezone`.
  - `status ∈ {active, paused, stopped, completed}`; `source ∈ {manual, prescription_ocr, doctor}`; `verification_status` mirrors the medication (schedule inherits confirmed-only rule).
- **`DoseOccurrence(id, schedule_id, scheduled_utc, local_render, state, idempotency_key, source_schedule_version)`** — materialized dose events; `state ∈ {pending, notified, taken, skipped, missed}`. `idempotency_key = hash(schedule_id, schedule_version, scheduled_utc)`.
- **Scheduler (concurrency-safe):** a periodic worker materializes upcoming `DoseOccurrence`s within a horizon. **Idempotent** via unique `idempotency_key`; **concurrency-safe** via row-level advisory lock / `INSERT … ON CONFLICT DO NOTHING`. A **retry never creates duplicate dose events** (same key ⇒ no-op).
- **Edit/supersession:** editing a schedule creates a **new schedule version** (`superseded_by` chain); already-materialized **past** occurrences are immutable; **future** occurrences are regenerated from the new version. Deduplication prevents double-notifying an already-materialized future slot.
- **Paused/stopped:** `paused` suspends materialization (existing future pending occurrences cancelled); `stopped/completed` ends the schedule; adherence history is retained.
- **PRN (as-needed):** `schedule_type=prn` materializes **no** timed occurrences and fires **no** reminders; the patient logs ad-hoc `taken` events against the medication.
- **Unstructurable OCR frequency:** when a prescription's frequency cannot be **safely** structured (ambiguous/handwritten/low-confidence), **no schedule is created**; the medication is confirmed without a schedule and the patient is prompted to set dose times manually (or a doctor structures it later). The app never guesses dose times.

### 1.9 General medical-report candidate & review model (finding 7)

General-report extraction produces **candidates only** (via `ExtractionCandidate`, §1.5), never canonical clinical facts:

- **Candidate types:** `diagnosis`, `medication`, `procedure`, `finding`, `recommendation`, `follow_up`.
- **Confirmation is per-field/per-candidate;** patient corrections are appended to `corrections_json` (correction history preserved); the raw extraction + original document remain **immutable provenance**.
- **Diagnosis never becomes canonical without explicit confirmation** (and, where policy requires, doctor verification). An unconfirmed diagnosis is display-only and clearly badged.
- **Medication candidates route through reconciliation** (§medication) — they enter as `MedicationStatement`s and reconcile to canonical meds, never bypassing the confirm/verify path.
- **Follow-up:** a `follow_up` candidate creates a task/reminder **only after confirmation** (never auto-scheduled from raw extraction).
- **Doctor verification** can further attest confirmed candidates where consented.

### 1.10 Progressive feature-flag enablement (finding 12)

Feature flags are **not** all enabled at program start. Each is flipped **in staging only**, **after** its owning workstream meets its exit criterion:
- `OCR` → after §1.7 ingestion + lab review pass green (M4 exit).
- `MEDICATION_KNOWLEDGE_RETRIEVAL` → after finding-10 gate (usable reviewed content + provenance + authorization tests + defined empty-state) — **not** merely because the endpoint exists (M-K exit).
- Meto flag → **after** the confirmed-data restriction + flag/consent gate land and SafetyGuard tests pass (M8 exit).
Production flags are never touched.

---

## 2. Backend contracts (new/changed)

- **MDI ingestion (§1.7):** `POST /documents/upload-session` (write-only quarantine SAS) · `POST /documents/{upload_id}/finalize` (validate+scan+accept) · `GET /documents` · `GET /documents/{id}` · `GET /documents/{id}/file` (per-request authorized signed read) · `GET /documents/{id}/extraction`.
- **MDI candidates/promotion (§1.5):** `GET /documents/{id}/candidates` · `POST /candidates/{cid}/confirm` · `POST /candidates/{cid}/reject` · `POST /candidates/{cid}/merge` (into an existing canonical record) · `POST /documents/{id}/reprocess` (new extraction, no duplicate promotion) · `DELETE /documents/{id}` (supersede/delete).
- **Medication schedule/reminder (§1.8):** `POST/GET/PATCH /patients/{id}/medications/{mid}/schedule` · `GET /patients/{id}/reminders/due` · dose occurrences materialized by the concurrency-safe scheduler; reminder events emitted to Notification Delivery.
- **Reconciliation:** `GET /patients/{id}/medication-statements?pending=1` · `POST …/statements/{sid}/accept|merge|reject`.
- **K2 lifecycle API (admin/doctor):** wrap `knowledge_repository` writes — `POST /knowledge/drafts/{id}/submit|approve|retire|reject` + list pending. `MEDICATION_KNOWLEDGE_RETRIEVAL` is enabled in staging **only after the finding-10 gate** (see §1.10 / §9), not on endpoint existence.
- **Notifications:** `POST /devices` (register the **app installation UUID** (ADR-03; BRD §A / Plan §1.2) + push token when available) · `GET/PATCH /notification-preferences` (server-side, fixes web localStorage gap) · internal scheduler.
- **Account:** `POST /account/export` · `POST /account/delete`.
- All new endpoints: patient-owned BOLA check via `PatientProfile.id`, audited, flag-gated where risky.

## 3. Migration strategy (finding 9 — migration-bearing PR policy)
Additive-first, reversible, data-preserving defaults, SQLite↔Postgres parity, real-Postgres execution, populated-data downgrade guards. **A migration is added only when a PR actually requires a schema change** (not one-per-PR); migration-bearing PRs **branch from the verified current single head**, **serialize their merges** (WS0 gates the order so two migrations never fork the head), and use **expand → migrate → contract** for any change that isn't purely additive. Every migration ships with **upgrade/downgrade roundtrip + SQLite↔Postgres parity tests**. New tables (added as their workstreams land): `medical_documents`, `document_pages`, `document_extractions`, `extraction_candidates`, `promotion_links`, `medication_schedules`, `dose_occurrences`, `device_installations`, `notification_preferences`. **CI single-head gate** (`alembic heads | wc -l == 1`) lands in the first batch — see §7.

## 4. Test strategy
Pyramid: unit · service · API-contract · migration · authorization/**BOLA matrix** · OCR deterministic-fixture (per field) · mobile component · mobile integration · E2E · device · staging smoke. Required E2E journeys (BRD §Test): onboarding · prescription→meds · reminder/adherence · lab→result→trend · report→timeline · Meto-on-confirmed · discovery/booking · consented access · consultation-with-history · revocation/masking · account export · account delete. **Autonomous review loop per batch:** implement → targeted tests → regression → independent fresh-context review (source+tests, not self-report) → classify P0/P1/P2 → fix all P0/P1 → re-review → integrate → re-run E2E. No owner return between steps.

## 5. Rollout & evidence strategy (finding 5 — two-tier RC)

Staging-only via existing ACA CD. **Two distinct release-candidate tiers so missing external credentials never block product assessment:**

- **Engineering Release Candidate (ENG-RC) — achievable with NO external credentials.** Android installable **development/internal artifact** (EAS dev build / APK); iOS **simulator / EAS development** artifact; **deterministic push transport + in-app delivery** active (real APNs/FCM not required); **all functional journeys implemented + all automated tests green**; staging backend live. **The owner can fully assess the product at ENG-RC.**
- **Distribution-Ready Release Candidate (DIST-RC) — requires the deferred external inputs.** Apple signing / **TestFlight**; Google **Play internal track**; **APNs/FCM real-device** delivery. DIST-RC is a superset of ENG-RC; the deferred credentials (Apple/Google signing, APNs/FCM) upgrade ENG-RC → DIST-RC without reopening functional work.

Fixture documents = synthetic/authorized VN prescriptions + lab reports (extend `ocr_dataset/`). Evidence continuously accumulated into `docs/patient-platform-program/evidence/` (test summaries, OCR field-accuracy, security review, screenshots, demo video paths, commit/PR/build IDs). No secrets or local paths in committed evidence.

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

## 8. Execution batches & dependency graph (finding 8 — ordered batches, no calendar)

Sequencing is by **ordered batch + objective exit criterion**, not calendar dates. A batch starts when its dependencies' exit criteria are met.

- **Batch 0 — Foundations gate:** WS10 lands the **CI single-head gate**; WS0 stands up decision/risk logs. *Exit:* single-head gate enforced on `main`.
- **Batch 1 — Parallel foundations:** WS1 (mobile shell + email/password auth + secure/biometric), WS2 (Object Storage §1.7 + MDI artifact/candidate lifecycle), WS6 (Notification Delivery: deterministic + in-app transports). *Exit:* login→dashboard on an internal artifact; upload-session→accepted→needs_review; deterministic+in-app delivery proven.
- **Batch 2 — Extractors & journeys:** WS3 (prescription + general extractors on §1.5 candidate model), WS4 (lab mobile reuse), WS5 (schedule §1.8 + reconciliation + K2 API). *Exit:* per-candidate confirm→promote for prescription & lab.
- **Batch 3 — Aggregation & AI:** WS7 (timeline unification + dashboard + Meto confirmed-data restriction), WS8 (marketplace mobile + payment mock). *Exit:* unified timeline + Meto-on-confirmed.
- **Batch 4 — Hardening & RC:** WS9 (security/consent/PHI/BOLA), WS10 (E2E + staging smoke), WS12 (evidence + ENG-RC builds). *Exit:* P0/P1 closed; ENG-RC package.

```
WS0 orchestration ─ underpins all;  WS11 independent review + WS12 evidence ─ continuous
Batch0: WS10 single-head gate ─► Batch1 ┌ WS1 mobile shell/auth
                                        ├ WS2 Object-Storage(§1.7)+MDI ─► Batch2 WS3 extractors
                                        └ WS6 Notification(det.+in-app)          WS4 lab mobile
Batch2: WS5 schedule(§1.8)+reconcile+K2 ── needs WS6 ──► Batch3 WS7 timeline/dashboard/Meto
                                                          WS8 marketplace (needs WS1 only)
Batch4: WS9 security/BOLA ─► gates ENG-RC (object-storage authz, consent, Meto confirmed-data)
```
**Longest chain:** WS2(storage+MDI) → WS3(prescription extractor) → per-candidate promote → WS7(timeline) → WS9(security sign-off) → **ENG-RC**.

## 9. Internal milestones (not owner gates)

Exit criteria are stated at the **ENG-RC level** (Android internal artifact / iOS simulator + deterministic/in-app transport) so **none depends on an external credential**. "on artifact" = runs on the Android internal build or iOS simulator.

| M | Milestone | Depends on | Exit criterion (ENG-RC level) |
|---|---|---|---|
| M0 | Audit + approved BRD/plan + team + CI single-head gate | — | this doc (v1.1) approved; single-head gate merged |
| M1 | Mobile foundation + email/password auth + first internal artifact | WS1, WS12 | login→dashboard on Android artifact / iOS simulator |
| M2 | Object Storage (§1.7) + MDI foundation (artifact/classify/candidate lifecycle) | WS2 | upload-session→accepted→classified→needs_review; authorized read only |
| M3 | Prescription OCR end-to-end | M1,M2,WS3 | photo→**per-candidate** confirm→meds(+schedule when structurable) on artifact |
| M4 | Lab-report OCR end-to-end | M1,M2,WS4 | photo→confirmed result→trend on artifact; **then** enable `OCR` flag in staging |
| M5 | Health timeline + dashboard | M2,M4,WS7 | unified timeline (docs/labs/meds/adherence/appts) + decision-first dashboard |
| M6 | Medication reminders + adherence | M3,WS5,WS6 | scheduled dose occurrence → deterministic/in-app reminder → adherence logged |
| M7 | General medical-report OCR | M2,WS3 | report→candidates→confirmed timeline summary+source |
| M-K | K2 knowledge lifecycle + retrieval gate | WS5 | usable reviewed content + provenance + authz tests + empty-state → **then** enable `MEDICATION_KNOWLEDGE_RETRIEVAL` in staging (finding 10) |
| M8 | Meto AI (confirmed-data) | M4,M5,WS7 | confirmed-data-only context + flag/consent gate + SafetyGuard green → **then** enable Meto flag; explain-confirmed-result on artifact |
| M9 | Doctor marketplace continuity | M1,WS8 | booking→consultation→review on artifact (mock payment) |
| M10 | Security/ops hardening complete | WS9 (all) | P0/P1 closed; BOLA matrix green; account export/delete functional |
| **M11a** | **Engineering Release Candidate** | all above | **Program DoD (ENG-RC) met with no external credential**; evidence package |
| M11b | Distribution-Ready RC (only if creds provided) | M11a + Apple/Google signing + APNs/FCM | TestFlight + Play internal track + real-device push |

## 10. Risk register (top)

| Risk | Sev | Control |
|---|---|---|
| Parallel migrations → divergent Alembic heads | HIGH | CI single-head gate (M0); migration-bearing PRs branch off the verified current head and WS0 serializes their merges (§3) |
| Two OCR stacks + chat-only provider registry drift | MED | Unify onto staged interface (§1.4); retire skeleton |
| Object-storage authz bug leaks PHI | HIGH | WS9 signed-URL + retrieval authz + BOLA matrix before any real doc in staging |
| Meto leaks unconfirmed data | HIGH | WS7 confirmed-data filter + flag/consent gate + existing SafetyGuard tests |
| OCR accuracy below threshold on VN docs | MED | Per-field eval harness + mandatory-review bands; ship review-gated, not auto-accept |
| No signing identity / push creds (external) | LOW (was BLOCKER) | Two-tier RC (§5): ENG-RC needs none — EAS internal-dev/simulator + deterministic/in-app transport. Creds only upgrade ENG-RC→DIST-RC; **program never idles** |
| Object never leaves quarantine (no scanner) | MED | Defined quarantine posture (§1.7): object flagged, never handed to worker; not silently accepted |
| Duplicate promotion on document reprocess | MED | Unique confirmed `PromotionLink(candidate_id)` + `dedupe_key` (§1.5); reprocess carries forward, never re-promotes |
| AI meto-gate flakiness throttles merges | MED | Deterministic mock gate in CI; cloud only in nightly |
| Suite runtime at high merge frequency | MED | Diff-based selection + sharding (WS10) |

## 11. No-production assumptions
No production deploy. Staging (ACA), preview, TestFlight/internal Android, test data, mocks, migrations on staging DB only. DigitalOcean untouched. Admin accounts not seeded. Never `--no-verify`.

---

## 12. Owner Decisions — RECORDED (v1.1)

**Owner default decisions (approved, no further input required):**
1. Mobile stack = **Expo React Native** (ADR-01) — **APPROVED**.
2. OCR = **Tesseract local baseline + Azure Document Intelligence provider adapter** — **APPROVED with evaluation + PHI controls** (adapter is opt-in per upload, flag-gated, PHI-to-cloud only under the deferred credential C + consent posture).
3. Payment = **mock abstraction** — **APPROVED** (real gateway pluggable, deferred).
4. Object storage staging adapter = **Azure Blob** — **APPROVED with quarantine/finalize controls** (§1.7).
5. Staging-only flags — **APPROVED, progressively enabled after each workstream exit criterion** (§1.10), not at program start.

**External inputs — ALL DEFERRED; none blocks the Engineering RC (§5):**
- **Apple signing** → deferred; does not block ENG-RC.
- **Google Play signing** → deferred; does not block ENG-RC.
- **APNs/FCM** → deferred; use deterministic + in-app transport.
- **Azure Document Intelligence credential** → deferred; local/mock OCR path continues.
- **VNPay/MoMo** → deferred; mock payment adapter remains.

**Remaining owner decisions: NONE.** Execution is autonomous to the Engineering Release Candidate on approval of v1.1. Distribution-Ready RC (M11b) is unlocked later, without reopening functional work, if/when the deferred external inputs are provided.

---

## Appendix Z — Correction Map (v1.1 findings → sections)

| Finding | Correction | Changed sections (this doc) | BRD sections |
|---|---|---|---|
| 1 — Promotion cardinality | One-to-many candidate/promotion model + idempotency | §1.3, **§1.5 (rewritten)**, §2 | D, E |
| 2 — Secure object-storage ingestion | Upload-session→quarantine→finalize→validate→scan→accept | §1.3, **§1.7 (new)**, §2, §6, risk register | C |
| 3 — Medication scheduling | Full schedule/occurrence/scheduler design | **§1.8 (new)**, §2, §3 | G |
| 4 — Phone/OTP scope | Email/password + biometric; OTP deferred | **§1.2 (ADR-02)** | A |
| 5 — RC split | ENG-RC vs DIST-RC | **§5 (rewritten)**, §9 (M11a/M11b), risk register | Program DoD |
| 6 — Device ID | App installation UUID (ADR-03) | **§1.2 (ADR-03)**, §2 | A |
| 7 — General-report candidates | Candidate + review model | **§1.9 (new)**, §1.5, §2 | F |
| 8 — Calendar → batches | Ordered batches + objective exits | **§8 (rewritten)**, §9 | — |
| 9 — Migration policy | Migration-bearing PR policy | **§3 (rewritten)** | — |
| 10 — K2 enable gate | Content/provenance/authz/empty-state before enable | §1.10, §2, §9 (M-K) | G, P |
| 11 — Notification transports | 4 capability-gated adapters | **§1.1 (rewritten)**, §5, risk register | N |
| 12 — Progressive flags | Enable after exit criteria | **§1.10 (new)**, §9 | O, R |
