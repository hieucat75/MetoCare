# MEDICATION_ROADMAP.md
# MetoCare — Medication Management Roadmap P0 → P4

**Version:** 1.0  
**Date:** 2026-07-10  
**Total estimated effort:** ~66 developer-days  
**Constraint:** Independent rollout per slice. No Clinic SaaS changes. No destructive migrations.

---

## Overview

```
P0: Medication Data Correctness + Safety Foundation    (~10 days)
P1: Schedule + Reminder + Adherence                    (~10 days)
P2: OCR Prescription Capture                           (~15 days)
P3: Interaction + Allergy Intelligence                 (~20 days)
P4: Refill + Caregiver + Doctor Loop                   (~11 days)
```

---

## Phase P0 — Medication Data Correctness + Safety Foundation

### Scope

Fix the underlying data model and UI so medication records are complete, safe, and usable. No interaction logic yet. No OCR. Just making the core correct.

### User Stories

- As a patient, I want to mark a medication as "Đã ngừng" so it no longer appears in my active list but is still in history.
- As a patient, I want to know which medications are supplements vs prescription drugs.
- As a patient, I want to see the generic name and drug class of my medications, not just the brand name.
- As a patient, I want to record when I started a medication and who prescribed it.
- As a patient, I want a dedicated detail screen for each medication.
- As a patient, I want to see drug catalog caution flags when I pick a medication.

### Schema / API / UI

**Backend:**
- Alembic migration: add columns to `medications` table (status, generic_name, active_ingredient, drug_class, drug_catalog_id, dose_amount, dose_unit, route, start_date, end_date, is_prn, indication, prescribed_by, source_type, is_supplement, supplement_category, supplement_evidence_note)
- Update `MedicationCreate` / `MedicationUpdate` / `MedicationOut` schemas
- Update `add_medication()` service: if `drug_catalog_id` provided, auto-populate generic_name, active_ingredient, drug_class
- Enforce `supplement_evidence_note` auto-population when `is_supplement=True`
- Update `_build_medications()` in AI context builder to include generic_name, drug_class, status, is_supplement
- Extend drug catalog seed to ~80 drugs (add pain management, antibiotics, vitamins, TCM)

**Frontend:**
- Expand AddMedication bottom sheet with status selector, start_date picker, prescribed_by field, is_supplement toggle
- Add supplement_category selector when is_supplement=True
- Show caution_flags from DrugSuggestItem in autocomplete dropdown
- Show generic_name below brand name in MedicationRow
- Build `/medications/[id]` detail page (Screen MF-03)
- Wire `MedicationCard` design system component to real API data

### Migration

```
med_p0_a_medications_enhance  — ADD COLUMNS (all nullable, no data loss)
med_p0_b_medications_constraints — ADD CHECK CONSTRAINTS
med_p0_c_medications_indexes — CREATE INDEXES
```

**Rollback:** DROP COLUMNS (all nullable — safe) or drop constraints/indexes.

### Safety Risks

- Adding nullable columns to large table: LOW risk (SQLite handles this without lock)
- supplement_evidence_note population: must be enforced at service layer, not just schema
- Generic name denormalization: if catalog is updated, existing records have stale generic_name — accept this (immutable snapshot)

### Test Cases

- All P0-U01 through P0-A08 from test matrix
- Regression: existing medication CRUD tests must still pass
- New: supplement creation requires supplement_category + auto-evidence-note

### Dependencies

- None — P0 is standalone

### Acceptance Criteria

| # | Criterion |
|---|-----------|
| AC-P0-1 | Patient can mark medication as "Đang dùng / Tạm dừng / Đã ngừng" |
| AC-P0-2 | Active medication list shows only status=active records |
| AC-P0-3 | Medication created from catalog has generic_name populated |
| AC-P0-4 | Supplement medication has is_supplement=True and supplement_evidence_note populated |
| AC-P0-5 | Medication detail page /medications/[id] loads all fields |
| AC-P0-6 | Caution flags shown in autocomplete for drugs with caution_flags |
| AC-P0-7 | AI context includes generic_name and drug_class for Meto |
| AC-P0-8 | All existing medication API tests pass |

### Rollout / Rollback

- Deploy backend migration first (nullable columns — zero downtime)
- Deploy frontend after migration confirmed
- Rollback: remove frontend feature flag, run migration downgrade

### Codex Review Gate

- [ ] Migration is additive only (no column drops or renames)
- [ ] supplement_evidence_note is enforced at service layer
- [ ] AI_SERVICE token still blocked on write endpoints after schema change
- [ ] No PHI in error messages or logs

---

## Phase P1 — Schedule + Reminder + Adherence

### Scope

Enable patients to set specific dose times. Build reminder notification infrastructure. Fix the approximated weekly adherence chart with real per-day data.

### User Stories

- As a patient, I want to set "Uống thuốc lúc 8:00 sáng và 20:00 tối" and receive push reminders.
- As a patient, I want to see my actual per-day adherence history (not approximated).
- As a patient, I want to receive a notification when it's time to take a medication.
- As a patient, I want to log a dose directly from the notification.

### Schema / API / UI

**Backend:**
- Create `medication_schedules` table
- Add `medication_reminder` to `NOTIFICATION_TYPES`
- Add `schedule_id` FK to `medication_adherence`
- Add `GET /patients/{id}/medications/{mid}/adherence/daily` — per-day aggregated history
- Add `POST /patients/{id}/medications/{mid}/schedules` — create schedule
- Add `DELETE /patients/{id}/medications/{mid}/schedules/{sid}` — remove schedule
- Notification scheduler service: query all active schedules, create Notification records at correct times
- PHI encryption: apply `EncryptedString` to `medications.name` and `medications.dose`

**Frontend:**
- Reminder schedule screen (Screen MF-08)
- Fix WeeklyAdherenceSection to use real per-day API data
- Per-medication adherence history tab on detail screen

### Migration

```
med_p1_a_schedules              — CREATE medication_schedules table
med_p1_b_adherence_schedule_link — ADD schedule_id to medication_adherence
med_p1_c_notification_type      — Application code: add medication_reminder type
```

### Safety Risks

- PHI encryption migration: test that decrypt/encrypt roundtrip works on SQLite AND staging Postgres
- Notification scheduler: must not leak PHI in notification body
- Reminder fires after medication is soft-deleted: scheduler must check deleted_at before sending

### Test Cases

- P1-U01 through P1-N04 from test matrix
- PHI encryption: encrypted fields decrypt correctly; raw SQL shows no plaintext

### Acceptance Criteria

| # | Criterion |
|---|-----------|
| AC-P1-1 | Patient can create a daily reminder at a specific time |
| AC-P1-2 | Notification arrives at correct time with correct format |
| AC-P1-3 | Notification body contains NO dose or frequency |
| AC-P1-4 | Weekly adherence chart shows real per-day data |
| AC-P1-5 | Schedule linked to adherence record when patient logs from reminder |
| AC-P1-6 | medications.name encrypted at rest |

### Rollout / Rollback

- Deploy migrations first
- Deploy scheduler service
- Enable for internal test accounts only before general release
- Rollback: disable scheduler service, migrations reversible

### Codex Review Gate

- [ ] Notification body confirmed PHI-free
- [ ] PHI encryption confirmed on staging
- [ ] Reminder scheduler handles deleted medications
- [ ] No reminder fires for status != 'active' medications

---

## Phase P2 — OCR Prescription Capture

### Scope

Patient can photograph a prescription, system extracts medication data, patient confirms before saving. Reuse existing lab OCR infrastructure.

### User Stories

- As a patient, I want to photograph my prescription and have the medications pre-filled for me to review.
- As a patient, I must be able to review and correct each extracted medication before it is saved.
- As a patient, I trust that nothing is saved to my medication list without my explicit confirmation.

### Schema / API / UI

**Backend:**
- New endpoint: `POST /patients/{id}/medications/ocr-upload` — accepts image, returns OCR result in pending state
- New endpoint: `POST /patients/{id}/medications/ocr-confirm` — confirms one medication from OCR result
- New domain module: `app/domain/prescription_extractor.py` — text → structured medication fields
- Reuse existing `ocr_engine.py` and OCR provider chain
- Store OCR raw text encrypted (`EncryptedString`)
- Pending OCR state: store as temporary `ocr_pending` records (separate table or status field)

**Frontend:**
- Capture screen (Screen MF-11 part 1)
- OCR review screen per medication (Screen MF-11 part 2)
- Confidence indicators per field
- Summary screen (Screen MF-11 part 3)
- Allergy + duplicate check shown before confirm button

### Migration

- No medication schema changes needed (source_type='ocr_confirmed' already planned in P0)
- New table: `medication_ocr_sessions` for pending state

### Safety Risks (CRITICAL)

- Auto-activation without confirmation: triple-guard (state machine + service check + frontend disabled until confirm)
- Wrong drug name from OCR: confidence threshold enforced; low-confidence fields left empty
- PHI in raw OCR text: must be encrypted at rest; never logged; never in error messages
- Allergy conflict on confirm: check BEFORE allowing patient to tap confirm

### Stop Gate

**STOP if:** Prescription OCR is to be released to real users before PTH manually verifies on staging with real prescriptions.

### Acceptance Criteria

| # | Criterion |
|---|-----------|
| AC-P2-1 | Patient can upload prescription photo |
| AC-P2-2 | Extracted medications shown for review with confidence indicators |
| AC-P2-3 | Low-confidence (<60%) fields shown empty with warning |
| AC-P2-4 | Medication NOT saved until patient taps "Xác nhận" per item |
| AC-P2-5 | Allergy check runs before confirm is allowed |
| AC-P2-6 | OCR raw text encrypted in DB |
| AC-P2-7 | No OCR text in application logs |

### Codex Review Gate

- [ ] No auto-activation path exists in code (search for source_type='ocr_confirmed' assignments without explicit confirm call)
- [ ] OCR encrypted storage confirmed
- [ ] Allergy check runs on confirm endpoint
- [ ] PHI-free error messages

---

## Phase P3 — Drug Interaction + Allergy Intelligence

### Scope

Patient allergies recorded. Drug-drug interactions detected. Drug-lab interactions detected. Warnings surfaced with proper severity and evidence labels. Vietnamese doctor review required before production release.

### User Stories

- As a patient, I want to record my drug allergies so the app can warn me.
- As a patient, when I add a medication that conflicts with an allergy, I want to see a critical warning.
- As a patient, I want to know if two of my medications may interact.
- As a patient, I want the interaction warning to tell me what might happen and what to do.

### Schema / API / UI

**Backend:**
- Create `patient_allergies` table + CRUD endpoints
- Create `medication_warnings` table
- Create `drug_interaction_rules` table + seed 50 priority pairs
- Warning generator service: `generate_medication_warnings(patient_id, db)` — runs on add/confirm
- Drug-lab trigger: hook into lab save pipeline to check active medications
- New endpoints:
  - `POST/GET/DELETE /patients/{id}/allergies`
  - `GET /patients/{id}/medications/warnings`
  - `POST /patients/{id}/medications/warnings/{wid}/dismiss`

**Frontend:**
- Add allergy screen (Screen MF-09)
- Warning banner on medication list
- Warning detail screen (Screen MF-10)
- CRITICAL warning: no dismiss button
- HIGH warning: "Tôi đã hỏi bác sĩ" acknowledge button
- Allergy section on patient profile

### Stop Gates

**STOP if:**
- External paid drug database needed (DrugBank, Lexicomp, MIMS API)
- Vietnamese doctor has NOT reviewed the 50-pair interaction rule set before production
- Any interaction feature is framed as "diagnosis" rather than "warning"

### Migration

```
med_p3_a_allergies          — CREATE patient_allergies
med_p3_b_warnings           — CREATE medication_warnings
med_p3_c_interaction_rules  — CREATE drug_interaction_rules + seed 50 pairs
med_p3_d_catalog_enrich     — ADD is_traditional_medicine, evidence_level to drug_catalog
```

### Acceptance Criteria

| # | Criterion |
|---|-----------|
| AC-P3-1 | Patient can add, edit, and remove allergies |
| AC-P3-2 | Adding medication with allergy conflict shows CRITICAL warning |
| AC-P3-3 | CRITICAL warning cannot be dismissed |
| AC-P3-4 | Warfarin + Aspirin triggers HIGH/CRITICAL warning |
| AC-P3-5 | All warnings show severity + evidence_source + evidence_quality |
| AC-P3-6 | All warnings show disclaimer: "Cảnh báo tham khảo, không phải chẩn đoán" |
| AC-P3-7 | Supplement interactions show evidence_quality = 'limited' |
| AC-P3-8 | Vietnamese doctor has signed off on interaction rule set (required before production) |

### Codex Review Gate

- [ ] CRITICAL warning dismiss endpoint returns 403
- [ ] Warning schema requires evidence_source and evidence_quality
- [ ] Disclaimer text present in all warning responses
- [ ] Supplement interactions use limited evidence_quality
- [ ] Doctor clinical review completed (sign-off document in docs/)

---

## Phase P4 — Refill + Caregiver + Doctor Loop

### Scope

Track medication refills, enable caregiver access, export medication list for doctor visits.

### User Stories

- As a patient, I want to know when I'm running low on a medication so I can refill in time.
- As a patient, I want my spouse to see my medication list and receive reminder copies.
- As a patient, I want to export my medication list as a summary for my doctor appointment.
- As a doctor, I want to see a patient's complete medication history in one view.

### Schema / API / UI

**Backend:**
- Create `medication_refills` table + CRUD endpoints
- Create `caregiver_assignments` table + CRUD endpoints
- Refill alert service: calculate remaining days, create alert notification
- Export endpoint: `GET /patients/{id}/medications/summary.pdf` or structured JSON for doctor
- Caregiver auth: use existing consent model extended for caregiver relationship

**Frontend:**
- Refill tracking screen (Screen MF-12)
- Caregiver setup flow in Settings
- Export action on medication detail screen
- Doctor portal: enhanced medication tab showing history + refills

### Stop Gates

- **STOP if:** Caregiver feature needs Vietnamese personal data law review (data sharing between two private individuals)
- **STOP if:** Export format requires medical record compliance review

### Acceptance Criteria

| # | Criterion |
|---|-----------|
| AC-P4-1 | Patient can add refill record |
| AC-P4-2 | Refill alert fires at 7 days remaining |
| AC-P4-3 | Patient can add a caregiver with specific permissions |
| AC-P4-4 | Caregiver cannot add/edit/delete medications |
| AC-P4-5 | Caregiver notification has no medication name in body |
| AC-P4-6 | Patient can export medication list as summary |
| AC-P4-7 | Doctor sees medication summary including refill history |

### Codex Review Gate

- [ ] Caregiver cannot modify patient medications (test RT-series)
- [ ] Refill notification body PHI-free
- [ ] Export endpoint respects consent scope before returning data

---

## Stop Gate Registry

| Gate | Condition | Block |
|------|-----------|-------|
| SG-01 | External drug database license needed | Block P3 interaction rules if needed |
| SG-02 | Production SMS/push for medication reminders | Block P1 production release |
| SG-03 | OCR on real users without staging verification | Block P2 production release |
| SG-04 | Vietnamese doctor review of interaction rules | Block P3 production release |
| SG-05 | Real patient data for testing | Block all development use of production data |
| SG-06 | Destructive medication schema migration | Block — requires explicit PTH approval |
| SG-07 | AI auto-medication change | Block permanently — not in roadmap |
| SG-08 | Caregiver legal/privacy review | Block P4 production release |
| SG-09 | Electronic prescription / hospital integration | Block — separate program |
