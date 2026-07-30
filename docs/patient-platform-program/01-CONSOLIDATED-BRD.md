# MetoCare Patient Platform — Consolidated Business Requirements Document (BRD)

**Version:** 1.0 (single owner-approval gate)
**Date:** 2026-07-30
**Scope:** The complete remaining patient-platform program, delivered **product-first and mobile-first**. Self-contained — implementable without access to the origination conversation. Grounded in `00-CAPABILITY-AUDIT.md`.

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
- **Journey:** Install → language (VN default) → phone/OTP or email register → consent → onboarding (health profile basics) → land on Dashboard. Returning: biometric/secure-token unlock → Dashboard.
- **Functional requirements:** Phone-first auth reusing backend `/auth` (JWT + refresh rotation); secure token storage (Keychain/Keystore, **not** AsyncStorage); MFA-aware (respects `mfa_enforcement_enabled`); deep links; environment separation (dev/staging); crash reporting + analytics; global Meto entry point.
- **Acceptance:** Cold start → interactive < 3s on mid-tier Android; token refresh transparent; forced-logout on refresh-reuse; VN copy throughout.
- **States:** unauthenticated / onboarding-incomplete / authenticated / token-expired / offline.
- **Authorization:** all patient data keyed to `PatientProfile.id` resolved from `User.id` (honor the dual-namespace rule).
- **Audit:** login/logout/refresh already audited server-side; add device-id to client calls.
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
- **Functional requirements:** camera + photo library + PDF + HEIC-where-practical; multi-page; crop/rotate; image-quality feedback + retry; client uploads to **object storage** via signed URL; backend classifies document type; duplicate detection by hash.
- **Acceptance:** a photographed document is stored durably, classified, and routed; low-quality images prompt re-capture.
- **States:** uploaded → preprocessing → processing → needs_review → partially_confirmed → confirmed / rejected / failed / superseded (canonical set; see Master Plan §Doc-Intelligence).
- **Authorization:** patient-owned artifact; access to bytes only via short-lived signed URL, authorization-checked.
- **Audit:** upload, classification, retrieval, deletion all audited.
- **Mobile behavior:** native camera; background upload with progress; offline queue.
- **Out-of-scope (MVP):** handwriting auto-acceptance (best-effort + mandatory review only).
- **DoD:** photo→stored→classified→review on device for all three doc types.

### D. Prescription OCR

- **Personas:** Patient (primary); doctor (later verification).
- **Problem:** Patients manually type medications; error-prone and abandoned.
- **Journey:** photograph VN printed prescription → extraction → **review screen: one card per medicine** with original-image reference, field-level confidence, uncertain fields highlighted, quick correction → confirm all / confirm individually / reject per medicine → medications created/reconciled.
- **Functional requirements:** extract where present — facility, prescriber, date, diagnosis, medicine name, active-ingredient candidate, strength, form, quantity, dose/administration, frequency, time, route, duration, instructions. **Never write to canonical medication list without confirmation.** On confirm: create/reconcile via existing `MedicationStatement`→canonical path, avoid duplicates, preserve provenance + original document; create schedule if enough info confirmed. Handwriting → best-effort, low-confidence, mandatory review, raw preserved.
- **Acceptance:** printed VN prescription yields ≥ target field accuracy (see O); no medication persists pre-confirmation; provenance links original image.
- **States:** inherits C; per-medicine: extracted / confirmed / rejected.
- **Authorization:** patient-owned.
- **Audit:** extraction, each confirm/reject (medication_write with source=ocr).
- **Mobile behavior:** card carousel; tap-to-zoom original; inline edit.
- **DoD:** "prescription photo → confirmed medications + schedule" e2e on device.

### E. Laboratory Report OCR

- **Personas:** Patient; doctor (read).
- **Problem:** (Web has this; mobile does not.) Bring the proven lab pipeline to mobile.
- **Journey:** photograph/upload VN lab report → draft with per-field confidence → review/correct → confirm → written to record + timeline + trend charts.
- **Functional requirements:** reuse existing pipeline (`lab_interpreter`, `lab_provenance`, confirm→promote). Prioritize metabolic panels (glucose, fasting glucose, HbA1c, insulin, lipid panel, AST/ALT/GGT, bilirubin, creatinine/eGFR/urea/uric acid, TSH/FT4, CBC, urinalysis, BP, weight/BMI). Extract analyte, original label, result, unit, reference range, abnormal flag, specimen/report date, facility, method. Preserve original+normalized value/unit, source doc, bounding box, confidence, confirmation status. **Never silently normalize a unit when conversion confidence is insufficient.**
- **Acceptance:** confirmed results appear on trend charts, comparable across dates; abnormal results surfaced with safe language; per-field accuracy meets O.
- **States:** inherits D5 lab pipeline states + confirm gate.
- **Authorization / Audit / Mobile / DoD:** as C/D; "lab photo → confirmed result → trend" e2e on device.

### F. General Medical Report OCR

- **Personas:** Patient; doctor (read).
- **Problem:** Discharge/imaging/pathology/referral documents have no home.
- **Journey:** photograph/upload → classify (exam/discharge/imaging/ultrasound/CT-MRI/pathology/referral/other) → structured summary + preserved original → added to timeline.
- **Functional requirements:** extract where present — doc type, facility, clinician, date, symptoms, diagnoses, findings, conclusion, recommendations, follow-up date, medications, procedures. Produce a **structured summary**; **do not** auto-create a confirmed diagnosis.
- **Acceptance:** report classified + summarized + original retrievable + timelined; diagnoses remain unconfirmed until explicitly promoted.
- **DoD:** "medical report → timeline entry with summary + source" e2e on device.

### G. Medication Management & Adherence

- **Personas:** Patient; doctor (verify).
- **Problem:** Adherence loop is passive (no reminders); reconciliation has no UI.
- **Journey:** active/past meds → detail (linked prescription, schedule, education, knowledge) → reminder fires → taken/skipped (+ skip reason) → adherence trend → side-effect check-in → refill/end.
- **Functional requirements:** **new structured schedule + reminder engine** (dose times → notifications via F7); reuse CRUD/adherence/verification; **new reconciliation API** to list/accept/merge pending statements; K2 knowledge retrieval behind flag; medication education content. Unverified extracted data must not drive unsafe advice.
- **Acceptance:** reminder fires at scheduled time; taken/skipped recorded; reconciliation drivable from app; doctor verification visible.
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

- **Functional requirements:** **real delivery infrastructure** — push (APNs/FCM) primary, email fallback; categories: medication reminder, new result ready, OCR needs review, appointment, security alert, doctor message. Per-category preferences (persisted server-side, fixing web localStorage gap). Deep-link into the relevant screen.
- **Acceptance:** scheduled reminder delivered to device; tapping opens correct screen; preferences honored; no PHI in payload.
- **DoD:** push received on device.

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

## Program-level Definition of Done (gate for final owner review)

Installable iOS + Android internal builds · working staging backend + mobile app · prescription OCR journey · lab-report OCR journey · general medical-document journey · medication confirmation + reminder · unified health timeline · trend charts · Meto AI on confirmed data · doctor marketplace flow · consented doctor access · test accounts · fixture documents · automated tests · migration evidence · security/PHI evidence · performance + accessibility checks · **no unresolved P0/P1** · known-limitations register · rollback/recovery instructions · final demo package.

*Backend-only, document-only, or web-only is NOT complete.*
