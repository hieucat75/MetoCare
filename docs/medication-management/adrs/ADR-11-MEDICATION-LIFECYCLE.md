# ADR-11 — Medication Lifecycle

**Status:** PROPOSED — Gate 1 (blocks all implementation)  
**Date:** 2026-07-11  
**Revision:** 2026-07-11 (PTH review — tách lifecycle_status khỏi verification_status; bỏ `planned` cho patient; patient-reported non-adherence khác với clinical transition)  
**Deciders:** PTH, Clinical Advisor, Tech Lead

---

## Context

`medications.status` hiện tại không tồn tại — chỉ có soft delete (`deleted_at`). Tài liệu P0 đề xuất 4 states: `active | paused | completed | discontinued`.

Lifecycle đầy đủ của medication trong một clinical setting phức tạp hơn nhiều. Quyết định sai ở đây ảnh hưởng trực tiếp đến: Doctor Portal display, AI context accuracy, medication reconciliation, và audit trail.

---

## Problem

**4 states (`active | paused | completed | discontinued`) thiếu:**

1. **`on_hold`**: Tạm dừng theo y lệnh lâm sàng — chỉ doctor có thể set/clear. Khác hoàn toàn với patient-initiated `paused`.
2. **`expired`**: `end_date` đã qua nhưng patient chưa review. Phân biệt với `completed` (deliberately ended) vs `expired` (not reviewed).
3. **`entered_in_error`**: OCR đọc sai, patient nhập sai. Giữ lại cho audit nhưng không active. Khác với delete.
4. Thiếu transition rules — ai được phép chuyển state nào?

**PTH review critique (2026-07-11):**

- `paused` và `on_hold` cần phân biệt rõ: paused = patient decision (reversible by patient); on_hold = clinical instruction (only doctor can clear).
- `planned` và `unknown` không nên là lifecycle states. Chúng là verification uncertainty, không phải operational state.
- Patient reporting non-adherence ≠ lifecycle transition. Phải là separate event.
- Cần `verification_status` field riêng, không trộn vào lifecycle.

---

## Decision Drivers

- Doctor Portal cần distinguish: medication prescribed vs medication patient actively taking
- AI context accuracy: different states → different inclusion rules
- RBAC: some transitions patient-only, some doctor-only
- Not over-engineer: clear state machine, trainable for team
- Separation: what state is it (lifecycle) vs how confident are we this record is correct (verification)
- Audit: every state transition must be logged (ADR-03)

---

## Options Considered

### Option A — 4 states (active | paused | completed | discontinued)
Too few. Missing on_hold, expired, entered_in_error.

### Option B — 8 states (lean model)
`planned | active | paused | on_hold | completed | discontinued | expired | entered_in_error`  
Over-uses lifecycle for verification concerns (`planned` = not-yet-confirmed).

### Option C — 12+ states (FHIR full model)
Over-engineered. Separates MedicationRequest from MedicationStatement into full FHIR bounded context.

### Option D — 8 states + unknown for reconciliation
Option B + `unknown` for pending reconciliation. Still mixes verification into lifecycle.

### Option E — Separate lifecycle_status + verification_status (recommended)
Two independent fields:
- `lifecycle_status`: operational state of the medication (7 values)
- `verification_status`: confidence in record accuracy (4 values)

A medication can be `lifecycle_status=active` AND `verification_status=patient_reported` simultaneously. These are orthogonal concerns.

---

## Trade-off Table

| Criterion | A (4 states) | B (8 states) | C (FHIR) | D (9 states) | E (two fields) |
|-----------|-------------|-------------|---------|-------------|---------------|
| Covers clinical scenarios | ❌ | ✅ | ✅ | ✅ | ✅ |
| Verification/lifecycle separation | ❌ | ❌ | ✅ | ❌ | ✅ |
| Implementation simplicity | ✅ | ✅ | ❌ | ✅ | ✅ |
| FHIR compatibility | ❌ | ⚠️ | ✅ | ⚠️ | ✅ better |
| Doctor vs patient distinction | ❌ | ✅ | ✅ | ✅ | ✅ |
| Avoids overloaded states | ✅ | ❌ | ✅ | ❌ | ✅ |

---

## Recommended Decision

**Option E — Two separate fields: `lifecycle_status` (7 values) + `verification_status` (4 values)**

**lifecycle_status values (7):**  
`active | paused | on_hold | completed | discontinued | expired | entered_in_error`

**verification_status values (4):**  
`patient_reported | clinician_confirmed | ocr_extracted | system_inferred`

**Removed from original model, per PTH review:**
- `planned` removed: Doctor-prescribed-not-yet-started belongs in `medication_statements` (ADR-04), not `medications` canonical table.
- `unknown` removed: Records pending reconciliation live in `medication_statements`. Uncertainty about record accuracy = `verification_status`, not lifecycle.
- `patient_intent_to_start` is not a lifecycle state: stored as `medication_statements` entry with `statement_status='pending'` if feature needed.

**FHIR alignment:**
- `active`, `paused`, `on_hold` → FHIR MedicationStatement.status active/on-hold
- `completed`, `discontinued` → FHIR completed/stopped
- `entered_in_error` → FHIR entered-in-error
- `verification_status` → FHIR MedicationStatement.informationSource

---

## Consequences

**Two-field schema (both columns in P0 foundation migration):**

```sql
-- On medications table:
lifecycle_status    VARCHAR(32) NOT NULL DEFAULT 'active',
  -- CHECK: IN ('active','paused','on_hold','completed','discontinued','expired','entered_in_error')
verification_status VARCHAR(32) NOT NULL DEFAULT 'patient_reported',
  -- CHECK: IN ('patient_reported','clinician_confirmed','ocr_extracted','system_inferred')
```

**Lifecycle state machine:**
```
        ┌──────────────────────────────────────────┐
        │                                          ▼
   ┌────► active ◄──────────────────────────── paused
   │       │    │
   │       │    └──► on_hold (set: doctor only → clear: doctor only)
   │       │              │
   │       ▼              ▼
   │   completed     discontinued
   │       │              │
   │       └──────┬───────┘
   │              ▼
   │          expired (system auto-sets when end_date passed)
   │
   └────── entered_in_error (from any state, PATIENT/ADMIN, requires reason)
```

**Verification status transitions (independent axis):**
```
  patient_reported  ──► clinician_confirmed   (clinician reviews and confirms)
  patient_reported  ──► entered_in_error   (doctor flags this as incorrect)
  ocr_extracted     ──► patient_reported   (patient confirms OCR result)
  ocr_extracted     ──► entered_in_error   (patient rejects OCR result)
  system_inferred   ──► patient_reported   (patient acknowledges AI suggestion)
```

**Lifecycle state definitions:**

| State | Definition | Who can set | From states | Notes |
|-------|-----------|-------------|-------------|-------|
| `active` | Currently being taken | PATIENT, DOCTOR | paused (patient un-pauses), on_hold (doctor clears) | In CML, in AI context, in interaction check |
| `paused` | Patient-initiated temporary pause | PATIENT only | active | Patient's own choice. Remains in CML display (flagged). NOT in interaction check. Patient can un-pause freely. |
| `on_hold` | Clinical hold — do not take | DOCTOR only (set AND clear) | active | Pre-surgery, interaction-based hold. Patient CANNOT change lifecycle_status. Patient CAN report non-adherence via event. |
| `completed` | Deliberate, planned end | PATIENT, DOCTOR | active | "Finished the antibiotic course." Optional transition reason. |
| `discontinued` | Stopped early or permanently | PATIENT, DOCTOR | active, paused, on_hold | Adverse effect, ineffective, cost, patient decision. Requires reason. |
| `expired` | `end_date` passed, not reviewed | SYSTEM only | active | Daily background job. Patient notified to review. |
| `entered_in_error` | Record should not exist | PATIENT (own), ADMIN | any | Kept for audit. Excluded from all display and clinical processing. Requires reason. |

**Paused vs on_hold distinction (critical):**

| | paused | on_hold |
|--|--------|---------|
| Who sets | Patient | Doctor only |
| Who clears | Patient freely | Doctor only |
| CML display | Yes, flagged | Yes, flagged |
| AI interaction check | No | No |
| Patient can un-set | Yes, any time | No — only report non-adherence as event |
| Clinical intent | "I'll resume soon" | "Do not take until I clear this" |

**Patient reporting non-adherence to on_hold (key design):**
```python
# Patient reports they stopped taking a medication despite on_hold
# This is important clinical info — but NOT a lifecycle transition
# Record as event:
MedicationEvent(
    medication_id = ...,
    event_type = 'patient_reported_non_adherence',
    event_data = {
        'note': 'Patient reports not following on_hold clinical instruction',
        'patient_statement': '...'  # optional free text from patient
    },
    created_by = patient_id
)
# lifecycle_status stays 'on_hold'
# Notify linked doctor if Doctor Portal notification configured (P3)
# Do NOT change lifecycle_status
```

**CML, AI context, and interaction check queries:**
```sql
-- Current Medication List (CML):
WHERE lifecycle_status IN ('active', 'paused', 'on_hold')
  AND deleted_at IS NULL

-- AI context:
WHERE lifecycle_status IN ('active', 'paused')
  AND deleted_at IS NULL
-- on_hold excluded: patient is not taking it; its interactions are not current risk
-- paused included (flagged): patient may resume any time

-- Interaction check:
WHERE lifecycle_status = 'active'
  AND deleted_at IS NULL
-- Only medications actively being taken are checked for interactions
```

**Verification status in UI:**
```
Medication card shows verification_status badge:
  patient_reported  → "👤 Tự khai"
  clinician_confirmed  → "✅ Bác sĩ xác nhận"
  ocr_extracted     → "📷 Từ đơn thuốc"
  system_inferred   → "🤖 Gợi ý tự động"

CDS: if verification_status='patient_reported', interaction alert shown with disclaimer:
  "Thông tin thuốc do bệnh nhân tự khai — hỏi dược sĩ để xác nhận."
```

**Transition reasons:**
| Transition | Reason required? |
|-----------|-----------------|
| active → discontinued | Required (dropdown: adverse_effect \| ineffective \| patient_preference \| doctor_decision \| cost + optional free text) |
| active → on_hold | Required (doctor must provide clinical reason) |
| on_hold → active | Required (doctor documents clearance) |
| any → entered_in_error | Required (free text) |
| other transitions | Optional |

**Patient intent to start (not a lifecycle state):**
- If patient wants to "plan" to start a medication: this is stored in `medication_statements` with `statement_status='pending'`
- It does NOT create a `medications` canonical record until patient is actually taking it
- P0 scope: patient adds a medication when they begin taking it (`lifecycle_status='active'` from creation)

---

## Data Model Impact

- ADD `lifecycle_status` VARCHAR(32) NOT NULL DEFAULT 'active' to `medications`
  - CHECK CONSTRAINT: IN ('active','paused','on_hold','completed','discontinued','expired','entered_in_error')
- ADD `verification_status` VARCHAR(32) NOT NULL DEFAULT 'patient_reported' to `medications`
  - CHECK CONSTRAINT: IN ('patient_reported','clinician_confirmed','ocr_extracted','system_inferred')
- `medication_events` table (ADR-03) captures every `lifecycle_status` transition AND `verification_status` change as separate event types
- Queries that filter `deleted_at IS NULL` → also filter `lifecycle_status != 'entered_in_error'`

---

## API Impact

- `MedicationCreate`: defaults to `lifecycle_status='active'`, `verification_status='patient_reported'`
- `PATCH /medications/{id}`: accepts `lifecycle_status` + optional `transition_reason`
- `POST /medications/{id}/verify`: clinician endpoint — sets `verification_status='clinician_confirmed'`
- `POST /medications/{id}/report-non-adherence`: patient endpoint — creates event, does NOT change lifecycle_status
- Role enforcement (service layer, not frontend):
  - PATIENT cannot set `lifecycle_status='on_hold'`
  - PATIENT cannot set `lifecycle_status='active'` when current state is `on_hold`
  - PATIENT can set `lifecycle_status` to anything except `on_hold` (from non-on_hold states)
  - AI_SERVICE cannot set lifecycle_status or verification_status (already blocked)
- `GET /medications` default filter: `lifecycle_status IN ('active', 'paused', 'on_hold')`
- `GET /medications?include_history=true`: include completed, discontinued
- `GET /medications?lifecycle_status=all`: admin view only

---

## Security and Privacy Impact

Role enforcement for `on_hold` transitions is a patient safety requirement, not just UX. Enforced at service layer — frontend cannot override.

---

## Clinical Safety Impact

`on_hold` as doctor-only state prevents patient from accidentally reactivating a clinically suspended medication. Critical for anticoagulants, immunosuppressants, pre-surgical medications.

`expired` auto-detection prevents invisible medications — drugs prescribed for 30 days that remain `active` indefinitely.

`verification_status` allows CDS to communicate confidence level of safety checks: interaction alert from `patient_reported` data has lower confidence than from `clinician_confirmed` data. UI can show this nuance.

---

## Migration Impact

P0 migration:
- ADD `lifecycle_status` VARCHAR(32) NOT NULL DEFAULT 'active' to `medications`
- ADD `verification_status` VARCHAR(32) NOT NULL DEFAULT 'patient_reported' to `medications`
- All existing rows: `lifecycle_status = 'active'`, `verification_status = 'patient_reported'`
- No data loss. Conservative defaults are correct for existing patient-entered medications.

---

## Operational Ownership

- Background job (expired detection): Tech Lead, runs daily
- Notification for expired: existing notification infrastructure
- State transition enforcement: medication service layer
- Doctor `on_hold` notifications: deferred to P3 Doctor Portal

---

## PTH Decisions Confirmed (from review session 2026-07-11)

- [x] `on_hold` is doctor-only — confirmed
- [x] Patient CANNOT add medications in `planned` state — confirmed. Intent-to-start goes to `medication_statements` if needed, not canonical `medications` table
- [x] Patient reports non-adherence: creates event record, does NOT change `lifecycle_status`
- [x] `paused` (patient-initiated) vs `on_hold` (doctor-only) distinction preserved and enforced
- [x] Handwritten prescription OCR: NOT in P2 default scope — separate scoped feature with strict confidence thresholds

---

## Resolved Open Questions

1. **`expired` re-review — RESOLVED (PTH 2026-07-11):** Patient saying "I'm still taking it" MUST create a new `medication_statement` (assertion_type='continued_use'). Direct re-activation of lifecycle_status is NOT allowed. Four-case resolution model in ADR-04 and P0 Implementation Plan §2a.
2. **FHIR future compatibility:** Acknowledged. Two-field model aligns with FHIR MedicationStatement. No immediate action needed.
3. **Doctor Portal `on_hold` notification:** Deferred to P3 Doctor Portal build.

---

## Approval Required From

- [x] PTH — two-field model approval (`lifecycle_status` + `verification_status`) — **APPROVED 2026-07-11**
- [x] PTH — `doctor_confirmed` → `clinician_confirmed` rename — **APPROVED 2026-07-11**
- [x] PTH — expired re-review statement-first flow — **APPROVED 2026-07-11**
- [ ] Clinical Advisor — lifecycle state definitions and transition rules sign-off
- [ ] Tech Lead — role enforcement implementation at service layer

## Implementation Gate

**Gate 1 — APPROVED by PTH 2026-07-11.**

Both `lifecycle_status` and `verification_status` are in P0 schema foundation. Implementation may begin.
