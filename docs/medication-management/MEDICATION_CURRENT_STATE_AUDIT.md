# Medication Current State Audit

**Metocare — Medication Management**
Audit Date: 2026-07-10
Auditor: Architecture Review (read-only)
Branch audited: `chore/next15-react19`

---

## 1. Scope of Audit

This document covers every file in the Metocare codebase that touches medication, prescription, drug catalog, adherence, allergy, drug interactions, reminders, refill, and caregiver workflows.

---

## 2. Files Audited

### Backend Python

| File | Purpose |
|------|---------|
| `backend/app/models/clinical.py` | `Medication` and `MedicationAdherence` ORM models |
| `backend/app/models/drug_catalog.py` | `DrugEntry` reference catalog model |
| `backend/app/models/notification.py` | In-app notification model |
| `backend/app/models/user.py` | User + PatientProfile model (allergies field) |
| `backend/app/schemas/medication.py` | Pydantic schemas for medication API |
| `backend/app/schemas/drug_catalog.py` | Pydantic schemas for drug suggest API |
| `backend/app/api/v1/routes/medications.py` | GET /medications/suggest only |
| `backend/app/api/v1/routes/patients.py` | Full medication CRUD + adherence endpoints |
| `backend/app/api/v1/routes/notifications.py` | Notification endpoints (no medication type) |
| `backend/app/services/medication.py` | add, list, update, soft-delete, log_adherence, get_adherence, adherence_summary |
| `backend/app/services/drug_catalog.py` | Fuzzy drug name search and normalization |
| `backend/app/ai/context/builder.py` | Medications block in AI context (up to 10 meds) |
| `backend/app/domain/policies.py` | PROHIBITED_ACTIONS including prescribe_medication, change_medication_dose, start_stop_medication |
| `backend/app/domain/guardrails.py` | Guardrail regex patterns for AI output |
| `backend/app/ai/prompt/safety.py` | Red flag detection, safe refusal messages |
| `backend/scripts/seed_drug_catalog.py` | Drug catalog seed data loader |

### Migrations

| Migration file | What it does |
|----------------|-------------|
| `2c30ffd33627_initial_schema_14_core_entities.py` | Creates `medications` table: id, patient_id, name, dose, note |
| `pr_d_add_medication_frequency.py` | Adds `frequency` column to medications |
| `pr_f_add_notification_prefs.py` | Adds `notify_medication`, `notify_lab_results`, `notify_doctor_messages` to users |
| `t4_m10_add_adhr_add_medication_adherence_table.py` | Creates `medication_adherence` table |
| `t9_m1_drug_cat.py` | Creates `drug_catalog` table |
| `t9_m2_drug_seed.py` | Loads initial drug catalog seed data |

### Frontend TypeScript/React

| File | Purpose |
|------|---------|
| `frontend/src/app/(patient)/medications/page.tsx` | Medication list page: add/edit/delete UI, take/skip dose logging |
| `frontend/src/app/(patient)/medications/adherence-widgets.tsx` | AdherenceSummaryCard, WeeklyAdherenceSection UI widgets |
| `frontend/src/components/patient/medications/MedicationNameAutocomplete.tsx` | Debounced autocomplete from drug catalog API |
| `frontend/src/lib/api/patient.ts` | API client: profile has `known_conditions` and `allergies` as free-text strings |

### AI/Docs

| File | Purpose |
|------|---------|
| `docs/meto-ai/09_TOOLS_AND_ACTIONS.md` | Tool spec: `explain_medication`, `create_reminder` — DESIGNED but not yet implemented |
| `docs/meto-ai/04_SAFETY_PRIVACY.md` | Comprehensive AI safety rules including medication behavior |
| `docs/AI_Safety_Guardrail.md` | Master safety policy document |

### Tests

| File | Purpose |
|------|---------|
| `backend/tests/test_medication_adherence.py` | Unit tests for adherence log, summary, streak calculation |

---

## 3. What Currently Exists (Implemented and Working)

### 3.1 Medication CRUD

**Fully implemented, tested.**

- **Model:** `medications` table with fields: `id` (UUID), `patient_id` (FK), `name` (String 255), `dose` (String 128, nullable), `frequency` (String 128, nullable), `note` (Text, nullable), `created_at`, `updated_at`, `deleted_at` (soft delete).
- **API:**
  - `POST /api/v1/patients/{patient_id}/medications` — creates medication
  - `GET /api/v1/patients/{patient_id}/medications` — lists active (non-deleted) medications, paginated
  - `PATCH /api/v1/patients/{patient_id}/medications/{med_id}` — partial update
  - `DELETE /api/v1/patients/{patient_id}/medications/{med_id}` — soft-delete
- **RBAC:** PATIENT (own), DOCTOR (consent-gated), INTERNAL_ADMIN, SUPER_ADMIN can write. AI_SERVICE and CLINIC_ADMIN are **blocked from all writes** (critical safety enforcement).
- **Service:** `add_medication`, `update_medication`, `list_medications`, `delete_medication` in `medication.py`. All correct. Soft-delete is idempotent.

### 3.2 Medication Adherence Tracking

**Implemented and tested.**

- **Model:** `medication_adherence` table: `id`, `medication_id` (FK), `patient_id` (FK), `scheduled_time` (DateTime, nullable), `taken_at` (DateTime, nullable), `skipped` (bool), `note`, `created_at`.
- **API:**
  - `POST /api/v1/patients/{patient_id}/medications/{med_id}/adherence` — log dose taken/skipped
  - `GET /api/v1/patients/{patient_id}/medications/{med_id}/adherence` — list adherence records
  - `GET /api/v1/patients/{patient_id}/medications/adherence-summary` — aggregate summary
- **Schema validation:** `taken_at` and `skipped=True` are mutually exclusive (model_validator enforced).
- **Computed fields:** AdherenceSummaryOut includes total_doses_logged, taken, skipped, adherence_rate, today_medications (with taken_today/skipped_today flags), current_streak, longest_streak, weekly_rate, last_taken_at.
- **Streak calculation:** `_compute_streaks()` correctly calculates current and longest day-based streaks.
- **Tests:** `test_medication_adherence.py` covers log_adherence, get_adherence, adherence_summary, streak calculation.

### 3.3 Drug Name Autocomplete

**Fully implemented.**

- **API:** `GET /api/v1/medications/suggest?q={query}&metric_group={group}&limit={n}&strict={bool}`
- **Drug Catalog model:** `DrugEntry` with fields: `generic_name`, `brand_names` (JSON array), `vietnamese_common_names` (JSON array), `aliases`, `active_ingredients` (JSON array), `drug_class`, `metric_groups`, `common_indications`, `prescription_required`, `country_context`, `caution_flags`, `contraindication_keywords`, `renal_caution`, `hepatic_caution`, `pregnancy_caution`.
- **Service:** Fuzzy matching via `drug_catalog.py` service with scoring. Can filter/boost by `metric_group`.
- **Frontend:** `MedicationNameAutocomplete.tsx` — debounced (300ms), abort-controller for request cancellation, keyboard navigation (ArrowUp/Down/Enter/Escape), accessibility (role=combobox/listbox/option), safety notice displayed, prescription_required badge shown.
- **Safety notice** embedded in every result and in the autocomplete component: "Thông tin thuốc chỉ để nhận diện tên thuốc. Không tự ý dùng, ngừng hoặc đổi liều nếu chưa có chỉ định của bác sĩ."

### 3.4 Medication Context in Meto AI

**Implemented.**

- `ContextBuilder._build_medications()` builds a medications block for AI context.
- Up to `_MAX_MEDICATIONS = 10` active medications included.
- Included on screens: dashboard, labs, medications, metrics, nutrition, care_plan, profile.
- Token budget: 300 tokens.
- All queries parameterized with `user_id` (no cross-patient data leakage).

### 3.5 AI Safety Guardrails for Medications

**Implemented and comprehensive.**

- `PROHIBITED_ACTIONS`: `prescribe_medication`, `change_medication_dose`, `start_stop_medication`
- `PRESCRIPTION_PATTERNS` regex: detects and blocks AI output mentioning specific drug names (metformin, insulin, amlodipine, atorvastatin) with dosing units.
- `DOSE_CHANGE_PATTERNS` regex: blocks phrases like "tăng liều", "giảm liều", "ngừng thuốc".
- `SAFE_REFUSAL_MEDICATION_VI`: hard-coded safe refusal message.
- `SYSTEM_SAFETY_PROMPT_VI`: injected into every LLM call prohibiting medication prescribing.

### 3.6 Notification Preferences (User Level)

**Implemented but not connected to medication reminders.**

- `users` table has columns: `notify_medication` (bool), `notify_lab_results` (bool), `notify_doctor_messages` (bool) — added in `pr_f_add_notification_prefs.py`.
- Preferences exist at DB level but there is no system that reads these prefs and sends medication reminders.

### 3.7 Frontend Medication UI

**Fully implemented.**

- Medication list page with add/edit modal, soft-delete confirm dialog.
- Dose logging: take/skip buttons per medication.
- `AdherenceSummaryCard` showing overall stats.
- `WeeklyAdherenceSection` showing 7-day breakdown.
- Drug name autocomplete with safety notice.

---

## 4. What Is UI-Only (No Backend Implementation)

### 4.1 AI Tool Actions: explain_medication, create_reminder

**Designed in `docs/meto-ai/09_TOOLS_AND_ACTIONS.md`, NOT implemented in backend.**

The spec describes:
- `explain_medication(name, context)` — AI-callable tool to explain a named medication from the drug catalog
- `create_reminder(medication_id, time, frequency)` — AI-callable tool to schedule medication reminders

No backend files exist implementing these tools: no `app/tools/` directory, no tool dispatcher, no backend reminder scheduler, no reminder delivery system.

### 4.2 Medication Reminders

**`notify_medication` preference exists in DB, but no reminder delivery system.**

- No scheduled task or cron to generate reminder notifications at medication times.
- No `medication_reminder` type in `NOTIFICATION_TYPES` (current types: appointment_reminder, health_alert, lab_ready, care_plan_update, system, profile_update_requested).
- No push notification integration (FCM/APNS or similar).
- No scheduled_time → reminder generation pipeline.

---

## 5. What Is Backend-Only (No UI)

### 5.1 Drug Catalog Fields: Interaction/Safety Data

The `DrugEntry` model has `caution_flags`, `contraindication_keywords`, `renal_caution`, `hepatic_caution`, `pregnancy_caution` fields. These are stored but:
- Not exposed in any API response shown to users.
- Not checked against patient data (allergies, conditions, other medications).
- Not surfaced in any frontend component.

### 5.2 Notification Preferences

`notify_medication` preference stored in DB but no UI for patient to toggle (may be in Settings but not confirmed).

---

## 6. What Is Missing / Not Implemented

### 6.1 Critical Gaps

| Gap | Impact | Current state |
|-----|--------|---------------|
| **Medication route of administration** | Clinical completeness | Not stored (no `route` field) |
| **Medication form** (tablet/capsule/injection/liquid) | Clinical completeness | Not stored |
| **Start date / End date** | Active/inactive distinction | Not stored |
| **Active/Inactive status** | Medication list quality | Only soft-delete exists; no `is_active` or `status` field |
| **PRN (as-needed) flag** | Scheduling logic | Not stored |
| **Reason for medication use** | Clinical context | Not stored |
| **Prescribing doctor/source** | Clinical governance | Not stored |
| **Drug-drug interaction checking** | Patient safety | Not implemented |
| **Allergy checking against medications** | Patient safety | `allergies` is free-text on profile; no matching against medications |
| **Drug-condition interaction** | Patient safety | Not implemented |
| **OCR prescription capture** | Usability | Not implemented anywhere |
| **Medication reminder delivery** | Adherence | System designed but not built |
| **Refill tracking** | Adherence | Not implemented |
| **Caregiver access model** | Family care | Not implemented |
| **Doctor medication review workflow** | Clinical governance | Not implemented |
| **Duplicate detection** (same active ingredient) | Patient safety | Not implemented |
| **Traditional medicine / supplement categorization** | Clinical accuracy | No separate category; supplements go in same list |
| **Export / visit summary** | Clinical utility | Not implemented for medications specifically |
| **Brand name ↔ generic name linking** | Drug catalog | Catalog has both but Medication record stores free-text name only (no catalog FK) |

### 6.2 Data Quality Gaps

| Gap | Detail |
|-----|--------|
| `dose` is free-text String | "2 viên", "500mg", "0.5mg" all stored the same way — no unit parsing |
| `frequency` is free-text String | "2 lần/ngày", "sáng & tối" — no structured schedule (no FHIR timing) |
| No catalog FK on Medication | Medication.name is not linked to DrugEntry.id — no way to look up drug properties at query time |
| Allergies is free-text on PatientProfile | Cannot check allergy against medication catalog algorithmically |
| No `drug_catalog_id` FK on Medication | Cannot join to check interactions, cautions, or active ingredients |

### 6.3 Mobile

No mobile-specific medication files found. Mobile app (`/Users/pth/Developer/Metocare/mobile`) has no medication-related code — the mobile app either is not yet built out or uses the same web frontend.

### 6.4 OCR

No OCR capability for prescriptions anywhere in the codebase. `LabDocument` model has OCR for lab reports (`ocr_status`, `raw_text`, `storage_key`) but there is no equivalent for prescription photos. No barcode/QR scanning capability.

---

## 7. Dependencies Map

| Domain | Medication Dependency |
|--------|-----------------------|
| **Lab Results** | Drug-lab interaction warnings need access to lab values. `ContextBuilder` includes both medications and recent_labs in same context block. |
| **Patient Profile** | `known_conditions` (free-text) and `allergies` (free-text) used for drug-condition and drug-allergy checking. Not structured. |
| **Notifications** | `medication_reminder` type does not exist in Notification model. `notify_medication` pref exists but nothing reads it. |
| **Meto AI** | `explain_medication` and `create_reminder` tools are DESIGNED but not implemented. AI receives medication list in context. |
| **Doctor Portal** | No doctor medication review endpoint exists. Doctor can view patient medications (consent-gated) but there is no dedicated medication review or approval workflow. |
| **Marketplace** | No medication-marketplace dependency found. |
| **Care Plan** | Care plans reference medications informally in AI context but there is no structured care_plan_medication linking table. |

---

## 8. Correctness Issues Found

| Issue | File | Severity |
|-------|------|----------|
| Medication.name not FK-linked to DrugEntry | `clinical.py` | Medium — prevents any catalog-based logic |
| Allergy checking impossible algorithmically | `user.py`, `patient.ts` | High — allergies stored as free-text |
| No `medication_reminder` notification type | `notification.py` | Medium — reminder system cannot be built without this |
| PRESCRIPTION_PATTERNS in guardrails may false-positive | `policies.py` | Low — listing metformin by name means AI cannot even explain it is prohibited — needs careful distinction between explaining a medication name vs. prescribing |
| `frequency` is unstructured string | `clinical.py` | Medium — cannot generate scheduled reminders from free-text |
| No audit log for medication changes | `medication.py` | Medium — changes (dose, name) are not audit-logged |
| Missing `explain_medication` action in ALLOWED_ACTIONS | `policies.py` | Low — `explain_lab_results` is allowed but no equivalent for medications |

---

## 9. Security / Privacy Findings

| Finding | Detail |
|---------|--------|
| AI_SERVICE blocked from medication writes | ✅ Correctly enforced in route RBAC |
| Medication data in AI context is user-scoped | ✅ All queries parameterized with user_id |
| No PHI in notification body leakage risk | ⚠️ Future medication reminders must not include drug name/dose in notification preview (OS notification center) |
| Drug catalog has no PII | ✅ Correct — catalog is reference only |
| Adherence records not encrypted | ⚠️ Currently plain text in DB; dose timing is sensitive PHI |

---

## 10. Summary Statistics

- **Tables in DB related to medications:** 2 (medications, medication_adherence) + 1 reference (drug_catalog)
- **API endpoints related to medications:** 7 (CRUD + adherence + suggest)
- **Frontend components:** 3 (medications/page.tsx, adherence-widgets.tsx, MedicationNameAutocomplete.tsx)
- **AI guardrail patterns for medications:** 8 regex patterns in PRESCRIPTION_PATTERNS + DOSE_CHANGE_PATTERNS
- **Missing critical features:** 14 (see Section 6.1)
- **Missing notification type:** medication_reminder
- **Missing model fields:** route, form, start_date, end_date, is_active, reason, prescribing_doctor, drug_catalog_id (FK)
- **Missing intelligence layer:** 0% implemented (drug interactions, allergy checking, duplicate detection = all missing)
- **Missing capture layer:** 0% implemented (OCR, barcode = all missing)
- **Missing care loop:** ~15% implemented (adherence log exists; reminders, refill, caregiver, doctor review = missing)
