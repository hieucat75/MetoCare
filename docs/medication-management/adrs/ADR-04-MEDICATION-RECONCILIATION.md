# ADR-04 — Medication Reconciliation

**Status:** PROPOSED — Gate 1 (blocks all implementation — schema must be designed now even if feature ships later)  
**Date:** 2026-07-11  
**Revision:** 2026-07-11 (PTH review — provenance-first model required at P0, not P2)  
**Deciders:** PTH, Clinical Advisor, Tech Lead

---

## ADR Metadata

| Field | Value |
|-------|-------|
| ADR | ADR-04 |
| Status | Accepted |
| Architecture Version | medication-architecture-v1.0 |
| Implementation Gate | Gate 1 |
| Domain | Reconciliation |
| Supersedes | None |
| Superseded By | None |

---


## Context

Medication Reconciliation là quá trình hợp nhất danh sách thuốc từ nhiều nguồn thành một "Current Medication List" (CML) chính xác và được xác nhận. 

MetoCare sẽ có nhiều nguồn dữ liệu thuốc:
- Patient self-entry (manual)
- Doctor kê từ Doctor Portal
- OCR từ đơn thuốc giấy
- Future: pharmacy import, hospital record import, FHIR import

Nếu không thiết kế reconciliation từ đầu, `medications` table sẽ chứa duplicates, conflicts, và unverified entries lẫn với verified entries — không thể phân biệt.

---

## Problem

**Scenario hiện tại không có reconciliation:**
1. Patient tự nhập "Metformin 500mg" (manual)
2. Doctor kê "Glucophage 1000mg" từ portal (khác brand, khác dose)
3. OCR đọc đơn cũ "Metformin 500mg BID" (trùng tên, có thể outdated)

Kết quả: 3 records trong `medications` table. Đây là 1 drug hay 3 drug? AI context sẽ đọc 3 entries → wrong context. Interaction check sẽ treat chúng là khác nhau → false positives.

---

## Decision Drivers

- Day 1: Patient App chỉ có manual entry → reconciliation đơn giản (patient tự manage)
- P2: OCR adds unverified entries → reconciliation needed
- P3: Doctor Portal adds entries → conflict resolution needed
- Schema must accommodate all sources from now — cannot retrofit
- Reconciliation does NOT mean automatic merge — human must confirm

---

## Options Considered

### Option A — Ignore reconciliation, treat all entries as independent
Simple. Works for day 1. Creates irreconcilable mess by P3.

### Option B — Source tagging only (add `source_type` field)
Tag each entry with source. No deduplication logic. Human must manually identify duplicates.

### Option C — Medication Statement + Reconciled Medication List
Separate "raw statements" (one per source) from "reconciled medication list" (verified CML). 
Reconciliation is a deliberate human action that maps statements → CML.

### Option D — Automatic merge with confidence scoring
System auto-merges entries if similarity > threshold. Human only reviews conflicts.

---

## Trade-off Table

| Criterion | A (ignore) | B (source tag) | C (statement+CML) | D (auto-merge) |
|-----------|-----------|----------------|-------------------|----------------|
| Handles duplicates | ❌ No | ❌ No | ✅ Yes | ⚠️ Risk of wrong merge |
| Human control | N/A | ✅ Full | ✅ Full | ❌ Partial |
| Implementation complexity | ✅ None | ✅ Low | ⚠️ Medium | ❌ High |
| Clinical safety | ❌ Low | ⚠️ Medium | ✅ High | ⚠️ Risk |
| Schema complexity | ✅ Minimal | ✅ Minimal | ⚠️ 2 new tables | ❌ High |
| AI context quality | ❌ Poor | ⚠️ Noisy | ✅ Clean CML | ⚠️ Depends on accuracy |
| Works for P0 (manual only) | ✅ | ✅ | ✅ | N/A |
| Works for P3 (multi-source) | ❌ | ❌ | ✅ | ❌ |

---

## Recommended Decision

**Option C — Medication Statement + Reconciled Medication List, with provenance-first P0.**

**Revised per PTH review:** Đưa `medication_statements` table vào P0 schema foundation. Không build reconciliation UI ở P0, nhưng data model phải phân biệt rõ từ đầu:
- **Medication Statement**: một nguồn nói bệnh nhân đang dùng thuốc gì (chưa xác minh)
- **Canonical Medication Record**: danh sách thuốc đã được hợp nhất và xác nhận (Current Medication List)

**PTH critique:** “Nếu P0 vẫn ghi trực tiếp mọi nguồn vào bảng medications, đến P2 mới thêm medication_statements, team có thể phải migrate dữ liệu nguồn, tách canonical record khỏi source assertion, sửa API và reconciliation logic, xử lý provenance thiếu từ dữ liệu cũ.”

Điều này đúng. Hai khái niệm không được trộn từ đầu.

**Phase 0 (P0):** Schema có cả hai bảng. `medication_statements` ở P0 chỉ serve patient manual entry. Mọi entry tự của patient được auto-promote thành canonical record ngay. Không có reconciliation UI, nhưng structure đúng từ đầu.

**Phase 1 (P2, khi OCR ships):** OCR creates statement, patient reviews, promotes to canonical. Reconciliation UI ships.

**Phase 2 (P3, Doctor Portal):** Doctor entries create statements. Full reconciliation session model.

**Automatic merge is NOT recommended** — wrong merge is worse than no merge for medication safety.

---

## Consequences

**`source_type` on `medications` (canonical record — always present from P0):**
```
source_type values:
  patient_manual    — patient typed it themselves (auto-promoted from statement)
  doctor_prescribed — doctor added via Doctor Portal (promoted with consent)
  ocr_confirmed     — OCR extracted, patient confirmed (promoted from statement)
  pharmacy_import   — future
  fhir_import       — future
  entered_in_error  — marked wrong, excluded from CML
```

**Two-table model (BOTH tables created at P0, usage grows with phases):**

| Table | What it is | When used |
|-------|-----------|----------|
| `medication_statements` | Raw assertion from any source, pre-verification | P0: auto-created for every patient entry; P2+: OCR/Doctor sources |
| `medications` | Canonical Current Medication List entry | Promoted from statement on confirmation |

P0 flow (patient manual entry):
```
Patient types medication
  → INSERT INTO medication_statements (source_type='patient_manual', statement_status='pending')
  → Auto-promote: INSERT INTO medications (source_type='patient_manual')
  → UPDATE medication_statements SET status='accepted', merged_into_medication_id=new_medication_id
  → No review screen (single-source, no conflict possible)
```

P2 flow (OCR):
```
OCR extracts medication
  → INSERT INTO medication_statements (source_type='ocr_pending', status='pending')
  → Patient reviews (reconciliation UI)
  → Patient confirms new drug: INSERT INTO medications, UPDATE statement status='accepted'
  → Patient rejects: UPDATE statement status='rejected'
```

**`medication_statements` table (created at P0, lightweight initially):**
```sql
CREATE TABLE medication_statements (
    id                  UUID PK,
    patient_id          VARCHAR(36) NOT NULL REFERENCES patient_profiles(id),
    source_type         VARCHAR(32) NOT NULL,     -- same values as above
    source_ref          VARCHAR(255) nullable,     -- OCR session ID, prescription ref, etc.
    raw_drug_name       TEXT NOT NULL,             -- exactly as extracted/entered
    normalized_name     TEXT nullable,             -- after catalog matching
    drug_product_id     FK nullable,               -- catalog match (nullable)
    match_confidence    FLOAT nullable,            -- 0.0–1.0
    raw_dose            TEXT nullable,
    raw_frequency       TEXT nullable,
    raw_prescriber      TEXT nullable,
    raw_date            DATE nullable,
    statement_status    VARCHAR(32) NOT NULL DEFAULT 'pending',
    -- pending | accepted | rejected | merged_into | superseded
    merged_into_medication_id VARCHAR(36) nullable REFERENCES medications(id),
    reviewed_by_user_id VARCHAR(36) nullable,
    reviewed_at         DATETIME nullable,
    review_note         TEXT nullable,
    created_at          DATETIME NOT NULL
);
```

**Reconciliation flow (P2+, OCR):**
```
New OCR result
  → INSERT INTO medication_statements (source_type='ocr_extracted', statement_status='pending')
  → Patient sees review screen: "Được tìm thấy trong đơn thuốc của bạn. Xác nhận chép vào danh sách thuốc?"
    → Patient confirms: new drug?
        → INSERT INTO medications (source_type='ocr_confirmed')
        → UPDATE medication_statements SET status='accepted', merged_into_medication_id=new_id
    → Patient identifies: same as existing drug?
        → UPDATE existing medication IF patient wants (e.g., update dose)
        → UPDATE medication_statements SET status='merged_into', merged_into_medication_id=existing_id
    → Patient rejects:
        → UPDATE medication_statements SET status='rejected'
```

**Doctor Portal (P3):**
```
Doctor adds medication from portal
  → INSERT INTO medication_statements (source_type='doctor_prescribed')
  → Notification to patient: "Bác sĩ đã thêm thuốc vào hồ sơ của bạn. Xác nhận để thêm vào danh sách."
  → Patient confirms → INSERT INTO medications
  → OR: Doctor marks as "CML" directly if consent level allows
```

**Current Medication List (CML) definition:**
CML = all records in `medications` WHERE:
- `deleted_at IS NULL`
- `status IN ('active', 'paused', 'on_hold')`
- `source_type != 'ocr_pending'` AND `source_type != 'entered_in_error'`

**AI context reads CML only** — never reads `medication_statements` directly.

---

## Data Model Impact

- P0: add `source_type` to `medications` AND create `medication_statements` table (both in P0 foundation migration)
- P2: reconciliation UI, OCR source_type values become active
- No existing data at risk (P0 migration is additive)

---

## API Impact

- P0: `POST /patients/{id}/medications` internally creates statement + auto-promotes to canonical. No external API change visible to client.
- P2: `GET /patients/{id}/medications/statements?status=pending` — get unreviewed OCR statements
- P2: `POST /patients/{id}/medications/statements/{sid}/accept` — promote to CML
- P2: `POST /patients/{id}/medications/statements/{sid}/reject` — discard

---

## Security and Privacy Impact

- `medication_statements` is PHI (contains raw prescription text, doctor names)
- Same RBAC as `medications`
- `source_ref` (e.g., OCR session ID) must not expose raw prescription image path to unauthorized parties

---

## Clinical Safety Impact

Auto-merge must NEVER happen without patient or doctor confirmation.

The greatest risk in reconciliation is **wrong merge** (treating two different drugs as the same). e.g., patient has "Metformin 500mg" (their old dose) and doctor prescribes "Metformin 1000mg" — these should NOT auto-merge, they should be reconciled with patient and doctor choosing which dose is current.

**Verification hierarchy:**
1. Doctor-verified > patient-confirmed > OCR-extracted > AI-suggested
2. Higher source does not overwrite lower source automatically — it creates a statement for review

---

## Migration Impact

P0: 
- Add `source_type` column to `medications` (nullable, defaults to 'patient_manual' for all existing rows)
- Create `medication_statements` table (empty at migration time — P0 writes to it going forward)
- All existing `medications` rows get `source_type = 'patient_manual'` (no corresponding statement record — acceptable, they pre-date the statement model)
- Going forward from P0: every new medication write creates a statement first, then auto-promotes to canonical

No data loss. Existing rows are grandfathered as 'patient_manual' with no statement record.

---

## Operational Ownership

- Pending statements older than 30 days: alert patient to review or auto-expire
- `statement_status = 'pending'` older than 90 days: archive + notify

---

## Resolved Decisions (PTH 2026-07-11)

### Q-OQ-1 Resolution: Expired Re-Review Flow

**Decision:** When a patient reports they are still taking an `expired` medication, the system MUST NOT directly transition `lifecycle_status` back to `active`. A new `medication_statement` must be created first.

**Four cases:**
- **Case A** (same drug/dose/route, no real gap): Create event `patient_reported_continued_use`, allow re-activation of canonical record.
- **Case B** (different dose/frequency/formulation or actual gap): Create new medication episode. Old record stays `expired`.
- **Case C** (insufficient data): Statement stays `pending`, no reminder reactivated, patient prompted.
- **Case D** (original expired from clinician-set prescription end_date): Patient CANNOT self-reactivate. Statement flagged `awaiting_clinician`. Requires Doctor Portal review (P3).

**Detection of Case D:** `source_type='doctor_prescribed'` OR (`source_type='ocr_confirmed'` AND `raw_prescriber IS NOT NULL`).

**New fields on `medication_statements` for this flow:**
- `assertion_type` — `'new_entry' | 'continued_use' | 'dose_update' | 'correction'`
- `related_medication_id` — FK to prior expired canonical record
- `effective_from` — patient-reported start of continued use
- `payload_snapshot` — JSONB snapshot of expired record at time of assertion
- `statement_status` extended: add `'awaiting_clinician'`

**Status:** ✅ RESOLVED

---

## Open Questions

1. ~~**Doctor Portal consent level:** Can doctor directly add to patient CML?~~ **RESOLVED:** Doctor can add directly (source_type + audit, no patient re-confirm needed) — confirmed PTH review 2026-07-11.
2. **Pharmacy integration timeline:** When does MetoCare plan pharmacy integration? **[PTH product roadmap decision — Gate 2/3 dependency]**

---

## Approval Required From

- [x] PTH — phased rollout acceptance — **APPROVED 2026-07-11**
- [x] PTH — doctor-to-CML consent policy — **APPROVED 2026-07-11**
- [x] PTH — expired re-review statement-first flow (Q-OQ-1) — **APPROVED 2026-07-11**
- [ ] Clinical Advisor — verification hierarchy (who has authority over whom in case of conflict)

## Implementation Gate

**Gate 1 — APPROVED by PTH 2026-07-11.**

`source_type` on `medications` AND `medication_statements` table are both in P0 schema foundation (per PTH decision: both tables from day 1, not deferred).
