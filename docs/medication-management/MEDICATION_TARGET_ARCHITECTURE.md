# MEDICATION_TARGET_ARCHITECTURE.md
# MetoCare — Medication Management: Target Architecture

**Version:** 1.0  
**Date:** 2026-07-10  
**Author:** OpenClaw (Product Architecture)  
**Status:** Design only — no code changes

---

## 1. Design Principles

1. **Patient safety above all.** Every architecture decision defaults to the safer option when there is a trade-off.
2. **Human-in-the-loop for clinical actions.** AI reads, humans decide. AI never writes medications, changes doses, or activates schedules without explicit patient confirmation.
3. **Layered trust.** Patient confirms their own medications. Doctor reviews and sources. AI explains only.
4. **Fail safe.** If drug catalog is unavailable, patient can still add medications as free text. If interaction check fails, the app does not block — it logs and surfaces a warning that check was unavailable.
5. **PHI minimization.** Medication names, doses, and schedules are PHI. Treat accordingly: encryption at rest, no PHI in logs, no PHI in notification preview body.
6. **Independent rollout.** Each architectural layer can be deployed independently and rolled back without affecting other layers.

---

## 2. The Four Layers

```
┌─────────────────────────────────────────────────────────┐
│               Layer 4: Medication Care Loop              │
│   Reminder · Adherence · Refill · Caregiver · Doctor    │
├─────────────────────────────────────────────────────────┤
│              Layer 3: Medication Capture                  │
│         OCR · Box Photo · Barcode · Confirmation        │
├─────────────────────────────────────────────────────────┤
│             Layer 2: Medication Intelligence              │
│    Duplicate · Allergy · Drug-Drug · Drug-Lab Warning   │
├─────────────────────────────────────────────────────────┤
│                Layer 1: Medication Core                   │
│  CRUD · Status · Generic Link · Schedule · PRN · Source │
└─────────────────────────────────────────────────────────┘
```

Each layer depends on the layer below. Layer 1 must be stable before Layer 2 is built. Layers can be deployed sequentially.

---

## 3. Layer 1 — Medication Core

**Goal:** A structurally correct, complete medication record per patient.

### 3.1 Data Model (target)

```
medications (enhanced)
├── id                    UUID PK
├── patient_id            FK → patient_profiles.id
├── drug_catalog_id       FK → drug_catalog.id (nullable — free text allowed)
├── name                  String(255) — user-facing display name (brand or generic)
├── generic_name          String(255) nullable — canonical generic name
├── active_ingredient     String(255) nullable — primary active ingredient
├── drug_class            String(128) nullable — therapeutic class
├── dose_amount           Numeric(10,4) nullable — structured dose value
├── dose_unit             String(32) nullable — mg, mcg, ml, IU, etc.
├── dose_text             String(128) nullable — free text fallback, e.g. "1 viên"
├── route                 String(64) nullable — oral, topical, injection, inhaled
├── frequency_code        String(32) nullable — QD, BID, TID, QID, PRN, WEEKLY, etc.
├── frequency_text        String(128) — human-readable, e.g. "2 lần/ngày"
├── timing_instructions   Text nullable — e.g. "uống sau bữa ăn sáng"
├── start_date            Date nullable
├── end_date              Date nullable
├── is_prn                Boolean default False — as-needed flag
├── prn_indication        String(255) nullable — when to take PRN
├── indication            String(512) nullable — reason for use (patient-entered)
├── prescribed_by         String(255) nullable — doctor name (free text)
├── prescription_ref      String(64) nullable — reference to prescription/encounter
├── source_type           String(32) — manual | ocr_confirmed | doctor_added
├── status                String(32) — active | paused | completed | discontinued
├── is_supplement         Boolean default False — supplement/traditional medicine flag
├── supplement_category   String(64) nullable — herbal | vitamin | functional_food | tcm
├── supplement_evidence_note Text nullable — evidence quality disclaimer
├── note                  Text nullable — patient free text
├── created_at            DateTime
├── updated_at            DateTime
├── deleted_at            DateTime nullable — soft delete
```

### 3.2 Key Invariants

- `drug_catalog_id` is nullable. Patient can always add free-text medication. Catalog link is a bonus, not a requirement.
- When `drug_catalog_id` is set, `generic_name` and `active_ingredient` are auto-populated from catalog at creation time and stored on the record (denormalized for immutability — catalog may be updated later).
- `status` must be one of: `active`, `paused`, `completed`, `discontinued`. Default: `active`.
- `is_supplement = True` when drug_class is `hepatoprotective_supplement` or when user explicitly marks as supplement. A separate `supplement_evidence_note` must be stored.
- `source_type = 'ocr_confirmed'` only after patient confirms the OCR result. OCR cannot create a record directly.
- `dose_amount + dose_unit` is structured; `dose_text` is free text fallback. Both can coexist.

### 3.3 Frequency Codes

| Code | Meaning |
|------|---------|
| QD | Once daily |
| BID | Twice daily |
| TID | Three times daily |
| QID | Four times daily |
| QOD | Every other day |
| WEEKLY | Once per week |
| PRN | As needed |
| CUSTOM | Custom schedule (see frequency_text) |

---

## 4. Layer 2 — Medication Intelligence

**Goal:** Surface clinically relevant warnings to the patient. Not diagnose. Not prescribe. Warn.

### 4.1 Warning Types

| Type | Trigger | Severity Levels |
|------|---------|----------------|
| Duplicate active ingredient | Same `active_ingredient` in two active medications | HIGH |
| Duplicate therapeutic class | Same `drug_class` in two active medications | MEDIUM |
| Known allergy | `active_ingredient` or `drug_class` in patient allergy list | CRITICAL |
| Drug-drug interaction | Pair match in interaction rules | LOW / MEDIUM / HIGH / CRITICAL |
| Drug-lab flag | Lab result + medication combination | MEDIUM / HIGH |
| Organ caution | `renal_caution=True` + elevated creatinine lab | MEDIUM |

### 4.2 Warning Schema

```
medication_warnings
├── id                UUID PK
├── patient_id        FK
├── medication_ids    JSON — list of involved medication ids
├── warning_type      String(64) — duplicate_ingredient | allergy | drug_drug | drug_lab | organ_caution
├── severity          String(16) — LOW | MEDIUM | HIGH | CRITICAL
├── title             String(255) — display title (Vietnamese)
├── body              Text — warning explanation (Vietnamese)
├── evidence_source   String(255) — e.g. "MetoCare Drug Catalog v1.0" or "MIMS Vietnam"
├── evidence_quality  String(32) — catalog_based | clinical_db | expert_reviewed
├── is_dismissed      Boolean default False
├── dismissed_at      DateTime nullable
├── dismissed_by      String(36) nullable — user id
├── created_at        DateTime
```

### 4.3 Warning Generation Points

1. **On medication ADD** — run duplicate ingredient + class check + allergy check against current active medications
2. **On medication CONFIRM (OCR)** — same checks before saving
3. **On lab result save** — run drug-lab check for all active medications
4. **Periodic background check** — daily re-evaluate active medications (catches catalog updates)

### 4.4 Allergy Schema

```
patient_allergies
├── id                UUID PK
├── patient_id        FK → patient_profiles.id
├── allergen_type     String(32) — drug | food | environmental | other
├── allergen_name     String(255) — e.g. "penicillin", "sulfonamides"
├── drug_catalog_id   FK nullable — link to catalog entry if drug allergy
├── active_ingredient String(255) nullable — canonical ingredient
├── drug_class        String(128) nullable — class-level allergy
├── reaction_type     String(128) nullable — rash | anaphylaxis | GI | unknown
├── severity          String(16) — mild | moderate | severe | life_threatening
├── notes             Text nullable
├── verified_by_doctor Boolean default False
├── created_at        DateTime
├── updated_at        DateTime
├── deleted_at        DateTime nullable
```

### 4.5 Drug Interaction Rules (MVP approach)

Phase 3 MVP: use curated static rule table (not external API). External paid API is a Stop Gate item.

```
drug_interaction_rules
├── id                UUID PK
├── ingredient_a      String(255)
├── ingredient_b      String(255)
├── interaction_type  String(64) — pk_interaction | additive | antagonistic | contraindicated
├── severity          String(16)
├── mechanism         Text nullable — pharmacological explanation
├── clinical_effect   String(512) — what happens to patient
├── management        String(512) — what patient/doctor should do
├── evidence_level    String(32) — A | B | C | expert_opinion
├── source            String(255)
├── version           String(16) — rule set version
├── is_active         Boolean
```

**MVP rule set:** ~50 high-priority pairs covering MetoCare patient population:
- warfarin + aspirin (major bleeding)
- warfarin + NSAIDs (major bleeding)
- statin + fibrate (myopathy)
- SGLT2i + loop diuretic (dehydration)
- ACEi/ARB + potassium-sparing diuretic (hyperkalemia)
- Beta-blocker + calcium channel blocker (heart block)
- Metformin + contrast/iodine dye (lactic acidosis)
- Colchicine + clarithromycin (toxicity via CYP3A4)
- Sulfonylurea + fluoroquinolone (dysglycemia)
- Levothyroxine + calcium/iron (absorption block)

---

## 5. Layer 3 — Medication Capture

**Goal:** Help patient add medications accurately from photos/prescriptions, with mandatory human confirmation.

### 5.1 Capture Sources

| Source | Feasibility | Confidence |
|--------|------------|------------|
| Manual text entry + autocomplete | ✅ Exists | Patient-confirmed |
| Prescription photo OCR | HIGH — build on existing lab OCR pipeline | Low-Medium (requires confirmation) |
| Drug box photo (brand name recognition) | MEDIUM — vision model | Low (requires confirmation) |
| Barcode / QR | LOW for VN prescriptions — not standardized | N/A (future) |

### 5.2 Prescription OCR Pipeline

```
Patient uploads prescription photo
         ↓
OCR Engine (reuse existing lab OCR providers: Google Cloud Vision, etc.)
         ↓
Prescription Text Extractor (new domain module)
  - Extract: drug names, doses, frequency, duration, doctor name
  - Match drug names → drug_catalog via normalize_medication_name()
  - Set confidence per extracted field
         ↓
OCR Review UI (mandatory — patient must confirm ALL fields)
  - Show extracted data with confidence indicators
  - Patient can edit each field before confirming
  - Low-confidence fields highlighted with warning
  - SAFETY: patient MUST tap "Confirm" per medication — no auto-add
         ↓
On Confirm: create medication record with source_type = 'ocr_confirmed'
On Reject: discard, patient returns to manual entry
```

### 5.3 Confidence Thresholds

| Confidence | Action |
|------------|--------|
| ≥ 90% | Pre-fill field, highlight green |
| 60–89% | Pre-fill field, highlight yellow, warn patient to verify |
| < 60% | Leave field empty, warn patient to fill manually |

### 5.4 OCR Safety Rules

- **CRITICAL:** OCR result MUST NOT auto-create an active medication record.
- OCR result is stored as `pending_ocr_review` state until patient confirms.
- If patient closes the review screen without confirming, the data is discarded.
- Generic name from OCR must be validated against drug_catalog — if no match, confidence = 0 for ingredient field.
- Doctor name from prescription is stored as free text (no FK validation).

---

## 6. Layer 4 — Medication Care Loop

**Goal:** Close the loop between prescription → taking → adherence → doctor review.

### 6.1 Reminder System

```
medication_schedules
├── id                UUID PK
├── medication_id     FK → medications.id
├── patient_id        FK
├── scheduled_time    Time (HH:MM, patient local time)
├── days_of_week      JSON — [1,2,3,4,5,6,7] or null (daily)
├── is_active         Boolean
├── created_at        DateTime
├── updated_at        DateTime
```

Push notification (or SMS fallback):
- Title: "Thuốc [name]"
- Body: "[dose] — [frequency_text]" — NO PHI beyond medication name
- Deep link: opens medication detail screen with quick Taken/Skipped buttons
- Notification type: `medication_reminder` (new type to add to Notification model)
- Respect `notify_medication` preference

### 6.2 Refill Tracking

```
medication_refills
├── id                    UUID PK
├── medication_id         FK → medications.id
├── patient_id            FK
├── quantity_dispensed    Integer nullable — number of pills/units
├── days_supply           Integer nullable — how many days this refill covers
├── refill_date           Date
├── refill_source         String(32) — pharmacy | clinic | self_purchased
├── notes                 Text nullable
├── created_at            DateTime
```

Refill alert logic:
- If `days_supply` is known: alert at day (days_supply - 7) and (days_supply - 3)
- If `quantity_dispensed` is known: alert when estimated remaining < 7 days based on frequency

### 6.3 Caregiver Access

```
caregiver_assignments
├── id                UUID PK
├── patient_id        FK → patient_profiles.id
├── caregiver_user_id FK → users.id
├── relationship      String(64) — spouse | parent | child | sibling | friend | professional
├── can_view_medications Boolean default True
├── can_view_adherence   Boolean default True
├── can_receive_reminders Boolean default False — caregiver reminder copy
├── can_add_notes     Boolean default False
├── granted_at        DateTime
├── revoked_at        DateTime nullable
├── created_at        DateTime
```

Caregiver sees:
- Patient's active medication list (read-only)
- Adherence history and today's status
- Optionally receive reminder notification copy

Caregiver CANNOT:
- Add or modify patient medications
- Change doses or schedules
- Access other patient health data beyond what patient explicitly shares

### 6.4 Doctor Review Loop

When patient has a linked doctor (via consent in consent table):
- Doctor can view medication list (existing — read-only)
- Doctor can add clinical note on a medication (new: `medication_notes` table)
- Doctor can mark a medication as "reviewed" for upcoming appointment
- Medication summary export: PDF or structured data for appointment

### 6.5 Meto AI Medication Explanation

What Meto CAN do:
- Explain what a medication is used for (using drug catalog data)
- Explain common side effects (from caution_flags + drug class knowledge)
- Remind patient to take with food or at specific time (from timing_instructions)
- Summarize adherence trend in plain language
- Help patient understand an interaction warning (explain severity, recommend consulting doctor)

What Meto CANNOT do:
- Prescribe, change, or stop any medication
- Override a warning or say "this interaction is not serious for you"
- Recommend doses
- Provide drug-specific clinical advice beyond general catalog information

---

## 7. Cross-Cutting Concerns

### 7.1 PHI Protection

- `medications` table: encrypted at rest for name, dose fields (future — currently plain text in DB)
- Notification body: MUST NOT include dose or frequency — medication name only
- Logs: medication IDs only, never names/doses in log files
- Analytics: aggregate only — no per-patient medication data in analytics events
- Error messages: never include medication name in 4xx/5xx responses

### 7.2 Audit Trail

All medication write actions must produce AuditLog entries (already enforced for add/delete):
- add_medication
- update_medication
- delete_medication (soft)
- ocr_confirm_medication
- add_allergy
- dismiss_warning
- add_caregiver_assignment
- revoke_caregiver_assignment

### 7.3 Versioning

- `drug_catalog` has `source_version` field — when catalog is updated, patient records retain the snapshot at time of creation (`generic_name`, `active_ingredient` denormalized)
- `drug_interaction_rules` has `version` field — warnings are regenerated when rule version changes

### 7.4 Traditional Medicine / Supplement Rules

- `is_supplement = True` medications must have `supplement_evidence_note` stored
- UI must display: "Thực phẩm chức năng — Bằng chứng khoa học còn hạn chế. Hỏi bác sĩ trước khi dùng."
- Drug catalog entries with `drug_class = 'hepatoprotective_supplement'` are automatically flagged
- Drug-drug interaction checks are run but displayed with evidence_quality = 'limited'
- Supplement-drug interactions flagged separately with different UI treatment

---

## 8. Integration Points

| System | Integration | Data Flow |
|--------|------------|-----------|
| Lab Results | Drug-lab interaction check | Lab save → trigger drug-lab check for active medications |
| Meto AI | Medication context (300 tokens, existing) | Add: active ingredient, drug_class, warnings, interaction count to context |
| Doctor Portal | Medication review, summary | Doctor reads (existing); add review note endpoint |
| Notifications | Reminder delivery | New notification_type + schedule engine |
| OCR pipeline | Prescription photo → structured data | New OCR module reusing existing OCR infrastructure |
| Patient Profile | Allergy data | New: patient_allergies table, linked to profile |
