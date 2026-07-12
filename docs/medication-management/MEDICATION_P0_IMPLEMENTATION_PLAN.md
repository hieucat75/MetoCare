# MetoCare Medication Platform — P0 Implementation Plan

**Version:** 1.1  
**Date:** 2026-07-11  
**Status:** ✅ GATE 1 APPROVED — Implementation may begin after Pre-P0 checklist complete  
**Scope:** P0 Foundation — Schema migration + minimal API adaptation. No new UI.  
**Prerequisite:** Gate 1 ADRs (ADR-01, ADR-03, ADR-04, ADR-09, ADR-11) — formally approved by PTH 2026-07-11.

> **v1.1 changes:** (1) ADR-06 removed from Gate 1 — not a P0 blocker; (2) `medication_category` changed from DB enum to `VARCHAR` + lookup table; (3) M-02 `medication_history` + M-03 `medication_events` merged into single `medication_audit_log` table with `before_snapshot`/`after_snapshot`; (4) `medication_statements` extended with `assertion_type`, `related_medication_id`, `effective_from`, `payload_snapshot` for expired re-review flow; (5) Q-OQ-1 resolved — expired patient re-review → statement-first, not direct active.

---

## 0. Objective

P0 creates the **irreversible foundation** of the Medication Intelligence Platform. All decisions made here are expensive to undo later. The goal is:

1. Migrate schema to support provenance-first, lifecycle-aware, reconciliation-ready medication data.
2. Retrofit existing records without data loss.
3. Prepare API layer to surface new fields — without breaking existing clients.
4. Create test gates before any subsequent phase can begin.

P0 does **not** build: Doctor Portal, interaction engine, allergy engine, OCR pipeline, AI features.

---

## 1. Scope Summary

| Layer | P0 includes | P0 excludes |
|-------|------------|-------------|
| DB schema | 3 new fields on `medications`, 3 new tables | Knowledge graph tables (P1), allergy tables (P2), interaction rules (P3) |
| Migration | Additive only — no column drops, no renames | Any destructive change |
| API | Expose new fields in response; accept on write | New reconciliation endpoints (P2), Doctor Portal endpoints (P3) |
| Service layer | RBAC enforcement for `lifecycle_status` transitions | CDS domain service (P1), full interaction check (P3) |
| Background jobs | `expired` detection job | Reminder engine changes, notification new types |
| Tests | Unit + integration for new fields and state machine | End-to-end UI flows |

---

## 2. Open Questions Status

| # | Question | Status |
|---|----------|--------|
| Q-OQ-1 | `expired` re-review: patient says "I'm still taking it" → direct `active` or re-statement? | ✅ **RESOLVED** — statement-first (see §2a below) |
| Q-OQ-2 | MIMS Vietnam licensing (~$15-50K/year)? | ⏳ Gate 2 — does not block P0 |
| Q-OQ-3 | DrugBank Open commercial license? | ⏳ Gate 2 — does not block P0 |
| Q-OQ-4 | WHO ATC commercial use approval? | ⏳ Gate 2 — does not block P0 |
| Q-OQ-5 | LLM provider DPA for health data? | ⏳ Gate 3 — does not block P0 |
| Q-OQ-6 | Vietnamese data deletion vs anonymization policy? | ⏳ Gate 2 — does not block P0 |
| Q-OQ-7 | Who is the designated Vietnamese clinical advisor? | ⏳ Needed for Gate 1 clinical sign-offs |

**All P0-blocking questions resolved. Implementation can begin.**

### §2a — Q-OQ-1 Resolution: Expired Re-Review Flow (PTH decision 2026-07-11)

**Decision:** When a patient reports they are still taking an `expired` medication, the system MUST NOT directly transition `lifecycle_status` back to `active`. A new `medication_statement` must be created first.

**Rationale:**
- `expired` reflects a clinical state that was believed correct at a point in time
- Patient's new assertion is a new provenance event, not a correction of the old record
- Dose, frequency, formulation, or schedule may have changed during the gap
- Direct re-activation loses provenance and flattens history
- Patient must not unilaterally change canonical clinical state without reconciliation

**Flow:**
```
Expired medication
  → Patient taps "I'm still taking this"
  → CREATE medication_statements:
      source_type         = 'patient_manual'
      assertion_type      = 'continued_use'
      related_medication_id = <expired medication id>
      statement_status    = 'pending'
      effective_from      = (patient-reported date or today)
      payload_snapshot    = current expired medication snapshot
  → Reconciliation decision:

    CASE A — same drug, same dose, same route, no real gap:
      → INSERT medication_events (event_type='patient_reported_continued_use')
      → UPDATE medications SET lifecycle_status='active'
      → UPDATE medication_statements SET statement_status='accepted'

    CASE B — different dose, frequency, formulation, or actual gap:
      → INSERT INTO medications (new canonical episode)
      → UPDATE old medication: lifecycle_status stays 'expired'
      → UPDATE medication_statements SET statement_status='accepted', merged_into_medication_id=new_id

    CASE C — insufficient data (patient unsure of current dose):
      → medication_statements stays statement_status='pending'
      → No reminder reactivated
      → Patient prompted to fill in missing info

    CASE D — original expired due to clinician-set prescription end_date:
      → Patient CANNOT self-reactivate canonical state
      → medication_statements created as assertion_type='continued_use'
      → Flagged for clinician review
      → No lifecycle change until clinician acts
```

**Decision rule post-reconciliation:**  
Cases A/B/C are patient-resolvable. Case D requires clinician. System determines Case D when `source_type='doctor_prescribed'` on the expired record OR when `source_type='ocr_confirmed'` and `raw_prescriber IS NOT NULL`.

**Required fields added to `medication_statements` (see M-04):**
- `assertion_type` — `'new_entry' | 'continued_use' | 'dose_update' | 'correction'`
- `related_medication_id` — FK to prior canonical record (for continued_use)
- `effective_from` — patient-reported start of continued use
- `payload_snapshot` — JSONB snapshot of related medication at time of assertion

---

## 3. Migration Sequence

> **Rule:** Each migration is a separate, independently-rollbackable unit. No mega-migration.  
> **Convention:** Filename = `YYYYMMDD_NNN_description.sql` (or ORM equivalent).

### Migration M-01 — Add lifecycle and verification fields to `medications`

**Type:** Additive (new columns, NOT NULL with safe defaults)  
**Risk:** Low — existing rows get conservative defaults, no existing behavior breaks  
**Rollback:** DROP COLUMN (safe if no code deployed yet)

```sql
-- M-01: Add lifecycle_status + verification_status + source_type to medications

ALTER TABLE medications
  ADD COLUMN lifecycle_status    VARCHAR(32) NOT NULL DEFAULT 'active',
  ADD COLUMN verification_status VARCHAR(32) NOT NULL DEFAULT 'patient_reported',
  ADD COLUMN source_type         VARCHAR(32) NOT NULL DEFAULT 'patient_manual',
  ADD COLUMN medication_category VARCHAR(64) NOT NULL DEFAULT 'conventional_drug',
  -- NOT a DB enum. Values validated via FK to medication_category_codes lookup table.
  -- Lookup table allows new categories without schema migration.
  ADD COLUMN status_reason       TEXT        NULL;

-- CHECK constraints for lifecycle fields (closed sets, safe to enforce at DB level)
ALTER TABLE medications
  ADD CONSTRAINT chk_lifecycle_status
    CHECK (lifecycle_status IN (
      'active','paused','on_hold','completed','discontinued','expired','entered_in_error'
    ));

ALTER TABLE medications
  ADD CONSTRAINT chk_verification_status
    CHECK (verification_status IN (
      'patient_reported','clinician_confirmed','ocr_extracted','system_inferred'
    ));

ALTER TABLE medications
  ADD CONSTRAINT chk_source_type
    CHECK (source_type IN (
      'patient_manual','doctor_prescribed','ocr_confirmed',
      'pharmacy_import','fhir_import','entered_in_error'
    ));

-- medication_category: NOT validated via CHECK constraint.
-- Validated via FK to medication_category_codes lookup table (see M-01b below).
-- This allows adding new categories (e.g., tcm_formula, medical_device) at P3 without ALTER TABLE.
```

---

### Migration M-01b — Create `medication_category_codes` lookup table

**Type:** New lookup table + FK  
**Risk:** Very low  
**Rationale:** PTH decision — `medication_category` must NOT be a database enum (hard to extend). Use versioned lookup table instead. New categories at P3 (ADR-06) require only INSERT, not schema migration.

```sql
-- M-01b: medication_category lookup table

CREATE TABLE medication_category_codes (
    code         VARCHAR(64)  NOT NULL,
    label_vi     VARCHAR(128) NOT NULL,     -- Vietnamese display label
    label_en     VARCHAR(128) NOT NULL,     -- English display label
    interaction_risk_level  VARCHAR(16) NULL,
    -- 'high' | 'medium' | 'low' | 'unknown' (used by CDS at P3)
    requires_clinician_review BOOLEAN NOT NULL DEFAULT FALSE,
    active       BOOLEAN      NOT NULL DEFAULT TRUE,
    display_order INT         NULL,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    PRIMARY KEY (code)
);

-- P0 seed values (ADR-06 full taxonomy deferred to Gate 3; only these 2 needed for P0):
INSERT INTO medication_category_codes (code, label_vi, label_en, interaction_risk_level, requires_clinician_review, display_order)
VALUES
  ('conventional_drug', 'Thuốc điều trị', 'Conventional Drug', 'high', FALSE, 1),
  ('supplement',        'Thực phẩm bổ sung', 'Supplement / OTC',  'low',  FALSE, 2);

-- P0 rows get 'conventional_drug' by default; 'supplement' covers ex-is_supplement rows.
-- Full taxonomy (prescription | otc | traditional_vn | tcm | herbal | ...) added at Gate 3 / ADR-06 approval
-- as simple INSERTs into this table — zero schema migration required.

-- Add FK (soft enforcement: if lookup table is authoritative, FK makes it hard)
ALTER TABLE medications
  ADD CONSTRAINT fk_medication_category
    FOREIGN KEY (medication_category)
    REFERENCES medication_category_codes(code);
```

**Existing data:**
- All existing rows → `lifecycle_status='active'`, `verification_status='patient_reported'`, `source_type='patient_manual'`, `medication_category='conventional_drug'`
- These are correct conservative defaults — all pre-P0 entries are patient-entered, unverified.

**Removes:**
- `is_supplement` boolean (if exists) — migrate: `is_supplement=TRUE` → `medication_category='supplement'` before dropping.

```sql
-- Only if is_supplement column exists:
UPDATE medications SET medication_category = 'supplement' WHERE is_supplement = TRUE;
ALTER TABLE medications DROP COLUMN is_supplement;
```

---

### Migration M-02 — Create `medication_audit_log` table

**Type:** New table (empty at creation time)  
**Risk:** None — no existing data affected  
**Rollback:** DROP TABLE

> **Design note (PTH decision 2026-07-11):** M-02 (history snapshots) and M-03 (event log) are merged into a single `medication_audit_log` table.  
> **Rationale:** Two separate tables recording every medication change have divergent-history risk — they would be written in the same transaction but query separately, creating a dual source of truth with no guaranteed consistency.  
> **Solution:** One table; every row is both an immutable business event AND carries `before_snapshot` + `after_snapshot` for technical audit/recovery.  
> **When to snapshot:** `before_snapshot` + `after_snapshot` are captured for all transitions. For pure business events with no field change (e.g., `patient_reported_non_adherence`), both snapshots are NULL — event_data carries the payload.  
> **Future:** If volume becomes a concern (high-frequency reminder events), reminder events (`reminder_taken`, `reminder_skipped`) can be routed to a separate append-only `medication_reminder_events` table at P2 with zero schema migration on `medication_audit_log`.

```sql
-- M-02: Unified medication audit log (business events + technical snapshots)

CREATE TABLE medication_audit_log (
    id                  UUID         NOT NULL DEFAULT gen_random_uuid(),
    medication_id       VARCHAR(36)  NOT NULL REFERENCES medications(id) ON DELETE CASCADE,
    patient_id          VARCHAR(36)  NOT NULL,

    -- Business event fields
    event_type          VARCHAR(64)  NOT NULL,
    -- 'create'
    -- 'lifecycle_change'               ← triggers before+after snapshot
    -- 'verification_change'            ← triggers before+after snapshot
    -- 'source_type_change'             ← triggers before+after snapshot
    -- 'dose_change'                    ← triggers before+after snapshot
    -- 'patient_reported_non_adherence' ← event_data only, no snapshot
    -- 'patient_reported_continued_use' ← event_data only (expired re-review)
    -- 'reminder_taken'                 ← event_data only, no snapshot
    -- 'reminder_skipped'               ← event_data only, no snapshot
    -- 'doctor_note'                    ← event_data only
    -- 'admin_correction'               ← triggers before+after snapshot
    field_changed       VARCHAR(64)  NULL,    -- e.g. 'lifecycle_status', 'dosage'
    old_value           VARCHAR(255) NULL,
    new_value           VARCHAR(255) NULL,
    transition_reason   TEXT         NULL,    -- required for certain transitions
    event_data          JSONB        NULL,
    -- Flexible extra payload: note, confidence, source_ref, clinical_context, etc.

    -- Technical audit fields (populated for state-changing events only)
    before_snapshot     JSONB        NULL,   -- full medications row BEFORE this change
    after_snapshot      JSONB        NULL,   -- full medications row AFTER this change
    -- Both NULL for pure observational events (non_adherence, reminder_taken, etc.)

    -- Actor
    created_by_user_id  VARCHAR(36)  NULL,
    created_by_role     VARCHAR(32)  NULL,
    -- 'patient' | 'doctor' | 'system' | 'admin'

    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    PRIMARY KEY (id)
);

CREATE INDEX idx_medaudit_medication_id ON medication_audit_log(medication_id);
CREATE INDEX idx_medaudit_patient_id    ON medication_audit_log(patient_id);
CREATE INDEX idx_medaudit_event_type    ON medication_audit_log(event_type);
CREATE INDEX idx_medaudit_created_at    ON medication_audit_log(created_at DESC);
-- Partial index for state-change events (most common query: full history per medication)
CREATE INDEX idx_medaudit_state_changes ON medication_audit_log(medication_id, created_at DESC)
    WHERE before_snapshot IS NOT NULL;
```

**When snapshots are captured:**

| event_type | before_snapshot | after_snapshot |
|-----------|----------------|----------------|
| create | NULL | full row |
| lifecycle_change | full row before | full row after |
| verification_change | full row before | full row after |
| dose_change | full row before | full row after |
| admin_correction | full row before | full row after |
| patient_reported_non_adherence | NULL | NULL |
| patient_reported_continued_use | NULL | NULL |
| reminder_taken / reminder_skipped | NULL | NULL |
| doctor_note | NULL | NULL |

---

### Migration M-03 — Create `medication_statements` table

**Type:** New table  
**Risk:** None (empty at creation; P0 API writes to it going forward)  
**Rollback:** DROP TABLE

```sql
-- M-03: Medication statements — raw source assertions (ADR-04)
-- Extended for Q-OQ-1 resolution: expired re-review flow (PTH 2026-07-11)

CREATE TABLE medication_statements (
    id                        UUID         NOT NULL DEFAULT gen_random_uuid(),
    patient_id                VARCHAR(36)  NOT NULL REFERENCES patient_profiles(id),
    source_type               VARCHAR(32)  NOT NULL,
    -- 'patient_manual' | 'doctor_prescribed' | 'ocr_confirmed' | 'pharmacy_import' | 'fhir_import'
    source_ref                VARCHAR(255) NULL,
    -- OCR session ID, prescription doc ID, Doctor Portal encounter ID, etc.

    -- Assertion type (Q-OQ-1: needed for expired re-review routing)
    assertion_type            VARCHAR(32)  NOT NULL DEFAULT 'new_entry',
    -- 'new_entry'     — patient or OCR adding a medication for the first time
    -- 'continued_use' — patient says they are still taking an expired medication
    -- 'dose_update'   — patient reports same medication, different dose/frequency
    -- 'correction'    — patient corrects a previous entry

    -- Link back to prior canonical record (required when assertion_type = 'continued_use')
    related_medication_id     VARCHAR(36)  NULL REFERENCES medications(id),

    raw_drug_name             TEXT         NOT NULL,
    normalized_name           TEXT         NULL,
    drug_product_id           VARCHAR(36)  NULL,
    -- FK to drug_products when catalog exists (P1)
    match_confidence          FLOAT        NULL,
    raw_dose                  TEXT         NULL,
    raw_frequency             TEXT         NULL,
    raw_prescriber            TEXT         NULL,
    raw_date                  DATE         NULL,

    -- Temporal fields for continued_use flow
    effective_from            DATE         NULL,
    -- patient-reported start date of (re-)use; may differ from raw_date

    -- Snapshot of related_medication at time of assertion (for diff and reconciliation)
    payload_snapshot          JSONB        NULL,
    -- populated when assertion_type IN ('continued_use', 'dose_update', 'correction')

    statement_status          VARCHAR(32)  NOT NULL DEFAULT 'pending',
    -- 'pending' | 'accepted' | 'rejected' | 'merged_into' | 'superseded' | 'awaiting_clinician'
    -- 'awaiting_clinician' = Case D: doctor-prescribed expired record, patient cannot self-reactivate

    merged_into_medication_id VARCHAR(36)  NULL REFERENCES medications(id),
    reviewed_by_user_id       VARCHAR(36)  NULL,
    reviewed_at               TIMESTAMPTZ  NULL,
    review_note               TEXT         NULL,
    created_at                TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    PRIMARY KEY (id)
);

CREATE INDEX idx_medstmt_patient_id           ON medication_statements(patient_id);
CREATE INDEX idx_medstmt_status               ON medication_statements(statement_status);
CREATE INDEX idx_medstmt_source_type          ON medication_statements(source_type);
CREATE INDEX idx_medstmt_assertion_type       ON medication_statements(assertion_type);
CREATE INDEX idx_medstmt_related_medication   ON medication_statements(related_medication_id)
    WHERE related_medication_id IS NOT NULL;
CREATE INDEX idx_medstmt_created_at           ON medication_statements(created_at DESC);
```

---

### Migration M-04 — Add `drug_product_id` FK and `generic_name` to `medications`

**Type:** Additive (nullable FK — safe, no existing data impact)  
**Risk:** Very low  
**Rollback:** DROP COLUMN

```sql
-- M-04: Knowledge structure FK (ADR-01 — nullable until catalog table exists)

ALTER TABLE medications
  ADD COLUMN drug_product_id VARCHAR(36)  NULL,
  -- FK to drug_products when table is created in P1
  ADD COLUMN generic_name    VARCHAR(255) NULL;
  -- INN name, manually maintained until catalog at P1
```

---

## 4. Rollback Plan

| Migration | Rollback action | Safe? | Pre-condition |
|-----------|----------------|-------|---------------|
| M-01 | DROP COLUMN for 5 new columns; restore is_supplement if dropped | ✅ if no app writes yet | Must roll back before any API deployment uses new columns |
| M-01b | DROP TABLE medication_category_codes; DROP CONSTRAINT fk_medication_category | ✅ always | Before M-01 rollback |
| M-02 | DROP TABLE medication_audit_log | ✅ always | Append-only, no FK deps |
| M-03 | DROP TABLE medication_statements | ✅ always | No FK from other tables |
| M-04 | DROP COLUMN drug_product_id, generic_name | ✅ if no app writes yet | Before API uses new columns |

**Rollback sequence:** Reverse order — M-04 → M-03 → M-02 → M-01b → M-01.

**Full rollback script must be written and tested before migration is run on staging.**

---

## 5. API Compatibility Strategy

P0 follows **additive-only API changes**. No existing client breaks.

### 5.1 New fields in GET responses

All medication read endpoints now return 5 new fields:

```json
{
  "id": "...",
  "name": "...",
  "dosage": "...",
  
  "lifecycle_status": "active",
  "verification_status": "patient_reported",
  "source_type": "patient_manual",
  "medication_category": "conventional_drug",
  "status_reason": null
}
```

- Existing clients that don't read these fields: **no impact**.
- Mobile clients must handle unknown fields gracefully (per API contract).

### 5.2 New write behavior (POST /patients/{id}/medications)

Request body unchanged. Internal behavior changes:

```
Before P0:  INSERT INTO medications (...)
After P0:   1. INSERT INTO medication_statements (source_type='patient_manual', assertion_type='new_entry', statement_status='pending')
            2. INSERT INTO medications (..., lifecycle_status='active', verification_status='patient_reported', source_type='patient_manual')
            3. UPDATE medication_statements SET statement_status='accepted', merged_into_medication_id=new_id
            4. INSERT INTO medication_audit_log (event_type='create', after_snapshot=<full row>, before_snapshot=NULL)
```

Client sees same response shape. Internally, provenance is captured from day 1.

### 5.3 New PATCH behavior (PATCH /medications/{id})

Accepts new fields:

```json
{
  "lifecycle_status": "paused",
  "status_reason": "Dừng trước phẫu thuật"
}
```

Service layer enforces RBAC before write:

```
if new lifecycle_status == 'on_hold' AND caller_role != 'DOCTOR':
    → 403 Forbidden: "on_hold chỉ được set bởi bác sĩ"

if current lifecycle_status == 'on_hold' AND new lifecycle_status == 'active' AND caller_role != 'DOCTOR':
    → 403 Forbidden: "Chỉ bác sĩ có thể xóa on_hold"
```

On any lifecycle or verification change:
- INSERT into `medication_audit_log` with `before_snapshot` + `after_snapshot` + `event_type` + `old_value` + `new_value`

### 5.4 New endpoint — patient non-adherence report

```
POST /medications/{id}/report-non-adherence
Body: { "note": "..." }  (optional)

→ INSERT INTO medication_audit_log (event_type='patient_reported_non_adherence', event_data={note}, before_snapshot=NULL, after_snapshot=NULL)
→ Does NOT change lifecycle_status
→ 200 OK: { "recorded": true }
```

### 5.5 Default query filters

All `GET /patients/{id}/medications` responses default to:

```sql
WHERE lifecycle_status IN ('active', 'paused', 'on_hold')
  AND lifecycle_status != 'entered_in_error'
  AND deleted_at IS NULL
```

Optional filter params:
- `?include_completed=true` → add `completed`, `discontinued`
- `?lifecycle_status=all` → admin only
- `?lifecycle_status=expired` → show expired for review

---

## 6. Service Layer Changes

### 6.1 RBAC enforcement (MedicationService)

```
MedicationService.updateLifecycleStatus(medicationId, newStatus, reason, callerRole):
  ALLOWED TRANSITIONS:
    PATIENT can set: active (from paused), paused (from active), completed, discontinued, entered_in_error
    PATIENT CANNOT set: on_hold (from any), active (from on_hold)
    DOCTOR can set: all states including on_hold; set/clear on_hold; verify verification_status
    SYSTEM can set: expired (background job only)
    AI_SERVICE: cannot set lifecycle_status or verification_status
```

### 6.2 `expired` detection background job

```
Runs daily (UTC 00:00 or configurable, idempotent):
  SELECT id FROM medications
  WHERE lifecycle_status = 'active'
    AND end_date IS NOT NULL
    AND end_date < CURRENT_DATE
    AND deleted_at IS NULL;

  For each found (in transaction):
    snapshot_before = SELECT * FROM medications WHERE id=...
    UPDATE medications SET lifecycle_status = 'expired'
    snapshot_after  = SELECT * FROM medications WHERE id=...
    INSERT INTO medication_audit_log (
      event_type='lifecycle_change', field_changed='lifecycle_status',
      old_value='active', new_value='expired',
      before_snapshot=snapshot_before, after_snapshot=snapshot_after,
      created_by_role='system'
    )
    → Trigger patient notification (existing notification infrastructure)
```

### 6.3 Expired re-review flow (Q-OQ-1)

```
PATIENT taps "Đang dùng" on an expired medication:

  1. Check: is source_type='doctor_prescribed' on expired record?
     YES → statement_status = 'awaiting_clinician' (Case D)
     NO  → statement_status = 'pending' (Cases A/B/C — patient-resolvable)

  2. INSERT INTO medication_statements (
       assertion_type='continued_use',
       related_medication_id=<expired_id>,
       payload_snapshot=<snapshot of expired record>,
       effective_from=TODAY or patient-provided date,
       source_type='patient_manual',
       statement_status= 'awaiting_clinician' | 'pending'
     )

  3. Present patient with reconciliation UI:
     "Bạn đang dùng cùng liều lượng không?"
       → Yes, same dose+frequency (Case A) → allow re-activation
       → No, dose/frequency changed (Case B) → create new medication record
       → Not sure (Case C) → stay pending, prompt to fill info

  4. Case A resolution (same drug, same dose):
     BEGIN TRANSACTION
       UPDATE medications SET lifecycle_status='active'
       INSERT INTO medication_audit_log (event_type='patient_reported_continued_use', ...)
       UPDATE medication_statements SET statement_status='accepted', merged_into_medication_id=<expired_id>
     COMMIT

  5. Case D (awaiting_clinician):
     No lifecycle change. Clinician sees pending statement in Doctor Portal (P3).
     Patient informed: "Yêu cầu đã gửi tới bác sĩ. Vui lòng chờ xác nhận."
```

### 6.4 Audit capture (must be atomic with business operation)

All lifecycle transitions and verification changes must happen in a DB transaction:
```
BEGIN TRANSACTION
  1. before_snapshot = SELECT * FROM medications WHERE id=...
  2. UPDATE medications SET lifecycle_status=..., verification_status=..., status_reason=...
  3. after_snapshot  = SELECT * FROM medications WHERE id=...
  4. INSERT INTO medication_audit_log (
       event_type, field_changed, old_value, new_value,
       transition_reason, before_snapshot, after_snapshot,
       created_by_user_id, created_by_role
     )
COMMIT
```

No partial writes. Notifications are fire-and-forget after commit (eventually consistent).

---

## 7. Test Gates

**P0 cannot be declared done until all test gates pass.** No P1 work starts until this list is ✅.

### Gate T-01 — Migration correctness

| Test | Expected |
|------|----------|
| All existing medications rows have `lifecycle_status='active'` | ✅ |
| All existing medications rows have `verification_status='patient_reported'` | ✅ |
| All existing medications rows have `source_type='patient_manual'` | ✅ |
| All existing medications rows have `medication_category='conventional_drug'` | ✅ |
| `is_supplement=TRUE` rows converted to `medication_category='supplement'` | ✅ |
| `medication_category_codes` table has 2 seed rows | ✅ |
| FK `fk_medication_category` rejects unknown category value | ✅ |
| `medication_audit_log` table exists and is empty | ✅ |
| `medication_statements` table exists and is empty | ✅ |
| CHECK constraints (lifecycle, verification, source_type) reject invalid values | ✅ |

### Gate T-02 — New medication write creates all records

| Test | Expected |
|------|----------|
| POST /medications → creates 1 `medication_statements` row (status='accepted', assertion_type='new_entry') | ✅ |
| POST /medications → creates 1 `medications` row with correct defaults | ✅ |
| POST /medications → creates 1 `medication_audit_log` row (event_type='create', before_snapshot=NULL, after_snapshot populated) | ✅ |
| All 3 operations in same transaction (all-or-nothing) | ✅ |

### Gate T-03 — Lifecycle state machine enforcement

| Test | Expected |
|------|----------|
| PATIENT sets lifecycle_status='paused' → 200 OK | ✅ |
| PATIENT sets lifecycle_status='on_hold' → 403 Forbidden | ✅ |
| PATIENT sets lifecycle_status='active' when current='on_hold' → 403 Forbidden | ✅ |
| DOCTOR sets lifecycle_status='on_hold' → 200 OK | ✅ |
| DOCTOR sets lifecycle_status='active' when current='on_hold' → 200 OK | ✅ |
| SYSTEM job sets lifecycle_status='expired' for overdue medications → success | ✅ |
| AI_SERVICE cannot write lifecycle_status or verification_status → 403 | ✅ |

### Gate T-04 — Audit capture

| Test | Expected |
|------|----------|
| Every lifecycle_status change creates 1 `medication_audit_log` row | ✅ |
| `before_snapshot` matches row values BEFORE the change | ✅ |
| `after_snapshot` matches row values AFTER the change | ✅ |
| `old_value` + `new_value` match the field that changed | ✅ |
| `status_reason` saved to `transition_reason` when provided | ✅ |
| Pure observational events (non_adherence, reminder_taken) have NULL before/after snapshots | ✅ |

### Gate T-05 — Non-adherence report + expired re-review

| Test | Expected |
|------|----------|
| POST /medications/{id}/report-non-adherence → 200 OK | ✅ |
| No change to lifecycle_status after call | ✅ |
| 1 `medication_audit_log` row created (event_type='patient_reported_non_adherence', snapshots NULL) | ✅ |
| Expired medication → patient reports continued use → creates 1 `medication_statements` row (assertion_type='continued_use') | ✅ |
| Source_type='doctor_prescribed' expired → statement_status='awaiting_clinician' (not auto-resolvable) | ✅ |
| Case A resolution → medication lifecycle_status='active' + audit log row | ✅ |
| Case B resolution → new canonical medication row created, old stays 'expired' | ✅ |

### Gate T-06 — API backward compatibility

| Test | Expected |
|------|----------|
| Existing GET /medications endpoints still return correct data | ✅ |
| Response now includes 5 new fields (lifecycle_status, verification_status, source_type, medication_category, status_reason) | ✅ |
| Default GET filter excludes completed, discontinued, expired, entered_in_error | ✅ |
| No existing mobile client breaks (no field removed, no type changed) | ✅ (requires QA sign-off from mobile team) |

### Gate T-07 — `expired` detection job

| Test | Expected |
|------|----------|
| Medications with end_date in past get lifecycle_status='expired' | ✅ |
| Medications with end_date in future stay 'active' | ✅ |
| `medication_audit_log` row captured for each expiry (before+after snapshot) | ✅ |
| Job is idempotent (running twice doesn't duplicate events) | ✅ |

---

## 8. Compatibility Strategy for Existing Mobile App

**Assumption:** Mobile client is live and must not break.

| Risk | Mitigation |
|------|-----------|
| New fields in API response break mobile JSON parser | Ensure mobile client uses lenient JSON parsing (ignore unknown fields). If not: deploy API with `Content-Type: application/vnd.metocare.v2+json` versioned endpoint and serve new fields only to clients that send `Accept: v2`. |
| Default filter change hides medications | Existing medications are `active` by default → no change. Only explicitly `completed/discontinued/expired` are now filtered. If any existing medications were soft-deleted and showed in list, verify they're still excluded. |
| `status` field name conflicts | If mobile expects `status` (old field) vs new `lifecycle_status`: keep old `status` field in response as alias during transition period (`"status": lifecycle_status`). Drop after mobile releases new version. |

**Mobile coordination required:** Before P0 API deployment, mobile team must:
1. Confirm JSON parser handles unknown fields.
2. Confirm no hardcoded `status` field dependency (or get alias window).
3. Sign off on Gate T-06.

---

## 9. Phase Timeline

| Phase | Duration estimate | Start condition | End condition |
|-------|------------------|----------------|---------------|
| **Pre-P0: ADR sign-off** | ✅ Done | — | PTH approved Gate 1: ADR-01, 03, 04, 09, 11 (2026-07-11) |
| **Pre-P0: Q-OQ-1 resolved** | ✅ Done | — | Statement-first expired re-review (PTH 2026-07-11) |
| **M-01, M-01b, M-02, M-03, M-04 (staging)** | 2–3 days | v1.1 plan approved | All migration tests pass on staging |
| **API + service layer** | 3–5 days | Migrations on staging | New write behavior + RBAC enforced |
| **Test gate T-01 to T-07** | 2–3 days | API complete | All 7 gates ✅ |
| **Mobile coordination** | 2–3 days (parallel) | ADR sign-off | Mobile team signs off T-06 |
| **Production deployment** | 1 day | All gates ✅ + mobile sign-off | P0 declared done |

**Total P0 estimate: 10–15 working days** (depending on team size and whether mobile coordination blocks or runs parallel).

---

## 10. Production Deployment Checklist

Before running any migration on production:

- [ ] All 7 test gates passed on staging
- [ ] Mobile team signed off on API compatibility (Gate T-06)
- [ ] Full rollback script written and tested on staging
- [ ] DB backup confirmed within 1 hour of migration window
- [ ] Maintenance window communicated to users (if needed)
- [ ] Migration run in dry-run mode on production schema copy (if available)
- [ ] At least one senior dev monitoring during migration
- [ ] PTH approval for production deployment

**Migration execution order on production:**
```
M-01  → verify row counts + CHECK constraints
M-01b → verify medication_category_codes seeded + FK active
M-02  → verify medication_audit_log table created
M-03  → verify medication_statements table created
M-04  → verify nullable columns added
→ Deploy API changes
→ Enable background expired-detection job
→ Run Gate T-01 verification queries
→ Monitor error logs for 30 minutes
→ Declare P0 done
```

---

## 11. What P0 Does NOT Include

To prevent scope creep, the following are explicitly out of P0:

| Item | Phase |
|------|-------|
| Interaction check engine | P3 (Gate 2 ADRs required) |
| Allergy engine | P2 (Gate 2 ADRs required) |
| OCR prescription pipeline | P2 (Gate 3 ADRs required) |
| Doctor Portal endpoints | P3 |
| Drug catalog / knowledge structure tables | P1 |
| AI medication explanation | P3 |
| Reconciliation UI for patient | P2 |
| MIMS / RxNorm integration | P2/P3 |
| `herb_catalog` table | P3 |
| PHI column encryption | P1 (DB encryption is baseline) |

---

## 12. P1 Start Conditions (After P0)

P1 (Knowledge Structure + CDS foundation) can begin when:

- [ ] P0 all 7 test gates ✅
- [ ] P0 on production ✅
- [ ] ADR-01 (Knowledge Structure) formally approved by PTH
- [ ] ADR-09 (CDS Placement) formally approved by PTH
- [ ] INN standard confirmed by clinical advisor (ADR-01 open question)

---

## Approval Required

- [ ] **PTH** — Approve Gate 1 ADRs (ADR-01, ADR-03, ADR-04, ADR-06, ADR-09, ADR-11)
- [ ] **PTH** — Approve this P0 Implementation Plan
- [ ] **PTH** — Answer Q-OQ-1 (expired re-review flow)
- [ ] **PTH** — Approve production deployment when all test gates pass
- [ ] **Tech Lead** — Review migration scripts before staging run
- [ ] **Mobile Team** — API compatibility sign-off (Gate T-06)
- [ ] **Clinical Advisor** — ADR-11 lifecycle state definitions and transition rules (identity of advisor still TBD per Q-OQ-7)
