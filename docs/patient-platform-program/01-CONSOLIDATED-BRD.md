# MetoCare Patient Platform — Consolidated Business Requirements Document (BRD)

**Version:** 1.1 (one-time correction — ready for final single owner approval)
**Date:** 2026-07-30
**Scope:** The complete remaining patient-platform program, delivered **product-first and mobile-first**. Self-contained — implementable without access to the origination conversation. Grounded in `00-CAPABILITY-AUDIT.md`.
**Change log:** v1.1 applies the owner's one-time P1/P2 correction round (findings 1–12). See **Appendix Z — Correction Map** (bottom) for finding→section traceability. Deep schema/flow detail lives in the Master Plan; this BRD carries the product-behavior corrections.

---

## 0. Product Thesis & Global Principles

**The patient mobile app is the primary product.** Every significant capability must terminate in a usable mobile journey. An API without a mobile journey is *not* done.

**Document-first.** Patients must not re-enter data that already exists in a prescription, lab report, or medical document. Manual entry is a fallback/correction path, not the primary path.

**Confirmed vs unconfirmed data is a first-class distinction.** OCR output is *never* presented as verified clinical truth. Canonical records (medications, lab results, diagnoses) are only written after explicit patient confirmation. AI and doctors must visually distinguish: patient-confirmed / doctor-confirmed / OCR-extracted-unconfirmed.

**Vietnamese-first.** All patient copy, OCR targets (printed VN prescriptions & lab reports), and empty/error states in Vietnamese.

**No production.** Local, migrations, staging, preview, internal TestFlight/Android builds only. Never weaken an existing security control to accelerate.

**Global acceptance bar (applies to every capability):** empty/loading/error/retry states defined; authorization enforced and tested; PHI audited; mobile-native behavior (keyboard-safe, touch targets ≥44pt, offline-aware); no unresolved P0/P1 at delivery.

---

## Capability Requirements

Each capability uses a fixed template: **Personas · Problem · Journey · Functional Requirements · Acceptance Criteria · States · Authorization · Audit · Mobile Behavior · Web/Admin Dependencies · Out-of-Scope · Definition of Done.** Capabilities already `COMPLETE` in the audit are specified as **reuse + wire-to-mobile + close named gaps**, not rebuilds.

---

### A. Patient Mobile App (Shell, Auth, Onboarding, Navigation)

- **Personas:** New patient; returning patient; low-tech middle-aged metabolic patient (primary VN persona).
- **Problem:** There is no mobile product today; the patient experience lives only on web.
- **Journey:** Install → language (VN default) → **email/password register** → consent → onboarding (health profile basics) → land on Dashboard. Returning: **optional biometric unlock** over a secure-stored session → Dashboard.
- **Functional requirements (finding 4):** **email/password auth** reusing backend `/auth` (JWT + refresh rotation); **secure session storage** (Keychain/Keystore, **not** AsyncStorage) with **optional biometric unlock**; MFA-aware (respects `mfa_enforcement_enabled`); deep links; environment separation (dev/staging); crash reporting + analytics; global Meto entry point. **Phone/SMS-OTP is explicitly DEFERRED** — the audit did not establish a phone-OTP backend; it is not an implicit net-new requirement and would need a dedicated Identity/SMS workstream.
- **Acceptance:** Cold start → interactive < 3s on mid-tier Android; token refresh transparent; forced-logout on refresh-reuse; VN copy throughout.
- **States:** unauthenticated / onboarding-incomplete / authenticated / token-expired / offline.
- **Authorization:** all patient data keyed to `PatientProfile.id` resolved from `User.id` (honor the dual-namespace rule).
- **App installation identifier (finding 6):** a **random UUID** generated at first install, securely stored, **reset on reinstall/account unlink** — never a hardware ID, serial, IMEI, ad ID, or fingerprint. Used only for session/device management, push registration, and specifically justified audit events — **not** attached to every API call.
- **Audit:** login/logout/refresh already audited server-side; installation-id included only on session/device and justified audit events.
- **Mobile behavior:** keyboard-safe forms, pull-to-refresh, offline banner, retry.
- **Web/Admin deps:** none new; reuses existing auth backend.
- **Out-of-scope:** social login, web-app parity beyond patient surfaces.
- **DoD:** installable iOS + Android internal builds; login→dashboard e2e green on device.

### B. Patient Health Record (Home of everything clinical)

- **Personas:** Patient; (read) treating doctor.
- **Problem:** Clinical data is scattered across labs/meds/metrics with no single record home.
- **Journey:** Health Record hub with tabs: **Overview · Timeline · Medications · Laboratory Results · Diagnoses · Medical Documents · Add Document.** (OCR is *inside* this module — no top-level "OCR" nav.)
- **Functional requirements:** aggregate existing endpoints (labs, medications, metrics, timeline, insight); every structured item derived from a document links back to its source document.
- **Acceptance:** each tab loads real confirmed data; source-document backlink present on derived items.
- **States:** empty (no data yet, with "Add Document" CTA), loading, error/retry.
- **Authorization:** patient-owned; doctor read only via consult access grant.
- **Audit:** record views of PHI-heavy screens (data_access).
- **Mobile behavior:** tabbed, swipeable; large tap targets.
- **DoD:** hub navigable on device; backlinks functional.

### C. Medical Document Upload (Add Document)

- **Personas:** Patient.
- **Problem:** No generic document capture exists; only lab image upload on web.
- **Journey:** "Add Document" → choose: **Take prescription photo · Take lab-report photo · Take other medical-document photo · Choose images · Upload PDF** → capture/crop/rotate → auto-classify → route to the correct extractor → review.
- **Functional requirements (finding 2 — secure ingestion):** camera + photo library + PDF + HEIC-where-practical; multi-page; crop/rotate; image-quality feedback + retry. Upload uses an **upload session** → a **short-lived, write-only** signed URL to a **server-generated quarantine key** (no read/list) → client uploads → **finalize** → server validates owner/hash/size/magic-byte-MIME/page-limits, runs **malware scan or defined quarantine posture**, and only then marks the object **accepted**; OCR workers process **accepted** objects only. Backend classifies document type; **duplicate detection is scoped within the owning patient by hash** (BOLA-safe). Full flow in Master Plan §1.7.
- **Acceptance:** a photographed document is stored durably in an accepted (post-validation) object, classified, and routed; low-quality images prompt re-capture; a failed-scan object stays quarantined and is never processed.
- **States:** uploaded → preprocessing → processing → needs_review → partially_confirmed → confirmed / rejected / failed / superseded (canonical set; `quarantined` is an object-storage state, not a document status). See Master Plan §1.5/§1.7.
- **Authorization:** patient-owned artifact; **every** read of bytes is via a per-request, authorization-checked, short-lived signed URL.
- **Audit:** upload, classification, retrieval, deletion all audited.
- **Mobile behavior:** native camera; background upload with progress; offline queue.
- **Out-of-scope (MVP):** handwriting auto-acceptance (best-effort + mandatory review only).
- **DoD:** photo→stored→classified→review on device for all three doc types.

### D. Prescription OCR

- **Personas:** Patient (primary); doctor (later verification).
- **Problem:** Patients manually type medications; error-prone and abandoned.
- **Journey:** photograph VN printed prescription → extraction → **review screen: one card per medicine candidate** with original-image reference, field-level confidence, uncertain fields highlighted, quick correction → confirm all / confirm individually / reject per candidate → medications created/reconciled.
- **Functional requirements (finding 1 — one document → many meds):** extract where present — facility, prescriber, date, diagnosis, medicine name, active-ingredient candidate, strength, form, quantity, dose/administration, frequency, time, route, duration, instructions. One prescription yields **many independent medication candidates**, each **confirmed/rejected/merged per-candidate**. **Never write to canonical medication list without confirmation.** On confirm: create/reconcile via existing `MedicationStatement`→canonical path (merge into an existing medication where it matches), **no duplicate promotion on re-upload** (candidate `dedupe_key` + one-promotion-per-candidate rule, Master Plan §1.5); preserve full **bidirectional provenance** back to the exact source candidate + image; create a schedule (§G) **only when frequency is safely structurable**. Handwriting → best-effort, low-confidence, mandatory review, raw preserved.
- **Acceptance:** printed VN prescription yields ≥ target field accuracy (see O); no medication persists pre-confirmation; each candidate independently actionable; reprocessing never double-promotes; provenance links original image.
- **States:** inherits C; per medication candidate: extracted / needs_review / confirmed / rejected / merged / superseded.
- **Authorization:** patient-owned.
- **Audit:** extraction, each confirm/reject (medication_write with source=ocr).
- **Mobile behavior:** card carousel; tap-to-zoom original; inline edit.
- **DoD:** "prescription photo → confirmed medications + schedule" e2e on device.

### E. Laboratory Report OCR

- **Personas:** Patient; doctor (read).
- **Problem:** (Web has this; mobile does not.) Bring the proven lab pipeline to mobile.
- **Journey:** photograph/upload VN lab report → draft with per-field confidence → review/correct → confirm → written to record + timeline + trend charts.
- **Functional requirements:** reuse existing pipeline (`lab_interpreter`, `lab_provenance`, confirm→promote). Prioritize metabolic panels (glucose, fasting glucose, HbA1c, insulin, lipid panel, AST/ALT/GGT, bilirubin, creatinine/eGFR/urea/uric acid, TSH/FT4, CBC, urinalysis, BP, weight/BMI). Extract analyte, original label, result, unit, reference range, abnormal flag, specimen/report date, facility, method. Preserve original+normalized value/unit, source doc, bounding box, confidence, confirmation status. **Never silently normalize a unit when conversion confidence is insufficient.**
- **Acceptance:** one report yields **many independent lab-result candidates** (finding 1), each confirmed/rejected per-candidate; confirmed results appear on trend charts, comparable across dates; abnormal results surfaced with safe language; reprocessing never double-promotes; per-field accuracy meets O.
- **States:** inherits D5 lab pipeline states + per-candidate confirm gate (extracted / needs_review / confirmed / rejected / merged / superseded).
- **Authorization / Audit / Mobile / DoD:** as C/D; "lab photo → confirmed result → trend" e2e on device.

### F. General Medical Report OCR

- **Personas:** Patient; doctor (read).
- **Problem:** Discharge/imaging/pathology/referral documents have no home.
- **Journey:** photograph/upload → classify (exam/discharge/imaging/ultrasound/CT-MRI/pathology/referral/other) → structured summary + preserved original → added to timeline.
- **Functional requirements (finding 7 — candidate & review model):** extract where present — doc type, facility, clinician, date, symptoms, and typed **candidates**: `diagnosis`, `medication`, `procedure`, `finding`, `recommendation`, `follow_up`. Produce a **structured summary**. Rules: **confirmation is per-field/per-candidate**; patient corrections keep a **correction history**; raw extraction + original document are **immutable provenance**; **diagnosis never becomes canonical without explicit confirmation** (and doctor verification where policy requires); **medication candidates route through reconciliation** (never bypass confirm/verify); a **follow-up task/reminder is created only after confirmation** (never auto-scheduled from raw extraction). Detail in Master Plan §1.9.
- **Acceptance:** report classified + summarized + original retrievable + timelined; every candidate independently confirmable; unconfirmed diagnoses are display-only and badged.
- **DoD:** "medical report → candidates → confirmed timeline entry with summary + source" e2e on device.

### G. Medication Management & Adherence

- **Personas:** Patient; doctor (verify).
- **Problem:** Adherence loop is passive (no reminders); reconciliation has no UI.
- **Journey:** active/past meds → detail (linked prescription, schedule, education, knowledge) → reminder fires → taken/skipped (+ skip reason) → adherence trend → side-effect check-in → refill/end.
- **Functional requirements (finding 3 — scheduling design):** **new structured schedule + reminder engine.** A schedule captures **patient timezone, schedule type (fixed_daily / interval / days_of_week / cyclic / PRN), local dose times, recurrence, start/end dates, status (active/paused/stopped/completed), source, verification status**; instants **stored in UTC, rendered in patient local time**; dose occurrences carry an **idempotency/dedupe key** so a **concurrency-safe scheduler retries without duplicate dose events**; schedule edits create a **new version (supersession)**; **paused/stopped** medications materialize no future doses; **PRN** medications fire no timed reminders (ad-hoc taken logging). **Only confirmed data may create a schedule**; when OCR frequency cannot be **safely** structured, **no schedule is created** and the patient sets dose times manually. Reuse CRUD/adherence/verification; **new reconciliation API** to list/accept/merge pending statements; K2 knowledge retrieval behind flag (enabled only after its content/authz gate); medication education content. Unverified extracted data must not drive unsafe advice. Full schema in Master Plan §1.8.
- **Acceptance:** reminder fires at the scheduled local dose time (deterministic/in-app transport suffices); duplicate-safe on scheduler retry; taken/skipped recorded; reconciliation drivable from app; doctor verification visible; PRN meds never auto-remind.
- **DoD:** "reminder → adherence logged" + "reconcile extracted med" e2e on device.

### H. Health Timeline

- **Personas:** Patient; doctor (read).
- **Problem:** Timeline omits appointments, documents, nutrition, adherence.
- **Functional requirements:** unify medical documents, prescriptions, medications (+adherence events), lab results, diagnoses, self-measurements, appointments, consultations, patient-displayable doctor notes, care plans, alerts, goals. Filter + drilldown. Every document-derived item backlinks to source.
- **Acceptance:** all listed event types appear, filterable; backlinks work.
- **DoD:** unified timeline on device.

### I. Patient Dashboard

- **Personas:** Patient.
- **Problem:** Dashboard must drive action, not display density.
- **Functional requirements:** surface — today's medication actions; **pending OCR confirmations**; newly received results; trends needing attention; upcoming appointments; measurements due; follow-up tasks; recent Meto guidance; doctor messages (where supported).
- **Acceptance:** action items are tappable and route correctly; empty state guides to "Add Document".
- **DoD:** decision-first dashboard live on device.

### J. Meto AI

- **Personas:** Patient.
- **Problem:** Chat currently feeds unverified data and lacks gating.
- **Functional requirements:** explain a lab result; summarize a document; summarize history; explain a medication; prepare doctor questions; adherence support; app navigation; safe next-step guidance. **Restrict context to CONFIRMED data** (fix AI2 gap); apply flag + consent gate; distinguish confirmed/unconfirmed; show source/time; escalate red flags (115); audit provider/model/version. Guardrails (reuse `SafetyGuard`): no diagnosis, no prescription/dose change.
- **Acceptance:** chat cites confirmed data only; forbidden patterns blocked (existing tests); escalation on red-flag input.
- **DoD:** "explain my confirmed HbA1c" e2e on device.

### K. Doctor Marketplace & Consultation

- **Personas:** Patient; doctor; admin (verification).
- **Problem:** Vertical is COMPLETE on backend/web; needs mobile + real payment abstraction.
- **Functional requirements:** discovery/filters/detail/pricing/availability/booking/consent/**payment abstraction** (mock adapter default, real gateway pluggable)/consultation/patient-summary/selected-document sharing/outcome/follow-up/review/refund-dispute/payout abstraction. Doctor UI must distinguish confirmed vs OCR-unconfirmed data.
- **Acceptance:** end-to-end booking→consultation→review on device; sharing consent-scoped.
- **DoD:** marketplace flow e2e on device.

### L. Patient–Doctor Record Sharing

- **Functional requirements:** field/document-level consented sharing; revocation/masking; doctor sees data-provenance badges. Reuse `ConsultationAccessGrant` + `ConsentGuard` (after fixing fail-open, F5).
- **Acceptance:** revoke immediately masks doctor view; access audited.
- **DoD:** grant→view→revoke e2e.

### M. Clinic Integration (patient-continuity slice only)

- **Functional requirements:** appointment, patient matching, doctor assignment, encounter linkage, clinic-uploaded document/prescription/lab, follow-up, consented record sharing. Broader Clinic SaaS continues as independent workstream where non-blocking.
- **Out-of-scope:** full clinic operations beyond continuity.
- **DoD:** clinic-originated document appears in patient timeline via consent.

### N. Notifications

- **Functional requirements (finding 11 — transports, no assumed fallback):** a `NotificationTransport` with **four capability-gated adapters** — (1) **deterministic test transport** (CI), (2) **in-app transport** (DB-backed, always available), (3) **push adapter** (APNs/FCM) active **only when device credentials are configured**, (4) **email adapter** active **only when an email provider is configured**. Email is **not** assumed to exist. Categories: medication reminder, new result ready, OCR needs review, appointment, security alert, doctor message. Per-category preferences persisted **server-side** (fixes web localStorage gap). Deep-link into the relevant screen; no PHI in payload.
- **Acceptance:** scheduled reminder delivered via the best **available** transport (deterministic + in-app always suffice); when push/email credentials exist, delivered on that channel; tapping opens correct screen; preferences honored; no PHI in payload.
- **DoD (ENG-RC):** reminder delivered via deterministic + in-app transport; push delivery is a Distribution-RC add-on.

### O. Security, Consent & Privacy

- **Functional requirements (hardening):** enforce MFA per policy; password policy; fix consent **fail-open**; replace committed default keys with required-env + fail-closed validation; object-storage authorization + signed URLs; upload rate-limit + type/size/AV posture; no PHI in logs/analytics; retention; **account export**; **account deletion**; BOLA test matrix; secure mobile token storage. **OCR quality thresholds gate auto-display vs mandatory-review vs reject**; high-risk fields require confirmation even at high confidence; never present OCR as verified truth.
- **Acceptance:** all P0/P1 security findings closed; BOLA matrix green; export/delete functional.
- **DoD:** security evidence pack (see Master Plan §Evidence).

### P. Administration & Support Operations

- **Functional requirements:** admin can view/verify doctors, manage patients/users, toggle feature flags, review audit + AI safety, review OCR extraction quality; wire the two STUB admin pages (clinics/reports) or explicitly defer. Support: account export/delete request handling.
- **DoD:** admin can action a document-review escalation and a doctor verification.

### Q. Analytics & Observability

- **Functional requirements:** mobile analytics (screen views, funnel: install→onboard→first-document→first-confirmation) + crash reporting; backend metrics (`/metrics`), OCR per-field accuracy dashboards, AI cost/latency; **PHI never in analytics**.
- **DoD:** funnel + crash + OCR-accuracy observable.

### R. Staging & Internal Release

- **Functional requirements:** working staging backend (existing ACA CD); patient mobile app pointed at staging; internal iOS (TestFlight) + Android (internal track / APK) builds; test accounts + synthetic fixture documents; post-deploy staging smoke.
- **DoD:** installable internal builds + staging URL + test accounts in the final evidence package.

---

## Program-level Definition of Done (finding 5 — two tiers)

**Engineering Release Candidate (ENG-RC) — the gate for final owner assessment; achievable with NO external credential:**
Android installable development/internal artifact + iOS simulator/EAS development artifact · working staging backend + patient mobile app · prescription OCR journey · lab-report OCR journey · general medical-document journey · medication confirmation + reminder (deterministic + in-app transport) · unified health timeline · trend charts · Meto AI on confirmed data · doctor marketplace flow (mock payment) · consented doctor access · test accounts · fixture documents · automated tests · migration evidence · security/PHI evidence · performance + accessibility checks · **no unresolved P0/P1** · known-limitations register · rollback/recovery instructions · final demo package.

**Distribution-Ready Release Candidate (DIST-RC) — superset, unlocked only if deferred credentials are provided:** Apple signing / TestFlight · Google Play internal track · APNs/FCM real-device push. Missing external credentials must **not** block ENG-RC or halt the program.

*Every ENG-RC item is achievable without any external credential. Backend-only, document-only, or web-only is NOT complete.*

---

## Appendix Z — Correction Map (v1.1 findings → BRD sections)

| Finding | Correction | BRD section(s) | Master-Plan detail |
|---|---|---|---|
| 1 — Promotion cardinality (one→many) | Per-candidate confirm/reject/merge; no duplicate promotion | **D, E** | §1.5 |
| 2 — Secure object-storage ingestion | Upload-session→quarantine→finalize→accept; authorized reads | **C** | §1.7 |
| 3 — Medication scheduling | Timezone/type/recurrence/occurrence/idempotency; confirmed-only | **G** | §1.8 |
| 4 — Phone/OTP scope | Email/password + biometric; OTP deferred | **A** | §1.2 (ADR-02) |
| 5 — RC split | ENG-RC vs DIST-RC | **Program DoD**, N | §5, §9 |
| 6 — Device ID | App installation UUID | **A** | §1.2 (ADR-03) |
| 7 — General-report candidates | Candidate + review model; diagnosis never auto-canonical | **F** | §1.9 |
| 8 — Calendar → batches | (plan-side) ordered batches | — | §8, §9 |
| 9 — Migration policy | (plan-side) migration-bearing PR policy | — | §3 |
| 10 — K2 enable gate | Retrieval enabled only after content/authz/empty-state gate | **G, P** | §1.10, §9 (M-K) |
| 11 — Notification transports | 4 capability-gated adapters; email not assumed | **N** | §1.1 |
| 12 — Progressive flags | Enable after each exit criterion | **O, R** | §1.10 |
