# MetoCare Clinic SaaS — BRD Analysis

Source: `docs/brd/README.md`, `docs/brd/v1.0/executive-brd.md` (v1.0, executive/approved-for-BOD baseline),
`docs/brd/v2.0/*.md` (v2.0, detailed module spec, supersedes v1.0 on conflict per README).
All 22 source files were read in full. None were missing.

Numbering conventions used by the BRD itself (kept as-is below):
- `US-Mxx-nn` = user story, `BR-Mxx-nn` = business rule (backend-enforced, the closest thing to a numbered FR), `AC-Mxx-nn` = acceptance criterion.
- v1.0 also has its own flat FR codes (`CLINIC-01`, `BRANCH-01`, `STAFF-01`, `SERVICE-01`, `PATIENT-01`, `APPT-01`, `QUEUE-01`, `ENCOUNTER-01`, `NOTE-01`, `AI-01`, `CARE-01`, `GAP-01`, `CRM-01`, `BILL-01`, etc.) which v2.0 restates and elaborates per module. These are cross-referenced but not treated as a second source of truth.
- P0 = blocks go-live, P1 = required in phase, P2 = nice-to-have.

---

## Overview (00-overview.md, README.md, v1.0 §1–§9)

### Goals
- Business: increase on-time follow-up (retention) rate, reduce no-show and loss-to-follow-up, reduce doctor pre-visit prep time ≥50%, grow recurring revenue per patient, build a repeatable multi-clinic SaaS with MRR/ARR (v1.0 §4–§5).
- Product positioning: NOT a general HIS/EMR replacement; core differentiators are longitudinal health record, Care Gap Queue, and Clinical Copilot (v1.0 §1, §26).
- Pilot targets (v1.0 §5.4): +15% on-time follow-up, -20% no-show, -50% doctor prep time, ≥60% chronic patients with a care plan, ≥70% pilot patients with digitized lab records.

### Actors / Personas
Platform Super Admin, Clinic Owner, Clinic Admin, Doctor, Nurse, Receptionist, Care Coordinator, Accountant, Patient (v1.0 §7, elaborated per-module in M01–M18). Three product surfaces: MetoCare Clinic (staff), MetoCare Doctor, MetoCare Patient (v1.0 §6).

### Use Cases
End-to-end flow (v1.0 §9): acquire patient → create/link record → book → confirm → check-in → queue → doctor views record + AI briefing → encounter → clinical note → care plan → billing → reminders → Care Gap Queue → outreach → patient returns.

### Functional Requirements (module index)
18 modules, each with its own numbered BRs — see per-module sections below. High-level v1.0 FR groups: CLINIC-0x (M01), BRANCH-0x (M02), STAFF-0x (M03), SERVICE-0x (M05), PATIENT-0x (M06), APPT-0x (M07), QUEUE-0x (M08), ENCOUNTER-0x/NOTE-0x (M09), AI-0x (M14), CARE-0x (M11), GAP-0x (M12), CRM-0x (M13), BILL-0x (M10).

### Non-Functional Requirements
See Appendix B analysis below — security, performance, availability, scale, audit are cross-cutting and inherited by every module (BR-Mxx entries reference them implicitly via P0 gates).

### Acceptance Criteria (program-level, v1.0 §22)
14 program-level ACs gate "pilot-ready", e.g.: each clinic is an isolated tenant; cross-clinic access blocked by backend tests; clinic can create branch/staff/doctor/service; receptionist creates patient+appointment; patient checks in to queue; doctor sees only in-scope records; doctor finalizes notes; clinic creates care plans and follow-ups; system generates overdue-patient lists; care staff logs outreach outcomes; owner sees retention/revenue; UI works on desktop+mobile; zero open P0/P1 security findings; CI/migration/deploy/authenticated-smoke all pass.

### Out of Scope (v1.0 §19, restated per-module)
Full hospital HIS, bed management, surgery, ICU, PACS, health insurance, advanced pharmacy inventory, general ledger accounting, payroll, national e-prescription, AI auto-diagnosis/auto-prescription. Also explicitly deferred to later phases: e-invoice, payment gateway, lab/device/pharmacy integrations, teleconsultation, corporate health, partner API (Phase C4).

### Cross-Module Dependencies
Tenant (M01) underlies all; Branch (M02) + Staff/RBAC (M03) underlie Service/Patient/Appointment/Billing; Subscription (M04) gates feature access across M05–M16; Appointment (M07) feeds Check-in/Queue (M08) and Care Gap (M12 via no-show); Encounter/Notes (M09) feeds Care Plan (M11), Copilot (M14), and Dashboard (M16); Care Plan (M11) is the primary rule source for Care Gap Queue (M12); Care Gap Queue feeds CRM (M13); Consent (M17) gates Copilot (M14) and Notifications (M15); Audit (M18) is a sink for nearly every module.

### Open Decisions (program-level, v1.0 §25)
Niche approval (Endocrine–Cardio–Metabolic), positioning approval, phase C0/C1 approval, pilot budget, pricing model, pilot clinic list, AI/data usage principles, production security gate — all explicitly flagged as requiring BOD approval and not yet decided.

---

## M01 — Tenant & Clinic Management (C0, P0)

**Goals:** Establish the multi-tenant foundation; every business record is scoped by `clinic_id`.

**Actors:** Platform Super Admin (create/suspend/activate tenants, ops visibility, no default clinical access), Clinic Owner (full config), Clinic Admin (delegated config).

**Use Cases:** US-M01-01 (create tenant), US-M01-02 (branding config), US-M01-03 (suspend without data loss), US-M01-04 (cancellation policy config).

**Functional Requirements:** BR-M01-01 (P0, every record has `clinic_id`, server-side scoping only — client-supplied clinic id must never override session context), BR-M01-02 (P0, Suspended/Expired blocks all writes, reads allowed at minimum, no data deletion), BR-M01-03 (P0, Deactivated is terminal, restore requires platform approval + audit), BR-M01-04 (P1, legal-info changes Owner-only + audit old/new), BR-M01-05 (P1, reminder content must not embed PHI/diagnosis).

**Non-Functional:** Tenant status machine must be race-safe under concurrent admin actions (not explicitly tested in AC, see Cross-Cutting Findings). Legacy field: `queue_config` (numbering scheme) lives here but is consumed by M08.

**Acceptance Criteria:** AC-M01-01..04 — tenant creation produces `clinic_id` + Trial plan + Owner invite; automated cross-tenant test (403/404 on ID substitution); suspend blocks writes but preserves data; branding reflected in patient-facing messages.

**Out of Scope:** Subscription billing (M04), branch management (M02).

**Dependencies:** Feeds M02–M18 via `clinic_id`; M04 assigns default Trial plan on tenant creation (M01 §1.4 step 2).

**Open Decisions:** Owner-recovery process when Owner loses email access is described narratively (§1.8) but has no BR/AC — not formally specified as a testable requirement.

---

## M02 — Branch Management (C0, P0)

**Goals:** Support multi-location clinics with independent hours/staff/services/queue while sharing one patient record pool.

**Actors:** Clinic Owner/Admin (CRUD branch, assign staff/services, pause), multi-branch staff (switch working branch).

**Use Cases:** US-M02-01 (create branch), US-M02-02 (switch branch context), US-M02-03 (pause branch without losing history).

**Functional Requirements:** BR-M02-01 (P0, `branch_id` must come from authenticated membership/session; client-sent `branch_id` only selects among the user's valid set, never trusted absolutely), BR-M02-02 (P0, no booking outside branch working hours unless overridden with audited reason), BR-M02-03 (P1, Paused branch blocks new bookings, existing bookings flagged for reschedule), BR-M02-04 (P1, no hard delete of a branch with history — Paused/Archived only).

**Acceptance Criteria:** AC-M02-01..03 — staff see only assigned branches; out-of-membership `branch_id` → 403; pausing blocks new bookings without losing old ones.

**Out of Scope:** Not stated explicitly, but by omission: cross-branch reporting rollups are M16's concern, not M02's.

**Dependencies:** M01 (tenant), M03 (membership defines branch assignment), M04 (Trial/Basic/Professional cap branch count — **not cross-referenced in M02's own BRs**, see Cross-Cutting Findings), M05/M07 (branch-scoped services/appointments).

**Open Decisions:** None self-flagged.

---

## M03 — Staff, Membership & RBAC (C0, P0)

**Goals:** Separate platform-level user identity from tenant-level membership (role + branch + status); enforce backend RBAC as the single source of truth (Appendix A).

**Actors:** Clinic Owner (min. 1 active Owner required), Clinic Admin, Doctor, Nurse, Receptionist, Care Coordinator, Accountant — see role table §3.2.

**Use Cases:** US-M03-01 (invite by email/phone), US-M03-02 (multi-role per user), US-M03-03 (one doctor account, multiple clinics, strict data separation), US-M03-04 (suspend membership without losing authored data).

**Functional Requirements:** BR-M03-01 (P0, every endpoint checks membership.roles × resource × action against Appendix A as source of truth), BR-M03-02 (P0, multi-clinic doctor: independent membership/schedule/patient-list per clinic, cross-clinic query forbidden), BR-M03-03 (P0, suspend takes effect ≤60s incl. token revocation, authored data retained with original attribution), BR-M03-04 (P0, cannot demote/lock the tenant's last Owner), BR-M03-05 (P1, Doctor role requires a doctor profile; clinic is responsible for license verification per v1.0 assumption A-03), BR-M03-06 (P1, least-privilege: Receptionist/Accountant get zero API surface for notes/diagnosis/labs; Care Coordinator gets only the M13 "care context" subset).

**Acceptance Criteria:** AC-M03-01..04 — every role has both a positive and a 403 negative test per Appendix A; suspend revokes tokens within 60s; two-clinic doctor session leaks nothing cross-clinic; last Owner cannot be removed.

**Out of Scope:** Doctor license/credential verification itself (delegated to clinic, per BR-M03-05 — MetoCare does not verify).

**Dependencies:** Appendix A is authoritative for every other module's access checks; M04 entitlements should cap doctor/staff counts but M03 doesn't reference this itself (see Cross-Cutting Findings).

**Open Decisions:** None self-flagged, but see Finding on RBAC matrix duplication (v1.0 §14 vs Appendix A) below.

---

## M04 — Subscription & Entitlement (C0, P0)

**Goals:** Gate features/limits (branches, doctors, active patients, Copilot, CRM/automation, advanced reports, API/SSO) per plan, enforced server-side, not just hidden in UI.

**Actors:** Platform Admin (assign/change plan), Clinic Owner (see usage vs. limits).

**Use Cases:** US-M04-01 (assign plan), US-M04-02 (usage visibility), US-M04-03 (graceful block at limit, not a silent failure).

**Functional Requirements:** BR-M04-01 (P0, over-limit request → HTTP 403 `ENTITLEMENT_EXCEEDED` + Vietnamese message), BR-M04-02 (P0, downgrade never deletes over-limit data; it goes read-only), BR-M04-03 (P1, Trial expiry → Expired per M01 state machine, warnings at 7/3/1 days), BR-M04-04 (P1, Copilot usage counted per successful AI call, quota shown to doctor).

**Acceptance Criteria:** AC-M04-01..03 — Basic plan calling Copilot API → 403; 3rd doctor on Trial blocked; Professional→Basic downgrade with 3 branches makes branches 2–3 read-only without data loss.

**Out of Scope:** Actual payment/billing rails for the subscription itself (that's business-side contract admin, distinct from M10 patient billing).

**Dependencies:** Consumed by M02 (branch cap), M03 (doctor/staff cap — not cross-referenced), M06 (active-patient cap — "active" undefined, see Cross-Cutting Findings), M13/M14/M16 (feature gating).

**Open Decisions:** Trial active-patient cap is explicitly "đề xuất 200" (proposed, not final) — self-flagged as not yet decided.

---

## M05 — Services & Pricing (C1, P0)

**Goals:** Service/package catalog feeding booking (M07) and billing (M10); support 3/6/12-month chronic-care packages.

**Actors:** Clinic Admin (CRUD services/packages).

**Use Cases:** US-M05-01 (create service), US-M05-02 (create a bundled chronic-care package), US-M05-03 (restrict service by branch/doctor).

**Functional Requirements:** BR-M05-01 (P0, price changes are non-retroactive — appointments/invoices snapshot price at creation time), BR-M05-02 (P0, all price changes audited old→new), BR-M05-03 (P1, cannot deactivate a service with future bookings without warning + affected list), BR-M05-04 (P1, package benefit consumption must decrement correctly; exhausted benefits fall back to itemized billing with receptionist confirmation).

**Acceptance Criteria:** AC-M05-01..03 — price change after booking keeps old price on invoice; 7th visit on a 6-visit package warns; branch-restricted service invisible when booking at another branch.

**Out of Scope:** Not stated.

**Dependencies:** M07 (appointment price snapshot), M10 (invoice line items), M11 (package "chương trình bệnh" relationship — **undefined**, see Cross-Cutting Findings).

**Open Decisions:** None self-flagged.

---

## M06 — Patient Management (C1, P0)

**Goals:** Single source of truth for a patient's administrative + longitudinal health record within a tenant, linked to a platform-level core identity (per v1.0 §8.2); dedup; MetoCare Patient account linkage; CSV/XLSX import.

**Actors:** Receptionist (admin record only, no clinical read), Nurse (vitals/attachments), Doctor (full clinical read/write in scope), Care Coordinator (care-context only), Clinic Admin (merge/import), Patient (self, consent).

**Use Cases:** US-M06-01..06 — fast patient creation (<60s), duplicate-candidate surfacing on phone match, controlled merge, biomarker timeline view, CSV/XLSX import with per-row errors, MetoCare account activation.

**Functional Requirements:** BR-M06-01 (P0, no hard delete, Inactive/Merged only; deletion requests go through M17's separate process), BR-M06-02 (P0, cross-clinic: a clinic sees only data it created + consented shared data, default no sharing), BR-M06-03 (P0, Receptionist has zero API access to clinical content), BR-M06-04 (P1, patient code auto-generated, unique-in-tenant, immutable), BR-M06-05 (P1, manual lab entry requires standard biomarker name+value+unit+draw date; unit mismatch warns, never auto-converts), BR-M06-06 (P1, patient list must paginate, no full-dataset endpoint), BR-M06-07 (P2, national ID stored only if tenant opts in with legal basis, encrypted + partially masked).

**Acceptance Criteria:** AC-M06-01..06 — <60s creation; duplicate warning before create; merge/un-merge within 30 days restores state exactly; import rejects bad rows while committing good ones, mid-batch failure leaves zero partial records; Receptionist blocked (403) from clinical detail; biomarker timeline ordered/unit-correct with reference ranges.

**Out of Scope:** Not explicitly stated but implied: platform-level identity/account management itself is out of this module's scope (belongs to a platform user-account system referenced only by pointer).

**Dependencies:** M17 (consent gates cross-clinic visibility), M09 (clinical content lives here conceptually but is authored via Encounter/Notes), M04 (active-patient entitlement count), M12 (dedup/merge and import-baseline interact with Care Gap task generation, explicitly handled via a "baseline mode" in M12 §12.6).

**Open Decisions:** BR-M06-02's third v1.0 carve-out — "data necessary for the current consultation" (v1.0 §8.4) — has **no corresponding BR/AC in M06 v2.0** (see Cross-Cutting Findings, Finding 2).

---

## M07 — Appointment Management (C1, P0)

**Goals:** Full appointment lifecycle across multiple booking sources with a strict state machine, multi-channel reminders, and change/cancel audit trail; primary input to retention/no-show metrics.

**Actors:** Receptionist, Doctor, Patient (self-booking), Care Coordinator, Marketplace, Partner API — all as booking sources (`created_by_source`).

**Use Cases:** US-M07-01..05 — slot-finding, patient self-booking, audited reschedule, automatic end-of-day no-show marking, doctor-initiated rebooking from an active encounter.

**Functional Requirements:** BR-M07-01 (P0, out-of-state-machine transitions rejected + audited), BR-M07-02 (P0, no double-booking for one doctor unless controlled overbooking is explicitly enabled with a % cap), BR-M07-03 (P0, booking must respect branch + doctor working hours; override needs permission + reason), BR-M07-04 (P1, cancellation inside the cancellation-policy window is flagged for reporting), BR-M07-05 (P1, idempotent end-of-day no-show job, configurable grace period, default 60 min), BR-M07-06 (P1, patient self-booking sees only tenant-opened online slots, never other patients' names).

**Acceptance Criteria:** AC-M07-01..05 — full transition table tested (valid pass, invalid blocked); concurrent double-booking resolves to exactly one winner; 24h/2h reminders fire at VN-timezone-correct times with delivery status; end-of-day no-show job feeds Care Gap Queue; reschedule keeps full audit chain.

**Out of Scope:** Not explicitly stated.

**Dependencies:** M02 (branch hours), M03 (doctor schedule/membership), M05 (service duration/price snapshot), M08 (check-in transitions), M12 (no-show → Care Gap), M15 (reminder delivery). The "controlled overbooking" toggle referenced in BR-M07-02 is **not listed as a configurable field anywhere in M01's clinic settings (§1.5) or M02** — see Cross-Cutting Findings.

**Open Decisions:** None self-flagged.

---

## M08 — Check-in & Queue (C1, P0)

**Goals:** Front-desk check-in (scheduled or walk-in), queue number assignment, real-time doctor/reception queue view, wait-time measurement.

**Actors:** Receptionist (check-in, walk-in intake, priority flag with reason), Doctor (call next), Nurse (vitals while waiting).

**Use Cases:** US-M08-01..05 — fast check-in, walk-in intake flow, real-time queue for doctor, nurse pre-vitals, audited priority elevation.

**Functional Requirements:** BR-M08-01 (P0, check-in transitions appointment to Arrived→In queue; walk-in creates a matching appointment), BR-M08-02 (P0, system never self-determines an emergency — priority flags are human-entered, audited, and clinical rules only ever *suggest*, requiring qualified-person confirmation), BR-M08-03 (P1, queue numbers scoped/reset per tenant config, no duplicates within a reset scope), BR-M08-04 (P1, "no-show at call" returns patient to queue with a missed-call flag, capped retry count), BR-M08-05 (P1, wait time measured check-in→In consultation, feeds M16).

**Acceptance Criteria:** AC-M08-01..04 — check-in ≤3 actions; queue updates real-time or ≤10s polling; public display never shows full name/service; priority elevation requires reason + is audited.

**Out of Scope:** Not stated.

**Dependencies:** M07 (appointment state machine), M09 (queue feeds encounter start), M16 (wait-time metric).

**Open Decisions:** None self-flagged.

---

## M09 — Encounter & Clinical Notes (C1, P0)

**Goals:** SOAP-structured clinical documentation with a strict append-only invariant after finalize — the legal/data-quality foundation for Care Gap, Copilot, and clinical dashboards.

**Actors:** Doctor (author/finalize, Assessment/Plan only they can write), Nurse (Subjective/Objective support only, no conclusions).

**Use Cases:** US-M09-01..05 — start encounter with AI briefing ready, specialty SOAP templates, draft→finalize with amendment-only correction, nurse vitals entry, coded diagnosis (ICD-10 or internal).

**Functional Requirements:** BR-M09-01 (P0, Finalized note is immutable — backend rejects UPDATE/DELETE; corrections are amendments linked to the original, full version chain visible), BR-M09-02 (P0, only Doctor finalizes / writes Assessment-Plan; Nurse cannot), BR-M09-03 (P0, doctor can only open encounters for in-scope patients — own schedule/queue or Admin-assigned), BR-M09-04 (P1, encounter must link to an appointment or be flagged walk-in; max one primary encounter per appointment), BR-M09-05 (P1, AI/Copilot content is never auto-written to a note — doctor must manually insert/accept, and the system marks AI-sourced text for audit), BR-M09-06 (P1, lab orders in Plan auto-create a "not yet performed" tracking item, feeding GAP-01/R2).

**Acceptance Criteria:** AC-M09-01..05 — direct update to a Finalized note is rejected via API; amendment succeeds and shows version history; Nurse cannot write Assessment/Plan or finalize (403); Doctor A cannot open Doctor B's out-of-scope encounter; autosave survives an abrupt browser close (≤30s loss).

**Out of Scope:** Not stated.

**Dependencies:** M11 (Plan → Care Plan), M12 (lab-order tracking → GAP-R2), M14 (Copilot output insertion + AI-sourced marking), M18 (who-viewed-which-note audit).

**Open Decisions:** Amendment authority when a doctor is unavailable long-term (§9.6: "Admin không được finalize thay") is described but has no formal escalation/timeout AC beyond a quality report at 7 days in Draft — no hard resolution defined.

---

## M10 — Billing & Invoicing (C1, P1)

**Goals (MVP-scoped):** Front-desk revenue capture: invoice from service/package/surcharge/discount, multi-method payment, AR status, audited adjustments. Explicitly excludes e-invoice, payment gateway, e-wallet (Phase C4), and general-ledger accounting.

**Actors:** Receptionist (create/collect), Accountant (view all transactions/adjustments, no clinical access), Clinic Owner (approval above discount threshold).

**Use Cases:** US-M10-01..04 — invoice from encounter, partial/deposit payment tracking, accountant transaction/refund visibility, discount-above-threshold approval.

**Functional Requirements:** BR-M10-01 (P0, locked invoice cannot be edited by Receptionist; all price/discount/refund adjustments audited with before/after + reason), BR-M10-02 (P0, line price comes from the M05 price snapshot; manual discount has a role-based cap, e.g. Receptionist ≤10%, Admin ≤30%, above-cap needs approval), BR-M10-03 (P1, one encounter/appointment links to at most one primary invoice; extra charges append pre-lock or become a secondary invoice), BR-M10-04 (P1, package benefit usage creates a 0-price line item + decrements benefit balance), BR-M10-05 (P1, invoice numbers sequential per tenant/branch, never reused after cancellation).

**Acceptance Criteria:** AC-M10-01..04 — Paid invoice line-item edit rejected via API, refund is a separate audited record; 15% discount on a 10%-cap receptionist account requires approval or is rejected; two-part payment (50%+50%) correctly transitions Partially-paid→Paid; Accountant sees revenue reports but is 403'd from clinical notes.

**Out of Scope:** E-invoice, payment gateway integration, e-wallet, general-ledger accounting, payroll (deferred to Phase C4 or explicitly excluded).

**Dependencies:** M05 (price snapshot), M09 (encounter link), M03/Appendix A (Doctor gets limited invoice-view for own encounters — **not reflected in M10's own text**, see Cross-Cutting Findings).

**Open Decisions:** BR-M10-05's "sequential per tenant/branch" phrasing does not specify whether the sequence is one-per-tenant or one-per-branch — ambiguous and has Vietnamese accounting/legal implications (see Cross-Cutting Findings).

---

## M11 — Care Plan (C2, P0)

**Goals:** Standardize long-term chronic-care treatment plans (goals, meds, monitoring, labs, follow-up, lifestyle, alert thresholds) as the primary rule source for Care Gap Queue.

**Actors:** Doctor (create/edit/activate, sole owner), Patient (sees only published content), Care Coordinator (sees overdue items).

**Use Cases:** US-M11-01..04 — create from specialty template, quantitative goal-setting (HbA1c, BP, LDL-C, weight), patient sees only doctor-confirmed content, coordinator sees overdue items.

**Functional Requirements:** BR-M11-01 (P0, only Doctor creates/edits/activates; only one active plan per "disease program" at a time; edits version, preserving history), BR-M11-02 (P0, patient never sees draft/internal content, only published), BR-M11-03 (P1, each item auto-derives Done/Not-done/Overdue/Skipped/Unreachable status and emits events to M12), BR-M11-04 (P1, alert thresholds are deterministic rules generating high-priority Care Gaps requiring qualified confirmation, never auto-messaging medical content to the patient), BR-M11-05 (P2, tenant-level template library, cloneable from a MetoCare template library).

**Acceptance Criteria:** AC-M11-01..04 — template-based plan creation ≤2 min for a standard case; 1-day-overdue follow-up item appears in Care Gap Queue with correct priority; patient app shows zero unpublished content; edits create a new version, old version read-only.

**Out of Scope:** Not stated.

**Dependencies:** M12 (rule source), M05/services packages (relationship to "chương trình bệnh"/disease program concept is **undefined** — see Cross-Cutting Findings), M09 (Plan originates from encounter's Plan section).

**Open Decisions:** The entity "chương trình bệnh" (disease program) that BR-M11-01 scopes uniqueness by is never formally modeled anywhere in the BRD set.

---

## M12 — Care Gap Queue (C2, P0 — core differentiator)

**Goals:** Detect patients falling out of the treatment program via deterministic rules, prioritize, assign, and close the loop with measured outcomes — the product's central differentiator.

**Actors:** Care Coordinator (daily worklist), Clinic Admin (assignment, SLA tracking), Doctor (handles "needs doctor review" cases), Clinic Owner (ROI visibility).

**Use Cases:** US-M12-01..04 — daily prioritized worklist, assignment + SLA tracking, doctor review escalation, weekly outreach-to-return ROI.

**Functional Requirements:** GAP-R1..R9 detection rules (§12.2: overdue follow-up, overdue labs, meds running out, worsening biomarker, lost-to-follow-up ≥90 days, no-show, missing care plan, missing key data, doctor-requested), BR-M12-01 (P0, priority is rule-deterministic, AI/LLM cannot change urgency, manual override needs reason+audit), BR-M12-02 (P0, dedupe — one patient with concurrent matching rules becomes one multi-reason task at the highest priority, no duplicate spam), BR-M12-03 (P1, idempotent rule engine — re-runs never duplicate a task for the same patient/rule/cycle), BR-M12-04 (P1, overdue tasks escalate to Admin; "urgent" tasks must be claimed within ≤4 business hours), BR-M12-05 (P1, "Booked" outcome must link to a real appointment for conversion reporting), BR-M12-06 (P1, patient revoking care-program consent closes open tasks and stops new ones, except safety obligations at doctor's discretion).

**Acceptance Criteria:** AC-M12-01..04 — each GAP-R1..R9 rule has a test producing the correct task+priority, re-running the job twice does not duplicate; overdue-follow-up + meds-running-out on the same patient produces one task with two reasons; "Booked" outcome links to a real appointment; weekly dashboard shows created/on-time-handled/converted-to-visit counts.

**Out of Scope:** Not stated.

**Dependencies:** M07 (no-show), M09 (lab-order tracking), M11 (plan thresholds/overdue items), M13 (feeds the CRM worklist), M17 (consent revocation stops task generation).

**Open Decisions:** None self-flagged, but BR-M12-04's "escalate to Admin" has no defined SLA for what Admin must then do — under-specified beyond the 4-hour claim window.

---

## M13 — CRM / Patient Outreach (C2, P1)

**Goals:** Care-staff working surface for the M12 worklist with a strict "minimum necessary data" (care-context) principle — no full clinical record exposure.

**Actors:** Care Coordinator (calls, logs outcomes, books directly), Clinic Admin (outreach history visibility).

**Use Cases:** US-M13-01..04 — reason-specific call scripts, in-call booking, full outreach history per patient, escalate clinical questions to "needs doctor review".

**Functional Requirements:** BR-M13-01 (P0, Care Coordinator API is a strict care-context whitelist — tested to guarantee no clinical field leaks), BR-M13-02 (P1, every call logs timestamp/caller/outcome/notes/created-appointment), BR-M13-03 (P1, call scripts are rule-configured, no medical detail beyond scope), BR-M13-04 (P1, max contact attempts per task, default 3, before forcing a closing outcome), BR-M13-05 (P2, configurable calling-hours window, default 8:30–19:30, warns on out-of-window logging).

**Acceptance Criteria:** AC-M13-01..03 — call-list API response schema contains zero note/lab/diagnosis fields; in-call booking creates a valid appointment and updates task outcome; outreach history shows the full contact chain over time.

**Out of Scope:** Not stated.

**Dependencies:** M12 (task source), M07 (in-call booking), M18 (call logs feed audit).

**Open Decisions:** None self-flagged.

---

## M14 — Clinical Copilot / AI (C3, P1)

**Goals:** AI-assisted pre-visit briefing and in-visit support for doctors only — explicitly a "prep assistant, not a diagnostic tool"; every output requires doctor confirmation.

**Actors:** Doctor only (in-scope patients), Clinic Owner (usage stats), Platform Admin (kill switch).

**Use Cases:** US-M14-01..04 — 30-second pre-visit briefing (≥50% prep-time reduction KPI), sourced data-conflict flags, usage/acceptance stats, emergency system-wide kill switch.

**Functional Requirements (capabilities):** AI-01 pre-visit briefing (fixed structure incl. "missing data"), AI-02 case analysis (conflicts, differentials-as-questions, source+confidence), AI-03 suggested history questions, AI-04 suggested counseling content (doctor-inserted, AI-origin tagged).
**Safety architecture (all P0, §14.3 — any violation is a go-live blocker):** deterministic risk priority (LLM cannot write urgency), consent gating (M17 C3 checked pre-call), data minimization via a central AI provider gateway, no PHI in technical logs, JSON-schema-validated structured output with a hard fallback on schema failure (never show raw output), mandatory human accept/reject with audit, per-tenant/per-feature flag defaulting OFF in production until operationally approved, 20s timeout with non-blocking fallback, entitlement-based quota.

**Business Rules:** BR-M14-01 (P0, the entire §14.3 safety table is a go-live blocker), BR-M14-02 (P0, Doctor-only, in-scope-patient-only), BR-M14-03 (P1, mandatory disclaimer on every AI output block), BR-M14-04 (P1, prompt/model versioning, production model/prompt changes need an approval process).

**Acceptance Criteria:** AC-M14-01..05 — missing consent disables the Copilot button + blocks the API (403); malformed LLM output shows fallback UI never raw text; production log audit finds zero PHI; accepting a suggestion produces a full audit event; disabling the tenant feature flag hides/blocks every entry point within ≤5 minutes.

**Out of Scope (absolute):** Auto-diagnosis, auto-prescription, auto medication changes, auto-writing to the record, auto-deciding urgency, direct-to-patient medical advice bypassing the doctor.

**Dependencies:** M17 (consent gate), M09 (output insertion + AI-origin tagging), M04 (quota/entitlement), M11/M12 (deterministic risk stays there, Copilot never overrides).

**Open Decisions:** None self-flagged — but note this module ships in Phase C3, after C0–C2, and defaults OFF in production regardless of phase (§14.3), i.e. it is explicitly not part of the C0 scope this program is currently building toward.

---

## M15 — Notifications & Reminders (C1–C2, P0)

**Goals:** Multi-channel (Push/Email now; SMS/Zalo OA later) notification infrastructure with tenant templates, scheduling, delivery status, and history, feeding M07 and M11.

**Actors:** System (automated sends), Clinic (branded templates), Patient (recipient, consent-gated).

**Functional Requirements:** BR-M15-01 (P0, external-channel content — SMS/Zalo/Email — never contains diagnosis/lab results/medication names, only scheduling/operational info; clinical detail stays in-app post-login), BR-M15-02 (P0, channel consent from M17 respected — disabled channel gets nothing sent except minimum legal/safety notices), BR-M15-03 (P1, every send logs template/channel/recipient/timestamp/status/error-code with bounded retry), BR-M15-04 (P1, idempotency — one trigger never double-sends via a dedupe key), BR-M15-05 (P2, configurable marketing-message frequency cap per patient/week).

**Acceptance Criteria:** AC-M15-01..03 — 24h reminder fires within ±5 minutes, re-running the job doesn't duplicate; sample SMS content review shows zero medical PHI; disabling email consent stops all email to that patient except a defined mandatory-notice group.

**Out of Scope:** SMS and Zalo OA are explicitly "giai đoạn sau" (later phase) — MVP is Push+Email only, though the template catalog and BRs are written channel-agnostically as if all channels exist now (see Cross-Cutting Findings — scope/spec mismatch).

**Dependencies:** M07 (appointment reminders), M11 (med/lab/follow-up reminders), M17 (channel consent).

**Open Decisions:** None self-flagged.

---

## M16 — Dashboard & Reports (C1–C2, P1)

**Goals:** Three dashboards — Operational (today), Business (revenue/retention), Clinical (treatment-goal attainment) — built on a shared, pre-agreed metric dictionary.

**Actors:** Clinic Owner/Admin (full), Doctor (own-scope by default), Accountant (business only, no clinical), Care Coordinator (n/a directly, feeds via M13).

**Functional Requirements:** Metric dictionary (§16.2) explicitly defines on-time follow-up rate, no-show rate, 3-month retention, actively-cared-for patient count, care→visit conversion rate, treatment-goal attainment rate — each with a precise formula. BR-M16-01 (P0, RBAC-respecting — Accountant never sees clinical dashboard, Doctor defaults to own numbers), BR-M16-02 (P0, exports are role-gated, no bulk PHI export for unauthorized roles, every export audited with filter+row-count), BR-M16-03 (P1, clinical dashboard only aggregates consented/in-scope data), BR-M16-04 (P1, heavy aggregation via background job/materialized view, dashboard load <3s per Appendix B), BR-M16-05 (P2, cohorts <5 patients anonymized to prevent re-identification).

**Acceptance Criteria:** AC-M16-01..03 — dashboard figure matches a direct metric-dictionary query; Accountant opening clinical dashboard → 403; unauthorized export blocked, authorized export creates an audit record.

**Out of Scope:** Not stated.

**Dependencies:** M07 (no-show/retention inputs), M09/M11 (clinical metrics), M12/M13 (care-conversion metric), M17 (consent-scoped clinical data), M18 (export audit).

**Open Decisions:** None self-flagged, but see Cross-Cutting Findings — the <3s/<2s performance NFRs (Appendix B) are not tied to a defined dataset size, while §15.4/Appendix B's scale target (1M patients, 10M lab records) exists separately with no explicit link between the two.

---

## M17 — Consent & Privacy (C0, P0)

**Goals:** Minimal, versioned, revocable, scoped consent model (C1–C5) gating cross-clinic sharing, AI use, notification channels, and active-care-program participation.

**Actors:** Patient (grants/revokes), Receptionist (counter-collected consent for non-app patients), all consuming modules (M06, M14, M15).

**Functional Requirements:** Consent catalog C1 (share record with clinic X), C2 (share lab results), C3 (AI analysis, opt-in, default off), C4 (notifications, per-channel), C5 (active care program participation). BR-M17-01 (P0, every consent has scope/content-version/grant-time/channel/expiry/status, evidence is immutable), BR-M17-02 (P0, revocation is immediate for future processing, never deletes existing audit/legal records), BR-M17-03 (P0, AI gateway checks C3 pre-call; notification service checks C4 pre-send), BR-M17-04 (P1, counter-collected consent for non-app patients needs a witness field, re-confirmed on app activation), BR-M17-05 (P1, self-flagged: compliance with current Vietnamese personal-data-protection law, including sensitive health-data classification, "needs legal review before pilot" — explicitly unresolved).

**Acceptance Criteria:** AC-M17-01..03 — disabling C3 blocks all AI calls for that patient immediately; revoking C1 for clinic B removes B's access outside what B itself created, while B retains its own legally-required records; every consent shows a full grant/change/revoke version history.

**Out of Scope:** Not stated.

**Dependencies:** M06 (cross-clinic sharing gate), M14 (AI gate), M15 (channel gate), M12 (program-participation gate).

**Open Decisions:** BR-M17-05 is explicitly an open legal-review item — Vietnamese PDPA-equivalent compliance is "to be settled after legal review before pilot," i.e., self-flagged as not resolved and P0-relevant.

---

## M18 — Audit Log (C0, P0)

**Goals:** Append-only, tamper-proof audit trail across every sensitive action platform-wide.

**Actors:** Clinic Owner (own-tenant audit), Platform Admin (operational audit, no default clinical content view).

**Functional Requirements:** Mandatory event catalog (§18.1): login/logout/failure, patient-record access, clinical-data views, note create/finalize/amend, role/membership changes, exports, invoice/discount/refund changes, AI calls, AI accept/reject, consent changes, tenant status changes, record merges, priority overrides. BR-M18-01 (P0, append-only — no app-level update/delete; captures actor/action/resource/tenant/UTC+VN-display time/IP-device/before-after), BR-M18-02 (P0, no PHI beyond necessary — reference IDs, not note content), BR-M18-03 (P1, query access is role-scoped — Owner sees own tenant, Platform Admin sees ops but not clinical content by default), BR-M18-04 (P1, retention period self-flagged as unresolved — "proposed ≥5 years, pending legal review").

**Acceptance Criteria:** AC-M18-01..03 — 100% of the §18.1 event catalog produces a record (checklist test); no API can modify/delete an audit record; "who viewed patient X's record in the last 30 days" query returns correctly.

**Out of Scope:** Not stated.

**Dependencies:** Sink for nearly every other module (M01, M03, M06, M09, M10, M14, M17 all write to it).

**Open Decisions:** BR-M18-04 retention period explicitly unresolved pending legal review (same open item as M17's BR-M17-05 — these two should be resolved together).

---

## Appendix A — RBAC Matrix (detailed)

Declared as the backend "source of truth" for all authorization (referenced by BR-M03-01). Uses ✓ (full), R (read-only), L (limited per module's own scope description), ✗ (forbidden). Covers M01–M18 resources by role (Owner/Admin/Doctor/Nurse/Reception/Care/Accountant). See Cross-Cutting Findings for a discrepancy against the v1.0 §14 summary table it supersedes.

## Appendix B — Non-Functional Requirements (shared)

Inherits v1.0 §15 verbatim per its own header ("kế thừa nguyên trạng"). Security P0 gate list: tenant isolation with cross-tests, backend RBAC, TLS, encryption at rest, no PHI in logs, controlled error responses, rate limiting, session timeout, CI secret scanning, production security gate before go-live. Performance: list views <2s, dashboards <3s, mandatory pagination, background jobs for heavy work, AI timeout+fallback. Availability: responsive desktop/tablet/mobile, ≥16px body font, ≥44px touch targets, no horizontal scroll at 390px, Vietnamese UI. Scale target: 1,000 clinics, 10,000 staff, 1M patient records, 10M lab/measurement records.

## Appendix C — Traceability (module → phase → program AC)

Maps C0={M01,M02,M03,M04,M17,M18}→program AC #1,#2,#13; C1={M05–M10,M15,M16 operational+basic revenue}→AC #3–#7,#12,#14; C2={M11,M12,M13,M16 retention+clinical}→AC #8–#11; C3={M14 extended}→per AI operational approval. Defines "Done" for a module as: all P0/P1 ACs pass, RBAC negative tests pass, audit-event checklist complete, zero open P0/P1 security findings, CI/migration/deploy/authenticated-smoke all green.

---

## Cross-Cutting Findings

1. **RBAC matrix duplication with a real discrepancy (v1.0 §14 vs Appendix A).** `docs/brd/v1.0/executive-brd.md` §14 (line ~973) lists Care Coordinator's "Xem hồ sơ lâm sàng" (view clinical record) access as "Hạn chế" (restricted, implying *some* access). `docs/brd/v2.0/appendix-a-rbac-matrix.md` (line 13) lists Care Coordinator's "Hồ sơ lâm sàng (M06/M09)" access as flat `✗` (forbidden), with a separate `✓` only for the distinct "CRM chăm sóc (M13)" resource (care-context subset, line 21). BR-M03-01 declares Appendix A the sole source of truth, but the v1.0 table is never marked superseded/deprecated in the README, so a reader or reviewer citing v1.0 §14 would draw a materially different (looser) conclusion about Care Coordinator's clinical-record access than the one Appendix A and M13's BR-M13-01 actually enforce. Recommend the README explicitly deprecate v1.0 §14 in favor of Appendix A.

2. **Dropped requirement: "current-consultation" cross-clinic data carve-out.** `docs/brd/v1.0/executive-brd.md` §8.4 (line ~277–283) lists four categories of data a clinic may see about a multi-clinic patient, including "Dữ liệu cần thiết cho consultation hiện tại" (data necessary for the current consultation — i.e., some form of break-glass/contextual access during an active visit, independent of standing consent). `docs/brd/v2.0/m06-patient.md` BR-M06-02 (line 73) restates only two of the four categories ("dữ liệu do mình tạo" + "dữ liệu bệnh nhân consent chia sẻ") and omits the consultation-context carve-out entirely — no BR or AC in M06 v2.0 operationalizes it. Since this directly affects the P0 tenant-isolation model, the architecture phase needs an explicit decision: is this v1.0 provision dropped intentionally, or missing from v2.0 by oversight?

3. **Undefined core entity: "chương trình bệnh" (disease program).** BR-M11-01 (`m11-care-plan.md` line 28) scopes care-plan uniqueness — "bản active tại một thời điểm là duy nhất cho mỗi chương trình bệnh" — by a "disease program" concept that is never modeled as an entity anywhere in M05, M06, M09, or M11. It's unclear whether this maps to a diagnosis code, a M05 SERVICE-03 package subscription, or a free-standing new entity. This blocks a clean data model for Care Plan and, transitively, Care Gap Queue (M12) rule scoping.

4. **Undefined/ambiguous term: "bệnh nhân active" (active patient).** Used as a hard entitlement limit in M04 (§4.2, "Bệnh nhân active: Giới hạn (đề xuất 200)"), as a Care Gap trigger condition in M12 (GAP-R5, `m12-care-gap-queue.md` line 15), and implicitly in M16's "Đạt mục tiêu điều trị" metric (line 18, "% bệnh nhân active có care plan..."). No module defines what makes a patient "active" (e.g., an open care plan? an encounter within N days? not merged/inactive?) — three modules use the term for three different purposes without a shared definition, risking three different implementations.

5. **Missing cross-reference: M04 entitlement caps not echoed in the modules that must enforce them.** M04 (BR-M04-01, AC-M04-02) states branch/doctor-count limits are enforced at the API layer with a specific 403 contract, and gives a worked example ("tạo bác sĩ thứ 3 trên gói Trial → bị chặn"). But M02 (branch creation, BR-M02-01..04) and M03 (staff invitation, BR-M03-01..06) — the actual enforcement points — never reference M04 or the entitlement check in their own business rules. This is a genuine cross-module dependency gap that risks the entitlement check being implemented only in M04's own tests and skipped in M02/M03's.

6. **Undefined settings field: controlled overbooking toggle.** BR-M07-02 (`m07-appointment.md` line 59) allows double-booking "trừ khi tenant bật chế độ overbooking có kiểm soát (giới hạn %, ghi nhận rõ)" — but no clinic-level settings field for this exists in M01's data-field table (§1.5) or M02's branch fields (§2.4). The toggle is referenced but never defined as configurable data.

7. **Ambiguous invoice numbering scope.** BR-M10-05 (`m10-billing.md` line 29) says invoice numbers are "liên tục theo tenant/chi nhánh" (sequential per tenant/branch) — the slash is ambiguous as to whether there is one sequence per tenant (shared across branches) or one sequence per branch. This has real Vietnamese accounting/tax-compliance implications and should be resolved explicitly, ideally alongside the legal review already flagged for M17/M18 (finding 9 below).

8. **Module-content gap: Doctor's invoice access defined in Appendix A but absent from M10's own text.** Appendix A (line 22) grants Doctor `L (xem của encounter mình)` — limited view of invoices tied to their own encounters — but M10's user stories, business rules, and ACs (`m10-billing.md`) never mention a Doctor actor at all. The permission exists only in the RBAC matrix, with no corresponding functional spec (what exactly can a doctor see on an invoice?) or AC in the owning module.

9. **Two P0-relevant legal/compliance items self-flagged as unresolved, but not linked to each other.** BR-M17-05 (`m17-consent-privacy.md` line 19) flags Vietnamese personal-data-protection law compliance (incl. sensitive health data) as needing legal review before pilot. BR-M18-04 (`m18-audit-log.md` line 12) separately flags audit-retention period ("đề xuất ≥5 năm") as pending the same kind of legal review. These are almost certainly the same legal-review workstream but are documented as two independent open items in two different modules — worth consolidating into one legal/compliance action item before C0 sign-off.

10. **Performance NFR not tied to a load/scale assumption.** Appendix B and v1.0 §15.2 state list views load "<2s" and dashboards "<3s" without specifying at what dataset size or concurrency this applies, while a separate scale target exists (§15.4/Appendix B: 1,000 clinics, 10,000 staff, 1M patient records, 10M lab/measurement records). Because a "<2s" list-load target is only meaningful relative to a stated N (rows scanned, index strategy, tenant size), these two numbers should be explicitly connected — otherwise "fast" is untestable at production scale even though a number is present.

11. **Security NFRs stated without a mechanism.** Appendix B / v1.0 §15.1 list "Encryption at rest" and "TLS" as requirements with no algorithm/version specified (e.g., AES-256? TLS 1.2 minimum?), and "Rate limit" with no threshold given anywhere in the BRD set. These read as complete requirements but are not independently testable/verifiable as written — classic "secure without a mechanism" under-specification.

12. **Scope/spec mismatch in Notifications.** M15 (`m15-notifications.md`) writes its business rules and template catalog as if all channels (Push, Email, SMS, Zalo OA) are equally in scope, but its own §15.1 states SMS/Zalo OA are "giai đoạn sau" (later phase, consistent with v1.0 §16's phase table putting SMS/Zalo/payment/e-invoice in "Giai đoạn sau"). BR-M15-01 through BR-M15-05 don't distinguish which rules apply to the MVP-available channels (Push/Email) vs. the deferred ones, which could lead to over-building for phase C1/C2.

13. **No formal doctor-unavailability escalation for stuck Draft notes.** M09 §9.6 explicitly forbids Admin from finalizing a note on a doctor's behalf ("Admin không được finalize thay") but the only defined consequence of a stuck Draft is a quality report at 7 days (§9.6) — there's no BR/AC defining what actually happens to that encounter's data integrity or downstream Care Gap/Copilot consumption while the note stays in Draft indefinitely. Worth flagging for the architecture phase since M12's rules key off finalized clinical data in places (e.g., GAP-R7 "chưa có care plan... sau 2 lượt khám").

14. **Program-level acceptance criteria (v1.0 §22) rely on modules not yet phased for C0/C1.** AC #8 ("Phòng khám tạo care plan và lịch tái khám") and AC #9 ("Hệ thống tạo danh sách bệnh nhân quá hạn") reference M11/M12, which Appendix C explicitly assigns to Phase C2 — meaning the full v1.0 §22 "pilot-ready" checklist cannot be satisfied by C0 or C1 alone. This is consistent with the phased plan (Appendix C ties AC groups to phases correctly) but is worth calling out explicitly so the orchestrating session doesn't mistake the v1.0 §22 list for a C0-completion checklist.
