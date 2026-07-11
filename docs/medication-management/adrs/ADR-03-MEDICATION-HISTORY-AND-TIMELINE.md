# ADR-03 — Medication History and Timeline

**Status:** PROPOSED — Gate 1 (blocks all implementation)  
**Date:** 2026-07-11  
**Deciders:** PTH, Tech Lead

---

## Context

`medications` table hiện có `updated_at` timestamp. Khi patient hoặc doctor edit một medication (dose, frequency, status), previous value bị ghi đè. Không có lịch sử.

MetoCare cần Medication Timeline cho: Doctor Portal (xem lịch sử thuốc), AI Copilot (reason về dose change), Adverse Event Detection (thuốc nào được add gần đây?), Longitudinal Health Record.

---

## Problem

`updated_at` không trả lời được:
- Dose của medication này trước đây là bao nhiêu?
- Medication này bị pause lần nào, từ khi nào đến khi nào?
- Ai đã change status từ active sang discontinued?
- Tại sao medication này bị ngừng?

Không có history = Doctor Portal không thể show medication timeline. AI Copilot không thể correlate "HbA1c tăng đột biến" với "Metformin bị pause 3 tuần trước".

---

## Decision Drivers

- Doctor Portal cần full medication history per patient
- AI Copilot cần temporal reasoning về medication changes
- Audit requirement: ai change gì, khi nào, lý do gì
- Must not slow down write path significantly
- Soft delete hiện có là insufficient (ghi đè ngay)
- Full Event Sourcing: expensive, requires event replay infrastructure

---

## Options Considered

### Option A — Keep `updated_at` only
No history. Rejected: insufficient for any clinical use case.

### Option B — Append-only event log table
`medication_events` table ghi mọi state change. Current state là projection từ latest event.

### Option C — Snapshot-on-write
Mỗi khi medication được update, copy current row vào `medication_history` table, sau đó update main row.

### Option D — Full Event Sourcing
`medications` table chỉ là materialized view. Source of truth là event stream. Rebuild state bằng replay.

### Option E — Snapshot + lightweight event log (hybrid)
`medication_history` table: snapshot trước khi update.  
`medication_events` table: structured events cho state transitions (status change, prescriber change, dose change).

---

## Trade-off Table

| Criterion | A (none) | B (event log only) | C (snapshot) | D (event sourcing) | E (hybrid) |
|-----------|----------|--------------------|--------------|--------------------|------------|
| Historical dose lookup | ❌ | ✅ | ✅ | ✅ | ✅ |
| Who changed what, when | ❌ | ✅ | ⚠️ Partial | ✅ | ✅ |
| Query current state | ✅ Fast | ❌ Must project | ✅ Fast | ❌ Must replay | ✅ Fast |
| Implementation complexity | ✅ None | ⚠️ Medium | ✅ Low | ❌ High | ⚠️ Medium |
| Storage overhead | ✅ None | ⚠️ Grows | ⚠️ Grows | ❌ Large | ⚠️ Moderate |
| AI temporal reasoning | ❌ | ✅ | ⚠️ | ✅ | ✅ |
| Correction of errors | ❌ | ⚠️ Compensation event | ❌ Hard | ✅ | ✅ via correction event |

---

## Recommended Decision

**Option E — Snapshot + lightweight event log.**

Full Event Sourcing (Option D) is not justified: MetoCare does not need event replay infrastructure, CQRS, or event bus at this scale. It adds months of complexity for a feature that can be achieved with two simple tables.

Option B (event log only) makes current state query require projection — slower reads for a high-frequency operation.

Option E gives: fast current state reads (from `medications` table as-is), full history (from `medication_history` snapshots), structured audit of important transitions (from `medication_events`).

---

## Consequences

**`medication_history` table (snapshot on write):**
```sql
CREATE TABLE medication_history (
    id                UUID PK,
    medication_id     VARCHAR(36) NOT NULL REFERENCES medications(id),
    patient_id        VARCHAR(36) NOT NULL,
    snapshot          JSON NOT NULL,          -- full row snapshot before change
    changed_by_user_id VARCHAR(36) NOT NULL,
    changed_by_role   VARCHAR(32) NOT NULL,
    change_type       VARCHAR(32) NOT NULL,   -- update | status_change | dose_change | delete
    change_reason     TEXT nullable,          -- optional: reason provided by actor
    changed_at        DATETIME NOT NULL,
    INDEX (medication_id, changed_at)
);
```

**`medication_events` table (structured transitions only):**
```sql
CREATE TABLE medication_events (
    id              UUID PK,
    medication_id   VARCHAR(36) NOT NULL REFERENCES medications(id),
    patient_id      VARCHAR(36) NOT NULL,
    event_type      VARCHAR(64) NOT NULL,
    -- event_type: status_changed | dose_changed | schedule_changed | prescriber_changed
    --             paused_by_patient | resumed | discontinued | expired | corrected_entry
    actor_user_id   VARCHAR(36) NOT NULL,
    actor_role      VARCHAR(32) NOT NULL,
    effective_date  DATE nullable,            -- when the change takes clinical effect (can differ from changed_at)
    previous_value  JSON nullable,
    new_value       JSON nullable,
    reason          TEXT nullable,
    occurred_at     DATETIME NOT NULL,
    INDEX (medication_id, occurred_at)
);
```

**Write path (service layer):**
```
UPDATE medications (current state)
├── Before update: INSERT INTO medication_history (snapshot of current row)
├── If event_type is structured (status, dose, prescriber):
│     INSERT INTO medication_events
└── Proceed with UPDATE medications
```

**Correction vs Deletion:**
- Correction: `event_type = 'corrected_entry'`, previous_value = wrong data, new_value = corrected data. Medication record is updated. History records why.
- Deletion: soft delete only (`deleted_at`). Never hard delete. `event_type = 'deleted'` recorded in `medication_events`.
- "Entered in error": `status = 'entered_in_error'` + `medication_events` entry. Record kept for audit. Never shown in active list.

**Pause/Resume semantics:**
```
status: active → paused
  medication_events: event_type='paused_by_patient', reason=optional
  on_hold vs paused:
    paused = patient decision (vacation, feeling unwell)
    on_hold = clinical decision (pre-surgery, drug interaction hold) — only doctor can set
```

**Future-dated changes:**
- `effective_date` in `medication_events` allows recording "dose change starting next Monday"
- System reads `effective_date` to determine when to apply the change
- Deferred: not in P0 scope. Schema supports it when needed.

---

## Data Model Impact

Two new tables. No modification to existing `medications` table structure.  
Service layer changes: `medication.py` service must write to both tables on every update.

---

## API Impact

- Add `GET /patients/{id}/medications/{mid}/history` — returns `medication_history` snapshots
- Add `GET /patients/{id}/medications/{mid}/events` — returns `medication_events` timeline
- Existing write endpoints: no interface change, only internal behavior change

---

## Security and Privacy Impact

- `medication_history.snapshot` is PHI (contains dose, name, etc.)
- Access: same RBAC as `medications` — patient (own), doctor (consent), admin
- `medication_history` must NOT be accessible to CAREGIVER by default (too much detail)
- Retention: minimum 7 years (align with Vietnamese medical record retention requirements)

---

## Clinical Safety Impact

History enables adverse event detection: "Patient started Drug X on date Y. Adverse symptom reported on date Z. Time delta = 3 days." Without history, this correlation is impossible.

Correction flow prevents permanent wrong medication entry. Important for OCR errors and manual entry mistakes.

---

## Migration Impact

No data migration needed. New tables. Existing medication records have no history (accepted — history starts from go-live).

Add ONE migration: `med_p0_medication_history_events` — CREATE two new tables.

---

## Operational Ownership

History tables are write-once, append-only. No cleanup needed.  
Archival after 7+ years: separate process, PTH approval required.

---

## Open Questions

1. **Effective date in P0 or P1?** Future-dated changes require UI support. Recommend defer to P2+ unless doctor portal requires it. **[PTH decides scope]**
2. **Vietnamese medical record retention law:** Is 7 years the correct retention period? **[Legal/Clinical advisor must confirm]**

---

## Approval Required From

- [ ] PTH — snapshot vs event log vs both (recommend both)
- [ ] PTH — retention period
- [ ] Tech Lead — write path implementation (service layer, not trigger-based)

## Implementation Gate

**Gate 1 — blocks all implementation.**  
Must be approved before P0 implementation starts. All subsequent features (Doctor Portal timeline, AI temporal reasoning, Adverse Event Detection) depend on history being captured from day 1. Cannot retroactively add history.
